"""tests/fixtures/mock_responses.py

Shared mock HTTP payloads and patching helpers for offline unit testing.

Covers:
  - OpenRouter and Groq success / error responses
  - Generic HTTP errors: 429, 402, 401, 403, 500, 503
  - Malformed bodies: empty, invalid JSON, missing fields
  - urllib.request.urlopen patching (for benchmark_gateways, monitor_leads, hn_leads)
  - subprocess.run patching (for outreach_agent -> bin/ai --json)

No third-party dependencies. Uses stdlib unittest.mock and urllib only.
"""

from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# ── Raw payloads ─────────────────────────────────────────────────────────────
# Shapes match what the real providers return and what benchmark_gateways.py
# and inference_bridge.py expect: {"choices": [{"message": {"content": "..."}}]}

# Groq 429 — tokens-per-minute ceiling, retryable
GROQ_429_TPM: Dict[str, Any] = {
    "error": {
        "message": (
            "Rate limit reached for model `openai/gpt-oss-120b` in organization "
            "`org_01k407mvmdfpq8m0ak32bn1wxk` service tier `on_demand` on tokens "
            "per minute (TPM): Limit 8000, Used 6651, Requested 2309. Please try "
            "again in 7.199999999s. Need more tokens? Upgrade to Dev Tier today at "
            "https://console.groq.com/settings/billing"
        ),
        "type": "tokens_rate_limit_error",
        "code": "rate_limit_exceeded",
    }
}

# Groq 429 — account out of credit, NOT retryable
GROQ_429_QUOTA_EXHAUSTED: Dict[str, Any] = {
    "error": {
        "message": "You have no credits remaining. Add credits to continue.",
        "type": "quota_exceeded_error",
        "code": "insufficient_quota",
    }
}

# OpenRouter 429 — generic rate limit
OPENROUTER_429: Dict[str, Any] = {
    "error": {
        "message": "Rate limit exceeded. Please try again in 3.5s.",
        "type": "rate_limit_error",
        "code": 429,
    }
}

# 402 payment required (Groq, Cerebras, Puter)
PAYMENT_REQUIRED_402: Dict[str, Any] = {
    "error": {
        "message": "Your account has no payment method. Add a card to continue.",
        "type": "payment_required",
        "code": "payment_required",
    }
}

# 401 unauthorized
UNAUTHORIZED_401: Dict[str, Any] = {
    "error": {
        "message": "Invalid API key",
        "type": "authentication_error",
        "code": "invalid_api_key",
    }
}

# 403 forbidden (Cloudflare-style, common on Groq/Cerebras with bad UA)
FORBIDDEN_403: Dict[str, Any] = {
    "error": {
        "message": "Access denied",
        "type": "error",
        "code": 1010,
    }
}

# 500 server error
SERVER_ERROR_500: Dict[str, Any] = {
    "error": {
        "message": "Internal server error",
        "type": "server_error",
    }
}

# 503 upstream unavailable (Gemini/Sageox upstream down)
UPSTREAM_503: Dict[str, Any] = {
    "error": {
        "message": "Service temporarily unavailable",
        "type": "upstream_error",
    }
}

# Valid OpenRouter chat completion — short draft-style reply
OPENROUTER_VALID_DRAFT: Dict[str, Any] = {
    "id": "gen-abc123",
    "object": "chat.completion",
    "created": 1726512000,
    "model": "nvidia/nemotron-3-super-120b-a12b:free",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": (
                    "Subject: Fractional Python backend help for VLM Run\n\n"
                    "Your post mentions inference platform work. I do exactly that — "
                    "Python backends and LLM gateways, on hardware you already own. "
                    "Could I see the repo?"
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 120,
        "completion_tokens": 38,
        "total_tokens": 158,
    },
}

# Valid Groq chat completion — short draft-style reply
GROQ_VALID_DRAFT: Dict[str, Any] = {
    "id": "req_groq_001",
    "object": "chat.completion",
    "created": 1726512001,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": (
                    "Subject: Speed up your LiveKit infrastructure code\n\n"
                    "You mentioned VoiceAI and WebRTC infrastructure. I specialize in "
                    "Python backend and LLM gateway work that could help your team "
                    "move faster. Could I see the repo?"
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 118,
        "completion_tokens": 32,
        "total_tokens": 150,
        "prompt_time": 0.025,
        "completion_time": 0.180,
        "total_time": 0.205,
    },
}

