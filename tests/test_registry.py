import httpx
import pytest
import respx

from snapgen_mcp import registry, server
from snapgen_mcp.client import SnapGenClient, SnapGenError

BASE = "https://api.snapgen.ai/uapi/v1"


@pytest.fixture(autouse=True)
def client(monkeypatch):
    monkeypatch.setattr(server, "_client", SnapGenClient(api_key="k", base_url="https://api.snapgen.ai"))


def build(model, prompt="a fox in the snow, cinematic", options=None, **kw):
    return registry.build_request(registry.get_model(model), prompt, options, **kw)


def test_every_spec_is_internally_consistent():
    for m in registry.all_models():
        assert m.kind in registry.KINDS and m.endpoint.startswith("/")
        for name, p in m.params.items():
            if p.default is not None and p.choices is not None:
                assert p.default in p.choices, (m.id, name)
        m.describe()  # must not raise


def test_model_counts_and_families():
    models = registry.all_models()
    assert len([m for m in models if m.kind in ("image", "video")]) == 35
    assert {m.family for m in models} == {"nano-banana", "grok", "gpt-image", "vela", "veo", "seedance",
                                          "kling", "minimax", "flux", "muse"}


def test_veo_request():
    ep, f = build("veo-3.1-lite", options={"duration": 4, "resolution": "720p"},
                  image_urls=["https://x/a.png"])
    assert ep == "/video-gen/veo"
    assert f["model"] == "veo-3.1-lite" and f["duration"] == 4 and f["ref_images"] == ["https://x/a.png"]


def test_veo2_rejects_1080p():
    with pytest.raises(SnapGenError, match="resolution"):
        build("veo-2", options={"resolution": "1080p"})


def test_unknown_option_lists_allowed():
    with pytest.raises(SnapGenError, match="Allowed options"):
        build("nano-banana-pro", options={"bogus": 1})


def test_grok_lower_has_no_model_field_and_caps_refs():
    ep, f = build("grok-lower", options={"duration": 10}, image_urls=["u1", "u2"])
    assert ep == "/video-gen/grok-lower" and "model" not in f and f["file_urls"] == ["u1", "u2"]
    with pytest.raises(SnapGenError, match="at most 5"):
        build("grok-lower", image_urls=[f"u{i}" for i in range(6)])


def test_grok_rejects_mixing_url_and_history():
    with pytest.raises(SnapGenError, match="either"):
        build("grok-3", image_urls=["u"], history_uuids=["h"])


def test_kling_motion_requires_video_and_long_prompt():
    with pytest.raises(SnapGenError, match="at least 1 reference videos"):
        build("kling-video-motion-3", image_urls=["u"])
    with pytest.raises(SnapGenError, match="at least 10"):
        build("kling-video-3-0", prompt="short")
    ep, f = build("kling-video-motion-3", video_urls=["https://x/v.mp4"], image_urls=["https://x/i.png"])
    assert "duration" not in registry.get_model("kling-video-motion-3").params
    assert f["ref_videos"] == ["https://x/v.mp4"]


def test_minimax_always_sends_required_mode_and_caps_total():
    _, f = build("minimax-h3")
    assert f["mode"] == "standard"
    # per-type caps (9 + 2 + 2) already sum to the 13 total, so exceeding any single cap is what trips
    with pytest.raises(SnapGenError, match="at most 9"):
        build("minimax-h3", image_urls=["i"] * 10)
    assert build("minimax-h3", image_urls=["i"] * 9, video_urls=["v"] * 2, audio_urls=["a"] * 2)


def test_seedance_per_model_limits():
    assert build("sd-2-lower", options={"duration": 5})[1]["duration"] == 5
    with pytest.raises(SnapGenError, match="duration"):
        build("sd-2-lower", options={"duration": 7})
    with pytest.raises(SnapGenError, match="does not support reference videos"):
        build("seedance-2-mini", video_urls=["v"])
    assert build("seedance-2-5-omni", options={"duration": 30})[1]["duration"] == 30


def test_image_models_without_url_support():
    with pytest.raises(SnapGenError, match="does not support reference images"):
        build("gpt-image-2", image_urls=["u"])
    assert build("gpt-image-2", history_uuids=["h"])[1]["ref_history"] == ["h"]


def test_wrong_kind_points_to_right_tool():
    with pytest.raises(SnapGenError, match="generate_video"):
        registry.get_model("veo-2", "image")
    with pytest.raises(SnapGenError, match="Unknown model"):
        registry.get_model("nope")


def test_bool_and_int_coercion():
    _, f = build("grok-1.5-lite", options={"skip_audio": "true", "duration": "10"})
    assert f["skip_audio"] is True and f["duration"] == 10


async def test_list_and_describe_tools():
    out = await server.list_models(kind="video", family="seedance")
    assert out["count"] == 5 and all(m["family"] == "seedance" for m in out["models"])
    d = await server.describe_model("kling-video-2-6")
    assert "professional_audio" in d["options"]["mode"]["choices"]


@respx.mock
async def test_generate_video_sends_form_to_right_endpoint():
    route = respx.post(f"{BASE}/video-gen/seedance").mock(return_value=httpx.Response(
        200, json={"uuid": "u1", "model_name": "sd-2-lower", "estimated_credit": 20}))
    out = await server.generate_video("a dog surfing", model="sd-2-lower", options={"duration": 5})
    body = route.calls[0].request.content.decode()
    assert "model=sd-2-lower" in body and "duration=5" in body
    assert out["uuid"] == "u1" and out["estimated_credit"] == 20


