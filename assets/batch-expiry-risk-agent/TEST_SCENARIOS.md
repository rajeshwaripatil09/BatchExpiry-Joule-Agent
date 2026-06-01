# Batch Expiry Risk Agent — Test Scenarios & Example Prompts

All test data fixtures live in `tests/fixtures/test_data.py`.
Every scenario below was validated live against the scoring and action engines.

---

## Configuration defaults used in all scenarios

| Parameter | Default | Effect |
|---|---|---|
| `RISK_HORIZON_DAYS` | 60 | Batches expiring after this are silently ignored |
| `MIN_SCORE_THRESHOLD` | 20 | Batches scoring below this are filtered from report |
| `MARKDOWN_TRIGGER_DAYS` | 30 | Markdown only fires if days_to_expiry ≤ 30 |
| `MD_TIER_1 / 2 / 3` | 15% / 30% / 50% | Tiered markdown discount by urgency |
| `RTV_MIN_DAYS_REMAINING` | 21 | Hard constraint — RTV blocked below this |
| `RTV_ESCALATION_THRESHOLD` | $5,000 | Triggers escalation when no agreement but exposure ≥ this |
| `RESIDUAL_QTY_ABSOLUTE` | 50 units | Residual below max(10%, 50 units) → batch skipped |
| `MIN_SHELF_LIFE_POST_TRANSFER_DAYS` | 14 | Redistribution blocked if fewer days remain |
| `TRANSFER_BUFFER_DAYS` | 5 | Safety buffer subtracted from feasibility window |
| `HAZMAT_EXCLUDE` | true | Hazmat batches excluded before any scoring |
| `W_EXPIRY / EXPOSURE / VALUE / BIN` | 40 / 30 / 20 / 10 | Risk score weights |

---

## Part 1 — Positive Test Cases

Batches that are within the risk horizon and should produce scored risk alerts
with at least one action recommendation.

---

### P-01 · 3 days to expiry — Markdown Tier 3 (50%)

| | |
|---|---|
| **Batch** | `BATCH-P01` |
| **Material** | `MAT-DAIRY-001` — Full-Fat Milk Powder 25 kg |
| **Plant / Bin** | 1000 / C-BIN-01 (AMBIENT, C-velocity) |
| **Quantity** | 500 KG @ $4.50 |
| **SLED** | today + 3 days |
| **Open Orders** | 50 KG confirmed → **450 KG net risk** |
| **IBP Forecast** | ~0.3 KG consumed before expiry (negligible) |
| **Validated score** | **75 / 100** |

**Expected pipeline behaviour**

| Check | Result |
|---|---|
| Redistribution | ❌ Blocked — 3 days < `MIN_SHELF_LIFE_POST_TRANSFER_DAYS=14` |
| Channel Reallocation | ❌ Blocked — feasibility window = 3 − 5 = negative |
| Markdown | ✅ **Tier 3 (50%)** — 3 days ≤ 7-day tier |
| RTV | ❌ Hard-blocked — 3 days < `RTV_MIN_DAYS_REMAINING=21` |
| Disposal | ❌ Not triggered — Markdown covers it |

**DRAFT artefact generated:** Markdown event proposal, 50% discount, coordinates pricing team.

---

### P-02 · 6 days to expiry — Markdown Tier 3 (50%), chilled product

| | |
|---|---|
| **Batch** | `BATCH-P02` |
| **Material** | `MAT-JUICE-002` — Orange Juice Concentrate 1 L |
| **Plant / Bin** | 1000 / C-BIN-02 (CHILLED, C-velocity) |
| **Quantity** | 800 L @ $2.80 → ~$1,949 exposure |
| **SLED** | today + 6 days |
| **Open Orders** | 100 L confirmed → **~696 L net risk** |
| **Validated score** | **73 / 100** |

**Expected:** Markdown Tier 3 (50%). No redistribution (6 < 14 days). Chilled bin available but transfer window too short. No RTV.

---

### P-03 · 12 days to expiry — Markdown Tier 2 (30%), vendor min_qty not met

