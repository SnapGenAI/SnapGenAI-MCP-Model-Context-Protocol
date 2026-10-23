# snapgen-mcp

MCP server for snapgen.ai image and video generation, for developers using Claude Code, Codex, Cursor
and similar clients. It runs locally over stdio or hosted over streamable HTTP. It is a thin adapter over the
snapgen.ai User API: auth, pricing, credit locking and billing all stay in the backend.

Authentication is your existing SnapGen API key. There is no OAuth: over HTTP you send the key as a header on
every request and the server forwards it to the API unchanged.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows; use .venv/bin/python on macOS/Linux
```

Create an API key at https://snapgen.ai/profile/integration/api-keys. Make a dedicated key for MCP so you can
revoke it on its own.

| Env var | Default | Used by |
|---|---|---|
| `SNAPGEN_API_KEY` | required for stdio | stdio only; **ignored in HTTP mode** |
| `SNAPGEN_BASE_URL` | `https://api.snapgen.ai` | both |
| `SNAPGEN_MCP_TRANSPORT` | `stdio` (or `--transport http`) | both |
| `SNAPGEN_MCP_HOST`, `SNAPGEN_MCP_PORT` | `127.0.0.1`, `8000` (or `--host`, `--port`) | HTTP |
| `SNAPGEN_MCP_ALLOWED_HOSTS` | unset | HTTP: comma-separated public hostnames, e.g. `mcp.example.com`. When set, requests whose `Host` header is not listed get `421`. |

## Tools

| Tool | Costs credits | Purpose |
|---|---|---|
| `get_account` | no | Plan and credit balance |
| `list_models` | no | Models, filterable by `kind` (image, video, extend, storyboard) or `family` |
| `describe_model` | no | One model's options with allowed values, reference limits, notes |
| `generate_image` | yes | Start an image job, returns a uuid |
| `generate_video` | yes | Start a video job, returns a uuid |
| `extend_video` | yes | Continue a Veo, Grok or Seedance video from its last frame |
| `generate_storyboard` | yes | Multi-scene Grok video (2-10 scenes) |
| `get_generation` | no | Poll a job; returns image or video URLs when done |
| `list_generations` | no | Recent history |

Generation is async: start a job, then poll `get_generation`.

## Models

35 image and video models in 10 families, plus 4 extend models and a storyboard, all driven by
`src/snapgen_mcp/registry.py`: nano-banana, gpt-image, grok, vela, veo (incl. omni-flash), seedance,
kling, minimax, flux, muse. Each model's options are validated locally before any credits are spent.
Model-specific settings go in `options`, e.g. `generate_video(model="seedance-2-omni", options={"duration": 8})`.

**Adding a model:** add one `ModelSpec` entry in `registry.py` and a test. Nothing else changes.

The registry was built from docs.snapgen.ai (geminigen-docs, `main`). Where the docs were ambiguous the
validation is permissive and the backend is the source of truth.

## Run over HTTP (hosted)

```bash
.venv/Scripts/python -m snapgen_mcp.server --transport http --host 0.0.0.0 --port 8000
```

- MCP endpoint: `POST /mcp`. Health check: `GET /health`.
- Stateless: each request is self-contained, so it works behind any load balancer. `GET` and `DELETE` on `/mcp`
  answer `405` with `Allow: POST`: there is no server-initiated stream to open and no session to end.
- Host header: bound to loopback (the default) the server only accepts loopback host names. Bound to anything else
  (the container uses `0.0.0.0`) it accepts the public hostname a proxy forwards, so it works behind a real domain.
  Set `SNAPGEN_MCP_ALLOWED_HOSTS` to enforce an allow-list.
- The key comes **only** from the request: `x-api-key: <key>` (preferred) or `Authorization: Bearer <key>`.
  The server never falls back to `SNAPGEN_API_KEY` for an HTTP caller, never stores keys and never logs them.
  A request without a key can list tools, but any tool call fails with a clear error before reaching the API.
- Terminate TLS at your proxy. Keys travel in headers, so never expose this endpoint over plain HTTP.

### Deploy with Docker

```bash
docker build -t snapgen-mcp .
docker run --rm -p 8000:8000 snapgen-mcp
```

The image holds no secrets and needs no configuration. It runs as an unprivileged user, listens on `0.0.0.0:8000`,
and reports health through `GET /health` (the container `HEALTHCHECK` uses it). `SNAPGEN_BASE_URL` can point it at a
different API environment (for example staging); `SNAPGEN_MCP_PORT` changes the port.

What the platform in front of it must do:

- **Terminate TLS.** Keys travel in request headers, so never publish the endpoint over plain HTTP.
- **Not log request headers or bodies** at the proxy or load balancer (`x-api-key`, `Authorization`). The server itself
  logs neither.
- **Rate limit per client IP** at the proxy. Per-user limits and credit checks already happen in the SnapGen API.
- **Health check** `GET /health` and send traffic to `POST /mcp`. Run as many replicas as you like: the server is
  stateless, so no sticky sessions are needed.
