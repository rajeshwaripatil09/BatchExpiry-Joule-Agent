# Batch Expiry Risk Management Agent

Proactive batch expiry risk management agent operating within SAP EWM and SAP IBP to prevent inventory write-offs by identifying at-risk batches early and recommending concrete, prioritised actions before expiry occurs.

## Business challenge

Warehouse and supply chain planners at companies handling perishable, time-sensitive, or shelf-life-regulated goods (food & beverage, pharma, chemicals, consumer products) face a recurring inventory write-off risk: batches expire before they can be consumed, sold, or returned. Current SAP EWM and IBP capabilities track batch SLED/BBD and demand forecasts separately, but no automated agent synthesises both signals, scores the financial risk, and recommends the right action (redistribution, channel reallocation, markdown, RTV, or disposal) in a single prioritised report delivered to planners before it's too late.

## Key Milestones

1. **Batch scan complete** — All batches in scope retrieved from SAP EWM (MCHA/MCHB / Batch Master API); SLED within risk horizon identified; hazmat batches filtered if configured.
2. **Risk calculation complete** — Net risk quantities computed per batch using IBP consensus demand forecast; each batch scored (1–100) on expiry urgency, exposure, financial value, and bin velocity.
3. **Action matching complete** — Each at-risk batch evaluated against all five action types (redistribution, channel reallocation, markdown, RTV, disposal); eligibility rules applied per configurable parameters.
4. **Draft artefacts generated** — Structured DRAFT artefacts produced for applicable actions (RTV request, markdown event description, transfer order proposal); clearly marked as requiring human approval.
5. **Report delivered** — Full structured report (per-batch blocks + summary action table + exceptions) delivered to planner/warehouse manager; data quality flags raised for batches with missing SLED or demand data.

## Business Architecture (RBA)

### End-to-End Process

Plan to Fulfill (generic)

### Process Hierarchy

```
Plan to Fulfill (generic)
├── Manage Fulfillment (generic)
│   └── Manage supply chain data and operations (generic) [BPS-342]
│       ├── Manage inventory and warehouse operations
│       └── Batch expiry monitoring and action recommendation
└── Plan to Optimize Fulfillment (generic)
    └── Plan demand (generic) [BPS-338]
        ├── Develop baseline demand forecast
        └── Consumption projection for shelf-life risk quantification
```

### Summary

Batch expiry risk management maps to Plan to Fulfill — spanning warehouse/inventory operations (SAP EWM: SLED/BBD tracking, bin redistribution) and demand-driven risk quantification (SAP IBP: consumption projection via consensus forecast) — with industry variants covering retail replenishment, consumer products, and consignment RTV flows.

## Fit Gap Analysis

| Requirement (business) | Standard asset(s) found | API ORD ID | MCP Server ORD ID | Gap? | Notes / assumptions |
|---|---|---|---|---|---|
| Batch master read (SLED, BBD, qty, classification, bin) | SAP S/4HANA Cloud EWM — Internal Warehouse Management (SC5130 / SC841) | `sap.s4:apiResource:API_BATCH_SRV:v1` | ✗ | No | Batch Master Record OData API available; no MCP server in landscape — direct API call required |
| Shelf life data read | SAP S/4HANA Cloud — Shelf Life Data API | `sap.s4:apiResource:CT_RIMS_SLVERSION_0001:v1` | ✗ | No | OData API available for SLED/BBD reads |
| Warehouse bin configuration (velocity class, temperature zone) | SAP S/4HANA EWM — Warehouse Storage Bin API | `sap.s4:apiResource:WAREHOUSESTORAGEBIN_0001:v1` | ✗ | No | OData API available; no MCP server |
| Open warehouse orders and confirmed picks | SAP S/4HANA EWM — Warehouse Order and Task (A2X) | `sap.s4:apiResource:WAREHOUSEORDER_0001:v1` | ✗ | No | OData API for confirmed picks; no MCP server |
| IBP consensus demand forecast per SKU/location | SAP Integrated Business Planning — Demand Forecasting (SC2989), Consensus Demand Management (SC2988) | ✗ (IBP OData — no ORD ID published) | ✗ | Maybe | IBP OData APIs exist (Forecast Data Extraction, Integrate Key Figure Data) but no ORD ID in catalog; integration via IBP API or flat-file extraction needed |
| Vendor return agreement lookup (RTV eligibility) | SAP S/4HANA — Return To Supplier (SOAP/OData) | ✗ (SOAP: no ORD ID) | ✗ | Maybe | SOAP API "Manage Return To Supplier In" / "Return To Supplier Query" found; no ORD ID or MCP server; custom tool wrapper needed |
| Risk scoring, action matching, report generation | No standard SAP product automates this end-to-end | — | — | Yes | Core gap — custom AI agent required to orchestrate multi-source reads, apply scoring logic, and generate prioritised recommendations |
| Configurable parameters (thresholds, weights, action toggles) | No standard product | — | — | Yes | Agent configuration layer needed (env vars / config file) |

### Key findings
- SAP S/4HANA Cloud (Public & Private) covers EWM inventory and warehouse management as mandatory capabilities; batch master and storage bin OData APIs are available but no MCP servers are registered in this landscape.
- SAP IBP mandatorily covers consensus demand management and demand forecasting (SC2988, SC2989); however IBP API ORD IDs are not published in the catalog — integration requires IBP OData endpoint configuration.
- The core orchestration gap (multi-source read → risk scoring → action recommendation → draft artefact generation) is unmet by any standard SAP product and requires a custom AI agent.
- Return-to-vendor flow is partially covered by SOAP APIs (no ORD ID); the agent will draft RTV request text rather than calling vendor APIs directly.
- All five recommended action types require human approval before execution — the agent is strictly a recommendation engine.

## Recommendations

### Batch Expiry Risk Management — Pro-Code AI Agent on SAP BTP

#### Executive Summary

Python AI agent on BTP; reads EWM + IBP; scores, ranks, recommends.

#### Recommended Solution

A pro-code Python AI agent (A2A protocol, LangGraph) deployed on SAP BTP / SAP AI Core. The agent:
- Reads batch master records, SLED/BBD dates, bin configurations, and open warehouse orders from SAP S/4HANA EWM via OData APIs.
- Reads IBP consensus demand forecasts via IBP OData APIs.
- Executes the five-step scanning logic: identify at-risk batches → calculate net risk quantity → score and rank → match to action types → generate structured report with DRAFT artefacts.
- Runs on a configurable cron schedule (default: daily 02:00) and on-demand invocation.
- Produces a structured operational report (per-batch blocks, summary action table, exceptions) delivered to planners/warehouse managers.
- All SAP system interactions are read-only (no document posting); all DRAFT artefacts require human approval.

#### Recommended solution category

AI Agent

#### Intent fit
92%
