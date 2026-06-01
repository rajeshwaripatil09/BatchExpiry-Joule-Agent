"""Tests for the report builder module."""

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from actions import evaluate_disposal, evaluate_markdown
from config import AgentConfig
from models import ActionRecommendation, BatchClassification, BatchRecord, RiskBatch
from report import build_report


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


def _make_risk_batch(batch_number="B001", material="MAT001", days=20, qty=50.0, score=80.0) -> RiskBatch:
    batch = BatchRecord(
        batch_number=batch_number,
        material=material,
        description="Perishable Item",
        plant="1000",
        storage_location="SL01",
        bin="WH-C-01",
        quantity=qty,
        uom="KG",
        unit_value=15.0,
        sled=date.today() + timedelta(days=days),
        batch_classification=BatchClassification(),
    )
    return RiskBatch(
        batch=batch,
        net_risk_qty=qty,
        projected_consumption=0.0,
        risk_qty=qty,
        days_to_expiry=days,
        risk_score=score,
        confidence="High",
    )


def test_report_contains_header():
    config = _make_config()
    rb = _make_risk_batch()
    report = build_report(
        run_timestamp=datetime(2026, 6, 1, 2, 0, 0),
        plants_covered=["1000"],
        total_batches_scanned=10,
        risk_batches_with_actions=[(rb, [])],
        exceptions=[],
        ibp_stale=False,
        config=config,
    )
    assert "BATCH EXPIRY RISK MANAGEMENT REPORT" in report
    assert "2026-06-01" in report
    assert "1000" in report
    assert "Total Batches Scanned" in report


def test_report_per_batch_block():
    config = _make_config()
    rb = _make_risk_batch()
    action = evaluate_markdown(rb, config)
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=5,
        risk_batches_with_actions=[(rb, [action] if action else [])],
        exceptions=[],
        ibp_stale=False,
        config=config,
    )
    assert "B001" in report
    assert "MAT001" in report
    assert "Perishable Item" in report
    assert "Score" in report


def test_report_summary_table():
    config = _make_config()
    rb = _make_risk_batch()
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=5,
        risk_batches_with_actions=[(rb, [])],
        exceptions=[],
        ibp_stale=False,
        config=config,
    )
    assert "Summary Action Table" in report
    assert "Batch #" in report
    assert "Risk Score" in report
    assert "Assigned To" in report


def test_report_exceptions_section():
    config = _make_config()
    exceptions = [{"batch_number": "B002", "material": "MAT002", "reason": "Missing SLED"}]
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=5,
        risk_batches_with_actions=[],
        exceptions=exceptions,
        ibp_stale=False,
        config=config,
    )
    assert "Exceptions" in report
    assert "B002" in report
    assert "Missing SLED" in report


def test_report_stale_ibp_warning():
    config = _make_config()
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=5,
        risk_batches_with_actions=[],
        exceptions=[],
        ibp_stale=True,
        config=config,
    )
    assert "STALE" in report.upper()


def test_report_draft_artefact_present():
    config = _make_config()
    rb = _make_risk_batch(days=10)
    action = evaluate_disposal(rb, config)
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=3,
        risk_batches_with_actions=[(rb, [action])],
        exceptions=[],
        ibp_stale=False,
        config=config,
    )
    assert "DRAFT" in report
    assert "REQUIRES HUMAN APPROVAL" in report


def test_report_no_at_risk_batches():
    config = _make_config()
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=20,
        risk_batches_with_actions=[],
        exceptions=[],
        ibp_stale=False,
        config=config,
    )
    assert "No at-risk batches" in report


def test_report_multiple_batches_sorted_by_score():
    config = _make_config()
    rb_high = _make_risk_batch(batch_number="B_HIGH", days=5, score=95.0)
    rb_low = _make_risk_batch(batch_number="B_LOW", days=55, score=25.0)
    # Pass in reverse order to verify report sorts correctly
    report = build_report(
        run_timestamp=datetime.utcnow(),
        plants_covered=["1000"],
        total_batches_scanned=10,
        risk_batches_with_actions=[(rb_high, []), (rb_low, [])],
        exceptions=[],
        ibp_stale=False,
        config=config,
    )
    assert report.index("B_HIGH") < report.index("B_LOW")
