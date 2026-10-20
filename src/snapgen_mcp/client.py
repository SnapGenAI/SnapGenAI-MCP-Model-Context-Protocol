"""Thin async client for the snapgen.ai User API (uapi).

The MCP server never touches credits or the database. It only forwards the
user's API key to uapi, which does auth, pricing, credit locking and billing.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.snapgen.ai"
TOP_UP_URL = "https://snapgen.ai/pricing"


def _load_dotenv() -> None:
    """Load the repo-root .env (dev convenience). Real environment variables win."""
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


class SnapGenError(Exception):
    """A user-presentable error from the snapgen.ai API."""


def _error_message(resp: httpx.Response) -> str:
    code = ""
    message = ""
    try:
        detail = resp.json().get("detail")
        if isinstance(detail, dict):
            code = detail.get("error_code") or ""
            message = detail.get("error_message") or detail.get("message") or ""
        elif isinstance(detail, str):
            message = detail
    except ValueError:
        pass

    if code in ("API_KEY_REQUIRED", "API_KEY_NOT_FOUND") or resp.status_code == 401:
        return "Invalid or missing SNAPGEN_API_KEY. Create one at https://snapgen.ai/profile/integration/api-keys"
    if code.endswith("PREMIUM_PLAN_REQUIRED"):
        return "This model requires a Premium plan. Upgrade at " + TOP_UP_URL
    if code in ("NOT_ENOUGH_CREDIT", "NOT_ENOUGH_AND_LOCK_CREDIT"):
        return f"Not enough credits ({code}). Top up at {TOP_UP_URL}"
    if resp.status_code in (502, 503, 504):
        return "snapgen.ai is temporarily unavailable (maintenance or outage). Try again later."
    if resp.status_code == 429:
        return "Rate limited by snapgen.ai. Wait a moment and try again."
    text = f"{code}: {message}".strip(": ") or f"HTTP {resp.status_code}"
    return f"snapgen.ai request failed ({resp.status_code}): {text}"


class SnapGenClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("SNAPGEN_API_KEY", "")
        self.base_url = (base_url or os.environ.get("SNAPGEN_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._transport = transport
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.api_key:
            raise SnapGenError(
                "SNAPGEN_API_KEY is not set. Create a key at "
                "https://snapgen.ai/profile/integration/api-keys and set it in the MCP server env."
            )
        async with httpx.AsyncClient(
            base_url=f"{self.base_url}/uapi/v1",
            headers={"x-api-key": self.api_key, "Accept": "application/json"},
            transport=self._transport,
            timeout=self._timeout,
        ) as http:
            try:
                resp = await http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise SnapGenError(f"Could not reach snapgen.ai: {exc}") from exc
        if resp.status_code >= 400:
            raise SnapGenError(_error_message(resp))
        return resp.json()

    async def account(self) -> dict:
        return await self._request("GET", "/account")

    async def submit(self, endpoint: str, fields: dict[str, Any]) -> dict:
        """POST a generation request (form fields) to any uapi endpoint."""
        return await self._request("POST", endpoint, data=_clean(fields))

    async def get_history(self, uuid: str) -> dict:
        return await self._request("GET", f"/history/{uuid}")

    async def list_histories(self, filter_by: str = "all", page: int = 1, items_per_page: int = 10) -> dict:
        return await self._request(
            "GET", "/histories",
            params={"filter_by": filter_by, "page": page, "items_per_page": items_per_page},
        )


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None and v != []}
