"""Tests for the scoring engine."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from config import AgentConfig
from models import (
    BatchClassification,
    BatchRecord,
    BinInfo,
    DemandForecast,
    OpenOrder,
    RiskBatch,
)
from scoring import (
    build_risk_batch,
    calculate_net_risk_qty,
    calculate_risk_score,
    is_residual_covered,
)


def _make_config(**kwargs) -> AgentConfig:
    import config as cfg_module
    cfg_module._config = None
    c = AgentConfig.__new__(AgentConfig)
    c.risk_horizon_days = 60
    c.demand_horizon_days = 90
    c.residual_qty_threshold = 0.10
    c.residual_qty_absolute = 50
    c.min_risk_qty = 0
    c.min_score_threshold = 20
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
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def _make_batch(sled_days=30, qty=100.0, unit_value=10.0, hazmat=False) -> BatchRecord:
    return BatchRecord(
        batch_number="B001",
        material="MAT001",
        description="Test Material",
        plant="1000",
        storage_location="0001",
        bin="WH-C-01",
        quantity=qty,
        uom="EA",
        unit_value=unit_value,
        sled=date.today() + timedelta(days=sled_days),
        batch_classification=BatchClassification(
            storage_conditions="STANDARD",
            temperature_class="AMBIENT",
            hazmat_flag=hazmat,
        ),
    )


# ─── is_residual_covered tests ─────────────────────────────────────────────────

def test_residual_not_covered_no_orders():
    config = _make_config()
    batch = _make_batch(qty=100.0)
    assert is_residual_covered(batch, [], config) is False


def test_residual_covered_fully_ordered():
    config = _make_config()
    batch = _make_batch(qty=100.0)
    orders = [OpenOrder(batch_number="B001", material="MAT001", plant="1000", confirmed_qty=98.0, order_type="SO")]
    # residual = 2 < 10% of 100 = 10 and < abs threshold 50 => covered
    assert is_residual_covered(batch, orders, config) is True


def test_residual_not_covered_large_remaining():
    config = _make_config()
    batch = _make_batch(qty=100.0)
    orders = [OpenOrder(batch_number="B001", material="MAT001", plant="1000", confirmed_qty=40.0, order_type="SO")]
    # residual = 60 > 10 and > 50 => not covered
    assert is_residual_covered(batch, orders, config) is False


# ─── calculate_net_risk_qty tests ────────────────────────────────────────────────

def test_net_risk_qty_no_orders_no_forecast():
    config = _make_config()
    batch = _make_batch(qty=100.0)
    net, projected, risk = calculate_net_risk_qty(batch, [], None, 30, config)
    assert net == 100.0
    assert projected == 0.0
    assert risk == 100.0


def test_net_risk_qty_with_orders():
    config = _make_config()
    batch = _make_batch(qty=100.0)
    orders = [OpenOrder(batch_number="B001", material="MAT001", plant="1000", confirmed_qty=30.0, order_type="SO")]
    net, projected, risk = calculate_net_risk_qty(batch, orders, None, 30, config)
    assert net == 70.0
    assert risk == 70.0


def test_net_risk_qty_with_forecast_consumption():
    config = _make_config()
    batch = _make_batch(qty=100.0)
    forecast = DemandForecast(material="MAT001", plant="1000", total_qty=90.0, horizon_days=90)
    # daily_consumption = 90/90 = 1.0; over 30 days = 30
    net, projected, risk = calculate_net_risk_qty(batch, [], forecast, 30, config)
    assert net == 100.0
    assert projected == 30.0
    assert risk == 70.0


def test_net_risk_qty_zero_floored():
    """risk_qty is floored at 0 when consumption > net_risk_qty."""
    config = _make_config()
    batch = _make_batch(qty=10.0)
    forecast = DemandForecast(material="MAT001", plant="1000", total_qty=900.0, horizon_days=90)
    net, projected, risk = calculate_net_risk_qty(batch, [], forecast, 30, config)
    assert risk == 0.0


# ─── calculate_risk_score tests ─────────────────────────────────────────────────

def test_risk_score_range():
    config = _make_config()
    batch = _make_batch(qty=100.0, unit_value=50.0)
    bin_info = BinInfo(bin_id="WH-C-01", plant="1000", storage_type="ST1", velocity_class="C", temperature_zone="AMBIENT")
    rb = RiskBatch(batch=batch, net_risk_qty=100.0, projected_consumption=0.0, risk_qty=100.0, days_to_expiry=10, risk_score=0.0, confidence="High")
    score = calculate_risk_score(rb, 100.0, bin_info, config)
    assert 1.0 <= score <= 100.0


def test_risk_score_c_bin_higher_than_a_bin():
    config = _make_config()
    batch = _make_batch(qty=50.0, unit_value=20.0)
    rb = RiskBatch(batch=batch, net_risk_qty=50.0, risk_qty=50.0, days_to_expiry=20, risk_score=0.0, confidence="Medium")
    bin_c = BinInfo(bin_id="C01", plant="1000", storage_type="ST1", velocity_class="C", temperature_zone="AMBIENT")
    bin_a = BinInfo(bin_id="A01", plant="1000", storage_type="ST1", velocity_class="A", temperature_zone="AMBIENT")
    score_c = calculate_risk_score(rb, 100.0, bin_c, config)
    score_a = calculate_risk_score(rb, 100.0, bin_a, config)
    assert score_c > score_a


# ─── build_risk_batch tests ──────────────────────────────────────────────────────

def test_build_risk_batch_returns_none_outside_horizon():
    config = _make_config(risk_horizon_days=60)
    batch = _make_batch(sled_days=90)  # outside horizon
    rb = build_risk_batch(batch, date.today(), [], None, 100.0, None, config)
    assert rb is None


def test_build_risk_batch_hazmat_excluded():
    config = _make_config(hazmat_exclude=True)
    batch = _make_batch(sled_days=10, hazmat=True)
    rb = build_risk_batch(batch, date.today(), [], None, 100.0, None, config)
    assert rb is None


def test_build_risk_batch_no_sled_returns_none():
    config = _make_config()
    batch = _make_batch(sled_days=10)
    batch.sled = None
    rb = build_risk_batch(batch, date.today(), [], None, 100.0, None, config)
    assert rb is None


def test_build_risk_batch_in_horizon():
    config = _make_config()
    batch = _make_batch(sled_days=30)
    rb = build_risk_batch(batch, date.today(), [], None, 100.0, None, config)
    assert rb is not None
    assert rb.days_to_expiry == 30
    assert rb.risk_score >= 1.0