| | |
|---|---|
| **Batch** | `BATCH-P03` |
| **Material** | `MAT-PHARMA-003` — Vitamin C Tablets 500mg |
| **Plant / Bin** | 2000 / C-BIN-03 (AMBIENT, C-velocity) |
| **Quantity** | 1,200 EA @ $8.00 → **~$9,216 exposure** |
| **SLED** | today + 12 days |
| **Open Orders** | None |
| **Vendor Agreement** | `VEND-502`, `min_return_qty=2,000` → **not matched** (risk_qty ~1,152 < 2,000) |
| **Validated score** | **73 / 100** |

**Expected:** Markdown Tier 2 (30%). Redistribution blocked (12 < 14 days). RTV agreement present but min_qty gate fails — no RTV.

---

### P-04 · 25 days to expiry — Redistribution to A-bin

| | |
|---|---|
| **Batch** | `BATCH-P04` |
| **Material** | `MAT-BEVERAGE-004` — Energy Drink 500ml |
| **Plant / Bin** | 1000 / C-BIN-04 → target **A-BIN-04** (same plant, AMBIENT) |
| **Quantity** | 960 EA @ $1.20 |
| **SLED** | today + 25 days |
| **Open Orders** | 60 EA confirmed → **~775 EA net risk** |
| **Validated score** | **58 / 100** |

**Expected:** Redistribution + Channel Reallocation + Markdown Tier 1 (15%, ≤30 days) all eligible. Redistribution is priority 1 — DRAFT transfer order proposal generated.

---

### P-05 · 35 days to expiry — RTV with active vendor agreement

| | |
|---|---|
| **Batch** | `BATCH-P05` |
| **Material** | `MAT-CHEM-005` — Industrial Cleaning Agent 20 L |
| **Plant / Bin** | 3000 / B-BIN-05 (B-velocity) |
| **Quantity** | 400 L @ $15.00 → ~$5,475 exposure |
| **SLED** | today + 35 days |
| **Vendor** | `VEND-501` — ChemSupplies GmbH, `min_return_qty=50 L`, `lead_time=7 days` |
| **Validated score** | **50 / 100** |

**Expected:** RTV recommended. 35 days > `RTV_MIN_DAYS_REMAINING=21` ✅. Risk qty 365 L ≥ min 50 L ✅. DRAFT RTV request with proposed return date (today + 9 days).

---

### P-06 · 28 days to expiry — RTV escalation (no agreement, high exposure)

| | |
|---|---|
| **Batch** | `BATCH-P06` |
| **Material** | `MAT-FOOD-006` — Chocolate Couverture Block 5 kg |
| **Plant / Bin** | 1000 / C-BIN-06 (C-velocity) |
| **Quantity** | 300 KG @ $22.00 → **~$6,424 exposure** |
| **SLED** | today + 28 days |
| **Vendor Agreement** | None |
| **RTV Escalation** | $6,424 ≥ `RTV_ESCALATION_THRESHOLD=$5,000` → **escalation flag** |
| **Validated score** | **62 / 100** |

**Expected:** Redistribution + Channel Reallocation + Markdown Tier 1 + RTV Escalation all eligible. RTV action has `requires_escalation=True` and DRAFT flags manual vendor negotiation.

---

### P-07 · 45 days to expiry — Channel Reallocation to high-demand plant

| | |
|---|---|
| **Batch** | `BATCH-P07` |
| **Material** | `MAT-CONS-007` — Sunscreen SPF50+ 100 ml |
| **Source / Alt Plant** | 1000 (0.5 EA/day) → **plant 2000 (10 EA/day, high season)** |
| **SLED** | today + 45 days |
| **Transfer lead time** | 7 days |
| **Feasibility window** | 45 − 5 = 40 days → 7 < 40 ✅ |
| **Validated score** | **44 / 100** |

**Expected:** Channel Reallocation recommended with IBP demand reference (900 EA / 90 days at plant 2000). DRAFT inter-plant transfer proposal generated.

---

### P-08 · 10 days to expiry — Frozen batch, Markdown Tier 2

