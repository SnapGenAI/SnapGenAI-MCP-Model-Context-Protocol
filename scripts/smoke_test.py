#!/usr/bin/env python3
"""Smoke test for a running SnapGen MCP server: local, container or hosted.

    python scripts/smoke_test.py --url https://mcp.example.com --api-key "$SNAPGEN_API_KEY"

It checks health, the HTTP method rules, the tool list, the free catalog tools, validation errors, and (with a key)
authentication and a free call to the SnapGen API. It never spends credits unless you pass --generate, which makes
one small image (about 3 credits) and waits for it.

The key comes from --api-key or $SNAPGEN_API_KEY and is never printed. Without a key the checks that need one are
skipped, not failed. Exit code: 0 when every check that ran passed, 1 when any failed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client import streamable_http as _sh

EXPECTED_TOOLS = {"get_account", "list_models", "describe_model", "generate_image", "generate_video",
                  "extend_video", "generate_storyboard", "get_generation", "list_generations"}
BAD_KEY = "geminiai-smoke-test-not-a-real-key"


@dataclass
class Report:
    key: str = ""
    rows: list[tuple[str, str, str, int]] = field(default_factory=list)  # status, name, detail, ms

    def mask(self, text: str) -> str:
        for secret in (self.key, BAD_KEY):
            if secret:
                text = text.replace(secret, "<key>")
        return text

    def add(self, status: str, name: str, detail: str = "", ms: int = 0) -> None:
        detail = self.mask(detail)
        self.rows.append((status, name, detail, ms))
        suffix = f"  ({ms} ms)" if ms else ""
        print(f"{status:5} {name}{suffix}" + (f"  - {detail}" if detail else ""), flush=True)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r[0] == "FAIL")


@asynccontextmanager
async def mcp_session(url: str, headers: dict[str, str], timeout: float):
    """An initialized MCP session. Uses the current client API when the SDK has it, else the older one."""
    if hasattr(_sh, "streamable_http_client"):
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as http:
            async with _sh.streamable_http_client(f"{url}/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    else:  # pragma: no cover - older SDKs
        async with _sh.streamablehttp_client(f"{url}/mcp", headers=headers, timeout=timeout) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def call(url, tool, args=None, headers=None, timeout=30.0):
    """(is_error, text) for one tool call on a fresh session."""
    async with mcp_session(url, headers or {}, timeout) as session:
        res = await session.call_tool(tool, args or {})
        return bool(res.isError), (res.content[0].text if res.content else "")


def root_cause(exc: BaseException) -> BaseException:
    """The MCP client wraps connection errors in exception groups; report the real cause."""
    while getattr(exc, "exceptions", None):
        exc = exc.exceptions[0]  # type: ignore[attr-defined]
    return exc


async def run_check(report: Report, name: str, fn, *, skip_reason: str | None = None):
    if skip_reason:
        report.add("SKIP", name, skip_reason)
        return None
    start = time.perf_counter()
    try:
        detail = await fn()
        report.add("PASS", name, detail or "", int((time.perf_counter() - start) * 1000))
        return detail
    except AssertionError as exc:
        report.add("FAIL", name, str(exc) or "assertion failed", int((time.perf_counter() - start) * 1000))
    except Exception as exc:  # network, TLS, protocol errors
        cause = root_cause(exc)
        report.add("FAIL", name, f"{type(cause).__name__}: {cause}"[:300], int((time.perf_counter() - start) * 1000))
    return None


async def main_async(args) -> int:
    url = args.url.rstrip("/")
    key = args.api_key or ""
    report = Report(key=key)
    timeout = args.timeout
    host = urlparse(url).hostname or ""
    print(f"SnapGen MCP smoke test: {url}  (key: {'provided' if key else 'none, key checks will be skipped'}"
          f"{', will generate one image' if args.generate else ''})\n")

    if urlparse(url).scheme == "http" and host not in ("127.0.0.1", "localhost", "::1"):
        report.add("WARN", "transport", "plain HTTP to a non-local host: API keys travel in headers, use HTTPS")

    # ---- checks that need no key
    async def health():
        async with httpx.AsyncClient(timeout=timeout) as http:
            r = await http.get(f"{url}/health")
        assert r.status_code == 200 and r.text.strip() == "OK", f"GET /health -> {r.status_code} {r.text[:60]!r}"

    async def method_rules():
        async with httpx.AsyncClient(timeout=timeout) as http:
            for method in ("GET", "DELETE"):
                r = await http.request(method, f"{url}/mcp", headers={"Accept": "text/event-stream"})
                assert r.status_code == 405, f"{method} /mcp -> {r.status_code}, expected 405"
                assert r.headers.get("allow", "").upper() == "POST", f"{method} /mcp Allow={r.headers.get('allow')!r}"
        return "GET and DELETE on /mcp answer 405, Allow: POST"

    async def tool_list():
        async with mcp_session(url, {}, timeout) as session:
            tools = (await session.list_tools()).tools
        names = {t.name for t in tools}
        missing = EXPECTED_TOOLS - names
        assert not missing, f"missing tools: {sorted(missing)}"
        for t in tools:
            assert "ctx" not in t.inputSchema.get("properties", {}), f"{t.name} exposes an internal 'ctx' argument"
        return f"{len(tools)} tools"

    catalog: dict = {}

    async def catalog_check():
        err, text = await call(url, "list_models", {}, timeout=timeout)
        assert not err, text[:200]
        data = json.loads(text)
        assert data["count"] >= 30, f"only {data['count']} models listed"
        catalog["first"] = next(m["id"] for m in data["models"] if m["kind"] == "video")
        err, text = await call(url, "describe_model", {"model": catalog["first"]}, timeout=timeout)
        assert not err and "options" in json.loads(text), f"describe_model({catalog['first']}) failed: {text[:120]}"
        return f"{data['count']} models; describe_model works"

    async def no_key_is_refused():
        err, text = await call(url, "get_account", timeout=timeout)
        assert err, "get_account without a key unexpectedly succeeded"
        assert "Missing API key" in text, f"unclear message: {text[:160]}"

    async def validation_is_local():
        err, text = await call(url, "generate_image", {"prompt": "smoke test", "model": "veo-2"}, timeout=timeout)
        assert err and "generate_video" in text, f"wrong-kind model not rejected clearly: {text[:160]}"
        err, text = await call(url, "generate_video", {"prompt": "smoke test", "model": "no-such-model"}, timeout=timeout)
        assert err and "Unknown model" in text, f"unknown model not rejected clearly: {text[:160]}"
        return "bad requests are rejected before any credit is spent"

    await run_check(report, "health", health)
    await run_check(report, "http methods", method_rules)
    await run_check(report, "tool list", tool_list)
    await run_check(report, "catalog tools", catalog_check)
    await run_check(report, "missing key is refused", no_key_is_refused)
    await run_check(report, "validation errors", validation_is_local)

    # ---- checks that need a key
    no_key = None if key else "no API key given"

    async def bad_key():
        err, text = await call(url, "get_account", headers={"x-api-key": BAD_KEY}, timeout=timeout)
        assert err, "an invalid key was accepted"
        assert "x-api-key" in text or "Invalid or missing API key" in text, f"unclear message: {text[:160]}"
        assert BAD_KEY not in text, "the error echoes the key back"

    async def key_via(header_name):
        value = key if header_name == "x-api-key" else f"Bearer {key}"
        err, text = await call(url, "get_account", headers={header_name: value}, timeout=timeout)
        assert not err, f"get_account failed: {text[:200]}"
        acct = json.loads(text)
        assert acct.get("plan_id") is not None, f"unexpected account shape: {list(acct)}"
        return f"plan {acct['plan_id']}, {acct.get('available_credit')} credits available"

    async def free_api_call():
        err, text = await call(url, "list_generations", {"per_page": 1}, headers={"x-api-key": key}, timeout=timeout)
        assert not err, text[:200]
        assert "items" in json.loads(text), "unexpected list_generations shape"

    await run_check(report, "invalid key is refused", bad_key, skip_reason=no_key)
    await run_check(report, "valid key via x-api-key", lambda: key_via("x-api-key"), skip_reason=no_key)
    await run_check(report, "valid key via Authorization: Bearer", lambda: key_via("authorization"), skip_reason=no_key)
    await run_check(report, "free API call (list_generations)", free_api_call, skip_reason=no_key)

    # ---- opt-in: spends about 3 credits
    async def generate():
        headers = {"x-api-key": key}
        err, text = await call(url, "generate_image", {"prompt": "a quiet street at dawn, smoke test",
                                                       "model": "nano-banana-2-lite"}, headers=headers, timeout=timeout)
        assert not err, text[:200]
        job = json.loads(text)
        uuid, est = job["uuid"], job.get("estimated_credit")
        deadline = time.time() + args.generate_wait
        while time.time() < deadline:
            await asyncio.sleep(5)
            err, text = await call(url, "get_generation", {"uuid": uuid}, headers=headers, timeout=timeout)
            assert not err, text[:200]
            g = json.loads(text)
            assert not g["failed"], f"generation failed: {g.get('error')}"
            if g["done"]:
                assert g.get("image_urls"), "completed but no image URL"
                return f"estimated {est}, used {g.get('credits_used')} credits, {len(g['image_urls'])} image"
        raise AssertionError(f"not done after {args.generate_wait}s (uuid {uuid})")

    await run_check(report, "generate one image (spends credits)", generate,
                    skip_reason=no_key if args.generate else "pass --generate to run (about 3 credits)")

    passed = sum(1 for r in report.rows if r[0] == "PASS")
    skipped = sum(1 for r in report.rows if r[0] == "SKIP")
    print(f"\n{passed} passed, {report.failed} failed, {skipped} skipped")
    return 1 if report.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test for a running SnapGen MCP server.")
    parser.add_argument("--url", default=os.environ.get("SNAPGEN_MCP_URL", "http://127.0.0.1:8000"),
                        help="server base URL, without /mcp (default: $SNAPGEN_MCP_URL or http://127.0.0.1:8000)")
    parser.add_argument("--api-key", default=os.environ.get("SNAPGEN_API_KEY"),
                        help="SnapGen API key (default: $SNAPGEN_API_KEY); without one, key checks are skipped")
    parser.add_argument("--generate", action="store_true", help="also make one small image (about 3 credits)")
    parser.add_argument("--generate-wait", type=int, default=150, help="seconds to wait for that image (default 150)")
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request timeout in seconds (default 30)")
    args = parser.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
