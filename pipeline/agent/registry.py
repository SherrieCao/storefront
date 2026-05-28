"""Tool registry — Hermes-idiom (registry + loop), running on native model function-calling.

Mirrors Nous Hermes's ToolEntry/ToolRegistry pattern (decorator registration, schema export,
name→handler routing) but imports NO Hermes code. Tools self-register at import time via the
@tool decorator; loop.py reads gemini_tool_defs() to advertise tools to the model and execute()
to run a call the model requested.

NOT for: making model calls (that's loop.py) or creative/judgment decisions.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]          # JSON-schema object: {"type":"object","properties":{...},"required":[...]}
    fn: Callable[..., Any]
    not_for: str = ""                   # one-line boundary, mirrors the repo's "NOT for:" idiom


_REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, parameters: dict[str, Any], not_for: str = ""):
    """Decorator: register the wrapped callable as a tool at import time."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        register(Tool(name=name, description=description, parameters=parameters, fn=fn, not_for=not_for))
        return fn
    return deco


def register(t: Tool) -> None:
    _REGISTRY[t.name] = t


def get(name: str) -> Tool:
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


def tool_schemas(tool_names: list[str]) -> list[dict[str, Any]]:
    """Provider-neutral schema list (also handy for tests / a future Claude adapter)."""
    return [{"name": (t := _REGISTRY[n]).name, "description": t.description, "parameters": t.parameters}
            for n in tool_names]


def execute(name: str, args: dict[str, Any] | None) -> Any:
    """Route a model-requested call to its handler. Raises KeyError if the name is unknown."""
    return _REGISTRY[name].fn(**(args or {}))


def register_fn(fn: Callable[..., Any], *, parameters: dict[str, Any] | None = None,
                not_for: str = "") -> None:
    """Register an existing function (e.g. a @traced_tool) by introspecting its docstring for
    the description and the repo's 'NOT for:' boundary. Used to make triage/review tools
    loop-ready without hand-writing schemas (they aren't loop-invoked in v0)."""
    doc = (fn.__doc__ or "").strip()
    desc = doc.split("\n", 1)[0].strip() or fn.__name__
    if not not_for and "NOT for:" in doc:
        not_for = doc.split("NOT for:", 1)[1].strip().splitlines()[0].strip()
    register(Tool(name=fn.__name__, description=desc,
                  parameters=parameters or {"type": "object", "properties": {}},
                  fn=fn, not_for=not_for))


def gemini_tool_defs(tool_names: list[str]) -> list[Any]:
    """Build the exact Gemini function-calling shape:
    [types.Tool(function_declarations=[FunctionDeclaration(name, description, parameters=<dict>)])].
    Imported lazily so the registry stays importable without google-genai."""
    from google.genai import types
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                       parameters=t["parameters"])
             for t in tool_schemas(tool_names)]
    return [types.Tool(function_declarations=decls)] if decls else []
