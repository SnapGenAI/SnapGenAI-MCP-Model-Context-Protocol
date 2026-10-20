import httpx
import pytest
import respx

from snapgen_mcp import server
from snapgen_mcp.client import SnapGenClient, SnapGenError

BASE = "https://api.snapgen.ai/uapi/v1"


@pytest.fixture(autouse=True)
def client(monkeypatch):
    c = SnapGenClient(api_key="test-key", base_url="https://api.snapgen.ai")
    monkeypatch.setattr(server, "_client", c)
    return c


@respx.mock
async def test_get_account():
    route = respx.get(f"{BASE}/account").mock(return_value=httpx.Response(200, json={
        "full_name": "Demo", "plan_id": "FP0001",
        "user_credit": {"available_credit": 100, "locked_credit": 5}}))
    out = await server.get_account()
    assert out == {"name": "Demo", "plan_id": "FP0001", "available_credit": 100, "locked_credit": 5}
    assert route.calls[0].request.headers["x-api-key"] == "test-key"


@respx.mock
async def test_generate_image_returns_job():
    respx.post(f"{BASE}/generate_image").mock(return_value=httpx.Response(200, json={
        "uuid": "abc", "status_desc": "Processing", "model_name": "nano-banana-pro"}))
    out = await server.generate_image(prompt="a fox")
    assert out["uuid"] == "abc" and "get_generation" in out["next_step"]


@respx.mock
async def test_get_generation_done_has_urls():
    respx.get(f"{BASE}/history/abc").mock(return_value=httpx.Response(200, json={
        "uuid": "abc", "type": "video", "status": 2, "status_desc": "COMPLETED",
        "error_code": "", "generated_video": [{"video_url": "https://x/v.mp4"}]}))
    out = await server.get_generation("abc")
    assert out["done"] and out["video_urls"] == ["https://x/v.mp4"]


@respx.mock
async def test_get_generation_failed():
    respx.get(f"{BASE}/history/abc").mock(return_value=httpx.Response(200, json={
        "uuid": "abc", "status": 3, "status_desc": "FAILED",
        "error_code": "X", "error_message": "bad prompt"}))
    out = await server.get_generation("abc")
    assert out["failed"] and not out["done"] and out["error"] == "bad prompt"


@respx.mock
async def test_insufficient_credit_message():
    respx.post(f"{BASE}/video-gen/veo").mock(return_value=httpx.Response(
        400, json={"detail": {"error_code": "NOT_ENOUGH_CREDIT", "error_message": "x"}}))
    with pytest.raises(SnapGenError, match="Top up"):
        await server.generate_video(prompt="a lake")


@respx.mock
async def test_bad_key():
    respx.get(f"{BASE}/account").mock(return_value=httpx.Response(
        404, json={"detail": {"error_code": "API_KEY_NOT_FOUND"}}))
    with pytest.raises(SnapGenError, match="SNAPGEN_API_KEY"):
        await server.get_account()


async def test_missing_key(monkeypatch):
    monkeypatch.setattr(server, "_client", SnapGenClient(api_key=""))
    monkeypatch.delenv("SNAPGEN_API_KEY", raising=False)
    server._client.api_key = ""
    with pytest.raises(SnapGenError, match="not set"):
        await server.get_account()
