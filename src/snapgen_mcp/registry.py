"""Model registry: one entry per model, built from docs.snapgen.ai (geminigen-docs, branch main).

Adding a model means adding one entry here. Nothing else in the server changes.

Validation is deliberately permissive where the docs are ambiguous: the backend is the source of
truth, and a false local rejection is worse than a clear backend error.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .client import SnapGenError

KINDS = ("image", "video", "extend", "storyboard")


@dataclass(frozen=True)
class Param:
    type: str  # "str" | "int" | "bool"
    description: str = ""
    choices: tuple | None = None
    min: int | None = None
    max: int | None = None
    default: Any = None  # sent when the caller omits it, only if always_send
    always_send: bool = False

    def describe(self) -> dict:
        out: dict[str, Any] = {"type": self.type}
        if self.description:
            out["description"] = self.description
        if self.choices is not None:
            out["choices"] = list(self.choices)
        if self.min is not None or self.max is not None:
            out["range"] = [self.min, self.max]
        if self.default is not None:
            out["default"] = self.default
        return out


@dataclass(frozen=True)
class Refs:
    """A reference-media slot: the backend form field, a cap, and whether it takes URLs or uuids."""
    field: str
    max: int | None = None
    min: int = 0


@dataclass(frozen=True)
class ModelSpec:
    id: str
    family: str
    kind: str
    endpoint: str  # path under /uapi/v1
    summary: str
    send_model: str | None = None  # value for the `model` form field; None = endpoint takes no model field
    params: dict[str, Param] = field(default_factory=dict)
    image_urls: Refs | None = None
    history: Refs | None = None  # uuids of previous generations (images, or the video to extend)
    video_urls: Refs | None = None
    audio_urls: Refs | None = None
    max_total_refs: int | None = None
    exclusive_refs: bool = False  # only one kind of reference (URLs OR history uuids) per request
    min_prompt_len: int = 1
    premium: bool = False
    pricing: str = ""
    notes: str = ""

    def describe(self) -> dict:
        refs: dict[str, Any] = {}
        for label, r in (("reference_image_urls", self.image_urls), ("reference_history_uuids", self.history),
                         ("reference_video_urls", self.video_urls), ("reference_audio_urls", self.audio_urls)):
            if r:
                refs[label] = {"max": r.max, "min_required": r.min}
        return {
            "id": self.id, "family": self.family, "kind": self.kind, "summary": self.summary,
            "premium_plan_required": self.premium, "pricing": self.pricing or "see estimated_credit on submit",
            "options": {k: p.describe() for k, p in self.params.items()},
            "references": refs or "none supported",
            "notes": self.notes,
        }


# ---------------------------------------------------------------- helpers
def P(type, description="", choices=None, min=None, max=None, default=None, always_send=False):
    return Param(type, description, tuple(choices) if choices is not None else None, min, max, default, always_send)


ASPECT_RATIOS_6 = ("16:9", "9:16", "1:1", "3:4", "4:3", "21:9")
GROK_MODES = ("custom", "normal", "extremely-crazy", "extremely-spicy-or-crazy")
MODES_NOTE = "mode: custom/normal are standard; the other two are the 'fun' and 'spicy' presets."

_REGISTRY: dict[str, ModelSpec] = {}


def _add(spec: ModelSpec) -> None:
    assert spec.id not in _REGISTRY, spec.id
    _REGISTRY[spec.id] = spec


# ---------------------------------------------------------------- images: nano banana
for _m, _s in (("nano-banana-pro", "Highest quality Nano Banana. Rate limited to 5 req/min, 100/hour."),
               ("nano-banana-2", "Nano Banana 2."),
               ("nano-banana-2-lite", "Cheapest, fastest Nano Banana.")):
    _add(ModelSpec(
        id=_m, family="nano-banana", kind="image", endpoint="/generate_image", send_model=_m, summary=_s,
        params={
            "aspect_ratio": P("str", choices=("1:1", "16:9", "9:16", "4:3", "3:4"), default="1:1"),
            "resolution": P("str", choices=("1K", "2K", "4K"), default="1K"),
            "style": P("str", "Artistic style preset.", choices=(
                "None", "3D Render", "Acrylic", "Anime General", "Creative", "Dynamic", "Fashion", "Game Concept",
                "Graphic Design 3D", "Illustration", "Photorealistic", "Portrait", "Portrait Cinematic",
                "Portrait Fashion", "Ray Traced", "Stock Photo", "Watercolor")),
        },
        image_urls=Refs("file_urls"), history=Refs("ref_history", 1),
    ))

# ---------------------------------------------------------------- images: others
_add(ModelSpec(
    id="grok-image", family="grok", kind="image", endpoint="/imagen/grok",
    summary="Grok image generation, up to 8 images per request.",
    params={
        "orientation": P("str", choices=("landscape", "portrait", "square"), default="landscape"),
        "num_result": P("int", "Number of images (QUALITY mode: max 4).", min=1, max=8, default=1),
        "mode": P("str", choices=("SPEED", "QUALITY"), default="SPEED"),
    },
    history=Refs("ref_history", 1),
    notes="No reference image URLs: only a previous generation uuid (reference_history_uuids).",
))
_add(ModelSpec(
    id="gpt-image-2", family="gpt-image", kind="image", endpoint="/imagen/gpt-image-2", premium=True,
    summary="GPT Image 2: quality tiers, transparent backgrounds, up to 12K.",
    params={
        "mode": P("str", "Quality tier; higher costs more.", choices=("low", "medium", "high"), default="low"),
        "aspect_ratio": P("str", choices=("1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "3:2", "2:3"), default="1:1"),
        "resolution": P("str", choices=("1K", "2K", "4K", "8K", "10K", "12K"), default="2K"),
        "background": P("str", choices=("auto", "transparent", "opaque"), default="auto"),
    },
    history=Refs("ref_history", 1),
    pricing="Depends on mode x resolution.",
    notes="No reference image URLs: only a previous generation uuid (reference_history_uuids).",
))
_add(ModelSpec(
    id="gpt-image-2.5-lower", family="gpt-image", kind="image", endpoint="/imagen/gpt-image-2.5-lower",
    premium=True, summary="GPT Image 2.5 Lower: flat-rate, fixed quality at 720p output.",
    params={"aspect_ratio": P("str", choices=("1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "3:2", "2:3"),
                              default="1:1")},
    history=Refs("ref_history", 10), pricing="Flat rate per image (docs say 2 credits; live estimate was 1, check estimated_credit).",
    notes="No mode/resolution/background options. No reference image URLs: only previous generation uuids.",
))
_add(ModelSpec(
    id="vela-image", family="vela", kind="image", endpoint="/imagen/vela", premium=True,
    summary="Vela AI image: 4 variants from text, or 1 edited result from one reference image.",
    params={
        "orientation": P("str", choices=("portrait", "vertical", "landscape", "square"), default="portrait"),
        "resolution": P("str", choices=("480p", "720p"), default="480p"),
    },
    image_urls=Refs("file_url", 1), history=Refs("ref_history", 1), exclusive_refs=True,
    pricing="Flat rate per request.",
    notes="Provide at most ONE reference (image URL or history uuid).",
))

# ---------------------------------------------------------------- video: Veo / Omni
for _m, _s, _res in (
    ("veo-3.1", "Veo 3.1, highest quality.", ("720p", "1080p")),
    ("veo-3.1-fast", "Veo 3.1 Fast, quicker turnaround.", ("720p", "1080p")),
    ("veo-3.1-lite", "Veo 3.1 Lite with synchronized audio (cheapest Veo).", ("720p", "1080p")),
    ("veo-2", "Veo 2, 720p only.", ("720p",)),
    ("omni-flash", "Omni Flash: 10s generation, or video editing with a reference video.", ("720p", "1080p")),
):
    _add(ModelSpec(
        id=_m, family="veo", kind="video", endpoint="/video-gen/veo", send_model=_m, summary=_s,
        params={
            "resolution": P("str", choices=_res, default="720p"),
            "duration": P("int", "Seconds. 10 is omni-flash only.", choices=(4, 6, 8, 10)),
            "aspect_ratio": P("str", choices=("16:9", "9:16"), default="16:9"),
            "mode_image": P("str", "frame = start/end frame images (1-2); ingredient = style/content images (1-3).",
                            choices=("frame", "ingredient"), default="frame"),
        },
        image_urls=Refs("ref_images", 3),
        video_urls=Refs("ref_videos") if _m == "omni-flash" else None,
        notes="In frame mode, send images in order: start frame first, end frame second.",
    ))
_add(ModelSpec(
    id="veo-extend", family="veo", kind="extend", endpoint="/video-extend/veo",
    summary="Continue a Veo video from its last frame. Model, aspect ratio and resolution are inherited.",
    history=Refs("ref_history", 1, min=1),
))

# ---------------------------------------------------------------- video: Grok family
_GROK_COMMON = {
    "duration": P("int", choices=(6, 10, 15)),
    "mode": P("str", MODES_NOTE, choices=GROK_MODES, default="custom"),
    "skip_audio": P("bool", "True = silent video.", default=False),
}
_add(ModelSpec(
    id="grok-3", family="grok", kind="video", endpoint="/video-gen/grok", send_model="grok-3",
    summary="Grok video (standard). Shares its daily allowance with grok-lower.",
    params={
        "resolution": P("str", choices=("480p", "720p"), default="480p"),
        "aspect_ratio": P("str", choices=("landscape", "portrait", "square", "vertical", "horizontal"),
                          default="landscape"),
        **_GROK_COMMON,
    },
    image_urls=Refs("file_urls"), history=Refs("ref_images"), exclusive_refs=True,
    notes="Use only one reference method per request: image URLs OR history uuids.",
))
_add(ModelSpec(
    id="grok-lower", family="grok", kind="video", endpoint="/video-gen/grok-lower", premium=True,
    summary="Cheaper Grok video, up to 5 reference images. Shares its daily allowance with grok-3.",
    params={
        "resolution": P("str", choices=("480p", "720p", "1080p"), default="480p"),
        "aspect_ratio": P("str", choices=("landscape", "portrait", "square", "3:2", "2:3"), default="landscape"),
        **_GROK_COMMON,
    },
    image_urls=Refs("file_urls", 5), history=Refs("ref_images", 5), exclusive_refs=True,
    notes="With 2+ images, refer to them in the prompt as @image1, @image2... 1 image = first frame. "
          "Use only one reference method per request.",
))
_add(ModelSpec(
    id="grok-1.5-lite", family="grok", kind="video", endpoint="/video-gen/grok-1.5-lite", premium=True,
    summary="Grok 1.5 Lite: text-to-video or one image animated.",
    params={
        "resolution": P("str", choices=("480p", "720p", "1080p"), default="480p"),
        "aspect_ratio": P("str", choices=("landscape", "portrait", "square", "3:2", "2:3"), default="landscape"),
        **_GROK_COMMON,
    },
    image_urls=Refs("file_urls", 1), history=Refs("ref_images", 1), exclusive_refs=True,
    pricing="480p: 3/5/7 credits (6/10/15s). 720p: 4/7/10. 1080p: 12/20/30.",
))
_add(ModelSpec(
    id="grok-extend", family="grok", kind="extend", endpoint="/video-extend/grok",
    summary="Continue a Grok video from its last frame.", history=Refs("ref_history", 1, min=1),
))
_add(ModelSpec(
    id="grok-1.5-lite-extend", family="grok", kind="extend", endpoint="/video-extend/grok-1.5-lite", premium=True,
    summary="Continue a Grok 1.5 Lite video. Omitted options inherit from the original.",
    params={
        "duration": P("int", choices=(6, 10, 15)),
        "resolution": P("str", choices=("480p", "720p", "1080p")),
        "mode": P("str", MODES_NOTE, choices=GROK_MODES),
        "skip_audio": P("bool"),
    },
    history=Refs("ref_history", 1, min=1),
    pricing="Same as grok-1.5-lite.",
))
_add(ModelSpec(
    id="grok-storyboard", family="grok", kind="storyboard", endpoint="/video-storyboard/grok", premium=True,
    send_model="grok-video",
    summary="Multi-scene Grok video: 2-10 scenes chained and merged. Use generate_storyboard.",
    params={
        "aspect_ratio": P("str", choices=("landscape", "portrait", "square"), default="landscape"),
        "resolution": P("str", choices=("480p", "720p"), default="480p"),
    },
    pricing="Charged per scene.",
    notes="Each scene: prompt + duration (6 or 10s). Max 45s total.",
))

# ---------------------------------------------------------------- video: Seedance
_SD_ASPECT = P("str", choices=ASPECT_RATIOS_6)
for _m, _s, _modes, _dur, _imgs, _vid, _aud, _price in (
    ("seedance-2-omni", "Seedance 2 Omni: multimodal references.", ("fast-vip", "pro-vip"),
     P("int", min=4, max=15), 4, 1, 1, ""),
    ("seedance-2-mini", "Seedance 2 Mini: fast, first/last frame references.", ("business_mini_vip",),
     P("int", min=4, max=15), 2, None, None, ""),
    ("seedance-2-5-omni", "Seedance 2.5 Omni: up to 30s, up to 14 reference images.", ("pro-vip",),
     P("int", min=4, max=30), 14, 1, 4, ""),
    ("sd-2-lower", "Seedance 2 Lower: cost-effective.", ("lower",),
     P("int", choices=(5, 10, 15)), 4, None, None, "4 credits per second."),
    ("sd-2-5-lower", "Seedance 2.5 Lower: cost-effective, up to 30s.", ("lower",),
     P("int", choices=(5, 10, 30)), 4, None, None, "5 credits per second."),
):
    _add(ModelSpec(
        id=_m, family="seedance", kind="video", endpoint="/video-gen/seedance", send_model=_m, summary=_s,
        params={"mode": P("str", "Required by the backend; defaults to the first choice.", choices=_modes,
                          default=_modes[0], always_send=True),
                "duration": _dur, "aspect_ratio": _SD_ASPECT},
        image_urls=Refs("ref_images", _imgs),
        video_urls=Refs("ref_videos", _vid) if _vid else None,
        audio_urls=Refs("ref_audios", _aud) if _aud else None,
        pricing=_price or "Duration x credits per second (varies by mode).",
        notes="Reference images up to 15MB each. Reference video: mp4/webm, max 15s." if _vid else
              "Reference images up to 15MB each.",
    ))
_add(ModelSpec(
    id="seedance-extend", family="seedance", kind="extend", endpoint="/video-extend/seedance",
    summary="Continue a Seedance video. All settings inherit from the original.",
    history=Refs("ref_history", 1, min=1),
))

# ---------------------------------------------------------------- video: Kling
_KLING = {  # id: (summary, modes, duration param or None, needs ref video, description)
    "kling-video-3-0": ("Kling 3.0: best text/image-to-video, up to 15s.", ("standard", "professional"),
                        P("int", min=3, max=15), False),
    "kling-video-2-6": ("Kling 2.6: stable, supports voiceover via professional_audio.",
                        ("standard", "professional", "professional_audio"), P("int", min=3, max=15), False),
    "kling-video-2-5": ("Kling 2.5: 'relax' mode is cheapest.", ("relax", "standard", "professional"),
                        P("int", min=3, max=15), False),
    "kling-video-2-1-5s": ("Kling 2.1, fixed 5s.", ("standard", "professional"), P("int", choices=(5,)), False),
    "kling-video-2-1-10s": ("Kling 2.1, fixed 10s.", ("standard", "professional"), P("int", choices=(10,)), False),
    # kling-video-1-6-5s / -10s are in the docs but the backend has no service price for them in
    # standard or professional mode (404 SERVICE_PRICE_NOT_FOUND, checked live 2026-10-20), so they are omitted.
    "kling-video-motion-3": ("Kling Motion Control 3: transfers motion from a reference video onto an image.",
                             ("standard", "professional"), None, True),
    "kling-video-motion": ("Kling Motion Control.", ("standard", "professional"), None, True),
    "kling-video-3-0-edit": ("Kling 3.0 Edit: edit an existing video with a prompt + key frame.",
                             ("standard", "professional"), None, True),
}
# Verified live 2026-10-20: these reject text-only requests ("Please attach an image").
_KLING_NEEDS_IMAGE = {"kling-video-2-5", "kling-video-2-1-5s", "kling-video-2-1-10s"}
for _m, (_s, _modes, _dur, _needs_video) in _KLING.items():
    _p: dict[str, Param] = {
        "mode": P("str", "standard = 720p, professional = 1080p.", choices=_modes, default="standard"),
        "aspect_ratio": P("str", choices=("16:9", "9:16", "1:1"), default="16:9"),
    }
    if _dur:
        _p["duration"] = _dur
    _add(ModelSpec(
        id=_m, family="kling", kind="video", endpoint="/video-gen/kling", send_model=_m, summary=_s,
        params=_p, image_urls=Refs("ref_images", 4, min=1 if _m in _KLING_NEEDS_IMAGE else 0),
        video_urls=Refs("ref_videos", 1, min=1 if _needs_video else 0),
        min_prompt_len=10,
        notes=("Requires one reference video (reference_video_urls); duration follows that video. "
               "A reference image is recommended." if _needs_video else
               "Prompt must be at least 10 characters. Reference videos are optional."
               + (" REQUIRES at least one reference image (image-to-video only)." if _m in _KLING_NEEDS_IMAGE else "")),
    ))

# ---------------------------------------------------------------- video: others
_add(ModelSpec(
    id="minimax-h3", family="minimax", kind="video", endpoint="/video-gen/minimax", send_model="minimax-h3",
    summary="Minimax H3 (Hailuo): dynamic motion, native audio, rich multimodal references.",
    params={
        "mode": P("str", choices=("standard",), default="standard", always_send=True),
        "duration": P("int", min=5, max=15),
        "aspect_ratio": P("str", choices=ASPECT_RATIOS_6),
    },
    image_urls=Refs("ref_images", 9), video_urls=Refs("ref_videos", 2), audio_urls=Refs("ref_audios", 2),
    max_total_refs=13, pricing="Duration x credits per second.",
    notes="Combined images + videos + audios must not exceed 13.",
))
_add(ModelSpec(
    id="flux-3", family="flux", kind="video", endpoint="/video-gen/flux", send_model="flux-3",
    summary="FLUX 3 video (Black Forest Labs): native audio, strong text rendering, up to 20s.",
    params={
        "mode": P("str", choices=("vip",), default="vip", always_send=True),
        "duration": P("int", min=5, max=20),
        "aspect_ratio": P("str", choices=("16:9", "9:16", "1:1", "3:4", "4:3", "2:1", "21:9")),
    },
    image_urls=Refs("ref_images", 10), pricing="Duration x credits per second.",
))
_add(ModelSpec(
    id="vela-ai-video", family="vela", kind="video", endpoint="/video-gen/vela", send_model="vela-ai-video",
    premium=True, summary="Vela AI video: 5s clips with optional start and end frames.",
    params={
        "orientation": P("str", choices=("portrait", "vertical", "landscape", "square"), default="portrait"),
        "resolution": P("str", choices=("480p", "720p"), default="480p"),
        "duration": P("int", choices=(5,), default=5),
    },
    image_urls=Refs("file_urls", 12), history=Refs("ref_history", 12),
    notes="First image = start frame, second = end frame. History uuids must be IMAGE generations.",
))
_add(ModelSpec(
    id="muse-ai-video", family="muse", kind="video", endpoint="/video-gen/muse", send_model="muse-ai-video",
    premium=True, summary="Muse AI video: always 10s, text-to-video or one image animated. Takes 1-5 minutes.",
    params={
        "orientation": P("str", choices=("portrait", "vertical", "landscape", "square"), default="portrait"),
        "duration": P("int", choices=(10,), default=10),
    },
    image_urls=Refs("file_urls", 1), history=Refs("ref_history", 1), exclusive_refs=True,
    notes="At most ONE reference (image URL or image history uuid). Resolution is fixed.",
))


# ---------------------------------------------------------------- observed pricing
# Estimated credits returned by the live API on 2026-10-20 at the cheapest settings. These are snapshots, not
# a price list: the docs differ for some models and prices change. Always trust estimated_credit on submit.
_OBSERVED = {
    "nano-banana-pro": "~3 credits (1K)", "nano-banana-2": "~3 credits (1K)", "nano-banana-2-lite": "~3 credits (1K)",
    "grok-image": "~4 credits (1 image, SPEED)", "gpt-image-2": "~3 credits (low, 1K)",
    "gpt-image-2.5-lower": "~1 credit", "vela-image": "~1 credit",
    "veo-3.1": "~100 credits (4s, 720p)", "veo-3.1-fast": "~4 credits (4s, 720p)",
    "veo-3.1-lite": "~4 credits (4s, 720p)", "veo-2": "~20 credits (8s)", "omni-flash": "~15 credits (10s)",
    "veo-extend": "~4 credits",
    "grok-3": "~15 credits (6s, 480p)", "grok-lower": "~8 credits (6s, 480p)",
    "grok-extend": "~15 credits", "grok-storyboard": "~15 credits per 6s scene (480p)",
    "seedance-2-omni": "~108 credits (4s)", "seedance-2-mini": "~84 credits (4s)",
    "seedance-2-5-omni": "~332 credits (4s)", "sd-2-lower": "~6 credits (5s)",
    "minimax-h3": "~150 credits (5s)", "flux-3": "~170 credits (5s)",
    "vela-ai-video": "~1 credit", "muse-ai-video": "~0 credits observed (may be promotional)",
    "kling-video-3-0": "~55 credits (5s, standard)", "kling-video-2-6": "~30 credits (5s, standard)",
    "kling-video-2-5": "~15 credits (5s, relax)", "kling-video-2-1-5s": "~35 credits (standard)",
    "kling-video-2-1-10s": "~30 credits (standard)",
    "kling-video-motion-3": "~100 credits (scales with the reference video length)",
    "kling-video-motion": "~60 credits (scales with the reference video length)",
    "kling-video-3-0-edit": "~120 credits (scales with the reference video length)",
}
for _id, _txt in _OBSERVED.items():
    _REGISTRY[_id] = replace(_REGISTRY[_id], pricing=f"Observed estimate: {_txt}.")


# ---------------------------------------------------------------- public API
def all_models() -> list[ModelSpec]:
    return list(_REGISTRY.values())


def get_model(model_id: str, kind: str | tuple | None = None) -> ModelSpec:
    spec = _REGISTRY.get(model_id)
    if spec is None:
        raise SnapGenError(f"Unknown model '{model_id}'. Call list_models to see valid ids.")
    kinds = (kind,) if isinstance(kind, str) else kind
    if kinds and spec.kind not in kinds:
        hint = {"image": "generate_image", "video": "generate_video", "extend": "extend_video",
                "storyboard": "generate_storyboard"}[spec.kind]
        raise SnapGenError(f"'{model_id}' is a {spec.kind} model. Use {hint} instead.")
    return spec


def _coerce(name: str, p: Param, value: Any) -> Any:
    if p.type == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise SnapGenError(f"Option '{name}' must be an integer.")
        try:
            value = int(value)
        except ValueError:
            raise SnapGenError(f"Option '{name}' must be an integer.") from None
    elif p.type == "bool":
        if isinstance(value, str):
            value = value.strip().lower() in ("true", "1", "yes")
        value = bool(value)
    else:
        value = str(value)
    if p.choices is not None and value not in p.choices:
        raise SnapGenError(f"Option '{name}' must be one of {list(p.choices)}, got {value!r}.")
    if p.min is not None and value < p.min or p.max is not None and value > p.max:
        raise SnapGenError(f"Option '{name}' must be between {p.min} and {p.max}, got {value}.")
    return value


def _check_refs(label: str, refs: Refs | None, values: list[str] | None, model: str) -> list[str]:
    values = [v for v in (values or []) if v]
    if refs is None:
        if values:
            raise SnapGenError(f"{model} does not support {label}. Call describe_model('{model}') for details.")
        return []
    if refs.max is not None and len(values) > refs.max:
        raise SnapGenError(f"{model} accepts at most {refs.max} {label}, got {len(values)}.")
    if len(values) < refs.min:
        raise SnapGenError(f"{model} requires at least {refs.min} {label}.")
    return values


def build_request(
    spec: ModelSpec, prompt: str, options: dict[str, Any] | None = None, *,
    image_urls: list[str] | None = None, history_uuids: list[str] | None = None,
    video_urls: list[str] | None = None, audio_urls: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate a call against the spec and return (endpoint, form fields). Raises SnapGenError."""
    prompt = (prompt or "").strip()
    if len(prompt) < spec.min_prompt_len:
        need = f"at least {spec.min_prompt_len} characters" if spec.min_prompt_len > 1 else "a non-empty prompt"
        raise SnapGenError(f"{spec.id} needs {need}.")

    options = dict(options or {})
    unknown = sorted(set(options) - set(spec.params))
    if unknown:
        allowed = sorted(spec.params) or "none"
        raise SnapGenError(f"Unknown option(s) {unknown} for {spec.id}. Allowed options: {allowed}.")

    fields: dict[str, Any] = {"prompt": prompt}
    if spec.send_model:
        fields["model"] = spec.send_model
    for name, p in spec.params.items():
        if name in options and options[name] is not None:
            fields[name] = _coerce(name, p, options[name])
        elif p.always_send and p.default is not None:
            fields[name] = p.default

    imgs = _check_refs("reference images", spec.image_urls, image_urls, spec.id)
    hist = _check_refs("reference history uuids", spec.history, history_uuids, spec.id)
    vids = _check_refs("reference videos", spec.video_urls, video_urls, spec.id)
    auds = _check_refs("reference audios", spec.audio_urls, audio_urls, spec.id)
    if spec.max_total_refs is not None and len(imgs) + len(vids) + len(auds) > spec.max_total_refs:
        raise SnapGenError(f"{spec.id} accepts at most {spec.max_total_refs} reference files in total.")
    if imgs and hist and (spec.exclusive_refs or (spec.image_urls and spec.history
                                                   and spec.image_urls.field == spec.history.field)):
        raise SnapGenError(f"{spec.id}: use either image URLs or history uuids, not both.")
    for refs, vals in ((spec.image_urls, imgs), (spec.history, hist), (spec.video_urls, vids),
                       (spec.audio_urls, auds)):
        if refs and vals:
            fields.setdefault(refs.field, []).extend(vals)
    return spec.endpoint, fields
