# Product Requirements Document (PRD)

**Title:** Batch Expiry Risk Management Agent  
**Date:** 2026-06-01  
**Owner:** Supply Chain / Warehouse Operations  
**Solution Category:** AI Agent

---

## Product Purpose & Value Proposition

**Elevator Pitch:**  
Inventory write-offs from expired batches represent a silent but recurring financial loss in any organisation handling perishable or shelf-life-regulated goods. This agent scans SAP EWM batch records, cross-references SAP IBP demand forecasts, scores financial risk, and delivers a prioritised action report to planners every day — before expiry happens.

**Business Need:**  
SAP EWM tracks batch SLED/BBD and SAP IBP maintains demand forecasts, but no standard SAP capability automatically synthesises both signals, quantifies the net risk quantity, and recommends a ranked set of actions (redistribution, channel reallocation, markdown, return-to-vendor, disposal) with draft artefacts ready for human approval. Planners currently rely on manual batch expiry reports that arrive too late for any meaningful intervention.

**Expected Value:**  
- Reduction in inventory write-off cost through earlier intervention  
- Faster planner response via prioritised, pre-drafted action proposals  
- Consistent application of FEFO, temperature, and hazmat rules across all recommendations  
- Structured audit trail of all draft artefacts and planner decisions

**Product Objectives (Prioritized):**
1. Deliver a daily, actionable batch expiry risk report with risk-scored batches and ready-to-approve draft artefacts
2. Accurately quantify net risk quantity by netting open orders against IBP-projected consumption
3. Eliminate write-off-blind-spots by flagging data quality issues (missing SLED, stale IBP data)

---

## User Profiles & Personas

### Primary Persona: Warehouse Planner

A supply chain planner responsible for inventory health across one or more warehouses/plants. Reviews the daily expiry risk report each morning, approves or rejects recommended actions, and escalates to pricing/procurement teams as needed. Comfortable with SAP EWM and IBP data. Frustrated by the current manual process where expiry risks are only visible after the fact.

### Secondary Persona: Warehouse Manager

Oversees warehouse operations and has approval authority for bin transfers and quality holds. Receives the same report and signs off on redistribution or disposal recommendations. Needs the report to be concise, structured, and ready for handoff to the team.

---

## Requirements

### Must-Have Requirements

**R1**: Batch Scan and Risk Identification

- **User Story**: As a warehouse planner, I need the agent to automatically identify all batches expiring within the configured risk horizon so that I am alerted before write-off risk becomes unavoidable.
- **Acceptance Criteria**:
  - Given the scan runs (scheduled or on-demand), when SAP EWM batch data is fetched, then all batches with SLED ≤ today + RISK_HORIZON_DAYS are returned
  - Hazmat batches are excluded if HAZMAT_EXCLUDE = true
  - Batches missing SLED are captured in the exceptions section, not silently dropped
- **Priority Rank**: 1

**R2**: Net Risk Quantity Calculation

- **User Story**: As a warehouse planner, I need the agent to compute net risk quantity per batch (netting confirmed open orders and IBP-projected consumption) so that I focus only on genuinely at-risk stock.
- **Acceptance Criteria**:
  - net_risk_qty = batch_qty_on_hand − qty_on_open_confirmed_orders
  - projected_consumption = (IBP consensus demand / DEMAND_HORIZON_DAYS) × days_to_expiry
  - risk_qty = max(0, net_risk_qty − projected_consumption)
  - Only batches where risk_qty > MIN_RISK_QTY are included in the report
- **Priority Rank**: 2

**R3**: Risk Scoring and Prioritisation

- **User Story**: As a warehouse planner, I need each at-risk batch scored 1–100 and sorted highest-first so that I act on the most critical items first.
- **Acceptance Criteria**:
  - Score computed from configurable weighted formula: days_to_expiry (W_EXPIRY), risk_qty as % of total SKU stock (W_EXPOSURE), financial exposure (W_VALUE), bin velocity class (W_BIN)
  - Weights sum to 100; configurable per deployment
  - Only batches with score ≥ MIN_SCORE_THRESHOLD appear in the report
- **Priority Rank**: 3

**R4**: Action Matching and Draft Artefact Generation

