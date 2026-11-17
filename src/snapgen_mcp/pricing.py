"""Live credit prices for describe_model, read from SnapGen's public price list.

Prices change far more often than this package is released, so the registry only says *how* a model is charged
and the numbers are looked up here. The list is public (no API key involved) and cached for a few minutes. When
it cannot be read, describe_model still answers and points at estimated_credit, which every submit returns and
which is always the exact charge.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from .client import DEFAULT_BASE_URL
from .registry import ModelSpec

PRICES_PATH = "/api/service-prices/all"
CACHE_SECONDS = 300
FAILURE_CACHE_SECONDS = 30  # do not hammer the API while the price list is down
FETCH_TIMEOUT = 5.0
# uapi charges a model's UAPI rows when it has any and falls back to the WEB rows (the backend's default
# platform) otherwise, e.g. Veo, Kling and most Seedance models have WEB rows only.
PLATFORMS = ("api", "web")

Table = dict[str, dict[str, list[dict[str, Any]]]]  # platform -> model_name -> rows

_cache: dict[str, tuple[float, Table | None]] = {}
_lock = asyncio.Lock()

EXACT_COST_NOTE = "The exact charge is estimated_credit, returned by every submit. State it before spending."


def _base_url() -> str:
    return (os.environ.get("SNAPGEN_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


async def _fetch_table(base_url: str) -> Table | None:
    """Download the price list for every platform in PLATFORMS. None if any of them cannot be read."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=FETCH_TIMEOUT,
                                     headers={"Accept": "application/json"}) as http:
            responses = await asyncio.gather(
                *(http.get(PRICES_PATH, params={"platform": p}) for p in PLATFORMS))
        table: Table = {}
        for platform, resp in zip(PLATFORMS, responses):
            resp.raise_for_status()
            rows: dict[str, list[dict[str, Any]]] = {}
            for category in resp.json().get("categories") or []:
                for family in category.get("families") or []:
                    for row in family.get("models") or []:
                        if row.get("model_name"):
                            rows.setdefault(row["model_name"], []).append(row)
            table[platform] = rows
        return table
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


async def price_table() -> Table | None:
    base_url = _base_url()
    async with _lock:
        hit = _cache.get(base_url)
        if hit and time.monotonic() < hit[0]:
            return hit[1]
        table = await _fetch_table(base_url)
        ttl = CACHE_SECONDS if table is not None else FAILURE_CACHE_SECONDS
        _cache[base_url] = (time.monotonic() + ttl, table)
        return table


def _price_per(spec: ModelSpec, row: dict[str, Any]) -> str:
    if spec.price_per:
        return spec.price_per
    unit = row.get("price_unit") or ""
    return "second" if unit == "second" else unit or "request"


def prices_for(spec: ModelSpec, table: Table) -> list[dict[str, Any]]:
    """The price rows that apply to one model, as compact dicts, cheapest settings first."""
    name = spec.price_name or spec.send_model or spec.id
    matched: list[tuple[str, dict[str, Any]]] = []
    for platform in PLATFORMS:
        matched = [(model_name[len(name) + 1:], row)
                   for model_name, rows in table.get(platform, {}).items()
                   if model_name == name or model_name.startswith(name + "_")
                   for row in rows]
        if matched:
            break

    # Rows for modes this server does not offer (e.g. seedance-2-omni "fast" vs our "fast-vip") would mislead.
    mode = spec.params.get("mode")
    if mode and mode.choices:
        offered = [(m, r) for m, r in matched if not m or m in mode.choices]
        matched = offered or matched

    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for mode_name, row in matched:
        item: dict[str, Any] = {}
        if mode_name:
            item["mode"] = mode_name
        if row.get("resolution") and row["resolution"] != mode_name:  # Kling 4: the mode is the resolution
            item["resolution"] = row["resolution"]
        # A duration on a per-second row is not a fixed clip length, so it would only confuse.
        per = _price_per(spec, row)
        if row.get("video_duration") and per not in ("second", "image"):
            item["duration_s"] = row["video_duration"]
        price = row.get("effective_price")
        item["credits"] = int(price) if isinstance(price, float) and price.is_integer() else price
        item["per"] = per
        key = tuple(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            out.append(item)
    order = list(mode.choices) if mode and mode.choices else []
    out.sort(key=lambda i: (order.index(i["mode"]) if i.get("mode") in order else len(order), i.get("mode", ""),
                            i["credits"] if isinstance(i["credits"], (int, float)) else 0))
    return out


async def describe(spec: ModelSpec) -> dict[str, Any]:
    """spec.describe() with the pricing filled in from the live price list."""
    out = spec.describe()
    pricing: dict[str, Any] = {"how_charged": spec.pricing or "See estimated_credit on submit."}
    table = await price_table()
    if table is None:
        pricing["prices"] = "Live price list unavailable right now."
    else:
        prices = prices_for(spec, table)
        pricing["prices"] = prices or ("Same as the original video's model." if spec.kind == "extend" else
                                       "Not in the public price list; see estimated_credit on submit.")
    pricing["exact_cost"] = EXACT_COST_NOTE
    out["pricing"] = pricing
    return out
