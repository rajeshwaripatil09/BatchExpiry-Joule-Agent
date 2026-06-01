# Specification: batch-expiry-risk-agent

> **Guidelines**: Read [guidelines.md](../guidelines.md) and [guidelines-agent.md](../guidelines-agent.md) before executing ANY tasks below. Follow all constraints described there throughout execution.

## Basic Setup

- [x] Read `product-requirements-document.md` and `intent.md` for full context
- [x] Bootstrap agent code in `assets/batch-expiry-risk-agent/` using skill `sap-agent-bootstrap` (invoke from inside `assets/batch-expiry-risk-agent/`, use copy commands — do NOT create files manually)
- [x] Install dependencies, validate the agent starts and responds at `/.well-known/agent.json`

## Configuration Module

- [x] Create `assets/batch-expiry-risk-agent/app/config.py` — loads all configurable parameters from environment variables with documented defaults:
  - RISK_HORIZON_DAYS (default: 60), DEMAND_HORIZON_DAYS (default: 90)
  - RESIDUAL_QTY_THRESHOLD (default: 0.10), RESIDUAL_QTY_ABSOLUTE (default: 50)
  - MIN_RISK_QTY (default: 0), MIN_SCORE_THRESHOLD (default: 20)
  - W_EXPIRY (default: 40), W_EXPOSURE (default: 30), W_VALUE (default: 20), W_BIN (default: 10)
  - MIN_SHELF_LIFE_POST_TRANSFER_DAYS (default: 14), TRANSFER_BUFFER_DAYS (default: 5)
  - MARKDOWN_ENABLED (default: True), MARKDOWN_TRIGGER_DAYS (default: 30), MARKDOWN_MIN_QTY (default: 1)
  - MD_TIER_1 (default: 15), MD_TIER_2 (default: 30), MD_TIER_3 (default: 50)
  - RTV_MIN_DAYS_REMAINING (default: 21), RTV_ESCALATION_THRESHOLD (default: 5000)
  - IBP_DATA_FRESHNESS_HOURS (default: 24)
  - HAZMAT_EXCLUDE (default: True)
  - CURRENCY (default: "USD")
  - PLANTS (default: "All"), STORAGE_TYPES_IN_SCOPE (default: "All")
  - ACTION_TYPES_ENABLED (default: "1,2,3,4,5")
  - Validate weights sum to 100; raise ValueError if not

## Data Models

- [x] Create `assets/batch-expiry-risk-agent/app/models.py` — define Python dataclasses:
  - `BatchRecord`: batch_number, material, description, plant, storage_location, bin, quantity, uom, unit_value, sled, batch_classification (storage_conditions, temperature_class, hazmat_flag)
  - `DemandForecast`: material, plant, total_qty, horizon_days, is_stale, data_timestamp
  - `OpenOrder`: batch_number, material, plant, confirmed_qty, order_type
  - `BinInfo`: bin_id, plant, storage_type, velocity_class (A/B/C), temperature_zone
  - `VendorReturnAgreement`: material, vendor, min_return_qty, lead_time_days, has_agreement
  - `RiskBatch`: BatchRecord + net_risk_qty, days_to_expiry, risk_qty, risk_score, confidence
  - `ActionRecommendation`: action_type (1-5), description, draft_artefact, eligible

## Scoring Engine

- [x] Create `assets/batch-expiry-risk-agent/app/scoring.py`:
  - `calculate_net_risk_qty(batch, open_orders, demand_forecast, config)` → net_risk_qty, projected_consumption, risk_qty
  - `calculate_risk_score(risk_batch, all_sku_stock, config)` → score 1–100 using weighted formula (W_EXPIRY: days_to_expiry normalised 0–60; W_EXPOSURE: risk_qty / total_sku_stock; W_VALUE: unit_value × risk_qty normalised; W_BIN: C=100, B=50, A=0)
  - `is_residual_covered(batch, open_orders, config)` → bool — returns True only if all remaining qty is below both RESIDUAL_QTY_THRESHOLD and RESIDUAL_QTY_ABSOLUTE thresholds (skip these batches)

## Action Evaluator

- [x] Create `assets/batch-expiry-risk-agent/app/actions.py`:
  - `evaluate_redistribution(risk_batch, bins, config)` → ActionRecommendation or None — checks: alternate higher-velocity bin exists at same plant, temperature zone compatible, remaining shelf life ≥ MIN_SHELF_LIFE_POST_TRANSFER_DAYS; draft: source bin → target bin, quantity, note
  - `evaluate_channel_reallocation(risk_batch, demand_forecast, config)` → ActionRecommendation or None — checks: IBP shows channel with higher near-term demand, inter-plant transfer lead time < days_to_expiry − TRANSFER_BUFFER_DAYS; draft: source plant → destination, quantity, IBP demand ref
  - `evaluate_markdown(risk_batch, config)` → ActionRecommendation or None — checks: MARKDOWN_ENABLED=True, days_to_expiry ≤ MARKDOWN_TRIGGER_DAYS, risk_qty > MARKDOWN_MIN_QTY; draft: tiered markdown % + event description
  - `evaluate_rtv(risk_batch, vendor_agreements, config)` → ActionRecommendation or None — checks: active agreement exists, days_to_expiry ≥ RTV_MIN_DAYS_REMAINING, qty ≥ min_return_qty; draft: structured RTV request (vendor, PO ref, qty, reason code, proposed return date); if no agreement but exposure > RTV_ESCALATION_THRESHOLD, flag for manual negotiation
  - `evaluate_disposal(risk_batch, config)` → ActionRecommendation — last resort if no other action eligible; draft: QM notification with batch details and financial write-off estimate
  - `match_actions(risk_batch, bins, demand_forecast, vendor_agreements, config)` → list[ActionRecommendation] in priority order, only enabled action types (ACTION_TYPES_ENABLED)
  - Hard constraint: never recommend redistribution to temperature-incompatible bin; never recommend RTV if days_to_expiry < RTV_MIN_DAYS_REMAINING (flag for disposal instead)

