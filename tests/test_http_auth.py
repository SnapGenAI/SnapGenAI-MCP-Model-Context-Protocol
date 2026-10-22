"""Per-request key handling in the tools, driven with a fake MCP context (no network server)."""
from types import SimpleNamespace

import httpx
import pytest
import respx
from starlette.datastructures import Headers

from snapgen_mcp import server
from snapgen_mcp.client import SnapGenError

BASE = "https://api.snapgen.ai/uapi/v1"


def http_ctx(**headers):
    request = SimpleNamespace(headers=Headers({k.replace("_", "-"): v for k, v in headers.items()}))
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


@pytest.fixture(autouse=True)
def owner_key_in_env(monkeypatch):
    """The server owner's key sits in the environment; HTTP callers must never be able to use it."""
    monkeypatch.setenv("SNAPGEN_API_KEY", "server-owner-key")
    monkeypatch.setenv("SNAPGEN_BASE_URL", "https://api.snapgen.ai")
    monkeypatch.setattr(server, "_client", None)


@respx.mock
async def test_http_key_is_forwarded_to_uapi():
    route = respx.get(f"{BASE}/account").mock(return_value=httpx.Response(200, json={
        "full_name": "A", "plan_id": "P", "user_credit": {"available_credit": 1, "locked_credit": 0}}))
    await server.get_account(ctx=http_ctx(x_api_key="caller-key"))
    assert route.calls[0].request.headers["x-api-key"] == "caller-key"


@respx.mock
async def test_bearer_key_is_forwarded_as_x_api_key():
    route = respx.get(f"{BASE}/account").mock(return_value=httpx.Response(200, json={"user_credit": {}}))
    await server.get_account(ctx=http_ctx(authorization="Bearer bearer-key"))
    assert route.calls[0].request.headers["x-api-key"] == "bearer-key"


@respx.mock
async def test_http_without_key_never_falls_back_to_env_key():
    route = respx.get(f"{BASE}/account").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(SnapGenError, match="Missing API key"):
        await server.get_account(ctx=http_ctx())
    assert not route.called  # nothing was sent upstream, certainly not with the owner's key


@respx.mock
async def test_each_call_uses_its_own_key():
    route = respx.get(f"{BASE}/history/u1").mock(return_value=httpx.Response(200, json={"uuid": "u1"}))
    await server.get_generation("u1", ctx=http_ctx(x_api_key="key-1"))
    await server.get_generation("u1", ctx=http_ctx(x_api_key="key-2"))
    assert [c.request.headers["x-api-key"] for c in route.calls] == ["key-1", "key-2"]


@respx.mock
async def test_stdio_context_still_uses_env_key():
    route = respx.get(f"{BASE}/account").mock(return_value=httpx.Response(200, json={"user_credit": {}}))
    stdio_ctx = SimpleNamespace(request_context=SimpleNamespace(request=None))
    await server.get_account(ctx=stdio_ctx)
    assert route.calls[0].request.headers["x-api-key"] == "server-owner-key"


@respx.mock
async def test_upstream_rejection_message_mentions_header_not_env():
    respx.get(f"{BASE}/account").mock(return_value=httpx.Response(
        404, json={"detail": {"error_code": "API_KEY_NOT_FOUND"}}))
    with pytest.raises(SnapGenError) as exc:
        await server.get_account(ctx=http_ctx(x_api_key="bad"))
    assert "x-api-key" in str(exc.value)
    assert "bad" not in str(exc.value)  # never echo the key back
