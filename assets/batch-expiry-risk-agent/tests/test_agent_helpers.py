"""Additional tests for agent parsing helpers and edge cases in agent.py."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from agent import (
    _parse_batch_scan_response,
    _parse_demand_forecasts,
    _parse_open_orders,
    _parse_vendor_agreements,
)
from config import AgentConfig


def _make_config() -> AgentConfig:
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
    return c


def test_parse_batch_scan_empty_response():
    config = _make_config()
    batches, exceptions, bins = _parse_batch_scan_response("No batches found.", config)
    assert isinstance(batches, list)
    assert isinstance(exceptions, list)
    assert isinstance(bins, list)


def test_parse_open_orders_empty():
    orders = _parse_open_orders("No open orders.")
    assert isinstance(orders, list)


def test_parse_demand_forecasts_empty():
    config = _make_config()
    forecasts, is_stale = _parse_demand_forecasts("No forecast data.", config)
    assert isinstance(forecasts, dict)
    assert isinstance(is_stale, bool)


def test_parse_vendor_agreements_empty():
    agreements = _parse_vendor_agreements("No vendor agreements found.")
    assert isinstance(agreements, list)


def test_agent_response_dataclass():
    from agent import AgentResponse
    r = AgentResponse(status="completed", message="Test report content")
    assert r.status == "completed"
    assert r.message == "Test report content"


def test_agent_model_name():
    from agent import get_model_name
    name = get_model_name()
    assert isinstance(name, str)
    assert len(name) > 0


def test_agent_temperature():
    from agent import get_temperature
    temp = get_temperature()
    assert isinstance(temp, float)
    assert 0.0 <= temp <= 1.0


def test_agent_system_prompt_contains_rules():
    from agent import get_system_prompt
    prompt = get_system_prompt()
    assert "NEVER" in prompt
    assert "human" in prompt.lower()
    assert "SAP" in prompt


def test_agent_class_supported_content_types():
    from agent import SampleAgent
    assert "text" in SampleAgent.SUPPORTED_CONTENT_TYPES


def test_channel_reallocation_disabled():
    """evaluate_channel_reallocation returns None when action type 2 disabled."""
    from actions import evaluate_channel_reallocation
    from datetime import date, timedelta
    from models import BatchClassification, BatchRecord, DemandForecast, RiskBatch

    config = _make_config()
    config.action_types_enabled = [1, 3, 4, 5]  # disable action 2

    batch = BatchRecord(
        batch_number="B001", material="MAT001", description="Test",
        plant="1000", storage_location="SL01", bin="BIN1",
        quantity=100.0, uom="EA", unit_value=10.0,
        sled=date.today() + timedelta(days=25),
        batch_classification=BatchClassification(),
    )
    rb = RiskBatch(batch=batch, risk_qty=100.0, days_to_expiry=25, risk_score=70.0, confidence="High")
    forecast = DemandForecast(material="MAT001", plant="2000", total_qty=500.0, horizon_days=90, is_stale=False)
    result = evaluate_channel_reallocation(rb, forecast, "2000", 3, config)
    assert result is None


def test_channel_reallocation_stale_forecast():
    """evaluate_channel_reallocation returns None when IBP data is stale."""
    from actions import evaluate_channel_reallocation
    from datetime import date, timedelta
    from models import BatchClassification, BatchRecord, DemandForecast, RiskBatch

    config = _make_config()
    batch = BatchRecord(
        batch_number="B001", material="MAT001", description="Test",
        plant="1000", storage_location="SL01", bin="BIN1",
        quantity=100.0, uom="EA", unit_value=10.0,
        sled=date.today() + timedelta(days=25),
        batch_classification=BatchClassification(),
    )
    rb = RiskBatch(batch=batch, risk_qty=100.0, days_to_expiry=25, risk_score=70.0, confidence="Low")
    forecast = DemandForecast(material="MAT001", plant="2000", total_qty=500.0, horizon_days=90, is_stale=True)
    result = evaluate_channel_reallocation(rb, forecast, "2000", 3, config)
    assert result is None


def test_channel_reallocation_transfer_infeasible():
    """evaluate_channel_reallocation returns None when transfer lead time exceeds feasibility window."""
    from actions import evaluate_channel_reallocation
    from datetime import date, timedelta
    from models import BatchClassification, BatchRecord, DemandForecast, RiskBatch

    config = _make_config()
    config.transfer_buffer_days = 5
    batch = BatchRecord(
        batch_number="B001", material="MAT001", description="Test",
        plant="1000", storage_location="SL01", bin="BIN1",
        quantity=100.0, uom="EA", unit_value=10.0,
        sled=date.today() + timedelta(days=10),
        batch_classification=BatchClassification(),
    )
    rb = RiskBatch(batch=batch, risk_qty=100.0, days_to_expiry=10, risk_score=70.0, confidence="Medium")
    forecast = DemandForecast(material="MAT001", plant="2000", total_qty=500.0, horizon_days=90, is_stale=False)
    # Transfer lead time 8 >= feasibility window (10 - 5 = 5)
    result = evaluate_channel_reallocation(rb, forecast, "2000", 8, config)
    assert result is None


def test_channel_reallocation_eligible():
    """evaluate_channel_reallocation returns recommendation when eligible."""
    from actions import evaluate_channel_reallocation
    from datetime import date, timedelta
    from models import BatchClassification, BatchRecord, DemandForecast, RiskBatch

    config = _make_config()
    config.transfer_buffer_days = 5
    batch = BatchRecord(
        batch_number="B001", material="MAT001", description="Test",
        plant="1000", storage_location="SL01", bin="BIN1",
        quantity=100.0, uom="EA", unit_value=10.0,
        sled=date.today() + timedelta(days=30),
        batch_classification=BatchClassification(),
    )
    rb = RiskBatch(batch=batch, risk_qty=100.0, days_to_expiry=30, risk_score=70.0, confidence="Medium")
    forecast = DemandForecast(material="MAT001", plant="2000", total_qty=500.0, horizon_days=90, is_stale=False)
    # Lead time 3 < feasibility window (30 - 5 = 25)
    result = evaluate_channel_reallocation(rb, forecast, "2000", 3, config)
    assert result is not None
    assert result.action_type == 2
    assert "2000" in result.description


def test_rtv_ineligible_qty_below_min():
    """RTV returns None when risk_qty < vendor min_return_qty."""
    from actions import evaluate_rtv
    from datetime import date, timedelta
    from models import BatchClassification, BatchRecord, RiskBatch, VendorReturnAgreement

    config = _make_config()
    batch = BatchRecord(
        batch_number="B001", material="MAT001", description="Test",
        plant="1000", storage_location="SL01", bin="BIN1",
        quantity=5.0, uom="EA", unit_value=10.0,
        sled=date.today() + timedelta(days=30),
        batch_classification=BatchClassification(),
    )
    rb = RiskBatch(batch=batch, risk_qty=5.0, days_to_expiry=30, risk_score=70.0, confidence="High")
    agreements = [
        VendorReturnAgreement(material="MAT001", vendor="V001", has_agreement=True, min_return_qty=100.0, lead_time_days=3)
    ]
    result = evaluate_rtv(rb, agreements, config)
    assert result is None