## Report Builder

- [x] Create `assets/batch-expiry-risk-agent/app/report.py`:
  - `build_report(run_meta, risk_batches_with_actions, exceptions, config)` → str (markdown)
  - Run header: timestamp, plants covered, scan horizon, total batches scanned, total at-risk, total financial exposure (sum of risk_qty × unit_value)
  - Per-batch blocks sorted by risk_score descending: Batch #, Material, Description, Plant/SLoc/Bin, qty at risk, UoM, unit value, total exposure, SLED, days_to_expiry, risk_score, recommended actions (priority order, one line each), confidence (High/Medium/Low), DRAFT artefact
  - Summary action table: Batch # | Material | Risk score | Days to expiry | Recommended action | Draft ready? | Assigned to (blank)
  - Exceptions section: missing SLED, stale IBP data, classification issues — flag for master data correction
  - All monetary values in CURRENCY; all quantities in SAP base UoM
  - Confidence language: "Recommended" (High), "Consider" (Medium), "Review manually" (Low)

## Agent Core

- [x] Update `assets/batch-expiry-risk-agent/app/agent.py`:
  - Replace placeholder system prompt with the full operational system prompt from `product-requirements-document.md` Automation & Agent Behaviour section
  - System prompt MUST instruct agent: (1) never post/create/confirm any SAP document, (2) always set top/page-size ≤ 100 on tool calls, (3) never hallucinate batch data or forecast values — only use data returned by tools, (4) if a required data source is unavailable, halt and report failure clearly
  - Implement `_run_agent(query, context_id)` async helper — orchestrates the five-step pipeline:
    1. Call EWM batch master tool → filter by SLED horizon and hazmat exclusion (M1)
    2. Call open warehouse orders tool + IBP demand forecast tool → compute net risk qty and risk scores (M2)
    3. Call warehouse bin and vendor return agreement tools → evaluate all action types per batch (M3)
    4. Generate DRAFT artefacts for eligible actions (M4)
    5. Assemble and return structured report (M5)
  - Instrument `_run_agent()` with OTel spans and milestone log statements (M1–M5)
  - `stream()` calls `_run_agent()` and yields results — NEVER wraps yield inside `with tracer.start_as_current_span(...)` (use decorator or instrument the helper instead)
  - Wire `get_mcp_tools()` lazily via `mcp_tools.py`

## MCP Tool Integration

- [x] Verify `specification/batch-expiry-risk-agent/api-specs/` contains downloaded EWM and IBP API specs
- [x] Invoke `mcp-translation-file` skill — if skill unavailable, skip and note that agent will use mock data only
- [x] If translation files generated, invoke `setup-solution` to create/register MCP server assets
- [x] Wire MCP tool loading in `agent.py` using `get_mcp_tools()` from `mcp_tools.py` — NEVER use direct HTTP clients
- [x] After MCP assets generated, invoke `mcp-mock-config` skill to generate `mcp-mock.json` for testing

## Instrumentation

- [x] Implement business step instrumentation for each milestone M1–M5: structured logging with pattern `[MILESTONE_ID].[achieved|missed]: [description]` and OpenTelemetry custom spans
- [x] Extract all business logic from `stream()` into `_run_agent()` and instrument that helper — never wrap `yield` inside `with tracer.start_as_current_span(...)`
- [x] Verify `auto_instrument()` is called at top of `main.py` before any AI framework imports

## Testing

- [x] `conftest.py` only sets `IBD_TESTING=true`
- [x] Write unit tests in `assets/batch-expiry-risk-agent/tests/`:
  - `test_config.py` — validate all defaults load correctly; validate weight-sum-to-100 check
  - `test_scoring.py` — test net risk qty calculation with known inputs; test risk score formula; test residual coverage filter
  - `test_actions.py` — test each action evaluator (redistribution, markdown, RTV, disposal) with eligible and ineligible inputs; test hazmat exclusion; test temperature incompatibility block; test RTV blocked when days < RTV_MIN_DAYS_REMAINING
  - `test_report.py` — test report assembly with known risk batch data; verify per-batch blocks and summary table structure
  - `test_agent.py` — one integration test: call agent `invoke` with on-demand scan query; mock MCP tools; verify report structure in response
- [x] Run each test file immediately after writing it; fix any failures before proceeding
- [x] Verify `app/agent.py` has exactly 3 decorated functions: run `grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/batch-expiry-risk-agent/app/agent.py` — must return 3
- [x] Run `pytest` from `assets/batch-expiry-risk-agent/` (no args) — coverage ≥ 70%; if not, add tests
- [x] Verify `test_report.json` exists after pytest run

## Solution Setup

- [x] Invoke `setup-solution` skill to create `solution.yaml` and `assets/batch-expiry-risk-agent/asset.yaml`
- [x] Validate all YAML files are well-formed and health probes use `/.well-known/agent.json`
