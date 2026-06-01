"""Tests for the configuration module."""

import os
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def test_default_config():
    """All defaults load correctly from environment."""
    # Reset singleton
    import config as cfg_module
    cfg_module._config = None
    os.environ.pop("RISK_HORIZON_DAYS", None)
    os.environ.pop("W_EXPIRY", None)
    os.environ.pop("W_EXPOSURE", None)
    os.environ.pop("W_VALUE", None)
    os.environ.pop("W_BIN", None)

    from config import AgentConfig
    c = AgentConfig()
    assert c.risk_horizon_days == 60
    assert c.demand_horizon_days == 90
    assert c.min_score_threshold == 20
    assert c.currency == "USD"
    assert c.hazmat_exclude is True
    assert c.markdown_enabled is True
    assert c.rtv_min_days_remaining == 21
    assert set(c.action_types_enabled) == {1, 2, 3, 4, 5}
    cfg_module._config = None


def test_weights_sum_to_100():
    """Default weights must sum to 100."""
    import config as cfg_module
    cfg_module._config = None
    from config import AgentConfig
    c = AgentConfig()
    assert c.w_expiry + c.w_exposure + c.w_value + c.w_bin == 100
    cfg_module._config = None


def test_invalid_weights_raise_error():
    """Weights that don't sum to 100 must raise ValueError."""
    import config as cfg_module
    cfg_module._config = None
    os.environ["W_EXPIRY"] = "50"
    os.environ["W_EXPOSURE"] = "50"
    os.environ["W_VALUE"] = "20"
    os.environ["W_BIN"] = "10"
    from config import AgentConfig
    with pytest.raises(ValueError, match="must sum to 100"):
        AgentConfig()
    for k in ["W_EXPIRY", "W_EXPOSURE", "W_VALUE", "W_BIN"]:
        os.environ.pop(k, None)
    cfg_module._config = None


def test_override_via_env():
    """Environment variables override defaults."""
    import config as cfg_module
    cfg_module._config = None
    os.environ["RISK_HORIZON_DAYS"] = "30"
    os.environ["CURRENCY"] = "EUR"
    from config import AgentConfig
    c = AgentConfig()
    assert c.risk_horizon_days == 30
    assert c.currency == "EUR"
    os.environ.pop("RISK_HORIZON_DAYS", None)
    os.environ.pop("CURRENCY", None)
    cfg_module._config = None


def test_action_types_enabled_parsing():
    """ACTION_TYPES_ENABLED comma string is parsed correctly."""
    import config as cfg_module
    cfg_module._config = None
    os.environ["ACTION_TYPES_ENABLED"] = "1,3,5"
    from config import AgentConfig
    c = AgentConfig()
    assert c.action_types_enabled == [1, 3, 5]
    os.environ.pop("ACTION_TYPES_ENABLED", None)
    cfg_module._config = None
