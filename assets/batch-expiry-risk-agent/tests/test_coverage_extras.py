"""Additional targeted tests to improve coverage on scoring/actions edge cases."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from config import AgentConfig
from models import BatchClassification, BatchRecord, BinInfo, DemandForecast, RiskBatch, VendorReturnAgreement
from scoring import _normalise, build_risk_batch, calculate_net_risk_qty


def _make_config() -> AgentConfig:
    c = AgentConfig.__new__(AgentConfig)
    c.risk_horizon_days = 60
    c.demand_horizon_days = 90
    c.residual_qty_threshold = 0.10
    c.residual_qty_absolute = 50
    c.min_risk_qty = 5.0  # positive threshold
    c.min_score_threshold = 0  # allow all scores
    c.w_expiry = 40
    c.w_exposure = 30
    c.w_value = 20
    c.w_bin = 10
    c.min_shelf_life_post_transfer_days = 14
    c.transfer_buffer_days = 5
    c.markdown_enabled = True
    c.markdown_trigger_days = 30
    c.markdown_min_qty = 1
    c.md_tier_1 = 15
    c.md_tier_2 = 30
    c.md_tier_3 = 50
    c.rtv_min_days_remaining = 21
    c.rtv_escalation_threshold = 5000.0
    c.ibp_data_freshness_hours = 24
    c.hazmat_exclude = True
    c.currency = "USD"
    c.plants = "All"
    c.storage_types_in_scope = "All"
    c.action_types_enabled = [1, 2, 3, 4, 5]
    return c


def _make_batch(sled_days=30, qty=100.0) -> BatchRecord:
    return BatchRecord(
        batch_number="B001", material="MAT001", description="Test",
        plant="1000", storage_location="SL01", bin="WH-C-01",
        quantity=qty, uom="EA", unit_value=10.0,
        sled=date.today() + timedelta(days=sled_days),
        batch_classification=BatchClassification(),
    )


# ─── _normalise edge cases ────────────────────────────────────────────────────

def test_normalise_when_max_equals_min():
    """When max == min, normalise should return 0."""
    assert _normalise(5.0, 5.0, 5.0) == 0.0


def test_normalise_clamp_above_max():
    assert _normalise(200.0, 0.0, 100.0) == 100.0


def test_normalise_clamp_below_min():
    assert _normalise(-10.0, 0.0, 100.0) == 0.0


# ─── build_risk_batch — min_risk_qty filter (line 143) ───────────────────────

def test_build_risk_batch_below_min_risk_qty_returns_none():
    """Batches with risk_qty ≤ MIN_RISK_QTY should be excluded."""
    config = _make_config()
    config.min_risk_qty = 100.0  # higher than batch quantity
    batch = _make_batch(sled_days=30, qty=50.0)
    rb = build_risk_batch(batch, date.today(), [], None, 50.0, None, config)
    assert rb is None


def test_build_risk_batch_ibp_stale_confidence_low():
    """When no forecast provided, IBP is considered stale — confidence = Low."""
    config = _make_config()
    config.min_risk_qty = 0
    batch = _make_batch(sled_days=20)
    rb = build_risk_batch(batch, date.today(), [], None, 100.0, None, config)
    assert rb is not None
    assert rb.confidence == "Low"
    assert rb.is_ibp_stale is True


def test_build_risk_batch_with_stale_forecast_flag():
    """When forecast.is_stale=True, confidence should be Low."""
    config = _make_config()
    config.min_risk_qty = 0
    batch = _make_batch(sled_days=20)
    forecast = DemandForecast(material="MAT001", plant="1000", total_qty=90.0, horizon_days=90, is_stale=True)
    rb = build_risk_batch(batch, date.today(), [], forecast, 100.0, None, config)
    assert rb is not None
    assert rb.confidence == "Low"


def test_build_risk_batch_short_expiry_high_confidence():
    """Batch expiring in ≤ 14 days with fresh IBP data gets High confidence."""
    config = _make_config()
    config.min_risk_qty = 0
    batch = _make_batch(sled_days=10)
    forecast = DemandForecast(material="MAT001", plant="1000", total_qty=10.0, horizon_days=90, is_stale=False)
    rb = build_risk_batch(batch, date.today(), [], forecast, 100.0, None, config)
    assert rb is not None
    assert rb.confidence == "High"


# ─── actions — markdown min qty edge (line 148) ──────────────────────────────

def test_markdown_qty_at_minimum():
    """Batch with risk_qty exactly equal to MARKDOWN_MIN_QTY should NOT get markdown (> not >=)."""
    from actions import evaluate_markdown
    config = _make_config()
    config.markdown_min_qty = 10
    batch = _make_batch(sled_days=20)
    rb = RiskBatch(batch=batch, risk_qty=10.0, days_to_expiry=20, risk_score=70.0, confidence="High")
    result = evaluate_markdown(rb, config)
    assert result is None


def test_markdown_qty_above_minimum():
    from actions import evaluate_markdown
    config = _make_config()
    config.markdown_min_qty = 10
    batch = _make_batch(sled_days=20)
    rb = RiskBatch(batch=batch, risk_qty=11.0, days_to_expiry=20, risk_score=70.0, confidence="High")
    result = evaluate_markdown(rb, config)
    assert result is not None


# ─── calculate_net_risk_qty — zero demand horizon guard ──────────────────────

def test_net_risk_qty_zero_horizon_days():
    """When horizon_days = 0, no division should occur."""
    config = _make_config()
    batch = _make_batch(qty=100.0)
    forecast = DemandForecast(material="MAT001", plant="1000", total_qty=0.0, horizon_days=0)
    net, projected, risk = calculate_net_risk_qty(batch, [], forecast, 30, config)
    assert net == 100.0
    assert projected == 0.0
    assert risk == 100.0


# ─── RiskBatch.total_exposure property ───────────────────────────────────────

def test_risk_batch_total_exposure():
    batch = _make_batch(qty=50.0)
    batch.unit_value = 20.0
    rb = RiskBatch(batch=batch, risk_qty=30.0, days_to_expiry=25, risk_score=60.0, confidence="Medium")
    assert rb.total_exposure == 600.0


# ─── VendorReturnAgreement defaults ──────────────────────────────────────────

def test_vendor_agreement_defaults():
    va = VendorReturnAgreement(material="MAT001", vendor="V001")
    assert va.has_agreement is False
    assert va.min_return_qty == 0
    assert va.lead_time_days == 0


# ─── Actions: redistribution - no higher velocity bins ───────────────────────

def test_redistribution_no_available_bins():
    from actions import evaluate_redistribution
    config = _make_config()
    batch = _make_batch(sled_days=30)
    rb = RiskBatch(batch=batch, risk_qty=100.0, days_to_expiry=30, risk_score=70.0, confidence="High")
    # Only C-bins available — no higher velocity
    bins = [BinInfo("WH-C-02", "1000", "ST1", "C", "AMBIENT")]
    result = evaluate_redistribution(rb, bins, config)
    assert result is None


def test_redistribution_different_plant_ignored():
    from actions import evaluate_redistribution
    config = _make_config()
    batch = _make_batch(sled_days=30)
    rb = RiskBatch(batch=batch, risk_qty=100.0, days_to_expiry=30, risk_score=70.0, confidence="High")
    # A-bin but different plant
    bins = [BinInfo("WH-A-01", "2000", "ST1", "A", "AMBIENT")]
    result = evaluate_redistribution(rb, bins, config)
    assert result is None