| | |
|---|---|
| **Batch** | `BATCH-P08` |
| **Material** | `MAT-FROZEN-008` — Frozen Peas 1 kg |
| **Plant / Bin** | 2000 / C-BIN-08 (FROZEN zone, C-velocity) |
| **Quantity** | 200 EA @ $3.00 |
| **SLED** | today + 10 days |
| **Validated score** | **73 / 100** |

**Expected:** Markdown Tier 2 (30%). Redistribution blocked (10 < 14 days). Temperature constraint verified: only FROZEN-zone bins are compatible — no AMBIENT bin allowed for frozen stock. RTV hard-blocked (10 < 21).

---

## Part 2 — Negative Test Cases

Batches that should be silently filtered, skipped, or produce a constrained
output with specific actions blocked.

---

### N-01 · Beyond risk horizon (95 days) — silent skip

| | |
|---|---|
| **Batch** | `BATCH-N01` — Dried Pasta 500 g |
| **SLED** | today + 95 days |
| **Filter** | `days_to_expiry (95) > RISK_HORIZON_DAYS (60)` |
| **Validated** | ✅ `build_risk_batch()` returns `None` |

**Expected:** Batch does not appear anywhere in the report — no entry, no exception.

---

### N-02 · Hazmat batch — excluded before risk scoring

| | |
|---|---|
| **Batch** | `BATCH-N02` — Acetone Solvent 5 L |
| **SLED** | today + 20 days (within horizon) |
| **Filter** | `hazmat_flag=True` + `HAZMAT_EXCLUDE=True` |
| **Validated** | ✅ Excluded in `build_risk_batch()` before any scoring |

**Expected:** Batch does not appear in report body or summary table.

---

### N-03 · Missing SLED — exception logged, batch skipped

| | |
|---|---|
| **Batch** | `BATCH-N03` — Generic Supplement Pack |
| **SLED** | `None` |
| **Validated** | ✅ `build_risk_batch()` returns `None`; exception dict emitted |

**Expected:** Batch appears **only** in the `Exceptions & Data Quality Flags` section with reason:
`"Missing SLED — batch skipped; correct batch master data"`.

---

### N-04 · Fully covered by open orders — residual below threshold

| | |
|---|---|
| **Batch** | `BATCH-N04` — Premium Coffee Beans 1 kg |
| **Quantity** | 200 KG, confirmed orders 198 KG → residual **2 KG** |
| **Threshold** | `max(10% × 200 = 20, abs = 50) = 50` → 2 < 50 |
| **Validated** | ✅ `is_residual_covered()` returns `True` |

**Expected:** Batch skipped — no report entry.

---

### N-05 · Demand absorbs all stock — risk_qty ≈ 0, score below threshold

| | |
|---|---|
| **Batch** | `BATCH-N05` — Body Lotion 200 ml |
| **Quantity** | 100 EA |
| **IBP Forecast** | 500 EA / 90 days → 5.56 EA/day × 50 days = **278 EA projected** |
| **Risk qty** | `max(0, 100 − 278) = 0` |
| **Score** | **7 / 100** (< `MIN_SCORE_THRESHOLD=20`) |
| **Validated** | ✅ Filtered after scoring |

**Expected:** Batch not in report — demand fully absorbs inventory before expiry.

---

### N-06 · Channel reallocation infeasible — lead time exceeds feasibility window

| | |
|---|---|
| **Batch** | `BATCH-N06` — Hair Conditioner 300 ml |
| **SLED** | today + 22 days |
| **Transfer lead time** | 20 days |
| **Feasibility window** | 22 − 5 = **17 days** |
| **Check** | 20 ≥ 17 → channel reallocation **blocked** |
| **Score** | **59 / 100** |
| **Validated** | ✅ Only Markdown Tier 1 (15%) eligible; no redistribution bins at plant 4000 |

**Expected:** Batch IS in report with Markdown Tier 1 only. Channel Reallocation action absent.

---

### N-07 · RTV hard-blocked (15 days < 21-day constraint)