- **User Story**: As a warehouse planner, I need the agent to recommend the best feasible action per batch and generate a DRAFT artefact (transfer proposal, RTV request, markdown event) so that I can approve and act immediately.
- **Acceptance Criteria**:
  - Five action types evaluated in priority order: Redistribution, Channel Reallocation, Markdown, RTV, Disposal
  - Each action type subject to its eligibility rules (temperature compatibility, days remaining, vendor agreement, etc.)
  - All artefacts clearly marked DRAFT and require human approval before execution
  - Agent NEVER creates, posts, or confirms any SAP document
- **Priority Rank**: 4

**R5**: Structured Report Delivery

- **User Story**: As a warehouse manager, I need a structured, human-readable report per run so that I can review, assign, and track all at-risk batches in one place.
- **Acceptance Criteria**:
  - Report includes: run header, per-batch blocks sorted by risk score, summary action table, exceptions section
  - Per-batch block shows: Batch #, Material, Description, Plant/SLoc/Bin, qty at risk, UoM, unit value, total exposure, SLED, days_to_expiry, risk score, recommended actions, confidence, draft artefact
  - Summary table columns: Batch # | Material | Risk score | Days to expiry | Recommended action | Draft ready? | Assigned to
  - Exceptions section lists batches skipped due to missing SLED, stale IBP data, or classification issues
- **Priority Rank**: 5

**R6**: Configurable Parameters

- **User Story**: As a deployment owner, I need all thresholds, weights, action toggles, and schedules to be configurable without code changes so that the agent adapts to each customer's policies.
- **Acceptance Criteria**:
  - All parameters from the parameter reference table are configurable via environment variables or config file
  - Defaults match the specification (RISK_HORIZON_DAYS=60, DEMAND_HORIZON_DAYS=90, MIN_SCORE_THRESHOLD=20, etc.)
- **Priority Rank**: 6

**R7**: Data Freshness and Failure Handling

- **User Story**: As a warehouse planner, I need the agent to halt and clearly report any data source failure so that I never receive a silent partial report.
- **Acceptance Criteria**:
  - If IBP data is older than IBP_DATA_FRESHNESS_HOURS, all confidence ratings are downgraded to Low and a prominent flag is added
  - If any required data source (EWM batch master, IBP forecast, open orders) cannot be fetched, the agent halts and reports the failure — no partial report is produced silently
- **Priority Rank**: 7

---

## Solution Architecture

**Architecture Overview:**  
A Python AI agent (LangGraph, A2A protocol) deployed on SAP BTP / SAP AI Core. The agent exposes a single A2A endpoint and is invoked by a scheduler (daily cron) or on-demand. It reads data from SAP EWM and SAP IBP via OData APIs (wrapped as MCP tools), applies the scanning/scoring/action-matching logic, and returns the structured report as its response.

**Key Components:**

- **Agent Core** (`app/agent.py`): LangGraph-based agent; orchestrates tool calls, scoring logic, action matching, and report assembly
- **MCP Tool Layer** (`app/mcp_tools.py`): loads SAP EWM and IBP tools from the Agent Gateway at runtime
- **Config Module** (`app/config.py`): loads all configurable parameters from environment variables with documented defaults
- **Scoring Engine** (`app/scoring.py`): implements the risk scoring formula and action eligibility rules
- **Report Builder** (`app/report.py`): assembles the structured markdown/text report from scored batch data

**Integration Points:**

- SAP EWM / S/4HANA: Batch Master Record API (read), Warehouse Storage Bin API (read), Warehouse Order and Task API (read) — via MCP tools
- SAP IBP: Forecast Data Extraction / Integrate Key Figure Data API (read) — via MCP tools
- Vendor Master / RTV: Return To Supplier Query (read) — via MCP tools

### Agent Extensibility & Instrumentation

**Agent Extensibility:**
- The agent is designed with a modular action-type system; new action types can be added by extending the action evaluator without modifying the core scoring engine
- Configuration parameters are all externalised; new parameters can be added with zero code change
- MCP tool loading is lazy and dynamic; new SAP API integrations can be added by registering additional MCP servers in `asset.yaml`

**Business Step Instrumentation:**
- All five milestone steps are instrumented with structured logs and OpenTelemetry custom spans
- Log pattern: `[MILESTONE_ID].[achieved|missed]: [description]`
- `auto_instrument()` called at top of `main.py` before any AI framework imports

### Automation & Agent Behaviour

**Automation Level:** Autonomous agent with human-in-the-loop approval gate

**Actions the system performs without human approval:**
- Fetching batch master records, demand forecasts, open orders, bin configurations
- Calculating net risk quantities, scores, and action eligibility
- Generating DRAFT artefacts (RTV request text, markdown event description, transfer order proposal)
- Assembling and returning the structured report

