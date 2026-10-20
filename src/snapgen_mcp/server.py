"""snapgen.ai MCP server (local stdio MVP)."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .client import SnapGenClient

mcp = FastMCP("snapgen")

IMAGE_MODELS = ["nano-banana-pro", "nano-banana-2", "nano-banana-2-lite"]
VIDEO_MODELS = ["veo-3.1", "veo-3.1-fast", "veo-3.1-lite", "veo-2", "omni-flash"]

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
async def list_models() -> dict:
    """List the image and video models this server can use."""
    return {"image_models": IMAGE_MODELS, "video_models": VIDEO_MODELS}


@mcp.tool()
async def generate_image(
    prompt: str,
    model: str = "nano-banana-pro",
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = "1:1",
    resolution: Literal["1K", "2K", "4K"] = "1K",
    style: str | None = None,
    reference_image_urls: list[str] | None = None,
) -> dict:
    """Start an image generation. COSTS CREDITS: tell the user before calling.

    Returns a job uuid immediately; poll get_generation for the image URL.
    """
    resp = await get_client().generate_image(
        prompt=prompt, model=model, aspect_ratio=aspect_ratio, resolution=resolution,
        style=style, file_urls=reference_image_urls,
    )
    return _job(resp)


@mcp.tool()
async def generate_video(
    prompt: str,
    model: str = "veo-3.1-fast",
    duration: Literal[4, 6, 8, 10] = 8,
    resolution: Literal["720p", "1080p"] = "720p",
    aspect_ratio: Literal["16:9", "9:16"] = "16:9",
    reference_image_urls: list[str] | None = None,
) -> dict:
    """Start a video generation (Veo family). COSTS CREDITS: tell the user before calling.

    Duration 10 is only for omni-flash; veo-2 supports 720p only.
    Returns a job uuid immediately; poll get_generation for the video URL.
    """
    resp = await get_client().generate_video_veo(
        prompt=prompt, model=model, duration=duration, resolution=resolution,
        aspect_ratio=aspect_ratio, ref_images=reference_image_urls,
    )
    return _job(resp)


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