@respx.mock
async def test_extend_video():
    route = respx.post(f"{BASE}/video-extend/veo").mock(return_value=httpx.Response(200, json={"uuid": "u2"}))
    await server.extend_video("veo-extend", "vid-uuid", "the camera pans up")
    assert "ref_history=vid-uuid" in route.calls[0].request.content.decode()


@respx.mock
async def test_storyboard_validation_and_send():
    scenes = [{"prompt": "a", "duration": 6}, {"prompt": "b", "duration": 10}]
    route = respx.post(f"{BASE}/video-storyboard/grok").mock(return_value=httpx.Response(200, json={"uuid": "u3"}))
    await server.generate_storyboard(scenes)
    assert "scenes=" in route.calls[0].request.content.decode()
    with pytest.raises(SnapGenError, match="between 2 and 10"):
        await server.generate_storyboard(scenes[:1])
    with pytest.raises(SnapGenError, match="45"):
        await server.generate_storyboard([{"prompt": "x", "duration": 10}] * 5)


@respx.mock
async def test_premium_required_message():
    respx.post(f"{BASE}/imagen/vela").mock(return_value=httpx.Response(
        403, json={"detail": {"error_code": "PREMIUM_PLAN_REQUIRED"}}))
    with pytest.raises(SnapGenError, match="Premium"):
        await server.generate_image("a cat", model="vela-image")


def test_seedance_always_sends_mode():
    assert build("sd-2-lower")[1]["mode"] == "lower"
    assert build("seedance-2-omni")[1]["mode"] == "fast-vip"
    assert build("seedance-2-omni", options={"mode": "pro-vip"})[1]["mode"] == "pro-vip"


def test_kling_image_required_models_and_removed_16():
    with pytest.raises(SnapGenError, match="at least 1 reference images"):
        build("kling-video-2-5")
    assert build("kling-video-2-5", image_urls=["https://x/i.png"])[1]["ref_images"] == ["https://x/i.png"]
    with pytest.raises(SnapGenError, match="Unknown model"):
        registry.get_model("kling-video-1-6-5s")


def test_every_priced_model_exists_and_has_observed_pricing():
    assert registry.get_model("veo-3.1").pricing.startswith("Observed estimate")
    assert "332" in registry.get_model("seedance-2-5-omni").pricing


def test_kling4_models_resolution_is_the_mode():
    ep, f = build("kling-video-4-0", options={"mode": "1080p", "duration": 30, "mode_image": "ingredient"},
                  image_urls=["https://x/a.png"], video_urls=["https://x/v1.mp4", "https://x/v2.mp4"])
    assert ep == "/video-gen/kling" and f["model"] == "kling-video-4-0" and f["mode"] == "1080p"
    assert f["duration"] == 30 and f["mode_image"] == "ingredient" and len(f["ref_videos"]) == 2
    with pytest.raises(SnapGenError, match="duration"):
        build("kling-video-4-0", options={"duration": 31})
    with pytest.raises(SnapGenError, match="at most 2 reference videos"):
        build("kling-video-4-0", video_urls=["a", "b", "c"])
    with pytest.raises(SnapGenError, match="at most 10 reference images"):
        build("kling-video-4-0", image_urls=["i"] * 11)
    with pytest.raises(SnapGenError, match="mode"):
        build("kling-video-4-0", options={"mode": "standard"})  # the old mode names do not apply to 4.0


def test_kling4_flash_is_720p_and_20s_max():
    assert build("kling-video-4-0-flash", options={"duration": 20})[1]["duration"] == 20
    with pytest.raises(SnapGenError, match="mode"):
        build("kling-video-4-0-flash", options={"mode": "1080p"})
    with pytest.raises(SnapGenError, match="duration"):
        build("kling-video-4-0-flash", options={"duration": 21})


def test_kling4_motion_needs_one_image_and_one_video_and_ignores_duration():
    spec = registry.get_model("kling-video-motion-4")
    assert "duration" not in spec.params and "aspect_ratio" not in spec.params
    with pytest.raises(SnapGenError, match="at least 1 reference videos"):
        build("kling-video-motion-4", image_urls=["i"])
    with pytest.raises(SnapGenError, match="at least 1 reference images"):
        build("kling-video-motion-4", video_urls=["v"])
    with pytest.raises(SnapGenError, match="at most 1 reference videos"):
        build("kling-video-motion-4", image_urls=["i"], video_urls=["v1", "v2"])
    _, f = build("kling-video-motion-4", options={"mode": "1080p"}, image_urls=["i"], video_urls=["v"])
    assert f["mode"] == "1080p" and f["ref_images"] == ["i"] and f["ref_videos"] == ["v"]


def test_kling4_prompt_must_be_at_least_ten_characters():
    with pytest.raises(SnapGenError, match="at least 10"):
        build("kling-video-4-0", prompt="too short")


def test_kling_25_and_26_accept_only_5_or_10_seconds_but_30_takes_3_to_15():
    for model in ("kling-video-2-5", "kling-video-2-6"):
        for ok in (5, 10):
            assert build(model, options={"duration": ok}, image_urls=["i"])[1]["duration"] == ok
        for bad in (3, 4, 7, 15):
            with pytest.raises(SnapGenError, match="duration"):
                build(model, options={"duration": bad}, image_urls=["i"])
    assert build("kling-video-3-0", options={"duration": 3})[1]["duration"] == 3
    assert build("kling-video-3-0", options={"duration": 15})[1]["duration"] == 15


def test_flux_and_minimax_pricing_notes_state_the_per_second_rate():
    assert "34 credits/s" in registry.get_model("flux-3").pricing
    assert "30 credits/s" in registry.get_model("minimax-h3").pricing
