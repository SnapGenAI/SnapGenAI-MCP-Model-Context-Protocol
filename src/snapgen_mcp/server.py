"""snapgen.ai MCP server: stdio for local use, streamable HTTP for hosting."""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Literal

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from collections.abc import Callable, Sequence
from typing import Protocol

from starlette.middleware import Middleware
from starlette.routing import BaseRoute

from . import registry, ui
from .auth import MISSING_KEY_MESSAGE, extract_api_key
from .client import SnapGenClient, SnapGenError

# Stateless: every HTTP request is self-contained (it carries its own key), so no session affinity is needed
# and the server can sit behind any load balancer. These settings only affect the HTTP transport.
mcp = FastMCP("snapgen", stateless_http=True, json_response=True)

_client: SnapGenClient | None = None  # stdio / dev only

# Hosts the inline result view may load generated media from (signed storage links).
DEFAULT_MEDIA_DOMAINS = "https://*.r2.dev https://*.r2.cloudflarestorage.com https://*.snapgen.ai https://*.geminigen.ai"


def _http_request(ctx: Context | None) -> Request | None:
    """The incoming HTTP request when running over HTTP, else None (stdio, or called outside a request)."""
    if ctx is None:
        return None
    try:
        return ctx.request_context.request  # type: ignore[return-value]
    except ValueError:
        return None


# Hooks for a hosting layer that wraps this package (sign-in, upload storage). Plain local and self-hosted use
# never sets them.

ClientFactory = Callable[[Request], SnapGenClient]


class UploadBackend(Protocol):
    """Where hosted uploads go: opens an upload slot, then reports what was uploaded into it."""

    async def create(self, api_key: str, request: Request) -> dict[str, Any]: ...

    async def get(self, upload_id: str, api_key: str) -> dict[str, Any]: ...


_client_factory: ClientFactory | None = None
_upload_backend: UploadBackend | None = None


def set_client_factory(factory: ClientFactory | None) -> None:
    """Replace how an HTTP request becomes a SnapGenClient (e.g. resolve an OAuth token to the user's key)."""
    global _client_factory
    _client_factory = factory


def set_upload_backend(backend: UploadBackend | None) -> None:
    """Enable upload_media / get_upload over HTTP."""
    global _upload_backend
    _upload_backend = backend


def get_client(ctx: Context | None = None) -> SnapGenClient:
    """Client for this call. Over HTTP the key comes from the request and only from the request."""
    request = _http_request(ctx)
    if request is not None:
        if _client_factory is not None:
            return _client_factory(request)
        key = extract_api_key(request.headers)
        if not key:
            raise SnapGenError(MISSING_KEY_MESSAGE)
        return SnapGenClient(api_key=key)
    global _client
    if _client is None:
        _client = SnapGenClient()
    return _client


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


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
    done = not failed and (h.get("status") == 2 or status_desc == "COMPLETED")
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
async def get_account(ctx: Context | None = None) -> dict:
    """Show the connected snapgen.ai account: plan and credit balance (available and locked)."""
    acct = await get_client(ctx).account()
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
    ctx: Context | None = None,
) -> dict:
    """Start an image generation. COSTS CREDITS: tell the user before calling.

    `options` holds model-specific settings such as aspect_ratio or resolution; call describe_model
    first if unsure what a model accepts. Returns a job uuid; poll get_generation for the image URL(s).
    """
    spec = registry.get_model(model, "image")
    endpoint, fields = registry.build_request(
        spec, prompt, options, image_urls=reference_image_urls, history_uuids=reference_history_uuids)
    return _job(await get_client(ctx).submit(endpoint, fields))


