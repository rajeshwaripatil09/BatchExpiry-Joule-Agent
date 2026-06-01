"""Data models for the Batch Expiry Risk Management Agent."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class BatchClassification:
    storage_conditions: str = ""
    temperature_class: str = ""  # e.g. "AMBIENT", "CHILLED", "FROZEN"
    hazmat_flag: bool = False


@dataclass
class BatchRecord:
    batch_number: str
    material: str
    description: str
    plant: str
    storage_location: str
    bin: str
    quantity: float
    uom: str
    unit_value: float  # moving average price in reporting currency
    sled: Optional[date]  # shelf life expiry date / best-before date
    batch_classification: BatchClassification = field(default_factory=BatchClassification)


@dataclass
class DemandForecast:
    material: str
    plant: str
    total_qty: float  # total consensus demand over horizon_days
    horizon_days: int
    is_stale: bool = False
    data_timestamp: Optional[datetime] = None


@dataclass
class OpenOrder:
    batch_number: str
    material: str
    plant: str
    confirmed_qty: float
    order_type: str  # e.g. "SALES_ORDER", "TRANSFER_ORDER", "REPLENISHMENT"


@dataclass
class BinInfo:
    bin_id: str
    plant: str
    storage_type: str
    velocity_class: str  # "A" (high), "B" (medium), "C" (low)
    temperature_zone: str  # e.g. "AMBIENT", "CHILLED", "FROZEN"


@dataclass
class VendorReturnAgreement:
    material: str
    vendor: str
    vendor_name: str = ""
    min_return_qty: float = 0
    lead_time_days: int = 0
    has_agreement: bool = False
    purchase_order_ref: str = ""


@dataclass
class RiskBatch:
    """A batch record enriched with risk calculations."""
    batch: BatchRecord
    net_risk_qty: float = 0.0
    projected_consumption: float = 0.0
    risk_qty: float = 0.0
    days_to_expiry: int = 0
    risk_score: float = 0.0
    confidence: str = "Medium"  # "High", "Medium", "Low"
    is_ibp_stale: bool = False

    @property
    def total_exposure(self) -> float:
        return self.risk_qty * self.batch.unit_value


@dataclass
class ActionRecommendation:
    action_type: int  # 1=Redistribution, 2=ChannelReallocation, 3=Markdown, 4=RTV, 5=Disposal
    action_label: str
    description: str
    draft_artefact: str = ""  # DRAFT text requiring human approval
    eligible: bool = True
    requires_escalation: bool = False  # e.g. manual RTV negotiation needed

    ACTION_LABELS = {
        1: "Redistribution to High-Velocity Bin",
        2: "Channel Reallocation",
        3: "Markdown / Price Promotion",
        4: "Return to Vendor (RTV)",
        5: "Quality Hold / Disposal",
    }
