"""Action evaluator — matches at-risk batches to eligible action types."""

import logging
from datetime import date

from config import AgentConfig
from models import ActionRecommendation, BinInfo, DemandForecast, RiskBatch, VendorReturnAgreement

logger = logging.getLogger(__name__)


def _temperature_compatible(batch_temp_class: str, bin_temp_zone: str) -> bool:
    """Check whether the batch's temperature class is compatible with a target bin's temperature zone."""
    # Normalise to uppercase for comparison
    b = batch_temp_class.upper()
    z = bin_temp_zone.upper()
    if b == z:
        return True
    # FROZEN items can go to FROZEN zones only
    if b == "FROZEN":
        return z == "FROZEN"
    # CHILLED items can go to CHILLED or FROZEN zones
    if b == "CHILLED":
        return z in ("CHILLED", "FROZEN")
    # AMBIENT items cannot go to temperature-controlled zones
    return z == "AMBIENT" or z == ""


def evaluate_redistribution(
    risk_batch: RiskBatch,
    bins: list[BinInfo],
    config: AgentConfig,
) -> ActionRecommendation | None:
    """
    ACTION 1: Redistribution to a higher-velocity bin at the same plant.
    Eligibility: higher velocity bin at same plant, temperature compatible,
                 remaining shelf life after transfer ≥ MIN_SHELF_LIFE_POST_TRANSFER_DAYS.
    """
    if 1 not in config.action_types_enabled:
        return None

    if risk_batch.days_to_expiry < config.min_shelf_life_post_transfer_days:
        return None

    batch_velocity = "C"  # assume current bin is C if unknown
    batch_temp = risk_batch.batch.batch_classification.temperature_class or "AMBIENT"

    velocity_order = {"A": 2, "B": 1, "C": 0}
    current_level = velocity_order.get(batch_velocity, 0)

    compatible_higher = [
        b for b in bins
        if b.plant == risk_batch.batch.plant
        and velocity_order.get(b.velocity_class.upper(), 0) > current_level
        and _temperature_compatible(batch_temp, b.temperature_zone)
        and b.bin_id != risk_batch.batch.bin
    ]

    if not compatible_higher:
        return None

    target_bin = sorted(compatible_higher, key=lambda b: velocity_order.get(b.velocity_class.upper(), 0), reverse=True)[0]

    draft = (
        f"[DRAFT — REQUIRES HUMAN APPROVAL]\n"
        f"Transfer Order Proposal:\n"
        f"  Source Bin: {risk_batch.batch.bin} | Target Bin: {target_bin.bin_id} ({target_bin.velocity_class}-velocity)\n"
        f"  Plant: {risk_batch.batch.plant} | Storage Location: {risk_batch.batch.storage_location}\n"
        f"  Material: {risk_batch.batch.material} | Batch: {risk_batch.batch.batch_number}\n"
        f"  Quantity: {risk_batch.risk_qty:.2f} {risk_batch.batch.uom}\n"
        f"  Rationale: Move to higher-velocity bin to accelerate FEFO consumption before SLED.\n"
        f"  Estimated remaining shelf life post-transfer: {risk_batch.days_to_expiry} days."
    )

    return ActionRecommendation(
        action_type=1,
        action_label=ActionRecommendation.ACTION_LABELS[1],
        description=f"Move {risk_batch.risk_qty:.0f} {risk_batch.batch.uom} from bin {risk_batch.batch.bin} to {target_bin.bin_id} ({target_bin.velocity_class}-velocity, {target_bin.temperature_zone})",
        draft_artefact=draft,
        eligible=True,
    )


def evaluate_channel_reallocation(
    risk_batch: RiskBatch,
    demand_forecast: DemandForecast | None,
    alternative_plant: str | None,
    transfer_lead_time_days: int,
    config: AgentConfig,
) -> ActionRecommendation | None:
    """
    ACTION 2: Channel reallocation — transfer to a plant/DC with higher near-term demand.
    Eligibility: IBP shows higher demand at an alternative location,
                 transfer lead time < days_to_expiry − TRANSFER_BUFFER_DAYS.
    """
    if 2 not in config.action_types_enabled:
        return None

    if demand_forecast is None or demand_forecast.is_stale:
        return None

    if alternative_plant is None:
        return None

    feasibility_window = risk_batch.days_to_expiry - config.transfer_buffer_days
    if transfer_lead_time_days >= feasibility_window:
        return None

    draft = (
        f"[DRAFT — REQUIRES HUMAN APPROVAL]\n"
        f"Inter-Plant Transfer Proposal:\n"
        f"  Source Plant: {risk_batch.batch.plant} | Destination Plant: {alternative_plant}\n"
        f"  Material: {risk_batch.batch.material} | Batch: {risk_batch.batch.batch_number}\n"
        f"  Quantity: {risk_batch.risk_qty:.2f} {risk_batch.batch.uom}\n"
        f"  IBP Demand Reference: Consensus demand at {alternative_plant} — {demand_forecast.total_qty:.0f} {risk_batch.batch.uom} over {demand_forecast.horizon_days} days.\n"
        f"  Transfer Lead Time: {transfer_lead_time_days} days | Days to Expiry: {risk_batch.days_to_expiry} days.\n"
        f"  Rationale: Reallocate to higher-demand channel before SLED."
    )

    return ActionRecommendation(
        action_type=2,
        action_label=ActionRecommendation.ACTION_LABELS[2],
        description=f"Transfer {risk_batch.risk_qty:.0f} {risk_batch.batch.uom} from plant {risk_batch.batch.plant} to {alternative_plant} (IBP demand: {demand_forecast.total_qty:.0f} {risk_batch.batch.uom}/{demand_forecast.horizon_days}d)",
        draft_artefact=draft,
        eligible=True,
    )


