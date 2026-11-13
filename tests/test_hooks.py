"""upload_media / get_upload and the hooks a hosting layer uses (client factory, upload backend)."""
from types import SimpleNamespace

import httpx
import pytest
import respx
from starlette.datastructures import Headers

from snapgen_mcp import server
from snapgen_mcp.client import SnapGenClient, SnapGenError

BASE = "https://api.snapgen.ai/uapi/v1"


def http_ctx(**headers):
    request = SimpleNamespace(headers=Headers({k.replace("_", "-"): v for k, v in headers.items()}))
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


STDIO = SimpleNamespace(request_context=SimpleNamespace(request=None))


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv("SNAPGEN_API_KEY", "local-key")
    monkeypatch.setenv("SNAPGEN_BASE_URL", "https://api.snapgen.ai")
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setattr(server, "_client_factory", None)
    monkeypatch.setattr(server, "_upload_backend", None)


@respx.mock
async def test_stdio_upload_sends_the_local_file(tmp_path):
    route = respx.post(f"{BASE}/uploads").mock(return_value=httpx.Response(200, json={
        "url": "https://cdn.example/a.png", "media_type": "image", "content_type": "image/png", "size": 4,
        "expires_at": None}))
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG")
    out = await server.upload_media(file_path=str(f), ctx=STDIO)
    assert out["url"] == "https://cdn.example/a.png" and out["status"] == "done"
    assert route.calls[0].request.headers["x-api-key"] == "local-key"
    assert b"\x89PNG" in route.calls[0].request.content


async def test_stdio_upload_needs_an_existing_path(tmp_path):
    with pytest.raises(SnapGenError, match="file_path"):
        await server.upload_media(ctx=STDIO)
    with pytest.raises(SnapGenError, match="File not found"):
        await server.upload_media(file_path=str(tmp_path / "missing.png"), ctx=STDIO)


async def test_http_upload_without_backend_says_to_use_a_url():
    with pytest.raises(SnapGenError, match="does not accept uploads"):
        await server.upload_media(ctx=http_ctx(x_api_key="k"))
    with pytest.raises(SnapGenError, match="only for hosted uploads"):
        await server.get_upload("x", ctx=http_ctx(x_api_key="k"))


async def test_upload_backend_receives_the_callers_key():
    seen = {}

    class Backend:
        async def create(self, api_key, request):
            seen["create"] = api_key
            return {"upload_id": "u1", "upload_url": "https://h/upload/u1"}

        async def get(self, upload_id, api_key):
            seen["get"] = (upload_id, api_key)
            return {"upload_id": upload_id, "status": "done", "url": "https://cdn/x"}

    server.set_upload_backend(Backend())
    assert (await server.upload_media(ctx=http_ctx(x_api_key="caller")))["upload_id"] == "u1"
    assert (await server.get_upload("u1", ctx=http_ctx(x_api_key="caller")))["url"] == "https://cdn/x"
    assert seen == {"create": "caller", "get": ("u1", "caller")}


@respx.mock
async def test_client_factory_replaces_header_lookup():
    route = respx.get(f"{BASE}/account").mock(return_value=httpx.Response(200, json={"user_credit": {}}))
    server.set_client_factory(lambda request: SnapGenClient(api_key="from-factory"))
    await server.get_account(ctx=http_ctx(x_api_key="header-key"))
    assert route.calls[0].request.headers["x-api-key"] == "from-factory"


def test_build_http_app_mounts_extra_routes_and_middleware():
    from starlette.middleware import Middleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    calls = []

    class Mark:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            calls.append(scope.get("path"))
            await self.app(scope, receive, send)

    saved = server.mcp._session_manager
    server.mcp._session_manager = None
    try:
        app = server.build_http_app(routes=[Route("/extra", lambda r: PlainTextResponse("hi"))],
                                    middleware=[Middleware(Mark)])
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            assert client.get("/extra").text == "hi"
        assert "/extra" in calls
    finally:
        server.mcp._session_manager = saved
