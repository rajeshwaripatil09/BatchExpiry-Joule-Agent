"""Scoring engine — net risk quantity calculation and risk score formula."""

import logging
from datetime import date
from typing import Optional

from config import AgentConfig
from models import BatchRecord, BinInfo, DemandForecast, OpenOrder, RiskBatch

logger = logging.getLogger(__name__)

# Velocity class scores for W_BIN component
BIN_VELOCITY_SCORE = {"C": 100.0, "B": 50.0, "A": 0.0}

# Normalisation cap for days_to_expiry scoring (beyond this = low risk)
EXPIRY_SCORE_CAP_DAYS = 60


def is_residual_covered(
    batch: BatchRecord,
    open_orders: list[OpenOrder],
    config: AgentConfig,
) -> bool:
    """
    Returns True if the batch is already fully covered by confirmed orders
    AND the residual quantity is below both thresholds — i.e. skip this batch.
    """
    confirmed_qty = sum(o.confirmed_qty for o in open_orders if o.batch_number == batch.batch_number)
    residual_qty = max(0.0, batch.quantity - confirmed_qty)

    pct_threshold = batch.quantity * config.residual_qty_threshold
    abs_threshold = float(config.residual_qty_absolute)
    floor_threshold = max(pct_threshold, abs_threshold)

    return residual_qty < floor_threshold


def calculate_net_risk_qty(
    batch: BatchRecord,
    open_orders: list[OpenOrder],
    demand_forecast: Optional[DemandForecast],
    days_to_expiry: int,
    config: AgentConfig,
) -> tuple[float, float, float]:
    """
    Returns (net_risk_qty, projected_consumption, risk_qty).
    """
    confirmed_qty = sum(o.confirmed_qty for o in open_orders if o.batch_number == batch.batch_number)
    net_risk_qty = max(0.0, batch.quantity - confirmed_qty)

    if demand_forecast and demand_forecast.horizon_days > 0:
        daily_consumption = demand_forecast.total_qty / demand_forecast.horizon_days
        projected_consumption = daily_consumption * days_to_expiry
    else:
        projected_consumption = 0.0

    risk_qty = max(0.0, net_risk_qty - projected_consumption)
    return net_risk_qty, projected_consumption, risk_qty


def _normalise(value: float, min_val: float, max_val: float) -> float:
    """Normalise a value to 0–100 range."""
    if max_val <= min_val:
        return 0.0
    return max(0.0, min(100.0, (value - min_val) / (max_val - min_val) * 100.0))


def calculate_risk_score(
    risk_batch: RiskBatch,
    total_sku_stock: float,
    bin_info: Optional[BinInfo],
    config: AgentConfig,
) -> float:
    """
    Returns a risk score 1–100 using the weighted formula.

    Components:
    - W_EXPIRY: sooner expiry = higher score (normalised 0–EXPIRY_SCORE_CAP_DAYS, inverted)
    - W_EXPOSURE: risk_qty as % of total SKU stock
    - W_VALUE: financial exposure (risk_qty × unit_value), normalised against a large reference
    - W_BIN: C-bin = 100, B-bin = 50, A-bin = 0
    """
    # Expiry component: fewer days = higher score
    days = max(0, min(risk_batch.days_to_expiry, EXPIRY_SCORE_CAP_DAYS))
    expiry_score = (1.0 - days / EXPIRY_SCORE_CAP_DAYS) * 100.0 if EXPIRY_SCORE_CAP_DAYS > 0 else 100.0

    # Exposure component: risk_qty / total_sku_stock
    exposure_score = 0.0
    if total_sku_stock > 0:
        exposure_score = min(100.0, (risk_batch.risk_qty / total_sku_stock) * 100.0)

    # Value component: normalise financial exposure (cap at $100k for normalisation)
    financial_exposure = risk_batch.risk_qty * risk_batch.batch.unit_value
    value_score = _normalise(financial_exposure, 0.0, 100_000.0)

    # Bin velocity component
    velocity_class = bin_info.velocity_class if bin_info else "B"
    bin_score = BIN_VELOCITY_SCORE.get(velocity_class.upper(), 50.0)

    # Weighted sum
    score = (
        (config.w_expiry / 100.0) * expiry_score
        + (config.w_exposure / 100.0) * exposure_score
        + (config.w_value / 100.0) * value_score
        + (config.w_bin / 100.0) * bin_score
    )

    # Clamp to 1–100
    return max(1.0, min(100.0, score))


def build_risk_batch(
    batch: BatchRecord,
    today: date,
    open_orders: list[OpenOrder],
    demand_forecast: Optional[DemandForecast],
    total_sku_stock: float,
    bin_info: Optional[BinInfo],
    config: AgentConfig,
) -> Optional[RiskBatch]:
    """
    Build a RiskBatch from raw inputs. Returns None if batch should be excluded.
    """
    if batch.sled is None:
        logger.warning("Batch %s has no SLED — adding to exceptions", batch.batch_number)
        return None

    days_to_expiry = (batch.sled - today).days

    if days_to_expiry > config.risk_horizon_days:
        return None

    # Skip if hazmat and HAZMAT_EXCLUDE is set
    if config.hazmat_exclude and batch.batch_classification.hazmat_flag:
        logger.info("Batch %s excluded (hazmat)", batch.batch_number)
        return None

    net_risk_qty, projected_consumption, risk_qty = calculate_net_risk_qty(
        batch, open_orders, demand_forecast, days_to_expiry, config
    )

    if risk_qty <= config.min_risk_qty and config.min_risk_qty > 0:
        return None

    # Determine IBP staleness
    is_stale = demand_forecast.is_stale if demand_forecast else True
    confidence = "Low" if is_stale else ("High" if days_to_expiry <= 14 else "Medium")

    rb = RiskBatch(
        batch=batch,
        net_risk_qty=net_risk_qty,
        projected_consumption=projected_consumption,
        risk_qty=risk_qty,
        days_to_expiry=days_to_expiry,
        confidence=confidence,
        is_ibp_stale=is_stale,
    )
    rb.risk_score = calculate_risk_score(rb, total_sku_stock, bin_info, config)
    return rb
