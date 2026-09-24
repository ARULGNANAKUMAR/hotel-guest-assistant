"""
LLM Service — lightweight abstraction over an external LLM provider.

Responsibilities
----------------
- Provide a single ``enhance_response`` function that rewrites a
  deterministic assistant message into more natural language.
- Read configuration from environment variables; never hardcode secrets.
- Fail silently: if the LLM is unavailable for ANY reason, return the
  original deterministic message unchanged so the app keeps working.

What this service must NOT do
------------------------------
- Decide room availability
- Determine room counts or capacity
- Invent hotel policies, prices, dates, or guest counts
- Replace the deterministic knowledge service

The system prompt below grounds the model strictly to the trusted hotel
information supplied to it and forbids invention.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration — read from environment, no defaults for the API key.
# ---------------------------------------------------------------------------
_LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
_LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
_LLM_BASE_URL: str = os.getenv(
    "LLM_BASE_URL", "https://api.anthropic.com/v1/messages"
)
_LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "5"))
_LLM_MAX_TOKENS: int = 300

# System prompt: grounds the model to trusted hotel info only.
_SYSTEM_PROMPT = (
    "You are a friendly and professional hotel guest assistant. "
    "Your sole job is to rephrase the provided hotel response into warm, "
    "natural, conversational language. "
    "You must NOT invent hotel facilities, policies, room information, "
    "prices, availability, dates, or guest counts. "
    "If information is missing from what you are given, do not add it. "
    "Keep the same facts; only improve the tone and phrasing. "
    "Reply with the rephrased message only — no commentary, no preamble."
)


def is_configured() -> bool:
    """Return True when an API key is present in the environment."""
    return bool(_LLM_API_KEY)


def enhance_response(
    deterministic_message: str,
    hotel_context: Optional[str] = None,
) -> str:
    """
    Attempt to rephrase *deterministic_message* into more natural language.

    Parameters
    ----------
    deterministic_message:
        The message produced by the deterministic assistant layer.
    hotel_context:
        Optional additional trusted hotel context to help ground the model
        (e.g. the hotel name).  This is trusted data from hotel_data.json,
        not from user input.

    Returns
    -------
    str
        The enhanced message, or *deterministic_message* unchanged if the
        LLM is unavailable or returns an unusable response.
    """
    if not is_configured():
        return deterministic_message

    user_content = deterministic_message
    if hotel_context:
        user_content = f"Hotel context: {hotel_context}\n\nMessage to rephrase: {deterministic_message}"
    else:
        user_content = f"Message to rephrase: {deterministic_message}"

    payload = {
        "model": _LLM_MODEL,
        "max_tokens": _LLM_MAX_TOKENS,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }

    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _LLM_BASE_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": _LLM_API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=_LLM_TIMEOUT) as resp:
            raw = resp.read()

        data = json.loads(raw)
        # Extract the first text content block
        content = data.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    return text

        # No usable text block found — fall back
        return deterministic_message

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        # Network issues, HTTP errors, timeouts
        return deterministic_message
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Malformed or unexpected response structure
        return deterministic_message
    except Exception:  # noqa: BLE001 — catch-all: never crash the app
        return deterministic_message