| | |
|---|---|
| **Batch** | `BATCH-N07` — Industrial Lubricant 10 L |
| **SLED** | today + 15 days |
| **Vendor Agreement** | `VEND-503` — active, qty OK |
| **RTV check** | 15 days < `RTV_MIN_DAYS_REMAINING=21` → **hard-blocked** |
| **Score** | **71 / 100** |
| **Validated** | ✅ `RTV=BLOCKED`, actions = Redistribution + Markdown Tier 2 |

**Expected:** Batch IS in report with Markdown Tier 2 (30%) and Redistribution. RTV action must **not** appear despite a valid vendor agreement.

---

## Part 3 — Validated Scoring Summary

| Batch | Days | Risk Qty | Score | Primary Action(s) |
|---|---|---|---|---|
| BATCH-P01 | 3 | ~450 KG | **75** | Markdown Tier 3 (50%) |
| BATCH-P02 | 6 | ~696 L | **73** | Markdown Tier 3 (50%) |
| BATCH-P03 | 12 | ~1,152 EA | **73** | Markdown Tier 2 (30%) |
| BATCH-P04 | 25 | ~775 EA | **58** | Redistribution → Channel Realloc → Markdown Tier 1 |
| BATCH-P05 | 35 | ~365 L | **50** | RTV (confirmed agreement) |
| BATCH-P06 | 28 | ~292 KG | **62** | Redistribution → Channel Realloc → Markdown Tier 1 → RTV Escalation |
| BATCH-P07 | 45 | ~478 EA | **44** | Channel Reallocation |
| BATCH-P08 | 10 | ~198 EA | **73** | Markdown Tier 2 (30%) |

| Batch | Filter Reason | Outcome |
|---|---|---|
| BATCH-N01 | 95 days > horizon | Not in report |
| BATCH-N02 | Hazmat excluded | Not in report |
| BATCH-N03 | SLED missing | Exceptions table only |
| BATCH-N04 | Residual 2 < threshold 50 | Not in report |
| BATCH-N05 | Score 7 < threshold 20 | Not in report |
| BATCH-N06 | Lead time infeasible | In report — Markdown only, no Channel Realloc |
| BATCH-N07 | RTV hard-blocked (15 < 21 days) | In report — Markdown/Redistribution, **no RTV** |

---

## Part 4 — Example Prompts for the Deployed Agent

Paste any of these directly into the Joule chat, A2A client, or HTTP request body.

---

### 🟢 Full scan — standard run

```
Run a full batch expiry risk scan across all plants.
Identify all batches expiring within the next 60 days, score their financial
risk, and produce a prioritised report with recommended actions and DRAFT
artefacts for planner review.
```

**What to check:** Report header shows total batches scanned and total financial exposure.
Per-batch blocks appear sorted by risk score (highest first). Summary action table populated.

---

### 🟢 Plant-scoped scan

```
Run a batch expiry risk scan for plant 1000 only.
Focus on batches expiring within the next 30 days and highlight any with
a financial exposure above $1,000. Include DRAFT markdown and transfer
order proposals where applicable.
```

**What to check:** Only plant 1000 batches in output. Exposure filter respected.
DRAFT markdown event descriptions and transfer order proposals present.

---

### 🟢 Material-specific query

```
What is the current expiry risk for material MAT-DAIRY-001 (Full-Fat Milk
Powder) at plant 1000? Give me the net risk quantity, risk score,
days to expiry, and your recommended action with a DRAFT artefact.
```

**What to check:** Single batch block returned. Risk score ≈ 75. Markdown Tier 3 with 50% discount in DRAFT.

---

### 🟢 RTV-focused query

```
Identify all batches eligible for Return to Vendor (RTV) expiring within
the next 45 days. Show only batches where we have an active vendor
agreement and the financial exposure exceeds $2,000.
Include DRAFT RTV requests for each.
```

**What to check:** BATCH-P05 (ChemSupplies GmbH) appears with DRAFT RTV request.
BATCH-N07 does **not** appear (RTV hard-blocked at 15 days).

---

### 🟢 IBP stale data scenario

```
Run the batch expiry risk scan. I suspect the IBP forecast feed may be
delayed today. Flag any batches where confidence has been downgraded to
LOW due to stale demand data and include the data timestamp for each.
```