def evaluate_markdown(
    risk_batch: RiskBatch,
    config: AgentConfig,
) -> ActionRecommendation | None:
    """
    ACTION 3: Markdown / price promotion.
    Eligibility: MARKDOWN_ENABLED=True, days_to_expiry ≤ MARKDOWN_TRIGGER_DAYS,
                 risk_qty > MARKDOWN_MIN_QTY.
    """
    if 3 not in config.action_types_enabled:
        return None

    if not config.markdown_enabled:
        return None

    if risk_batch.days_to_expiry > config.markdown_trigger_days:
        return None

    if risk_batch.risk_qty <= config.markdown_min_qty:
        return None

    # Tiered markdown percentage
    if risk_batch.days_to_expiry <= 7:
        pct = config.md_tier_3
        tier_label = f"Tier 3 (≤7 days)"
    elif risk_batch.days_to_expiry <= 14:
        pct = config.md_tier_2
        tier_label = f"Tier 2 (≤14 days)"
    else:
        pct = config.md_tier_1
        tier_label = f"Tier 1 (≤30 days)"

    draft = (
        f"[DRAFT — REQUIRES HUMAN APPROVAL]\n"
        f"Markdown Event Proposal ({tier_label} — {pct}% discount):\n"
        f"  Material: {risk_batch.batch.material} — {risk_batch.batch.description}\n"
        f"  Batch: {risk_batch.batch.batch_number} | Plant: {risk_batch.batch.plant}\n"
        f"  Quantity: {risk_batch.risk_qty:.2f} {risk_batch.batch.uom}\n"
        f"  SLED: {risk_batch.batch.sled} ({risk_batch.days_to_expiry} days remaining)\n"
        f"  Suggested Markdown: {pct}% off standard price\n"
        f"  Event Description: Short-dated stock clearance for {risk_batch.batch.description}. "
        f"Apply {pct}% markdown to move {risk_batch.risk_qty:.0f} {risk_batch.batch.uom} "
        f"before SLED {risk_batch.batch.sled}. Coordinate with pricing team for system update."
    )

    return ActionRecommendation(
        action_type=3,
        action_label=ActionRecommendation.ACTION_LABELS[3],
        description=f"{pct}% markdown ({tier_label}) on {risk_batch.risk_qty:.0f} {risk_batch.batch.uom} — SLED {risk_batch.batch.sled}",
        draft_artefact=draft,
        eligible=True,
    )


