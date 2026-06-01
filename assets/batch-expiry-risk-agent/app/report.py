"""Report builder — assembles the structured markdown report from scored batch data."""

from datetime import datetime
from typing import Any

from config import AgentConfig
from models import ActionRecommendation, RiskBatch

# Confidence language mapping
CONFIDENCE_LANGUAGE = {
    "High": "Recommended",
    "Medium": "Consider",
    "Low": "Review manually",
}


def _divider(char: str = "-", width: int = 80) -> str:
    return char * width


def _format_table_row(*cells: str, widths: list[int]) -> str:
    parts = [str(c).ljust(w) for c, w in zip(cells, widths)]
    return "| " + " | ".join(parts) + " |"


def _format_table_header(headers: list[str], widths: list[int]) -> str:
    header_row = _format_table_row(*headers, widths=widths)
    separator = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return header_row + "\n" + separator


def build_report(
    run_timestamp: datetime,
    plants_covered: list[str],
    total_batches_scanned: int,
    risk_batches_with_actions: list[tuple[RiskBatch, list[ActionRecommendation]]],
    exceptions: list[dict[str, Any]],
    ibp_stale: bool,
    config: AgentConfig,
) -> str:
    """
    Assemble the full structured report.

    Args:
        run_timestamp: When the scan was executed
        plants_covered: Plant codes in scope
        total_batches_scanned: Total batches evaluated (including those filtered out)
        risk_batches_with_actions: List of (RiskBatch, [ActionRecommendation]) tuples, sorted by risk_score desc
        exceptions: List of dicts with keys: batch_number, material, reason
        ibp_stale: Whether IBP data was stale for this run
        config: Agent configuration

    Returns:
        Formatted markdown report string
    """
    lines: list[str] = []

    # ─── RUN HEADER ─────────────────────────────────────────────────────────────
    lines.append("# BATCH EXPIRY RISK MANAGEMENT REPORT")
    lines.append("")
    lines.append(_divider("="))

    total_exposure = sum(rb.total_exposure for rb, _ in risk_batches_with_actions)
    plants_str = ", ".join(plants_covered) if plants_covered else "All"

    lines.append(f"**Run Timestamp**: {run_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Plants Covered**: {plants_str}")
    lines.append(f"**Scan Horizon**: {config.risk_horizon_days} days ahead")
    lines.append(f"**Total Batches Scanned**: {total_batches_scanned}")
    lines.append(f"**At-Risk Batches Found**: {len(risk_batches_with_actions)}")
    lines.append(f"**Total Financial Exposure**: {total_exposure:,.2f} {config.currency}")

    if ibp_stale:
        lines.append("")
        lines.append("> ⚠️  **WARNING: IBP demand data is STALE** (older than "
                     f"{config.ibp_data_freshness_hours}h). All confidence ratings downgraded to LOW.")

    lines.append(_divider("="))
    lines.append("")

    if not risk_batches_with_actions:
        lines.append("**No at-risk batches found for this run.** No actions required.")
        lines.append("")
    else:
        # ─── PER-BATCH BLOCKS ────────────────────────────────────────────────────
        lines.append("## At-Risk Batch Details")
        lines.append("")

        for i, (rb, actions) in enumerate(risk_batches_with_actions, 1):
            lines.append(f"### [{i}] Batch {rb.batch.batch_number} — Score: {rb.risk_score:.0f}/100")
            lines.append(_divider("-"))
            lines.append(f"- **Material**: {rb.batch.material}  |  {rb.batch.description}")
            lines.append(f"- **Location**: Plant {rb.batch.plant} / SLoc {rb.batch.storage_location} / Bin {rb.batch.bin}")
            lines.append(f"- **Quantity at Risk**: {rb.risk_qty:,.2f} {rb.batch.uom}  |  "
                         f"Unit Value: {rb.batch.unit_value:,.2f} {config.currency}  |  "
                         f"**Total Exposure: {rb.total_exposure:,.2f} {config.currency}**")
            lines.append(f"- **SLED**: {rb.batch.sled}  |  **Days to Expiry**: {rb.days_to_expiry}")
            lines.append(f"- **Risk Score**: {rb.risk_score:.0f}/100  |  "
                         f"**Confidence**: {CONFIDENCE_LANGUAGE.get(rb.confidence, rb.confidence)} ({rb.confidence})")

            if rb.is_ibp_stale:
                lines.append("- ⚠️  IBP data stale — consumption projection unreliable")

            lines.append("")
            if actions:
                lines.append("**Recommended Actions** (priority order):")
                for j, action in enumerate(actions, 1):
                    escalation_flag = " ⚠️ Escalation required" if action.requires_escalation else ""
                    lines.append(f"  {j}. [{action.action_label}] {action.description}{escalation_flag}")
            else:
                lines.append("**Recommended Actions**: None identified — manual review required")

            lines.append("")
            # Draft artefacts
            for action in actions:
                if action.draft_artefact:
                    lines.append(f"**Draft Artefact — {action.action_label}**:")
                    lines.append("```")
                    lines.append(action.draft_artefact)
                    lines.append("```")
                    lines.append("")

            lines.append("")

    # ─── SUMMARY ACTION TABLE ────────────────────────────────────────────────────
    lines.append("## Summary Action Table")
    lines.append("")

    col_widths = [18, 16, 10, 15, 35, 12, 20]
    headers = ["Batch #", "Material", "Risk Score", "Days to Expiry", "Recommended Action", "Draft Ready?", "Assigned To"]
    lines.append(_format_table_header(headers, col_widths))

    for rb, actions in risk_batches_with_actions:
        primary_action = actions[0].action_label if actions else "Manual Review"
        draft_ready = "Yes" if (actions and actions[0].draft_artefact) else "No"
        lines.append(_format_table_row(
            rb.batch.batch_number[:18],
            rb.batch.material[:16],
            f"{rb.risk_score:.0f}",
            str(rb.days_to_expiry),
            primary_action[:35],
            draft_ready,
            "",  # blank for planner to fill
            widths=col_widths,
        ))

    lines.append("")

    # ─── EXCEPTIONS ──────────────────────────────────────────────────────────────
    lines.append("## Exceptions & Data Quality Flags")
    lines.append("")

    if not exceptions:
        lines.append("No exceptions recorded for this run.")
    else:
        lines.append("The following batches were skipped and require master data correction:")
        lines.append("")
        exc_widths = [18, 16, 60]
        exc_headers = ["Batch #", "Material", "Reason / Action Required"]
        lines.append(_format_table_header(exc_headers, exc_widths))
        for exc in exceptions:
            lines.append(_format_table_row(
                str(exc.get("batch_number", ""))[:18],
                str(exc.get("material", ""))[:16],
                str(exc.get("reason", ""))[:60],
                widths=exc_widths,
            ))

    lines.append("")
    lines.append(_divider("="))
    lines.append("_All DRAFT artefacts above require human approval before any action is taken in SAP._")
    lines.append("")

    return "\n".join(lines)
