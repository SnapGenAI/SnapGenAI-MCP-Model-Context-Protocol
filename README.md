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

32 image and video models in 10 families, plus 4 extend models and a storyboard, all driven by
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
- Stateless: each request is self-contained, so it works behind any load balancer.
- The key comes **only** from the request: `x-api-key: <key>` (preferred) or `Authorization: Bearer <key>`.
  The server never falls back to `SNAPGEN_API_KEY` for an HTTP caller, never stores keys and never logs them.
  A request without a key can list tools, but any tool call fails with a clear error before reaching the API.
- Terminate TLS at your proxy. Keys travel in headers, so never expose this endpoint over plain HTTP.

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

These client configs follow each client's documentation but have not yet been tried against a deployed server.

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

## Inspect and test

```bash
npx @modelcontextprotocol/inspector .venv/Scripts/python.exe -m snapgen_mcp.server
.venv/Scripts/python -m pytest        # unit tests plus an end-to-end HTTP test with a fake API
```