def evaluate_rtv(
    risk_batch: RiskBatch,
    vendor_agreements: list[VendorReturnAgreement],
    config: AgentConfig,
) -> ActionRecommendation | None:
    """
    ACTION 4: Return to vendor (RTV).
    Eligibility: active agreement exists, days_to_expiry ≥ RTV_MIN_DAYS_REMAINING,
                 quantity ≥ vendor's min_return_qty.
    Hard constraint: NEVER recommend RTV if days_to_expiry < RTV_MIN_DAYS_REMAINING.
    """
    if 4 not in config.action_types_enabled:
        return None

    # Hard constraint check — flag for disposal instead
    if risk_batch.days_to_expiry < config.rtv_min_days_remaining:
        logger.info(
            "Batch %s: RTV blocked (days_to_expiry=%d < rtv_min_days_remaining=%d), flagging for disposal",
            risk_batch.batch.batch_number,
            risk_batch.days_to_expiry,
            config.rtv_min_days_remaining,
        )
        return None

    # Find matching agreement
    matching = [
        a for a in vendor_agreements
        if a.material == risk_batch.batch.material
        and a.has_agreement
        and risk_batch.risk_qty >= a.min_return_qty
    ]

    financial_exposure = risk_batch.total_exposure

    if not matching:
        # Check escalation threshold
        if financial_exposure >= config.rtv_escalation_threshold:
            draft = (
                f"[DRAFT — REQUIRES HUMAN APPROVAL]\n"
                f"⚠️  RTV Escalation Flag — No active return agreement found.\n"
                f"  Financial Exposure: {financial_exposure:,.2f} {config.currency} exceeds escalation threshold of {config.rtv_escalation_threshold:,.2f} {config.currency}.\n"
                f"  Material: {risk_batch.batch.material} | Batch: {risk_batch.batch.batch_number}\n"
                f"  Quantity: {risk_batch.risk_qty:.2f} {risk_batch.batch.uom} | SLED: {risk_batch.batch.sled}\n"
                f"  Recommendation: Initiate manual vendor negotiation for return authorisation."
            )
            return ActionRecommendation(
                action_type=4,
                action_label=ActionRecommendation.ACTION_LABELS[4],
                description=f"No RTV agreement — manual negotiation required (exposure: {financial_exposure:,.2f} {config.currency} ≥ threshold)",
                draft_artefact=draft,
                eligible=True,
                requires_escalation=True,
            )
        return None

    agreement = matching[0]
    from datetime import date, timedelta
    proposed_return_date = date.today() + timedelta(days=agreement.lead_time_days + 2)

    draft = (
        f"[DRAFT — REQUIRES HUMAN APPROVAL]\n"
        f"Return to Vendor Request:\n"
        f"  Vendor: {agreement.vendor} — {agreement.vendor_name}\n"
        f"  Material: {risk_batch.batch.material} | Batch: {risk_batch.batch.batch_number}\n"
        f"  Quantity: {risk_batch.risk_qty:.2f} {risk_batch.batch.uom}\n"
        f"  PO Reference: {agreement.purchase_order_ref or 'To be assigned'}\n"
        f"  Reason Code: SHELF_LIFE_RISK\n"
        f"  SLED: {risk_batch.batch.sled} ({risk_batch.days_to_expiry} days remaining)\n"
        f"  Proposed Return Date: {proposed_return_date}\n"
        f"  Vendor Lead Time: {agreement.lead_time_days} days\n"
        f"  Minimum Return Qty (vendor): {agreement.min_return_qty} {risk_batch.batch.uom}"
    )

    return ActionRecommendation(
        action_type=4,
        action_label=ActionRecommendation.ACTION_LABELS[4],
        description=f"Return {risk_batch.risk_qty:.0f} {risk_batch.batch.uom} to vendor {agreement.vendor} (agreement confirmed, proposed return {proposed_return_date})",
        draft_artefact=draft,
        eligible=True,
    )


def evaluate_disposal(
    risk_batch: RiskBatch,
    config: AgentConfig,
) -> ActionRecommendation:
    """
    ACTION 5: Quality hold / disposal — last resort.
    Always eligible; only recommended when no other action is feasible.
    """
    write_off_estimate = risk_batch.total_exposure

    draft = (
        f"[DRAFT — REQUIRES HUMAN APPROVAL]\n"
        f"QM Notification — Disposal Recommendation:\n"
        f"  Material: {risk_batch.batch.material} — {risk_batch.batch.description}\n"
        f"  Batch: {risk_batch.batch.batch_number} | Plant: {risk_batch.batch.plant} | Bin: {risk_batch.batch.bin}\n"
        f"  Quantity: {risk_batch.risk_qty:.2f} {risk_batch.batch.uom}\n"
        f"  SLED: {risk_batch.batch.sled} ({risk_batch.days_to_expiry} days remaining)\n"
        f"  Financial Write-Off Estimate: {write_off_estimate:,.2f} {config.currency}\n"
        f"  Recommendation: Place batch on quality hold and initiate disposal process per local policy."
    )

    return ActionRecommendation(
        action_type=5,
        action_label=ActionRecommendation.ACTION_LABELS[5],
        description=f"Place on quality hold and dispose — estimated write-off {write_off_estimate:,.2f} {config.currency}",
        draft_artefact=draft,
        eligible=True,
    )


def match_actions(
    risk_batch: RiskBatch,
    bins: list[BinInfo],
    demand_forecast: DemandForecast | None,
    alternative_plant: str | None,
    transfer_lead_time_days: int,
    vendor_agreements: list[VendorReturnAgreement],
    config: AgentConfig,
) -> list[ActionRecommendation]:
    """
    Evaluate all enabled action types in priority order and return eligible actions.
    Falls back to disposal if no other action is feasible.
    """
    actions: list[ActionRecommendation] = []

    rec1 = evaluate_redistribution(risk_batch, bins, config)
    if rec1:
        actions.append(rec1)

    rec2 = evaluate_channel_reallocation(risk_batch, demand_forecast, alternative_plant, transfer_lead_time_days, config)
    if rec2:
        actions.append(rec2)

    rec3 = evaluate_markdown(risk_batch, config)
    if rec3:
        actions.append(rec3)

    rec4 = evaluate_rtv(risk_batch, vendor_agreements, config)
    if rec4:
        actions.append(rec4)

    # Only recommend disposal if no other action is available
    if not actions and 5 in config.action_types_enabled:
        actions.append(evaluate_disposal(risk_batch, config))

    return actions