# Valid minimal 1-token ping response (for benchmark_gateways.py)
OPENROUTER_PING: Dict[str, Any] = {
    "id": "chatcmpl-ping",
    "object": "chat.completion",
    "created": 1726512002,
    "model": "nvidia/nemotron-3-super-120b-a12b:free",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "pong",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
    },
}

GROQ_PING: Dict[str, Any] = {
    "id": "req_ping",
    "object": "chat.completion",
    "created": 1726512003,
    "model": "openai/gpt-oss-120b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "pong",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "prompt_time": 0.010,
        "completion_time": 0.045,
        "total_time": 0.055,
    },
}

# ── Malformed bodies ─────────────────────────────────────────────────────────

EMPTY_BODY: bytes = b""
INVALID_JSON_BODY: bytes = b"<html><body>Something went wrong</body></html>"
MISSING_CHOICES_BODY: bytes = b'{"id":"req_xyz","usage":{}}'
EMPTY_JSON_OBJECT: bytes = b"{}"

# ── Helper: build mock urllib response objects ────────────────────────────────

def make_mock_response(
    status_code: int,
    payload: Any,
    headers: Optional[Dict[str, str]] = None,
    encoding: str = "utf-8",
) -> MagicMock:
    """Build a mock urllib.response object for use with `urllib.request.urlopen`.

    Args:
        status_code: HTTP status code to report.
        payload: JSON-serializable object, or bytes, or str.  Serialized to the
            response body automatically when not already bytes.
        headers: Optional response headers dict.
        encoding: Used when payload is a string.

    Returns:
        A MagicMock with `.status`, `.headers`, `.read()`, and context-manager
        support (`with ... as resp:`).
    """
    headers = headers or {}
    if isinstance(payload, bytes):
        body = payload
    elif isinstance(payload, str):
        body = payload.encode(encoding)
    else:
        body = json.dumps(payload, ensure_ascii=False).encode(encoding)

    resp = MagicMock()
    resp.status = status_code
    resp.headers = headers
    resp.read.return_value = body
    # Support `with urllib.request.urlopen(...) as resp:`
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def make_http_error(
    status_code: int,
    payload: Any,
    headers: Optional[Dict[str, str]] = None,
    url: str = "https://api.openai.com/v1/chat/completions",
    encoding: str = "utf-8",
) -> urllib.error.HTTPError:
    """Build an `urllib.error.HTTPError` with a JSON body.

    Args:
        status_code: HTTP error code.
        payload: JSON-serializable error body.
        headers: Optional response headers (e.g., Retry-After).
        url: The URL the error is attributed to.
        encoding: Body encoding.

    Returns:
        A fully formed HTTPError with a BytesIO fp containing the body.
    """
    headers = headers or {}
    if isinstance(payload, bytes):
        body = payload
    elif isinstance(payload, str):
        body = payload.encode(encoding)
    else:
        body = json.dumps(payload, ensure_ascii=False).encode(encoding)

    return urllib.error.HTTPError(
        url=url,
        code=status_code,
        msg=f"{status_code} error",
        hdrs=headers,
        fp=io.BytesIO(body),
    )


# ── Patching helpers ─────────────────────────────────────────────────────────

class UrlopenSequence:
    """Patches `urllib.request.urlopen` and returns a fixed sequence of responses.

    Each call to `urlopen` consumes the next item from `responses`.  An item may
    be:
      - a MagicMock response (from `make_mock_response`)
      - an Exception (raised instead of returned)
      - a callable `(request, timeout) -> response` for dynamic behaviour

    Usage::

        with UrlopenSequence([make_mock_response(200, OPENROUTER_VALID_DRAFT)]):
            ...
    """

    def __init__(self, responses: List[Any], target: str = "urllib.request.urlopen"):
        self._responses = list(responses)
        self._target = target
        self._patcher: Optional[Any] = None
        self._calls: List[Any] = []

    def __enter__(self) -> "UrlopenSequence":
        self._patcher = patch(self._target, side_effect=self._side_effect)
        self._patcher.start()
        return self

    def __exit__(self, *args: Any) -> None:
        assert self._patcher is not None
        self._patcher.stop()

    def _side_effect(self, request: Any, timeout: Any = None) -> Any:
        if not self._responses:
            raise RuntimeError(
                "urlopen called more times than mock responses were provided. "
                f"Called with request={request!r}"
            )
        self._calls.append(request)
        item = self._responses.pop(0)
        if callable(item) and not isinstance(item, MagicMock):
            return item(request, timeout)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def calls(self) -> List[Any]:
        """Every `urllib.request.Request` that was made, in order."""
        return list(self._calls)


