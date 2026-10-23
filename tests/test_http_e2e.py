"""End to end: a real `snapgen-mcp --transport http` process, a fake uapi that records every request it
receives, and the official MCP client talking to the server over HTTP.

This is what proves the per-request key really arrives through FastMCP's context, which the unit tests
only simulate.
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

OWNER_KEY = "server-owner-key"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeUapi:
    """Stands in for api.snapgen.ai/uapi/v1 and records the key each request arrived with."""

    def __init__(self):
        self.seen: list[dict] = []
        self.app = Starlette(routes=[
            Route("/uapi/v1/account", self.account),
            Route("/uapi/v1/generate_image", self.generate_image, methods=["POST"]),
        ])

    async def account(self, request):
        key = request.headers.get("x-api-key")
        self.seen.append({"path": "account", "key": key})
        if key == "bad":
            return JSONResponse({"detail": {"error_code": "API_KEY_NOT_FOUND"}}, status_code=404)
        return JSONResponse({"full_name": f"user-of-{key}", "plan_id": "P1",
                             "user_credit": {"available_credit": 100, "locked_credit": 0}})

    async def generate_image(self, request):
        key = request.headers.get("x-api-key")
        form = dict(await request.form())
        self.seen.append({"path": "generate_image", "key": key, "form": form})
        return JSONResponse({"uuid": "job-1", "model_name": form.get("model"), "estimated_credit": 3})


class Serve(threading.Thread):
    def __init__(self, app, port):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True
        self.join(timeout=5)


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    uapi = FakeUapi()
    uapi_port, mcp_port = free_port(), free_port()
    fake = Serve(uapi.app, uapi_port)
    fake.start()
    while not fake.server.started:
        time.sleep(0.05)

    log_path = tmp_path_factory.mktemp("logs") / "server.log"
    env = {**os.environ, "SNAPGEN_BASE_URL": f"http://127.0.0.1:{uapi_port}", "SNAPGEN_API_KEY": OWNER_KEY,
           "PYTHONUNBUFFERED": "1"}
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "snapgen_mcp.server", "--transport", "http", "--port", str(mcp_port)],
            env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{mcp_port}"
    try:
        deadline = time.time() + 20
        while True:
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None or time.time() > deadline:
                raise RuntimeError(f"MCP server did not start:\n{log_path.read_text(errors='replace')}")
            time.sleep(0.2)
        yield {"url": url, "uapi": uapi, "log": log_path}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        fake.stop()


async def call(stack, tool, args=None, headers=None):
    async with streamablehttp_client(f"{stack['url']}/mcp", headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, args or {})


def text(result) -> str:
    return result.content[0].text


async def test_health(stack):
    assert httpx.get(f"{stack['url']}/health").text == "OK"


async def test_lists_tools_without_exposing_internal_context_param(stack):
    async with streamablehttp_client(f"{stack['url']}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
    names = {t.name for t in tools}
    assert {"get_account", "generate_image", "generate_video", "get_generation", "list_models"} <= names
    for t in tools:
        assert "ctx" not in t.inputSchema.get("properties", {}), t.name


async def test_x_api_key_reaches_uapi(stack):
    res = await call(stack, "get_account", headers={"x-api-key": "key-a"})
    assert not res.isError
    assert json.loads(text(res))["name"] == "user-of-key-a"


async def test_bearer_token_works_too(stack):
    res = await call(stack, "get_account", headers={"Authorization": "Bearer key-b"})
    assert json.loads(text(res))["name"] == "user-of-key-b"


async def test_missing_key_is_a_clear_error_and_never_uses_the_owner_key(stack):
    before = len(stack["uapi"].seen)
    res = await call(stack, "get_account")
    assert res.isError and "Missing API key" in text(res)
    assert len(stack["uapi"].seen) == before  # no upstream call at all
    assert all(s["key"] != OWNER_KEY for s in stack["uapi"].seen)


async def test_invalid_key_message_points_to_the_header(stack):
    res = await call(stack, "get_account", headers={"x-api-key": "bad"})
    assert res.isError and "x-api-key" in text(res)


async def test_concurrent_callers_never_see_each_others_account(stack):
    keys = [f"k{i}" for i in range(12)]
    results = await asyncio.gather(*(call(stack, "get_account", headers={"x-api-key": k}) for k in keys))
    assert [json.loads(text(r))["name"] for r in results] == [f"user-of-{k}" for k in keys]


async def test_generate_image_forwards_key_and_form_fields(stack):
    res = await call(stack, "generate_image",
                     {"prompt": "a quiet street", "model": "nano-banana-2-lite", "options": {"aspect_ratio": "16:9"}},
                     headers={"x-api-key": "key-img"})
    assert not res.isError
    out = json.loads(text(res))
    assert out["uuid"] == "job-1" and out["estimated_credit"] == 3
    sent = [s for s in stack["uapi"].seen if s["path"] == "generate_image"][-1]
    assert sent["key"] == "key-img"
    assert sent["form"]["model"] == "nano-banana-2-lite" and sent["form"]["aspect_ratio"] == "16:9"


async def test_validation_errors_do_not_reach_uapi(stack):
    before = len(stack["uapi"].seen)
    res = await call(stack, "generate_image", {"prompt": "x", "model": "veo-2"}, headers={"x-api-key": "key-v"})
    assert res.isError and "generate_video" in text(res)
    assert len(stack["uapi"].seen) == before


async def test_server_logs_never_contain_api_keys(stack):
    log = stack["log"].read_text(errors="replace")
    for secret in ("key-a", "key-b", "key-img", "key-v", OWNER_KEY, "Bearer"):
        assert secret not in log, f"{secret!r} leaked into server log"


def test_container_healthcheck_exit_codes(stack, monkeypatch):
    from snapgen_mcp import healthcheck

    monkeypatch.setenv("SNAPGEN_MCP_PORT", stack["url"].rsplit(":", 1)[1])
    assert healthcheck.main() == 0
    monkeypatch.setenv("SNAPGEN_MCP_PORT", str(free_port()))  # nothing listens here
    assert healthcheck.main() == 1


# ------------------------------------------------------------------ endpoint method and Host handling
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
MCP_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def initialize_status(url, host=None):
    headers = dict(MCP_HEADERS, **({"Host": host} if host else {}))
    return httpx.post(f"{url}/mcp", json=INIT, headers=headers, timeout=10).status_code


import contextlib  # noqa: E402


@contextlib.contextmanager
def spawn(extra_args=(), extra_env=None):
    """A short-lived server on its own port, for tests that need a different binding or environment."""
    port = free_port()
    env = {k: v for k, v in os.environ.items() if k != "SNAPGEN_MCP_ALLOWED_HOSTS"}
    env.update({"PYTHONUNBUFFERED": "1", **(extra_env or {})})
    proc = subprocess.Popen(
        [sys.executable, "-m", "snapgen_mcp.server", "--transport", "http", "--port", str(port), *extra_args],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 20
        while True:
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None or time.time() > deadline:
                raise RuntimeError("test server did not start")
            time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_get_and_delete_on_the_mcp_endpoint_are_405_with_allow_post(stack, method, path):
    r = httpx.request(method, f"{stack['url']}{path}", headers={"Accept": "text/event-stream"}, timeout=5)
    assert r.status_code == 405
    assert r.headers["allow"] == "POST"


def test_405_needs_no_key_and_cannot_hold_a_connection_open(stack):
    start = time.time()
    r = httpx.get(f"{stack['url']}/mcp", headers={"Accept": "text/event-stream"}, timeout=5)
    assert r.status_code == 405 and time.time() - start < 2  # answered at once, no idle stream


def test_post_and_health_are_unaffected_by_the_405_rule(stack):
    assert initialize_status(stack["url"]) == 200
    assert httpx.get(f"{stack['url']}/health").status_code == 200


def test_loopback_binding_rejects_a_foreign_host_header(stack):
    assert initialize_status(stack["url"], host="mcp.example.com") == 421


def test_hosted_binding_accepts_the_public_host_a_proxy_forwards():
    with spawn(["--host", "0.0.0.0"]) as url:
        assert initialize_status(url, host="mcp.example.com") == 200
        assert initialize_status(url, host="anything.else.test:8443") == 200


def test_allow_list_accepts_only_the_listed_host():
    with spawn(["--host", "0.0.0.0"], {"SNAPGEN_MCP_ALLOWED_HOSTS": "mcp.example.com"}) as url:
        assert initialize_status(url, host="mcp.example.com") == 200
        assert initialize_status(url, host="mcp.example.com:443") == 200
        assert initialize_status(url, host="evil.example.org") == 421
        assert httpx.get(f"{url}/health", headers={"Host": "evil.example.org"}).status_code == 200  # health stays open
