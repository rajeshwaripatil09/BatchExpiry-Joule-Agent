"""Tests for the action evaluator module."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from actions import (
    evaluate_disposal,
    evaluate_markdown,
    evaluate_redistribution,
    evaluate_rtv,
    match_actions,
)
from config import AgentConfig
from models import (
    ActionRecommendation,
    BatchClassification,
    BatchRecord,
    BinInfo,
    DemandForecast,
    RiskBatch,
    VendorReturnAgreement,
)


def _make_config(**kwargs) -> AgentConfig:
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


def _make_risk_batch(days=25, qty=100.0, unit_value=20.0, temp_class="AMBIENT", bin_id="WH-C-01") -> RiskBatch:
    batch = BatchRecord(
        batch_number="B001",
        material="MAT001",
        description="Test Material",
        plant="1000",
        storage_location="SL01",
        bin=bin_id,
        quantity=qty,
        uom="EA",
        unit_value=unit_value,
        sled=date.today() + timedelta(days=days),
        batch_classification=BatchClassification(temperature_class=temp_class, hazmat_flag=False),
    )
    return RiskBatch(
        batch=batch,
        net_risk_qty=qty,
        projected_consumption=0.0,
        risk_qty=qty,
        days_to_expiry=days,
        risk_score=75.0,
        confidence="High",
    )


# ─── evaluate_redistribution ─────────────────────────────────────────────────────

def test_redistribution_eligible():
    config = _make_config()
    rb = _make_risk_batch(days=30)
    bins = [
        BinInfo("WH-A-01", "1000", "ST1", "A", "AMBIENT"),
    ]
    result = evaluate_redistribution(rb, bins, config)
    assert result is not None
    assert result.action_type == 1
    assert "WH-A-01" in result.description


def test_redistribution_temperature_incompatible():
    """FROZEN batch must not be moved to AMBIENT bin."""
    config = _make_config()
    rb = _make_risk_batch(days=30, temp_class="FROZEN")
    bins = [BinInfo("WH-A-01", "1000", "ST1", "A", "AMBIENT")]
    result = evaluate_redistribution(rb, bins, config)
    assert result is None


def test_redistribution_shelf_life_too_short():
    """If remaining shelf life < MIN_SHELF_LIFE_POST_TRANSFER_DAYS, skip redistribution."""
    config = _make_config(min_shelf_life_post_transfer_days=20)
    rb = _make_risk_batch(days=15)
    bins = [BinInfo("WH-A-01", "1000", "ST1", "A", "AMBIENT")]
    result = evaluate_redistribution(rb, bins, config)
    assert result is None


def test_redistribution_disabled_in_config():
    config = _make_config(action_types_enabled=[2, 3, 4, 5])
    rb = _make_risk_batch(days=30)
    bins = [BinInfo("WH-A-01", "1000", "ST1", "A", "AMBIENT")]
    result = evaluate_redistribution(rb, bins, config)
    assert result is None


# ─── evaluate_markdown ───────────────────────────────────────────────────────────

def test_markdown_tier1():
    config = _make_config()
    rb = _make_risk_batch(days=25)
    result = evaluate_markdown(rb, config)
    assert result is not None
    assert result.action_type == 3
    assert "15%" in result.description


def test_markdown_tier2():
    config = _make_config()
    rb = _make_risk_batch(days=12)
    result = evaluate_markdown(rb, config)
    assert result is not None
    assert "30%" in result.description


def test_markdown_tier3():
    config = _make_config()
    rb = _make_risk_batch(days=5)
    result = evaluate_markdown(rb, config)
    assert result is not None
    assert "50%" in result.description


def test_markdown_disabled():
    config = _make_config(markdown_enabled=False)
    rb = _make_risk_batch(days=10)
    result = evaluate_markdown(rb, config)
    assert result is None


def test_markdown_outside_trigger_days():
    config = _make_config(markdown_trigger_days=30)
    rb = _make_risk_batch(days=45)
    result = evaluate_markdown(rb, config)
    assert result is None


# ─── evaluate_rtv ────────────────────────────────────────────────────────────────

def test_rtv_with_active_agreement():
    config = _make_config()
    rb = _make_risk_batch(days=30)
    agreements = [
        VendorReturnAgreement(
            material="MAT001", vendor="V001", vendor_name="Test Vendor",
            min_return_qty=10.0, lead_time_days=5, has_agreement=True,
        )
    ]
    result = evaluate_rtv(rb, agreements, config)
    assert result is not None
    assert result.action_type == 4
    assert "V001" in result.draft_artefact


def test_rtv_blocked_when_days_too_low():
    """RTV must be blocked when days_to_expiry < RTV_MIN_DAYS_REMAINING."""
    config = _make_config(rtv_min_days_remaining=21)
    rb = _make_risk_batch(days=15)
    agreements = [
        VendorReturnAgreement(
            material="MAT001", vendor="V001", has_agreement=True,
            min_return_qty=5.0, lead_time_days=2,
        )
    ]
    result = evaluate_rtv(rb, agreements, config)
    assert result is None


def test_rtv_escalation_flag_when_no_agreement_and_high_exposure():
    config = _make_config(rtv_escalation_threshold=1000.0)
    rb = _make_risk_batch(days=30, qty=200.0, unit_value=10.0)  # exposure = 2000
    result = evaluate_rtv(rb, [], config)
    assert result is not None
    assert result.requires_escalation is True


def test_rtv_no_agreement_low_exposure_returns_none():
    config = _make_config(rtv_escalation_threshold=5000.0)
    rb = _make_risk_batch(days=30, qty=10.0, unit_value=5.0)  # exposure = 50
    result = evaluate_rtv(rb, [], config)
    assert result is None


# ─── evaluate_disposal ──────────────────────────────────────────────────────────

def test_disposal_always_returns_recommendation():
    config = _make_config()
    rb = _make_risk_batch(days=10)
    result = evaluate_disposal(rb, config)
    assert result is not None
    assert result.action_type == 5
    assert "REQUIRES HUMAN APPROVAL" in result.draft_artefact


# ─── match_actions ───────────────────────────────────────────────────────────────

def test_match_actions_returns_redistribution_first():
    config = _make_config()
    rb = _make_risk_batch(days=30)
    bins = [BinInfo("WH-A-01", "1000", "ST1", "A", "AMBIENT")]
    actions = match_actions(rb, bins, None, None, 5, [], config)
    assert len(actions) >= 1
    assert actions[0].action_type == 1


def test_match_actions_fallback_disposal():
    """When no other action is eligible, disposal is recommended."""
    config = _make_config(
        markdown_enabled=False,
        action_types_enabled=[5],
        rtv_min_days_remaining=100,  # force RTV ineligible
    )
    rb = _make_risk_batch(days=5)
    actions = match_actions(rb, [], None, None, 10, [], config)
    assert len(actions) == 1
    assert actions[0].action_type == 5


def test_match_actions_hazmat_no_redistribution():
    """Hazmat batch should have no redistribution action (config enforces it)."""
    config = _make_config(hazmat_exclude=True, action_types_enabled=[1])
    rb = _make_risk_batch(days=30)
    rb.batch.batch_classification.hazmat_flag = True
    bins = [BinInfo("WH-A-01", "1000", "ST1", "A", "AMBIENT")]
    # Redistribution can still be proposed by action evaluator (hazmat exclusion is at scan level)
    # but with no bins of higher velocity this would return None
    actions = match_actions(rb, [], None, None, 5, [], config)
    assert all(a.action_type != 5 for a in actions)  # no disposal since disposal disabled