**Actions that require human review or approval:**
- Bin redistributions / transfer orders
- Channel reallocation / inter-plant transfers
- Markdown / price promotion events
- Return-to-vendor requests
- Quality holds and disposal instructions

**Model or engine used:** LLM via SAP Generative AI Hub (for natural-language report assembly and draft artefact text generation); deterministic Python logic for scoring and eligibility evaluation.

**Knowledge & data sources accessed:**

- SAP EWM: Batch master records (SLED, qty, bin, classification), warehouse orders (open confirmed picks), storage bin configuration (velocity class, temperature zone)
- SAP IBP: Consensus demand forecast per SKU/location for DEMAND_HORIZON_DAYS
- SAP ERP/S4: Vendor master — return-to-vendor agreements (lead time, minimum return qty)

**Tools or connectors invoked:**

- `get_batch_records`: Read batch master data including SLED/BBD, quantities, classification attributes — read-only
- `get_warehouse_bins`: Read storage bin velocity class and temperature zone — read-only
- `get_open_warehouse_orders`: Read confirmed open picks and transfer orders per batch — read-only
- `get_ibp_demand_forecast`: Read IBP consensus demand per SKU/location for the demand horizon — read-only
- `get_vendor_return_agreements`: Read active RTV agreements per material/vendor — read-only

**Guardrails & fail-safes:**

- Agent NEVER creates, posts, or confirms any SAP document (hard constraint enforced in system prompt and code)
- Temperature zone incompatibility check blocks redistribution to incompatible bins
- RTV is blocked if days_to_expiry < RTV_MIN_DAYS_REMAINING
- Hazmat batches excluded from standard actions if HAZMAT_EXCLUDE = true
- Stale IBP data (> IBP_DATA_FRESHNESS_HOURS) degrades all confidence ratings to Low
- Data source failures halt the agent — no silent partial reports

---

## Milestones

### M1: Batch Scan Complete

- **Description**: All batches in scope have been retrieved from SAP EWM; SLED filtering and hazmat exclusion applied
- **Achieved when**: Batch list fetched with SLED ≤ today + RISK_HORIZON_DAYS; hazmat batches filtered; missing-SLED batches captured in exceptions list
- **Log on achievement**: `M1.achieved: batch scan complete — {n} batches in risk horizon, {m} excluded (hazmat/missing-SLED)`
- **Log on miss**: `M1.missed: batch scan failed — EWM data source unreachable or returned empty; halting run`

### M2: Risk Calculation Complete

- **Description**: Net risk quantities computed per batch using IBP consensus demand; each batch ranked by risk score
- **Achieved when**: All at-risk batches have risk_qty, days_to_expiry, and risk_score computed; batches below MIN_SCORE_THRESHOLD filtered out
- **Log on achievement**: `M2.achieved: risk calculation complete — {n} batches scored, {k} above threshold`
- **Log on miss**: `M2.missed: risk calculation incomplete — IBP forecast unavailable or stale; confidence downgraded to Low`

### M3: Action Matching Complete

- **Description**: Each at-risk batch evaluated against all enabled action types; eligibility rules applied
- **Achieved when**: All five action types evaluated per batch; eligible actions ranked in priority order; no action = disposal recommendation
- **Log on achievement**: `M3.achieved: action matching complete — {n} batches with recommended actions, {d} flagged for disposal`
- **Log on miss**: `M3.missed: action matching incomplete — scoring data unavailable`

### M4: Draft Artefacts Generated

- **Description**: DRAFT artefacts produced for applicable actions (RTV request, markdown event, transfer proposal)
- **Achieved when**: All batches with eligible actions have associated DRAFT text; artefacts marked as requiring human approval
- **Log on achievement**: `M4.achieved: draft artefacts generated — {r} RTV drafts, {md} markdown events, {t} transfer proposals`
- **Log on miss**: `M4.missed: draft artefact generation failed — no LLM response or action data missing`

### M5: Report Delivered

- **Description**: Full structured report assembled and returned to the caller
- **Achieved when**: Report includes run header, all per-batch blocks, summary action table, and exceptions section
- **Log on achievement**: `M5.achieved: report delivered — {n} at-risk batches, {e} exceptions, total exposure {amount} {currency}`
- **Log on miss**: `M5.missed: report assembly failed — incomplete data prevented full report generation`
