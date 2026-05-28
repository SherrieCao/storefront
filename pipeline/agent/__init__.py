"""Hermes-idiom agent layer: a tool registry + a function-calling loop on native model APIs.

Public surface:
  - registry: tool / register / get / names / tool_schemas / execute / gemini_tool_defs
  - loop:     run_agent_loop
Tool implementations live in pipeline/agent/tools.py and self-register on import.
"""
from __future__ import annotations
from . import registry
from .registry import tool, register, Tool, execute, names, gemini_tool_defs, tool_schemas