- **Forward the original `Host` header** (most proxies do by default), and set `SNAPGEN_MCP_ALLOWED_HOSTS` to the public
  hostname if you want the server to enforce it. No special idle timeout is needed: there are no long-lived streams.
- **Handle shutdown signals:** the process is PID 1 and exits cleanly on `SIGTERM`.

### Client configs (HTTP)

Claude Code:

```bash
claude mcp add --transport http snapgen https://YOUR-MCP-HOST/mcp --header "x-api-key: $SNAPGEN_API_KEY"
```

or in `.mcp.json` (the key stays in your environment, not in the file):

```json
{
  "mcpServers": {
    "snapgen": {
      "type": "http",
      "url": "https://YOUR-MCP-HOST/mcp",
      "headers": { "x-api-key": "${SNAPGEN_API_KEY}" }
    }
  }
}
```

Codex (`~/.codex/config.toml`), per the Codex MCP docs:

```toml
[mcp_servers.snapgen]
url = "https://YOUR-MCP-HOST/mcp"
bearer_token_env_var = "SNAPGEN_API_KEY"
```

### Tested clients

| Client | Status | Notes |
|---|---|---|
| Claude Code 2.1.227 (Windows) | Verified 2026-10-23 against a local container over plain HTTP | `${SNAPGEN_API_KEY}` expansion inside `headers` works, and so does a literal header. One plain-English request ("make an image of ...") submitted, polled and returned the image URL in about a minute. A wrong key and a missing key both give a readable error. No OAuth probing and no keys in the server log. Rechecked after `GET /mcp` started answering `405`: Claude Code takes the 405 and carries on, and the full image flow still works. |
| Codex desktop | Worked | Added through its Streamable HTTP form and connected successfully. Tested by hand by the maintainers; version and date not recorded. |
| Cursor | Worked | Tested by hand by the maintainers; version and date not recorded. |
| VS Code | Not tested yet | |

Claude Code was checked step by step (connect, balance, a full image request, error messages). Codex and Cursor were
tested by hand against the same server.

Not yet tested: a deployed server behind TLS and a proxy.

## Run locally over stdio

Claude Code:

```bash
claude mcp add snapgen -e SNAPGEN_API_KEY=your-key -- /abs/path/to/.venv/Scripts/python.exe -m snapgen_mcp.server
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "snapgen": {
      "command": "C:\\path\\to\\.venv\\Scripts\\python.exe",
      "args": ["-m", "snapgen_mcp.server"],
      "env": { "SNAPGEN_API_KEY": "your-key" }
    }
  }
}
```

## Develop and test

```bash
npx @modelcontextprotocol/inspector .venv/Scripts/python.exe -m snapgen_mcp.server   # poke at the tools by hand
.venv/Scripts/python -m pytest        # unit tests plus end-to-end HTTP tests against a fake API
```

### Smoke test a running server

Run it against any server (local, container, staging or production) after a deploy:

```bash
python scripts/smoke_test.py --url https://YOUR-MCP-HOST --api-key "$SNAPGEN_API_KEY"
```

It checks health, the `GET`/`DELETE` 405 rule, the tool list, the catalog tools, missing and invalid keys, that bad
requests are refused before any credit is spent, and (with a key) a valid key via both headers and a free call to the
SnapGen API. It prints PASS, FAIL or SKIP per check and exits 1 if anything fails.

- It never spends credits unless you pass `--generate` (one small image, about 3 credits).
- Without a key, the checks that need one are skipped, not failed. `--url` defaults to `$SNAPGEN_MCP_URL`.
- The key is read from `--api-key` or `$SNAPGEN_API_KEY` and is never printed.

### Dependency lock files

`requirements.lock` (what the Docker image installs) and `requirements-dev.lock` (CI) pin every package with hashes, and
pip refuses to install anything that does not match. They are generated on Linux with Python 3.12, so they omit
Windows-only packages: for local development use `pip install -e ".[dev]"` instead.

To add a dependency, edit `pyproject.toml` and regenerate. Add `--upgrade` to move to newer versions. `pip` and `pip-tools`
are pinned to the versions that made the current locks, and the CI lock check pins the same ones:

```bash
docker run --rm -v "$PWD":/work -w /work python:3.12-slim sh -c "pip install -q pip==25.0.1 pip-tools==7.6.2 && \
  pip-compile --generate-hashes --strip-extras -o requirements.lock pyproject.toml && \
  pip-compile --generate-hashes --strip-extras --extra dev -o requirements-dev.lock pyproject.toml"
```

(In Git Bash on Windows, use `"$(pwd -W):/work"` and prefix the command with `MSYS_NO_PATHCONV=1`.)

### CI

`.github/workflows/ci.yml` runs on every push, on pull requests, and on demand from the Actions tab:

- **Tests** on Python 3.10 and 3.13 (latest releases, unpinned) and on 3.12 installed from the lock.
- **Lock files** are re-resolved and must come out unchanged, so `pyproject.toml` and the locks cannot drift apart.
- **Docker image** is built, must run as an unprivileged user, must become healthy, and must pass the smoke test (without
  an API key, so only the credit-free checks run).
