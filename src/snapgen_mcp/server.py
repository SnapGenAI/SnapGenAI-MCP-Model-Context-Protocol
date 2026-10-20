"""snapgen.ai MCP server (local stdio MVP)."""
from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import registry
from .client import SnapGenClient, SnapGenError

mcp = FastMCP("snapgen")

_client: SnapGenClient | None = None


def get_client() -> SnapGenClient:
    global _client
    if _client is None:
        _client = SnapGenClient()
    return _client


def _job(resp: dict) -> dict:
    """Shrink a generation response to what the model needs to poll later."""
    return {
        "uuid": resp.get("uuid"),
        "status": "submitted",
        "model": resp.get("model_name"),
        "estimated_credit": resp.get("estimated_credit"),
        "next_step": "Call get_generation with this uuid until done is true. Videos can take several minutes.",
    }


def _summarize(h: dict) -> dict:
    status_desc = (h.get("status_desc") or "").upper()
    # Observed live: status 1 = processing, 2 = completed, 3 = failed (status_desc may be empty or free text).
    failed = bool(h.get("error_code")) or h.get("status") == 3 or status_desc in {"FAILED", "ERROR"}
    done = not failed and (h.get("status") == 2 or status_desc == "COMPLETED" or h.get("status_percentage") == 100)
    out: dict[str, Any] = {
        "uuid": h.get("uuid"),
        "type": h.get("type"),
        "model": h.get("model_name"),
        "prompt": h.get("input_text"),
        "status": "failed" if failed else "completed" if done else "processing",
        "progress_percent": h.get("status_percentage"),
        "done": done,
        "failed": failed,
        "credits_used": h.get("used_credit"),
        "created_at": h.get("created_at"),
        "expires_at": h.get("expired_at"),
    }
    if failed:
        out["error"] = h.get("error_message") or h.get("error_code")
    if done:
        out["image_urls"] = [i.get("image_url") for i in h.get("generated_image") or [] if i.get("image_url")]
        out["video_urls"] = [v.get("video_url") for v in h.get("generated_video") or [] if v.get("video_url")]
    return out


@mcp.tool()
async def get_account() -> dict:
    """Show the connected snapgen.ai account: plan and credit balance (available and locked)."""
    acct = await get_client().account()
    credit = acct.get("user_credit") or {}
    return {
        "name": acct.get("full_name"),
        "plan_id": acct.get("plan_id"),
        "available_credit": credit.get("available_credit"),
        "locked_credit": credit.get("locked_credit"),
    }


@mcp.tool()
async def list_models(kind: Literal["image", "video", "extend", "storyboard"] | None = None,
                      family: str | None = None) -> dict:
    """List available models, optionally filtered by kind (image, video, extend, storyboard) or family.

    Families: nano-banana, grok, gpt-image, vela, veo, seedance, kling, minimax, flux, muse.
    Use describe_model for a model's exact options before generating.
    """
    items = [
        {"id": m.id, "family": m.family, "kind": m.kind, "premium": m.premium, "summary": m.summary}
        for m in registry.all_models()
        if (kind is None or m.kind == kind) and (family is None or m.family == family)
    ]
    return {"count": len(items), "models": items}


@mcp.tool()
async def describe_model(model: str) -> dict:
    """Show one model's options (with allowed values), reference-media limits, pricing and notes."""
    return registry.get_model(model).describe()


@mcp.tool()
async def generate_image(
    prompt: str,
    model: str = "nano-banana-pro",
    options: dict[str, Any] | None = None,
    reference_image_urls: list[str] | None = None,
    reference_history_uuids: list[str] | None = None,
) -> dict:
    """Start an image generation. COSTS CREDITS: tell the user before calling.

    `options` holds model-specific settings such as aspect_ratio or resolution; call describe_model
    first if unsure what a model accepts. Returns a job uuid; poll get_generation for the image URL(s).
    """
    spec = registry.get_model(model, "image")
    endpoint, fields = registry.build_request(
        spec, prompt, options, image_urls=reference_image_urls, history_uuids=reference_history_uuids)
    return _job(await get_client().submit(endpoint, fields))


