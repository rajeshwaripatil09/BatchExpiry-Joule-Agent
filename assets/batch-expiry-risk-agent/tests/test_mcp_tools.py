"""Tests for mcp_tools module (test mode — uses mock file if present)."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

# Ensure IBD_TESTING is set before importing
os.environ["IBD_TESTING"] = "1"


def test_build_mock_tools_missing_file(tmp_path):
    """_build_mock_tools returns empty list when mock file is absent."""
    import mcp_tools as mt
    original_mock_file = mt._MOCK_FILE
    mt._MOCK_FILE = tmp_path / "nonexistent.json"
    try:
        tools = mt._build_mock_tools()
        assert tools == []
    finally:
        mt._MOCK_FILE = original_mock_file


def test_build_mock_tools_invalid_json(tmp_path):
    """_build_mock_tools returns empty list on invalid JSON."""
    import mcp_tools as mt
    mock_file = tmp_path / "mcp-mock.json"
    mock_file.write_text("{ invalid json }")
    original_mock_file = mt._MOCK_FILE
    mt._MOCK_FILE = mock_file
    try:
        tools = mt._build_mock_tools()
        assert tools == []
    finally:
        mt._MOCK_FILE = original_mock_file


def test_build_mock_tools_empty_mock(tmp_path):
    """_build_mock_tools returns empty list from empty mock data."""
    import mcp_tools as mt
    mock_file = tmp_path / "mcp-mock.json"
    mock_file.write_text(json.dumps({"tools": []}))
    original_mock_file = mt._MOCK_FILE
    mt._MOCK_FILE = mock_file
    try:
        tools = mt._build_mock_tools()
        assert isinstance(tools, list)
    finally:
        mt._MOCK_FILE = original_mock_file


@pytest.mark.asyncio
async def test_get_mcp_tools_in_test_mode_no_mock_file(tmp_path):
    """get_mcp_tools in test mode returns empty list when no mock file."""
    import mcp_tools as mt
    original_mock_file = mt._MOCK_FILE
    original_cache = mt._tool_cache
    mt._MOCK_FILE = tmp_path / "nonexistent.json"
    mt._tool_cache = None
    try:
        tools = await mt.get_mcp_tools()
        assert isinstance(tools, list)
    finally:
        mt._MOCK_FILE = original_mock_file
        mt._tool_cache = original_cache


def test_build_mock_tools_with_valid_server_tool(tmp_path):
    """_build_mock_tools builds StructuredTool from valid mock data."""
    import mcp_tools as mt
    mock_data = {
        "servers": {
            "ewm-server": {
                "tools": {
                    "get_batches": {
                        "description": "Get batch records",
                        "mock_response": {"batches": []},
                        "input_schema": {
                            "properties": {
                                "plant": {"type": "string", "description": "Plant code"},
                                "top": {"type": "integer", "description": "Max results"},
                                "active": {"type": "boolean", "description": "Active only"},
                                "qty": {"type": "number", "description": "Min quantity"},
                            },
                            "required": ["plant"],
                        },
                    }
                }
            }
        }
    }
    mock_file = tmp_path / "mcp-mock.json"
    mock_file.write_text(json.dumps(mock_data))
    original_mock_file = mt._MOCK_FILE
    mt._MOCK_FILE = mock_file
    try:
        tools = mt._build_mock_tools()
        assert len(tools) == 1
        assert tools[0].name == "get_batches"
        assert tools[0].description == "Get batch records"
    finally:
        mt._MOCK_FILE = original_mock_file


@pytest.mark.asyncio
async def test_build_mock_tool_coroutine_returns_json(tmp_path):
    """Mock tool coroutine returns JSON string of mock_response."""
    import mcp_tools as mt
    mock_data = {
        "servers": {
            "test-server": {
                "tools": {
                    "fetch_data": {
                        "description": "Fetch data",
                        "mock_response": {"result": "ok"},
                        "input_schema": {"properties": {}, "required": []},
                    }
                }
            }
        }
    }
    mock_file = tmp_path / "mcp-mock.json"
    mock_file.write_text(json.dumps(mock_data))
    original_mock_file = mt._MOCK_FILE
    mt._MOCK_FILE = mock_file
    try:
        tools = mt._build_mock_tools()
        assert len(tools) == 1
        result = await tools[0].coroutine()
        data = json.loads(result)
        assert data == {"result": "ok"}
    finally:
        mt._MOCK_FILE = original_mock_file


def test_tool_cache_ttl_env():
    """MCP_TOOL_CACHE_TTL env variable is respected."""
    import importlib
    os.environ["MCP_TOOL_CACHE_TTL"] = "30.0"
    try:
        import mcp_tools as mt
        importlib.reload(mt)
        assert mt._CACHE_TTL == 30.0
    finally:
        os.environ.pop("MCP_TOOL_CACHE_TTL", None)
        importlib.reload(mt)
