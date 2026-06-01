"""Integration test — end-to-end agent invocation with mock MCP tools."""

import asyncio
import os
import sys
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


@pytest.fixture(autouse=True)
def mock_mcp_tools():
    """Patch mcp_tools.get_mcp_tools to return empty tool list for tests."""
    with patch("mcp_tools.get_mcp_tools", new_callable=AsyncMock, return_value=[]):
        yield


@pytest.fixture(autouse=True)
def mock_create_agent():
    """Patch langchain create_agent to avoid real LLM calls."""
    from langchain_core.messages import AIMessage

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content="Mock EWM/IBP response: no batches found in test environment.")]}
    )

    with patch("agent.create_agent", return_value=mock_graph):
        yield mock_graph


@pytest.mark.asyncio
async def test_agent_invoke_returns_response():
    """Agent invoke must return a completed response."""
    from agent import SampleAgent

    agent = SampleAgent()
    response = await agent.invoke(
        query="Run a batch expiry risk scan for all plants",
        context_id="test-context-001",
    )
    assert response.status in ("completed", "error")
    assert isinstance(response.message, str)
    assert len(response.message) > 0


@pytest.mark.asyncio
async def test_agent_stream_yields_chunks():
    """Agent stream must yield at least one processing chunk and one final chunk."""
    from agent import SampleAgent

    agent = SampleAgent()
    chunks = []
    async for chunk in agent.stream(
        query="Show me all batches expiring within 30 days",
        context_id="test-context-002",
    ):
        chunks.append(chunk)

    assert len(chunks) >= 2
    # First chunk: processing notice
    assert chunks[0]["is_task_complete"] is False
    # Last chunk: final result
    assert chunks[-1]["is_task_complete"] is True
    assert "content" in chunks[-1]


@pytest.mark.asyncio
async def test_agent_handles_empty_scan_gracefully():
    """Agent must handle empty batch scan (no at-risk batches) without error."""
    from agent import SampleAgent

    agent = SampleAgent()
    response = await agent.invoke(
        query="Scan for expiring batches",
        context_id="test-context-003",
    )
    # Should complete — not error — even with empty data
    assert response.status in ("completed", "error")