@mcp.tool()
async def generate_video(
    prompt: str,
    model: str = "veo-3.1-fast",
    options: dict[str, Any] | None = None,
    reference_image_urls: list[str] | None = None,
    reference_video_urls: list[str] | None = None,
    reference_audio_urls: list[str] | None = None,
    reference_history_uuids: list[str] | None = None,
) -> dict:
    """Start a video generation. COSTS CREDITS: tell the user before calling.

    `options` holds model-specific settings such as duration, resolution or aspect_ratio. Limits differ a
    lot between models (Kling motion models REQUIRE a reference video), so call describe_model first
    if unsure. Returns a job uuid; poll get_generation for the video URL. Videos take 1-5+ minutes.
    """
    spec = registry.get_model(model, "video")
    endpoint, fields = registry.build_request(
        spec, prompt, options, image_urls=reference_image_urls, history_uuids=reference_history_uuids,
        video_urls=reference_video_urls, audio_urls=reference_audio_urls)
    return _job(await get_client().submit(endpoint, fields))


@mcp.tool()
async def extend_video(
    model: Literal["veo-extend", "grok-extend", "grok-1.5-lite-extend", "seedance-extend"],
    video_uuid: str,
    prompt: str,
    options: dict[str, Any] | None = None,
) -> dict:
    """Continue an existing video from its last frame. COSTS CREDITS: tell the user before calling.

    `video_uuid` is the uuid of a completed video made with the matching family (veo, grok, seedance).
    Describe what happens next in `prompt`. Returns a job uuid; poll get_generation.
    """
    spec = registry.get_model(model, "extend")
    endpoint, fields = registry.build_request(spec, prompt, options, history_uuids=[video_uuid])
    return _job(await get_client().submit(endpoint, fields))


@mcp.tool()
async def generate_storyboard(
    scenes: list[dict[str, Any]],
    aspect_ratio: Literal["landscape", "portrait", "square"] = "landscape",
    resolution: Literal["480p", "720p"] = "480p",
) -> dict:
    """Make a multi-scene Grok video (2-10 scenes, max 45s total). COSTS CREDITS per scene.

    Each scene is {"prompt": str, "duration": 6 or 10}. The last frame of each scene seeds the next,
    and all clips are merged into one video. Returns a job uuid; poll get_generation.
    """
    if not 2 <= len(scenes) <= 10:
        raise SnapGenError("A storyboard needs between 2 and 10 scenes.")
    for i, sc in enumerate(scenes, 1):
        if not str(sc.get("prompt", "")).strip():
            raise SnapGenError(f"Scene {i} needs a prompt.")
        if sc.get("duration") not in (6, 10):
            raise SnapGenError(f"Scene {i}: duration must be 6 or 10 seconds.")
    if sum(sc["duration"] for sc in scenes) > 45:
        raise SnapGenError("Total storyboard duration cannot exceed 45 seconds.")
    spec = registry.get_model("grok-storyboard", "storyboard")
    fields = {"scenes": json.dumps(scenes), "model": spec.send_model,
              "aspect_ratio": aspect_ratio, "resolution": resolution}
    return _job(await get_client().submit(spec.endpoint, fields))


@mcp.tool()
async def get_generation(uuid: str) -> dict:
    """Check a generation by uuid. When done is true, image_urls or video_urls hold the results."""
    return _summarize(await get_client().get_history(uuid))


@mcp.tool()
async def list_generations(
    type: Literal["all", "image", "video"] = "all", page: int = 1, per_page: int = 10
) -> dict:
    """List recent generations, newest first."""
    resp = await get_client().list_histories(filter_by=type, page=page, items_per_page=per_page)
    return {
        "total": resp.get("total"),
        "items": [
            {k: v for k, v in _summarize(h).items() if k in
             ("uuid", "type", "model", "prompt", "status", "done", "failed", "credits_used", "created_at")}
            for h in resp.get("result") or []
        ],
    }


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
