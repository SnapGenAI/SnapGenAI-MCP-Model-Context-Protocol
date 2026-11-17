import httpx
import respx

from snapgen_mcp import pricing, registry, server
from snapgen_mcp.pricing import _fetch_table as real_fetch_table

PRICES = "https://api.snapgen.ai/api/service-prices/all"


def row(name, price, unit="video", **kw):
    return {"model_name": name, "effective_price": price, "price_unit": unit, **kw}


def payload(*rows):
    return {"success": True, "categories": [{"category": "video", "families": [{"family": "x", "models": list(rows)}]}]}


API_ROWS = payload(
    row("grok-video", 15.0, resolution="480p", video_duration=6),
    row("grok-video", 24.0, resolution="480p", video_duration=10),
    row("sd-2-lower_lower", 6.0, service_mode="lower", resolution="720p", video_duration=5),
)
WEB_ROWS = payload(
    row("grok-video", 999.0, resolution="480p", video_duration=6),  # UAPI rows win when a model has them
    row("veo-3.1", 100.0, service_mode="stable", resolution="720p"),
    row("veo-3.1", 100.0, service_mode="unstable", resolution="720p"),  # same price twice: shown once
    row("veo-3.1-fast", 4.0, resolution="720p"),  # must not leak into veo-3.1
    row("seedance-2-omni_fast", 22.0, "second", resolution="720p"),  # mode this server does not offer
    row("seedance-2-omni_fast-vip", 29.0, "second", resolution="720p"),
    row("kling-video-2-6_standard", 8.0),  # unit says video, but Kling charges per second
    row("kling-video-3-0-edit_standard", 12.0),  # must not leak into kling-video-3-0
    row("kling-video-3-0_standard", 11.0, "second", resolution="720p"),
)


def mock_price_list(monkeypatch, api=API_ROWS, web=WEB_ROWS):
    monkeypatch.setattr(pricing, "_fetch_table", real_fetch_table)
    route = respx.get(PRICES)
    route.side_effect = lambda request: httpx.Response(
        200, json=api if request.url.params["platform"] == "api" else web)
    return route


def prices(model, table):
    return pricing.prices_for(registry.get_model(model), table)


@respx.mock
async def test_describe_model_shows_live_prices_and_caches(monkeypatch):
    route = mock_price_list(monkeypatch)
    d = await server.describe_model("grok-3")
    assert d["pricing"]["prices"] == [
        {"resolution": "480p", "duration_s": 6, "credits": 15, "per": "video"},
        {"resolution": "480p", "duration_s": 10, "credits": 24, "per": "video"},
    ]
    assert "estimated_credit" in d["pricing"]["exact_cost"]
    await server.describe_model("veo-3.1")
    assert route.call_count == 2  # one request per platform, then served from the cache


@respx.mock
async def test_model_matching_modes_and_units(monkeypatch):
    mock_price_list(monkeypatch)
    table = await pricing.price_table()
    assert prices("veo-3.1", table) == [{"resolution": "720p", "credits": 100, "per": "video"}]
    assert prices("seedance-2-omni", table) == [
        {"mode": "fast-vip", "resolution": "720p", "credits": 29, "per": "second"}]
    assert prices("kling-video-2-6", table) == [{"mode": "standard", "credits": 8, "per": "second"}]
    assert prices("kling-video-3-0", table) == [
        {"mode": "standard", "resolution": "720p", "credits": 11, "per": "second"}]
    assert prices("sd-2-lower", table) == [
        {"mode": "lower", "resolution": "720p", "duration_s": 5, "credits": 6, "per": "video"}]
    assert prices("grok-storyboard", table)[0]["per"] == "scene"
    assert prices("veo-extend", table) == []


@respx.mock
async def test_price_list_down_still_describes_the_model(monkeypatch):
    monkeypatch.setattr(pricing, "_fetch_table", real_fetch_table)
    respx.get(PRICES).mock(return_value=httpx.Response(503))
    d = await server.describe_model("veo-3.1")
    assert d["pricing"]["prices"] == "Live price list unavailable right now."
    assert d["options"]["resolution"]["choices"] == ["720p", "1080p"]


async def test_model_missing_from_list():
    pricing._cache[pricing._base_url()] = (float("inf"), {"api": {}, "web": {}})
    assert "Not in the public price list" in (await server.describe_model("veo-3.1"))["pricing"]["prices"]
    assert (await server.describe_model("veo-extend"))["pricing"]["prices"] == "Same as the original video's model."


def test_modes_follow_the_models_order_and_kling4_drops_the_repeated_resolution():
    table = {"api": {}, "web": {
        "gpt-image-2_high": [row("gpt-image-2_high", 16.0, "image", resolution="1K")],
        "gpt-image-2_low": [row("gpt-image-2_low", 3.0, "image", resolution="1K")],
        "kling-video-4-0_720p": [row("kling-video-4-0_720p", 23.0, "second", resolution="720p")],
    }}
    assert [p["mode"] for p in prices("gpt-image-2", table)] == ["low", "high"]
    assert prices("kling-video-4-0", table) == [{"mode": "720p", "credits": 23, "per": "second"}]
