"""Per-request credentials for the remote (HTTP) transport.

In HTTP mode every request carries its own SnapGen API key and the server never falls back to an
environment variable, so one caller can never spend another caller's (or the server owner's) credit.
"""
from __future__ import annotations

from collections.abc import Mapping

CREATE_KEY_URL = "https://snapgen.ai/profile/integration/api-keys"

MISSING_KEY_MESSAGE = (
    "Missing API key. Send your SnapGen API key in the x-api-key header "
    f"(or as Authorization: Bearer <key>). Create one at {CREATE_KEY_URL}"
)


def extract_api_key(headers: Mapping[str, str]) -> str | None:
    """Return the caller's API key from `x-api-key`, else `Authorization: Bearer <key>`, else None.

    `headers` must be case-insensitive (Starlette's request.headers is).
    """
    key = (headers.get("x-api-key") or "").strip()
    if key:
        return key
    scheme, _, token = (headers.get("authorization") or "").strip().partition(" ")
    token = token.strip()
    if scheme.lower() == "bearer" and token:
        return token
    return None