@mcp.tool()
async def generate_video(
    prompt: str,
    model: str = "veo-3.1-fast",
    options: dict[str, Any] | None = None,
    reference_image_urls: list[str] | None = None,
    reference_video_urls: list[str] | None = None,
    reference_audio_urls: list[str] | None = None,
    reference_history_uuids: list[str] | None = None,
    ctx: Context | None = None,
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
    return _job(await get_client(ctx).submit(endpoint, fields))


@mcp.tool()
async def extend_video(
    model: Literal["veo-extend", "grok-extend", "grok-1.5-lite-extend", "seedance-extend"],
    video_uuid: str,
    prompt: str,
    options: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict:
    """Continue an existing video from its last frame. COSTS CREDITS: tell the user before calling.

    `video_uuid` is the uuid of a completed video made with the matching family (veo, grok, seedance).
    Storyboards cannot be extended.
    Describe what happens next in `prompt`. Returns a job uuid; poll get_generation.
    """
    spec = registry.get_model(model, "extend")
    endpoint, fields = registry.build_request(spec, prompt, options, history_uuids=[video_uuid])
    return _job(await get_client(ctx).submit(endpoint, fields))


@mcp.tool()
async def generate_storyboard(
    scenes: list[dict[str, Any]],
    aspect_ratio: Literal["landscape", "portrait", "square"] = "landscape",
    resolution: Literal["480p", "720p"] = "480p",
    ctx: Context | None = None,
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
    return _job(await get_client(ctx).submit(spec.endpoint, fields))


_UI_RESULT = {"ui": {"resourceUri": ui.RESULT_URI}, "ui/resourceUri": ui.RESULT_URI}
_UI_UPLOAD = {"ui": {"resourceUri": ui.UPLOAD_URI}, "ui/resourceUri": ui.UPLOAD_URI}


@mcp.tool(meta=_UI_RESULT)
async def get_generation(uuid: str, ctx: Context | None = None) -> dict:
    """Check a generation by uuid. When done is true, image_urls or video_urls hold the results.

    Hosts that support inline views show the finished images and videos under this call.
    """
    return _summarize(await get_client(ctx).get_history(uuid))


def _caller_key(ctx: Context | None) -> str:
    return get_client(ctx).api_key


NO_UPLOADS_MESSAGE = ("This server does not accept uploads. Pass a public URL of the file in reference_*_urls, "
                      "or run the server locally (stdio) and call upload_media with file_path.")


@mcp.tool(meta=_UI_UPLOAD)
async def upload_media(file_path: str | None = None, ctx: Context | None = None) -> dict:
    """Upload a reference image, video or audio file so it can guide a generation. Free.

    Use it when the user wants to use a file of their own (attached to the chat or on their computer) and you do not
    already have a public URL for it. A web URL can go straight into reference_*_urls without uploading.

    Local mode (stdio): pass file_path and the file is uploaded at once; the result holds its url.
    Hosted mode: call without file_path. The result shows an upload view (or upload_url to open in a browser, or a
    curl command if you have a shell with the file). After the user uploads, call get_upload with upload_id.
    """
    request = _http_request(ctx)
    if request is None:
        if not file_path:
            raise SnapGenError("Pass file_path: the path of the image, video or audio file on this computer.")
        import mimetypes
        from pathlib import Path

        path = Path(file_path).expanduser()
        if not path.is_file():
            raise SnapGenError(f"File not found: {path}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            result = await get_client(ctx).upload(path.name, fh, content_type)
        return {"status": "done", "filename": path.name, **{k: result.get(k) for k in
                ("url", "media_type", "content_type", "size", "expires_at")}}
    if _upload_backend is None:
        raise SnapGenError(NO_UPLOADS_MESSAGE)
    return await _upload_backend.create(_caller_key(ctx), request)


@mcp.tool()
async def get_upload(upload_id: str, ctx: Context | None = None) -> dict:
    """Check an upload started with upload_media (hosted mode). When status is done, url is ready for
    reference_*_urls. Not needed in local mode: upload_media with file_path returns the url directly."""
    if _http_request(ctx) is None or _upload_backend is None:
        raise SnapGenError("get_upload is only for hosted uploads. In local mode upload_media returns the url directly.")
    return await _upload_backend.get(upload_id, _caller_key(ctx))


def _media_domains() -> list[str]:
    return [d for d in os.environ.get("SNAPGEN_MCP_MEDIA_DOMAINS", DEFAULT_MEDIA_DOMAINS).split() if d]


@mcp.resource(ui.RESULT_URI, name="snapgen-result", description="Inline preview of finished generations",
              mime_type=ui.MIME, meta={"ui": {"csp": {"resourceDomains": _media_domains()}, "prefersBorder": False}})
def result_view() -> str:
    return ui.RESULT_HTML


@mcp.resource(ui.UPLOAD_URI, name="snapgen-upload", description="File picker for reference uploads",
              mime_type=ui.MIME, meta={"ui": {"csp": {"connectDomains": [
                  d for d in [os.environ.get("SNAPGEN_MCP_PUBLIC_URL", "").rstrip("/")] if d]},
                  "prefersBorder": True}})
def upload_view() -> str:
    return ui.UPLOAD_HTML


@mcp.tool()
async def list_generations(
    type: Literal["all", "image", "video"] = "all", page: int = 1, per_page: int = 10,
    ctx: Context | None = None,
) -> dict:
    """List recent generations, newest first."""
    resp = await get_client(ctx).list_histories(filter_by=type, page=page, items_per_page=per_page)
    return {
        "total": resp.get("total"),
        "items": [
            {k: v for k, v in _summarize(h).items() if k in
             ("uuid", "type", "model", "prompt", "status", "done", "failed", "credits_used", "created_at")}
            for h in resp.get("result") or []
        ],
    }


class PostOnlyEndpoint:
    """Answer GET and DELETE on the MCP endpoint with 405 and `Allow: POST`.

    The server is stateless and never sends server-initiated messages, so there is no stream to open and no
    session to end. The MCP spec lets a server without a GET stream answer 405. It also stops callers from holding
    idle connections open on an endpoint that, unlike the tools, needs no key.
    """

    def __init__(self, app: ASGIApp, path: str = "/mcp") -> None:
        self.app = app
        self.paths = {path, path.rstrip("/") + "/"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] in self.paths and scope["method"] in ("GET", "DELETE"):
            response = PlainTextResponse("Method Not Allowed: send JSON-RPC requests to this endpoint with POST.",
                                         status_code=405, headers={"Allow": "POST"})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def transport_security_for(host: str, allowed_hosts: list[str] | None = None) -> TransportSecuritySettings:
    """Host-header (DNS rebinding) protection, chosen from how the server is bound.

    - Bound to loopback (local use): on, accepting loopback names plus any extra allowed hosts.
    - Bound elsewhere (hosted, behind a proxy that forwards the public Host header): off by default. Callers prove
      themselves with a header key rather than ambient browser credentials, so rebinding is not the threat there.
      Set SNAPGEN_MCP_ALLOWED_HOSTS (comma separated, e.g. "mcp.example.com") to enforce an allow-list instead.
    """
    extra = [h.strip() for h in (allowed_hosts or []) if h.strip()]
    loopback = host in _LOOPBACK
    if not loopback and not extra:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"] if loopback else []
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"] if loopback else []
    for h in extra:
        hosts += [h, f"{h}:*"]
        origins += [f"https://{h}", f"http://{h}", f"https://{h}:*", f"http://{h}:*"]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                     allowed_origins=origins)


def build_http_app(host: str = "127.0.0.1", allowed_hosts: list[str] | None = None,
                   routes: Sequence[BaseRoute] = (), middleware: Sequence[Middleware] = ()) -> Starlette:
    """The streamable HTTP app with Host checking chosen for this binding and GET/DELETE refused.

    `routes` and `middleware` let a hosting layer add its own endpoints and outer middleware.
    """
    mcp.settings.transport_security = transport_security_for(host, allowed_hosts)
    app = mcp.streamable_http_app()
    app.router.routes.extend(routes)
    for m in middleware:
        app.add_middleware(m.cls, *m.args, **m.kwargs)
    app.add_middleware(PostOnlyEndpoint, path=mcp.settings.streamable_http_path)
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="snapgen-mcp", description="SnapGen MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"],
                        default=os.environ.get("SNAPGEN_MCP_TRANSPORT", "stdio"),
                        help="stdio (local, key from SNAPGEN_API_KEY) or http (hosted, key from each request)")
    parser.add_argument("--host", default=os.environ.get("SNAPGEN_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SNAPGEN_MCP_PORT", "8000")))
    args = parser.parse_args(argv)

    if args.transport == "http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        allowed = os.environ.get("SNAPGEN_MCP_ALLOWED_HOSTS", "").split(",")
        # endpoint: POST /mcp, health check: GET /health
        uvicorn.run(build_http_app(args.host, allowed), host=args.host, port=args.port,
                    log_level=mcp.settings.log_level.lower())
    else:
        mcp.run()


if __name__ == "__main__":
    main()
