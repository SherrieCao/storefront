"""Classify external-API failures so the orchestrator can stop cleanly.

Returns a small dict {provider, kind, fatal, message} for recognized API/network errors,
or None for anything unrecognized (so genuine bugs keep their traceback).

NOT for: retrying — the SDKs already auto-retry transient errors; this only labels the
final failure after their retries are exhausted.
"""
from __future__ import annotations
from typing import Any

# "fatal" = operator must fix something (don't just rerun). Everything else is transient.
_FATAL = {"auth", "credit", "not_found"}

_MESSAGES = {
    "auth":       "authentication failed — check the API key.",
    "credit":     "out of credit / billing issue — top up the account, then rerun.",
    "not_found":  "model or endpoint not found — check the id in config.MODEL_ROUTER.",
    "rate_limit": "rate limited — wait a bit and rerun.",
    "timeout":    "the service didn't respond in time — rerun later.",
    "server":     "the provider had a server error — rerun later.",
    "unknown_api":"the provider rejected the request — rerun later.",
}

_STATUS = {401: "auth", 403: "auth", 402: "credit", 404: "not_found", 429: "rate_limit"}


def _result(provider: str, kind: str) -> dict[str, Any]:
    return {"provider": provider, "kind": kind, "fatal": kind in _FATAL,
            "message": f"{provider}: {_MESSAGES.get(kind, 'API error.')}"}


def _looks_like_credit(exc: BaseException) -> bool:
    s = str(getattr(exc, "message", "") or exc).lower()
    return any(w in s for w in ("credit", "balance", "insufficient", "billing", "exhausted"))


def _looks_like_auth(exc: BaseException) -> bool:
    # some providers return 400 (not 401/403) for a bad key — e.g. Gemini's
    # "API key not valid" — so sniff the message, not just the status code.
    s = str(getattr(exc, "message", "") or exc).lower()
    return any(w in s for w in ("api key not valid", "api_key_invalid", "invalid api key",
                                "unauthenticated", "unauthorized", "permission denied",
                                "invalid authentication"))


def _from_status(provider: str, exc: BaseException) -> dict[str, Any]:
    if _looks_like_credit(exc):
        return _result(provider, "credit")
    if _looks_like_auth(exc):
        return _result(provider, "auth")
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    kind = _STATUS.get(code) if isinstance(code, int) else None
    if kind is None:
        kind = "server" if isinstance(code, int) and code >= 500 else "unknown_api"
    return _result(provider, kind)


def classify_api_error(exc: BaseException) -> dict[str, Any] | None:
    """Label a recognized API/network failure, or return None to let it propagate."""
    # --- Anthropic ---
    try:
        import anthropic
        if isinstance(exc, anthropic.APIError):
            if _looks_like_credit(exc):                         return _result("anthropic", "credit")
            if isinstance(exc, anthropic.AuthenticationError):  return _result("anthropic", "auth")
            if isinstance(exc, anthropic.PermissionDeniedError):
                return _result("anthropic", "credit" if getattr(exc, "type", "") == "billing_error" else "auth")
            if isinstance(exc, anthropic.NotFoundError):        return _result("anthropic", "not_found")
            if isinstance(exc, anthropic.RateLimitError):       return _result("anthropic", "rate_limit")
            if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
                return _result("anthropic", "timeout")
            if isinstance(exc, (anthropic.InternalServerError, getattr(anthropic, "OverloadedError", ()))):
                return _result("anthropic", "server")
            return _result("anthropic", "unknown_api")
    except ImportError:
        pass
    # --- Gemini ---
    try:
        from google.genai import errors as gerr
        if isinstance(exc, gerr.APIError):
            return _from_status("gemini", exc)
    except ImportError:
        pass
    # --- fal ---
    try:
        from fal_client.client import FalClientHTTPError
        if isinstance(exc, FalClientHTTPError):
            return _from_status("fal", exc)
    except ImportError:
        pass
    # --- shared httpx transport (timeouts / connection drops) ---
    try:
        import httpx
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
            return _result("network", "timeout")
    except ImportError:
        pass
    # --- fallback: recognized SDK module but unmatched type → transient API error ---
    root = (type(exc).__module__ or "").split(".")[0]
    if root in {"anthropic", "google", "fal_client", "httpx"}:
        return _result(root, "unknown_api")
    return None