def patch_urlopen(
    responses: List[Any],
    target: str = "urllib.request.urlopen",
) -> "UrlopenSequence":
    """Return a context manager that patches urlopen with a fixed response list.

    Prefer `with UrlopenSequence(...) as seq:` when you need to inspect calls.
    This wrapper exists for one-liner use::

        with patch_urlopen([make_mock_response(200, PAYLOAD)]) as seq:
            call_the_code()
            assert len(seq.calls) == 1
    """
    return UrlopenSequence(responses, target=target)


# ── Higher-level patching for outreach_agent (subprocess / bin/ai) ───────────

def make_bin_ai_envelope(
    ok: bool = True,
    reply: str = "",
    error: str = "",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the JSON envelope `bin/ai --json` prints to stdout.

    Args:
        ok: Whether the call succeeded.
        reply: The model's text reply (used when ok=True).
        error: Error description (used when ok=False).
        model: Optional model id echoed back.

    Returns:
        Dict shaped like `bin/ai`'s stdout: ``{"ok", "reply", "error", "model"}``.
    """
    envelope: Dict[str, Any] = {"ok": ok}
    if model:
        envelope["model"] = model
    if ok:
        envelope["reply"] = reply
    else:
        envelope["error"] = error
    return envelope


class SubprocessRunSequence:
    """Patches `subprocess.run` with a fixed sequence of CompletedProcess results.

    Each item in `responses` is either:
      - a dict of kwargs for `subprocess.CompletedProcess`
      - an Exception to raise

    Usage::

        with SubprocessRunSequence([{"returncode": 0, "stdout": '{"ok":true}', ...}]) as seq:
            call_the_code()
    """

    def __init__(self, responses: List[Any], target: str = "subprocess.run"):
        self._responses = list(responses)
        self._target = target
        self._patcher: Optional[Any] = None
        self.calls: List[Any] = []

    def __enter__(self) -> "SubprocessRunSequence":
        self._patcher = patch(self._target, side_effect=self._side_effect)
        self._patcher.start()
        return self

    def __exit__(self, *args: Any) -> None:
        assert self._patcher is not None
        self._patcher.stop()

    def _side_effect(self, *args: Any, **kwargs: Any) -> Any:
        if not self._responses:
            raise RuntimeError("subprocess.run called more times than expected")
        self.calls.append((args, kwargs))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return subprocess.CompletedProcess(**item)
        return item


def patch_subprocess_run(
    responses: List[Any],
    target: str = "subprocess.run",
) -> SubprocessRunSequence:
    """Return a context manager that patches subprocess.run with a response list."""
    return SubprocessRunSequence(responses, target=target)


def make_completed_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> Dict[str, Any]:
    """Convenience wrapper: build the dict `patch_subprocess_run` expects."""
    return {
        "args": ["python3", "bin/ai", "--json", "prompt"],
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


# ── Convenience bundles ──────────────────────────────────────────────────────

#: All Groq error responses keyed by a short name.
GROQ_ERRORS: Dict[str, Dict[str, Any]] = {
    "rate_limit_tpm": GROQ_429_TPM,
    "quota_exhausted": GROQ_429_QUOTA_EXHAUSTED,
    "payment_required": PAYMENT_REQUIRED_402,
    "unauthorized": UNAUTHORIZED_401,
    "forbidden": FORBIDDEN_403,
    "server_error": SERVER_ERROR_500,
    "upstream_unavailable": UPSTREAM_503,
}

#: All OpenRouter error responses keyed by a short name.
OPENROUTER_ERRORS: Dict[str, Dict[str, Any]] = {
    "rate_limit": OPENROUTER_429,
    "unauthorized": UNAUTHORIZED_401,
    "forbidden": FORBIDDEN_403,
    "server_error": SERVER_ERROR_500,
    "upstream_unavailable": UPSTREAM_503,
}

#: Valid draft payloads for both providers.
VALID_DRAFTS: Dict[str, Dict[str, Any]] = {
    "openrouter": OPENROUTER_VALID_DRAFT,
    "groq": GROQ_VALID_DRAFT,
}

#: 1-token ping payloads for benchmark tests.
PING_RESPONSES: Dict[str, Dict[str, Any]] = {
    "openrouter": OPENROUTER_PING,
    "groq": GROQ_PING,
}
