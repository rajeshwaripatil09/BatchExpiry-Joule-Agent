"""
Shared test fixtures for the Batch Expiry Risk Management Agent.

Covers 8 positive scenarios (should produce risk alerts + recommendations)
and 7 negative scenarios (should be filtered, skipped, or blocked).

Usage:
    from tests.fixtures.test_data import (
        POSITIVE_BATCHES, NEGATIVE_BATCHES,
        BINS, OPEN_ORDERS, DEMAND_FORECASTS, VENDOR_AGREEMENTS, TODAY
    )
"""

from datetime import date, datetime, timedelta

from app.models import (
    BatchClassification,
    BatchRecord,
    BinInfo,
    DemandForecast,
    OpenOrder,
    VendorReturnAgreement,
)

# Pin to today so all SLED offsets stay deterministic relative to each run
TODAY = date.today()


def _sled(days: int) -> date:
    """Return a SLED date N days from today."""
    return TODAY + timedelta(days=days)


# ══════════════════════════════════════════════════════════════════════════════
# POSITIVE BATCHES
# Within risk horizon; expected to produce risk scores above threshold
# and at least one action recommendation each.
# ══════════════════════════════════════════════════════════════════════════════

POSITIVE_BATCHES: list[BatchRecord] = [

    # ── P-01  3 days to expiry ────────────────────────────────────────────────
    # RTV hard-blocked (<21 days). Redistribution blocked (<14 day post-transfer min).
    # Markdown Tier 3 (50%, ≤7 days) is the primary action.
    BatchRecord(
        batch_number="BATCH-P01",
        material="MAT-DAIRY-001",
        description="Full-Fat Milk Powder 25 kg",
        plant="1000",
        storage_location="SL01",
        bin="C-BIN-01",
        quantity=500.0,
        uom="KG",
        unit_value=4.50,
        sled=_sled(3),
        batch_classification=BatchClassification(
            storage_conditions="Dry, cool",
            temperature_class="AMBIENT",
            hazmat_flag=False,
        ),
    ),

    # ── P-02  6 days to expiry ────────────────────────────────────────────────
    # Chilled product. Markdown Tier 3 (50%).
    # Redistribution blocked (6 < 14 day minimum). RTV hard-blocked.
    BatchRecord(
        batch_number="BATCH-P02",
        material="MAT-JUICE-002",
        description="Orange Juice Concentrate 1 L",
        plant="1000",
        storage_location="SL02",
        bin="C-BIN-02",
        quantity=800.0,
        uom="L",
        unit_value=2.80,
        sled=_sled(6),
        batch_classification=BatchClassification(
            storage_conditions="Chilled",
            temperature_class="CHILLED",
            hazmat_flag=False,
        ),
    ),

    # ── P-03  12 days to expiry ───────────────────────────────────────────────
    # Pharma. Vendor agreement exists but min_return_qty > risk_qty → RTV ineligible.
    # Markdown Tier 2 (30%, ≤14 days). Redistribution blocked (12 < 14).
    BatchRecord(
        batch_number="BATCH-P03",
        material="MAT-PHARMA-003",
        description="Vitamin C Tablets 500mg — 100 count",
        plant="2000",
        storage_location="SL03",
        bin="C-BIN-03",
        quantity=1200.0,
        uom="EA",
        unit_value=8.00,
        sled=_sled(12),
        batch_classification=BatchClassification(
            storage_conditions="Store below 25°C",
            temperature_class="AMBIENT",
            hazmat_flag=False,
        ),
    ),

    # ── P-04  25 days to expiry, C-bin ────────────────────────────────────────
    # A-velocity bin available at same plant, temperature compatible.
    # → Redistribution recommended; Markdown Tier 1 (15%) also eligible.
    BatchRecord(
        batch_number="BATCH-P04",
        material="MAT-BEVERAGE-004",
        description="Energy Drink 500 ml (case of 24)",
        plant="1000",
        storage_location="SL04",
        bin="C-BIN-04",
        quantity=960.0,
        uom="EA",
        unit_value=1.20,
        sled=_sled(25),
        batch_classification=BatchClassification(
            storage_conditions="Ambient",
            temperature_class="AMBIENT",
            hazmat_flag=False,
        ),
    ),

    # ── P-05  35 days to expiry, active RTV agreement ─────────────────────────
    # days_to_expiry (35) > rtv_min_days_remaining (21). Agreement matched.
    # → RTV with DRAFT vendor return request.
    BatchRecord(
        batch_number="BATCH-P05",
        material="MAT-CHEM-005",
        description="Industrial Cleaning Agent 20 L",
        plant="3000",
        storage_location="SL05",
        bin="B-BIN-05",
        quantity=400.0,
        uom="L",
        unit_value=15.00,
        sled=_sled(35),
        batch_classification=BatchClassification(
            storage_conditions="Cool, dry",
            temperature_class="AMBIENT",
            hazmat_flag=False,
        ),
    ),

    # ── P-06  28 days to expiry, no RTV agreement, exposure > $5 k threshold ──
    # No vendor agreement but financial exposure = ~$6,400 ≥ $5,000 escalation threshold.
    # → RTV escalation flag (requires_escalation=True).
    BatchRecord(
        batch_number="BATCH-P06",
        material="MAT-FOOD-006",
        description="Chocolate Couverture Block 5 kg",
        plant="1000",
        storage_location="SL06",
        bin="C-BIN-06",
        quantity=300.0,
        uom="KG",
        unit_value=22.00,
        sled=_sled(28),
        batch_classification=BatchClassification(
            storage_conditions="Store 15–18°C",
            temperature_class="AMBIENT",
            hazmat_flag=False,
        ),
    ),

    # ── P-07  45 days to expiry, high IBP demand at alternative plant ─────────
    # Transfer lead time (7 days) < feasibility window (45 − 5 = 40 days).
    # → Channel Reallocation to plant 2000.
    BatchRecord(
        batch_number="BATCH-P07",
        material="MAT-CONS-007",
        description="Sunscreen SPF50+ 100 ml",
        plant="1000",
        storage_location="SL07",
        bin="B-BIN-07",
        quantity=500.0,
        uom="EA",
        unit_value=6.50,
        sled=_sled(45),
        batch_classification=BatchClassification(
            storage_conditions="Ambient",
            temperature_class="AMBIENT",
            hazmat_flag=False,
        ),
    ),

    # ── P-08  10 days to expiry, frozen product ───────────────────────────────
    # A-velocity frozen bin available. Redistribution eligible (10 ≥ min 14? No — blocked).
    # Markdown Tier 2 (30%). RTV hard-blocked (10 < 21).
    BatchRecord(
        batch_number="BATCH-P08",
        material="MAT-FROZEN-008",
        description="Frozen Peas 1 kg (case of 20)",
        plant="2000",
        storage_location="SL08",
        bin="C-BIN-08",
        quantity=200.0,
        uom="EA",
        unit_value=3.00,
        sled=_sled(10),
        batch_classification=BatchClassification(
            storage_conditions="Frozen (-18°C)",
            temperature_class="FROZEN",
            hazmat_flag=False,
        ),
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# NEGATIVE BATCHES
# Each should be silently filtered, skipped, or produce a constrained output.
# ══════════════════════════════════════════════════════════════════════════════

NEGATIVE_BATCHES: list[BatchRecord] = [

    # ── N-01  95 days to expiry — outside risk horizon ────────────────────────
    # RISK_HORIZON_DAYS=60 → build_risk_batch returns None silently.
    BatchRecord(
        batch_number="BATCH-N01",
        material="MAT-DRY-101",
        description="Dried Pasta 500 g",
        plant="1000",
        storage_location="SL01",
        bin="A-BIN-11",
        quantity=1000.0,
        uom="KG",
        unit_value=1.50,
        sled=_sled(95),
        batch_classification=BatchClassification(temperature_class="AMBIENT"),
    ),

    # ── N-02  Hazmat batch — excluded before risk scoring ─────────────────────
    # SLED within horizon (20 days) but hazmat_flag=True + HAZMAT_EXCLUDE=True.
    BatchRecord(
        batch_number="BATCH-N02",
        material="MAT-HAZMAT-102",
        description="Acetone Solvent 5 L",
        plant="3000",
        storage_location="SL09",
        bin="C-BIN-11",
        quantity=300.0,
        uom="L",
        unit_value=12.00,
        sled=_sled(20),
        batch_classification=BatchClassification(
            storage_conditions="Flammable liquid storage",
            temperature_class="AMBIENT",
            hazmat_flag=True,          # ← triggers exclusion
        ),
    ),

    # ── N-03  Missing SLED — exception logged, batch skipped ─────────────────
    BatchRecord(
        batch_number="BATCH-N03",
        material="MAT-MISC-103",
        description="Generic Supplement Pack",
        plant="1000",
        storage_location="SL01",
        bin="B-BIN-12",
        quantity=150.0,
        uom="EA",
        unit_value=5.00,
        sled=None,                     # ← triggers exception path
        batch_classification=BatchClassification(temperature_class="AMBIENT"),
    ),

    # ── N-04  Fully covered by open orders ────────────────────────────────────
    # qty=200, confirmed=198 → residual=2 < max(10%×200=20, abs=50)=50 → skipped.
    BatchRecord(
        batch_number="BATCH-N04",
        material="MAT-FOOD-104",
        description="Premium Coffee Beans 1 kg",
        plant="1000",
        storage_location="SL02",
        bin="B-BIN-13",
        quantity=200.0,
        uom="KG",
        unit_value=18.00,
        sled=_sled(30),
        batch_classification=BatchClassification(temperature_class="AMBIENT"),
    ),

    # ── N-05  Low score — demand absorbs all stock ────────────────────────────
    # forecast 500 EA/90 days → 5.56/day × 50 days = 278 > qty 100 → risk_qty=0.
    # With risk_qty=0, score ≈ 7 < MIN_SCORE_THRESHOLD=20 → filtered.
    BatchRecord(
        batch_number="BATCH-N05",
        material="MAT-FMCG-105",
        description="Body Lotion 200 ml",
        plant="2000",
        storage_location="SL04",
        bin="A-BIN-16",
        quantity=100.0,
        uom="EA",
        unit_value=4.00,
        sled=_sled(50),
        batch_classification=BatchClassification(temperature_class="AMBIENT"),
    ),

    # ── N-06  Channel reallocation infeasible — lead time exceeds window ──────
    # days_to_expiry=22, TRANSFER_BUFFER_DAYS=5 → window=17.
    # transfer_lead_time=20 ≥ 17 → channel reallocation blocked.
    # No A-bin at same plant and ≤14 days for markdown Tier 1 → only disposal.
    BatchRecord(
        batch_number="BATCH-N06",
        material="MAT-CONS-106",
        description="Hair Conditioner 300 ml",
        plant="4000",
        storage_location="SL10",
        bin="B-BIN-20",
        quantity=250.0,
        uom="EA",
        unit_value=3.50,
        sled=_sled(22),
        batch_classification=BatchClassification(temperature_class="AMBIENT"),
    ),

    # ── N-07  RTV hard-blocked (15 days < rtv_min_days_remaining=21) ──────────
    # An active vendor agreement exists but the hard constraint fires first.
    # Markdown Tier 1 (15%) is the only action — NO RTV in output.
    BatchRecord(
        batch_number="BATCH-N07",
        material="MAT-CHEM-107",
        description="Industrial Lubricant 10 L",
        plant="3000",
        storage_location="SL05",
        bin="C-BIN-14",
        quantity=250.0,
        uom="L",
        unit_value=20.00,
        sled=_sled(15),
        batch_classification=BatchClassification(temperature_class="AMBIENT"),
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# BIN CONFIGURATIONS
# ══════════════════════════════════════════════════════════════════════════════

BINS: list[BinInfo] = [
    # C-velocity bins (current locations of at-risk batches)
    BinInfo(bin_id="C-BIN-01", plant="1000", storage_type="ST01", velocity_class="C", temperature_zone="AMBIENT"),
    BinInfo(bin_id="C-BIN-02", plant="1000", storage_type="ST02", velocity_class="C", temperature_zone="CHILLED"),
    BinInfo(bin_id="C-BIN-03", plant="2000", storage_type="ST01", velocity_class="C", temperature_zone="AMBIENT"),
    BinInfo(bin_id="C-BIN-04", plant="1000", storage_type="ST01", velocity_class="C", temperature_zone="AMBIENT"),
    BinInfo(bin_id="C-BIN-06", plant="1000", storage_type="ST01", velocity_class="C", temperature_zone="AMBIENT"),
    BinInfo(bin_id="C-BIN-08", plant="2000", storage_type="ST03", velocity_class="C", temperature_zone="FROZEN"),
    BinInfo(bin_id="C-BIN-11", plant="3000", storage_type="ST01", velocity_class="C", temperature_zone="AMBIENT"),
    BinInfo(bin_id="C-BIN-14", plant="3000", storage_type="ST01", velocity_class="C", temperature_zone="AMBIENT"),

    # B-velocity bins
    BinInfo(bin_id="B-BIN-05", plant="3000", storage_type="ST01", velocity_class="B", temperature_zone="AMBIENT"),
    BinInfo(bin_id="B-BIN-07", plant="1000", storage_type="ST01", velocity_class="B", temperature_zone="AMBIENT"),
    BinInfo(bin_id="B-BIN-12", plant="1000", storage_type="ST01", velocity_class="B", temperature_zone="AMBIENT"),
    BinInfo(bin_id="B-BIN-13", plant="1000", storage_type="ST01", velocity_class="B", temperature_zone="AMBIENT"),
    BinInfo(bin_id="B-BIN-20", plant="4000", storage_type="ST01", velocity_class="B", temperature_zone="AMBIENT"),

    # A-velocity bins — redistribution targets
    BinInfo(bin_id="A-BIN-04", plant="1000", storage_type="ST01", velocity_class="A", temperature_zone="AMBIENT"),
    BinInfo(bin_id="A-BIN-07", plant="1000", storage_type="ST01", velocity_class="A", temperature_zone="AMBIENT"),
    BinInfo(bin_id="A-BIN-11", plant="1000", storage_type="ST01", velocity_class="A", temperature_zone="AMBIENT"),
    BinInfo(bin_id="A-BIN-16", plant="2000", storage_type="ST01", velocity_class="A", temperature_zone="AMBIENT"),
    # Frozen A-bin — only compatible with FROZEN batches
    BinInfo(bin_id="A-BIN-FRZ", plant="2000", storage_type="ST03", velocity_class="A", temperature_zone="FROZEN"),
]


# ══════════════════════════════════════════════════════════════════════════════
# OPEN ORDERS
# ══════════════════════════════════════════════════════════════════════════════

OPEN_ORDERS: list[OpenOrder] = [
    # P-01: 50/500 KG confirmed → ~450 KG net risk
    OpenOrder(batch_number="BATCH-P01", material="MAT-DAIRY-001",    plant="1000", confirmed_qty=50.0,  order_type="SALES_ORDER"),
    # P-02: 100/800 L confirmed → ~700 L net risk
    OpenOrder(batch_number="BATCH-P02", material="MAT-JUICE-002",    plant="1000", confirmed_qty=100.0, order_type="SALES_ORDER"),
    # P-04: 60/960 EA confirmed → ~900 EA net risk
    OpenOrder(batch_number="BATCH-P04", material="MAT-BEVERAGE-004", plant="1000", confirmed_qty=60.0,  order_type="TRANSFER_ORDER"),
    # N-04: 198/200 KG confirmed → residual=2 < abs threshold 50 → batch skipped
    OpenOrder(batch_number="BATCH-N04", material="MAT-FOOD-104",     plant="1000", confirmed_qty=198.0, order_type="SALES_ORDER"),
]


# ══════════════════════════════════════════════════════════════════════════════
# DEMAND FORECASTS  (IBP consensus, keyed by (material, plant))
# ══════════════════════════════════════════════════════════════════════════════

DEMAND_FORECASTS: dict[tuple[str, str], DemandForecast] = {

    # P-01 Dairy — negligible consumption before 3-day expiry
    ("MAT-DAIRY-001", "1000"): DemandForecast(
        material="MAT-DAIRY-001", plant="1000",
        total_qty=9.0, horizon_days=90,        # 0.1 KG/day × 3 = 0.3 KG ≈ nothing
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-02 Juice — low consumption before 6-day expiry
    ("MAT-JUICE-002", "1000"): DemandForecast(
        material="MAT-JUICE-002", plant="1000",
        total_qty=54.0, horizon_days=90,       # 0.6 L/day × 6 = 3.6 L vs 700 at risk
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-03 Pharma — modest demand, insufficient to clear stock
    ("MAT-PHARMA-003", "2000"): DemandForecast(
        material="MAT-PHARMA-003", plant="2000",
        total_qty=360.0, horizon_days=90,      # 4 EA/day × 12 = 48 EA vs 1,200 at risk
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-04 Beverage — moderate demand, large residual remains
    ("MAT-BEVERAGE-004", "1000"): DemandForecast(
        material="MAT-BEVERAGE-004", plant="1000",
        total_qty=450.0, horizon_days=90,      # 5 EA/day × 25 = 125 EA vs 900 at risk
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-05 Cleaning Agent — low demand vs large stock
    ("MAT-CHEM-005", "3000"): DemandForecast(
        material="MAT-CHEM-005", plant="3000",
        total_qty=90.0, horizon_days=90,       # 1 L/day × 35 = 35 L vs 400 at risk
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-06 Chocolate — almost no demand, large financial exposure
    ("MAT-FOOD-006", "1000"): DemandForecast(
        material="MAT-FOOD-006", plant="1000",
        total_qty=27.0, horizon_days=90,       # 0.3 KG/day × 28 = 8.4 KG vs 300 at risk
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-07 Sunscreen at source plant — slow demand
    ("MAT-CONS-007", "1000"): DemandForecast(
        material="MAT-CONS-007", plant="1000",
        total_qty=45.0, horizon_days=90,       # 0.5 EA/day × 45 = 22.5 vs 500 at risk
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-07 Sunscreen at alternative plant — high-season demand (drives channel reallocation)
    ("MAT-CONS-007", "2000"): DemandForecast(
        material="MAT-CONS-007", plant="2000",
        total_qty=900.0, horizon_days=90,      # 10 EA/day — hot market
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # P-08 Frozen Peas — negligible demand
    ("MAT-FROZEN-008", "2000"): DemandForecast(
        material="MAT-FROZEN-008", plant="2000",
        total_qty=20.0, horizon_days=90,
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # N-05 Body Lotion — strong demand fully absorbs stock before expiry
    ("MAT-FMCG-105", "2000"): DemandForecast(
        material="MAT-FMCG-105", plant="2000",
        total_qty=500.0, horizon_days=90,      # 5.56/day × 50 = 278 > qty 100 → risk_qty=0
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # N-06 Hair Conditioner — some demand but channel realloc infeasible (lead time too long)
    ("MAT-CONS-106", "4000"): DemandForecast(
        material="MAT-CONS-106", plant="4000",
        total_qty=45.0, horizon_days=90,
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
    # N-07 Lubricant — no demand (RTV hard-blocked; markdown is only action)
    ("MAT-CHEM-107", "3000"): DemandForecast(
        material="MAT-CHEM-107", plant="3000",
        total_qty=0.0, horizon_days=90,
        is_stale=False, data_timestamp=datetime.utcnow(),
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR RETURN AGREEMENTS
# ══════════════════════════════════════════════════════════════════════════════

VENDOR_AGREEMENTS: list[VendorReturnAgreement] = [
    # P-05: Active agreement — RTV recommended (35 days > 21-day hard constraint; qty OK)
    VendorReturnAgreement(
        material="MAT-CHEM-005",
        vendor="VEND-501",
        vendor_name="ChemSupplies GmbH",
        min_return_qty=50.0,
        lead_time_days=7,
        has_agreement=True,
        purchase_order_ref="PO-2024-87654",
    ),
    # P-03: Agreement exists but min_return_qty (2,000) > risk_qty (~1,152) → not matched
    VendorReturnAgreement(
        material="MAT-PHARMA-003",
        vendor="VEND-502",
        vendor_name="PharmaDist Ltd",
        min_return_qty=2000.0,
        lead_time_days=10,
        has_agreement=True,
        purchase_order_ref="PO-2024-11234",
    ),
    # N-07: Agreement exists BUT 15 days < rtv_min_days_remaining=21 → hard-blocked
    VendorReturnAgreement(
        material="MAT-CHEM-107",
        vendor="VEND-503",
        vendor_name="LubriTech Corp",
        min_return_qty=50.0,
        lead_time_days=5,
        has_agreement=True,
        purchase_order_ref="PO-2024-99901",
    ),
]
