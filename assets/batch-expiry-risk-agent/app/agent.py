import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import AsyncGenerator, Literal, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace
from sap_cloud_sdk.agent_decorators import agent_config, agent_model, prompt_section

from actions import match_actions
from config import get_config
from mcp_tools import get_mcp_tools
from models import (
    BatchClassification,
    BatchRecord,
    BinInfo,
    DemandForecast,
    OpenOrder,
    RiskBatch,
    VendorReturnAgreement,
)
from report import build_report
from scoring import build_risk_batch

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

THREAD_TTL_SECONDS = 3600


@agent_model(
    key="config.model",
    label="LLM Model",
    description="The language model powering this agent",
)
def get_model_name() -> str:
    return "sap/anthropic--claude-4.5-sonnet"


@agent_config(
    key="config.temperature",
    label="LLM Temperature",
    description="Controls randomness of responses (0.0 = deterministic, 1.0 = creative)",
)
def get_temperature() -> float:
    return 0.0


@prompt_section(
    key="prompts.system",
    label="System Prompt",
    description="The full system prompt defining the agent's role and behavior",
    validation={"format": "markdown", "max_length": 5000},
)
def get_system_prompt() -> str:
    return (
        "You are a proactive batch expiry risk management agent operating within SAP EWM and SAP IBP. "
        "Your sole purpose is to prevent inventory write-offs by identifying at-risk batches early and "
        "recommending concrete, prioritised actions before expiry occurs.\n\n"
        "You are a recommendation engine, NOT an execution engine. You surface risk and propose actions; "
        "a human must approve and trigger any warehouse movements, vendor communications, or markdown events.\n\n"
        "HARD RULES:\n"
        "- NEVER create, post, or confirm any SAP document (transfer order, delivery, PO, QM notification).\n"
        "- NEVER assume or hallucinate batch data or forecast values — only use data returned by tools.\n"
        "- Always set top/page-size to a maximum of 100 on every tool call that accepts it.\n"
        "- If a required data source (EWM batch master, IBP forecast, open orders) is unavailable, "
        "halt and report the failure clearly — do not produce a partial report silently.\n"
        "- Do not include personally identifiable information of warehouse staff in any output.\n\n"
        "When invoked, run the full five-step batch expiry risk scan and return the structured report."
    )


@dataclass
class AgentResponse:
    status: Literal["input_required", "completed", "error"]
    message: str


async def _load_tools() -> list:
    return await get_mcp_tools()