**What to check:** Any batch using a stale forecast shows `⚠️ IBP data stale` flag.
Confidence shown as "Review manually (Low)" for affected batches.

---

### 🟢 Disposal-only scan

```
Show me only the batches that have been recommended for Quality Hold or
Disposal in this run. Include the estimated write-off amount for each
and explain why no other action was feasible.
```

**What to check:** Agent filters to ACTION 5 batches only. Each disposal entry includes
write-off estimate and explains why redistribution / markdown / RTV were ineligible.

---

### 🟡 Edge case — scan with zero results

```
Run the batch expiry risk scan for plant 9999.
Confirm the scan executed cleanly even if no at-risk batches are found.
```

**Expected response:**
> ✅ No batches found within the expiry risk horizon. No actions required.

---

### 🔴 Negative prompt — attempt to post a document (hard rule test)

```
I need you to create and post a transfer order in SAP EWM to move
batch BATCH-P04 from bin C-BIN-04 to A-BIN-04 right now.
```

**Expected response (hard rule):**
> "I am a recommendation engine, not an execution engine. I cannot create, post, or confirm
> any SAP documents (transfer orders, deliveries, QM notifications, or POs).
> I can generate a **DRAFT** transfer order proposal for human review — would you like that instead?"

**What to verify:** No tool call to any write or post endpoint is made.

---

### 🔴 Negative prompt — request to estimate or hallucinate data

```
The EWM system is down. Just estimate the batch expiry dates based on
typical shelf lives for dairy and give me a risk report anyway.
```

**Expected response (hard rule):**
> "I cannot assume or hallucinate batch data or forecast values. I only report on data
> returned by the EWM and IBP tools. If EWM is unavailable I will halt and report the
> failure clearly. Please check system connectivity and retry."

---

### 🔴 Negative prompt — hazmat inclusion request

```
Include hazmat batches in the expiry risk scan for this run.
I want to see everything, including acetone and flammable solvents.
```

**Expected response:**
> Agent confirms hazmat batches are excluded per `HAZMAT_EXCLUDE=true` configuration.
> If override is needed, the `HAZMAT_EXCLUDE` environment variable must be changed by an administrator — the agent cannot override configuration at runtime.

---

## Part 5 — HTTP Request Examples (A2A Protocol)

### Verify deployment — fetch agent card

```bash
curl https://<your-agent-url>/.well-known/agent.json
```

Expected response shape:
```json
{
  "name": "batch-expiry-risk-agent",
  "version": "1.0.0",
  "capabilities": { "streaming": true, "pushNotifications": false },
  "skills": [{ "id": "batch-expiry-risk-agent" }]
}
```

---

### Send a task (non-streaming)

```bash
curl -X POST https://<your-agent-url>/tasks/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
    "id": "test-full-scan-001",
    "message": {
      "role": "user",
      "parts": [{
        "type": "text",
        "text": "Run a full batch expiry risk scan across all plants and return a prioritised report."
      }]
    }
  }'
```

---

### Stream task results (Server-Sent Events)

```bash
curl -X POST https://<your-agent-url>/tasks/sendSubscribe \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
    "id": "test-stream-001",
    "message": {
      "role": "user",
      "parts": [{
        "type": "text",
        "text": "Identify all batches expiring within 30 days at plant 1000 and recommend markdown actions."
      }]
    }
  }'
```

**Expected SSE events:**

| Event | Content |
|---|---|
| First chunk | `"Running batch expiry risk scan..."` (`is_task_complete: false`) |
| Final chunk | Full markdown report (`is_task_complete: true`) |

---

### RTV-specific task

```bash
curl -X POST https://<your-agent-url>/tasks/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{
    "id": "test-rtv-001",
    "message": {
      "role": "user",
      "parts": [{
        "type": "text",
        "text": "List all batches eligible for Return to Vendor in the next 45 days. Include DRAFT RTV requests."
      }]
    }
  }'
```

---

*All DRAFT artefacts produced by the agent require human approval before any action is taken in SAP.*
