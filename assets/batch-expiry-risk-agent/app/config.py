"""Configuration module — loads all parameters from environment variables with defaults."""

import os


def _int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def _float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))


def _bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")


def _str(key: str, default: str) -> str:
    return os.environ.get(key, default)


class AgentConfig:
    """All configurable parameters for the Batch Expiry Risk Management Agent."""

    def __init__(self):
        # Scan horizons
        self.risk_horizon_days: int = _int("RISK_HORIZON_DAYS", 60)
        self.demand_horizon_days: int = _int("DEMAND_HORIZON_DAYS", 90)

        # Residual quantity thresholds
        self.residual_qty_threshold: float = _float("RESIDUAL_QTY_THRESHOLD", 0.10)
        self.residual_qty_absolute: int = _int("RESIDUAL_QTY_ABSOLUTE", 50)

        # Risk quantity filter
        self.min_risk_qty: float = _float("MIN_RISK_QTY", 0)
        self.min_score_threshold: int = _int("MIN_SCORE_THRESHOLD", 20)

        # Risk score weights (must sum to 100)
        self.w_expiry: int = _int("W_EXPIRY", 40)
        self.w_exposure: int = _int("W_EXPOSURE", 30)
        self.w_value: int = _int("W_VALUE", 20)
        self.w_bin: int = _int("W_BIN", 10)

        # Transfer eligibility
        self.min_shelf_life_post_transfer_days: int = _int("MIN_SHELF_LIFE_POST_TRANSFER_DAYS", 14)
        self.transfer_buffer_days: int = _int("TRANSFER_BUFFER_DAYS", 5)

        # Markdown configuration
        self.markdown_enabled: bool = _bool("MARKDOWN_ENABLED", True)
        self.markdown_trigger_days: int = _int("MARKDOWN_TRIGGER_DAYS", 30)
        self.markdown_min_qty: int = _int("MARKDOWN_MIN_QTY", 1)
        self.md_tier_1: int = _int("MD_TIER_1", 15)
        self.md_tier_2: int = _int("MD_TIER_2", 30)
        self.md_tier_3: int = _int("MD_TIER_3", 50)

        # Return-to-vendor configuration
        self.rtv_min_days_remaining: int = _int("RTV_MIN_DAYS_REMAINING", 21)
        self.rtv_escalation_threshold: float = _float("RTV_ESCALATION_THRESHOLD", 5000.0)

        # Data freshness
        self.ibp_data_freshness_hours: int = _int("IBP_DATA_FRESHNESS_HOURS", 24)

        # Hazmat
        self.hazmat_exclude: bool = _bool("HAZMAT_EXCLUDE", True)

        # Reporting
        self.currency: str = _str("CURRENCY", "USD")
        self.plants: str = _str("PLANTS", "All")
        self.storage_types_in_scope: str = _str("STORAGE_TYPES_IN_SCOPE", "All")
        self.action_types_enabled: list[int] = [
            int(x.strip()) for x in _str("ACTION_TYPES_ENABLED", "1,2,3,4,5").split(",")
        ]

        self._validate()

    def _validate(self):
        total = self.w_expiry + self.w_exposure + self.w_value + self.w_bin
        if total != 100:
            raise ValueError(
                f"Risk score weights must sum to 100. "
                f"Got W_EXPIRY={self.w_expiry} + W_EXPOSURE={self.w_exposure} + "
                f"W_VALUE={self.w_value} + W_BIN={self.w_bin} = {total}"
            )


# Singleton for import convenience
_config: AgentConfig | None = None


def get_config() -> AgentConfig:
    global _config
    if _config is None:
        _config = AgentConfig()
    return _config