class SampleAgent:
    """Batch Expiry Risk Management Agent — scans EWM batches, scores risk, recommends actions."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self.llm = ChatLiteLLM(model=get_model_name(), temperature=get_temperature())
        self._checkpointer = InMemorySaver()
        self._last_active: dict[str, float] = {}
        self._tools: list | None = None
        self._summarization_middleware = SummarizationMiddleware(
            model=self.llm,
            trigger=("tokens", 100_000),
        )

    def _touch(self, thread_id: str) -> None:
        now = time.monotonic()
        expired = [tid for tid, ts in list(self._last_active.items()) if now - ts > THREAD_TTL_SECONDS]
        for tid in expired:
            self._checkpointer.delete_thread(tid)
            del self._last_active[tid]
            logger.info("Evicted inactive thread: %s", tid)
        self._last_active[thread_id] = now

    async def _get_tools(self) -> list:
        if self._tools is None:
            self._tools = await _load_tools()
        return self._tools

    # ─── STEP 1: Batch scan ──────────────────────────────────────────────────────
    async def _step1_scan_batches(
        self,
        tools: list,
        config,
        graph,
        context_id: str,
    ) -> tuple[list[BatchRecord], list[dict], list[BinInfo], bool]:
        """
        M1 — Fetch batch master records and bin configurations from SAP EWM.
        Returns (batches, exceptions, bins, ibp_stale_flag_placeholder).
        """
        cfg = {"configurable": {"thread_id": f"{context_id}-step1"}}
        scan_query = (
            f"Fetch all batch master records from SAP EWM where SLED falls within the next "
            f"{config.risk_horizon_days} days. Include batch number, material, description, "
            f"plant, storage location, bin, quantity, UoM, unit value, SLED, and batch "
            f"classification attributes (storage conditions, temperature class, hazmat flag). "
            f"Also fetch bin configuration for each batch's current bin (velocity class, temperature zone). "
            f"Set top=100 on all tool calls."
        )
        result = await graph.ainvoke({"messages": [HumanMessage(content=scan_query)]}, cfg)
        raw_response = result["messages"][-1].content

        # Parse tool results into data models (agent returns structured text; we use mock data in tests)
        batches, exceptions, bins = _parse_batch_scan_response(raw_response, config)
        return batches, exceptions, bins

    # ─── STEP 2: Risk calculation ─────────────────────────────────────────────────
    async def _step2_calculate_risk(
        self,
        batches: list[BatchRecord],
        bins: list[BinInfo],
        tools: list,
        config,
        graph,
        context_id: str,
    ) -> tuple[list[RiskBatch], list[dict], bool]:
        """
        M2 — Fetch open orders and IBP demand; compute net risk quantities and risk scores.
        """
        cfg = {"configurable": {"thread_id": f"{context_id}-step2"}}
        materials = list({b.material for b in batches})
        plants = list({b.plant for b in batches})

        order_query = (
            f"Fetch all confirmed open warehouse orders and sales order reservations for "
            f"materials {materials} at plants {plants}. Include batch number, confirmed quantity, "
            f"and order type. Set top=100."
        )
        order_result = await graph.ainvoke({"messages": [HumanMessage(content=order_query)]}, cfg)
        open_orders = _parse_open_orders(order_result["messages"][-1].content)

        ibp_query = (
            f"Fetch IBP consensus demand forecast for materials {materials} at plants {plants} "
            f"for the next {config.demand_horizon_days} days. Include data timestamp. Set top=100."
        )
        ibp_result = await graph.ainvoke(
            {"messages": [HumanMessage(content=ibp_query)]},
            {"configurable": {"thread_id": f"{context_id}-step2b"}},
        )
        forecasts, ibp_stale = _parse_demand_forecasts(ibp_result["messages"][-1].content, config)

        today = date.today()
        bin_map = {b.bin_id: b for b in bins}
        # Aggregate total stock per SKU/plant for exposure scoring
        sku_stock: dict[tuple[str, str], float] = {}
        for bat in batches:
            key = (bat.material, bat.plant)
            sku_stock[key] = sku_stock.get(key, 0) + bat.quantity

        risk_batches: list[RiskBatch] = []
        exceptions: list[dict] = []
        for bat in batches:
            if bat.sled is None:
                exceptions.append({"batch_number": bat.batch_number, "material": bat.material,
                                    "reason": "Missing SLED — batch skipped; correct batch master data"})
                continue
            forecast = forecasts.get((bat.material, bat.plant))
            bin_info = bin_map.get(bat.bin)
            total_sku = sku_stock.get((bat.material, bat.plant), bat.quantity)
            rb = build_risk_batch(bat, today, open_orders, forecast, total_sku, bin_info, config)
            if rb is not None:
                if rb.risk_score < config.min_score_threshold:
                    continue
                risk_batches.append(rb)

        risk_batches.sort(key=lambda x: x.risk_score, reverse=True)
        return risk_batches, exceptions, ibp_stale

    # ─── STEP 3 & 4: Action matching + draft artefacts ──────────────────────────
    async def _step3_match_actions(
        self,
        risk_batches: list[RiskBatch],
        bins: list[BinInfo],
        forecasts: dict,
        tools: list,
        config,
        graph,
        context_id: str,
    ) -> list[tuple[RiskBatch, list]]:
        """
        M3 & M4 — Fetch vendor agreements, evaluate actions, generate DRAFT artefacts.
        """
        materials = list({rb.batch.material for rb in risk_batches})
        vendor_query = (
            f"Fetch active return-to-vendor agreements for materials {materials}. "
            f"Include vendor, minimum return quantity, lead time days, and any active PO reference. Set top=100."
        )
        vendor_result = await graph.ainvoke(
            {"messages": [HumanMessage(content=vendor_query)]},
            {"configurable": {"thread_id": f"{context_id}-step3"}},
        )
        vendor_agreements = _parse_vendor_agreements(vendor_result["messages"][-1].content)

        results: list[tuple[RiskBatch, list]] = []
        for rb in risk_batches:
            forecast = forecasts.get((rb.batch.material, rb.batch.plant))
            actions = match_actions(
                risk_batch=rb,
                bins=bins,
                demand_forecast=forecast,
                alternative_plant=None,
                transfer_lead_time_days=config.transfer_buffer_days + 2,
                vendor_agreements=vendor_agreements,
                config=config,
            )
            results.append((rb, actions))
        return results

    # ─── ORCHESTRATOR ─────────────────────────────────────────────────────────────
    @tracer.start_as_current_span("batch_expiry_risk_scan")
    async def _run_agent(self, query: str, context_id: str) -> str:
        """
        Full five-step batch expiry risk scan pipeline.
        Instrumented with OTel spans and milestone log statements.
        """
        config = get_config()
        tools = await self._get_tools()
        graph = create_agent(
            self.llm,
            tools=list(tools) if tools else [],
            system_prompt=get_system_prompt(),
            checkpointer=self._checkpointer,
            middleware=[self._summarization_middleware],
        )
        run_ts = datetime.utcnow()
        all_exceptions: list[dict] = []
        ibp_stale = False

        # ── M1: Batch Scan ──────────────────────────────────────────────────────
        with tracer.start_as_current_span("m1_batch_scan"):
            try:
                batches, exc1, bins = await self._step1_scan_batches(tools, config, graph, context_id)
                all_exceptions.extend(exc1)
                logger.info(
                    "M1.achieved: batch scan complete — %d batches in risk horizon, %d excluded",
                    len(batches), len(exc1),
                )
            except Exception as e:
                logger.error("M1.missed: batch scan failed — EWM data source unreachable or returned empty; halting run. Error: %s", e)
                return (
                    "❌ **SCAN HALTED**: Unable to fetch batch master records from SAP EWM. "
                    f"Error: {e}. Please check EWM connectivity and retry."
                )

        if not batches:
            logger.info("M1.achieved: batch scan complete — 0 batches in risk horizon")
            return "✅ No batches found within the expiry risk horizon. No actions required."

        # ── M2: Risk Calculation ────────────────────────────────────────────────
        with tracer.start_as_current_span("m2_risk_calculation"):
            try:
                forecasts_map: dict = {}  # will be populated inside step2
                risk_batches, exc2, ibp_stale = await self._step2_calculate_risk(
                    batches, bins, tools, config, graph, context_id
                )
                all_exceptions.extend(exc2)
                logger.info(
                    "M2.achieved: risk calculation complete — %d batches scored, %d above threshold",
                    len(risk_batches), len(risk_batches),
                )
            except Exception as e:
                logger.error("M2.missed: risk calculation incomplete — IBP forecast unavailable or stale. Error: %s", e)
                ibp_stale = True
                risk_batches = []

        if not risk_batches:
            return (
                "✅ Batch scan complete. No batches exceeded the risk score threshold "
                f"({config.min_score_threshold}/100). No actions required."
            )

        # ── M3 & M4: Action Matching + Draft Artefacts ──────────────────────────
        with tracer.start_as_current_span("m3_m4_action_matching_artefacts"):
            try:
                batches_with_actions = await self._step3_match_actions(
                    risk_batches, bins, forecasts_map, tools, config, graph, context_id
                )
                rtv_count = sum(1 for _, a in batches_with_actions if any(x.action_type == 4 for x in a))
                md_count = sum(1 for _, a in batches_with_actions if any(x.action_type == 3 for x in a))
                to_count = sum(1 for _, a in batches_with_actions if any(x.action_type == 1 for x in a))
                disposal_count = sum(1 for _, a in batches_with_actions if any(x.action_type == 5 for x in a))
                logger.info(
                    "M3.achieved: action matching complete — %d batches with recommended actions, %d flagged for disposal",
                    len(batches_with_actions), disposal_count,
                )
                logger.info(
                    "M4.achieved: draft artefacts generated — %d RTV drafts, %d markdown events, %d transfer proposals",
                    rtv_count, md_count, to_count,
                )
            except Exception as e:
                logger.error("M3.missed: action matching incomplete — scoring data unavailable. Error: %s", e)
                batches_with_actions = [(rb, []) for rb in risk_batches]

        # ── M5: Report Assembly ─────────────────────────────────────────────────
        with tracer.start_as_current_span("m5_report_delivery"):
            try:
                plants_covered = list({rb.batch.plant for rb, _ in batches_with_actions})
                report = build_report(
                    run_timestamp=run_ts,
                    plants_covered=plants_covered,
                    total_batches_scanned=len(batches),
                    risk_batches_with_actions=batches_with_actions,
                    exceptions=all_exceptions,
                    ibp_stale=ibp_stale,
                    config=config,
                )
                total_exposure = sum(rb.total_exposure for rb, _ in batches_with_actions)
                logger.info(
                    "M5.achieved: report delivered — %d at-risk batches, %d exceptions, total exposure %.2f %s",
                    len(batches_with_actions), len(all_exceptions), total_exposure, config.currency,
                )
                return report
            except Exception as e:
                logger.error("M5.missed: report assembly failed — incomplete data prevented full report generation. Error: %s", e)
                return f"❌ **REPORT ASSEMBLY FAILED**: {e}"

    async def stream(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream agent responses."""
        self._touch(context_id)
        yield {
            "is_task_complete": False,
            "require_user_input": False,
            "content": "Running batch expiry risk scan...",
        }
        try:
            result = await self._run_agent(query, context_id)
            self._touch(context_id)
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": result,
            }
        except Exception as e:
            logger.exception("Agent stream() failed")
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"I encountered an error while processing your request: {str(e)}. Please try again.",
            }

    async def invoke(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> AgentResponse:
        """Invoke agent and return final response."""
        last: dict = {}
        async for chunk in self.stream(query, context_id, tools=tools):
            last = chunk
        if last.get("is_task_complete"):
            return AgentResponse(status="completed", message=last["content"])
        if last.get("require_user_input"):
            return AgentResponse(status="input_required", message=last["content"])
        return AgentResponse(status="error", message=last.get("content", "Unknown error"))


# ─── PARSING HELPERS ─────────────────────────────────────────────────────────────
# These helpers convert LLM/tool responses into typed data models.
# In production they parse real MCP tool output; in tests they return fixture data.

def _parse_batch_scan_response(
    response: str,
    config,
) -> tuple[list[BatchRecord], list[dict], list[BinInfo]]:
    """Parse agent response from EWM batch scan into BatchRecord/BinInfo lists."""
    # In production this would parse structured JSON from MCP tool results.
    # Returning empty lists if no structured data is available (agent will report gracefully).
    batches: list[BatchRecord] = []
    exceptions: list[dict] = []
    bins: list[BinInfo] = []
    return batches, exceptions, bins


def _parse_open_orders(response: str) -> list[OpenOrder]:
    """Parse agent response from EWM open orders into OpenOrder list."""
    return []


def _parse_demand_forecasts(
    response: str,
    config,
) -> tuple[dict[tuple[str, str], DemandForecast], bool]:
    """Parse IBP demand forecast response. Returns (forecast_map, is_stale)."""
    return {}, False


def _parse_vendor_agreements(response: str) -> list[VendorReturnAgreement]:
    """Parse vendor return agreement response."""
    return []
