# Batch Expiry Risk Management Agent

A proactive batch expiry risk management agent that identifies at-risk batches in SAP EWM, cross-references SAP IBP demand forecasts, scores financial risk, and delivers a prioritised action report with DRAFT artefacts to prevent inventory write-offs.

## Overview

Uses A2A Protocol, LangGraph, LiteLLM, and SAP Cloud SDK.

## Structure

- `app/main.py` - A2A server entry
- `app/agent_executor.py` - Request handling
- `app/agent.py` - Agent logic
