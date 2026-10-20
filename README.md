# snapgen-mcp

Local MCP server (stdio) for snapgen.ai image and video generation. It is a thin adapter over the
snapgen.ai User API: auth, pricing, credit locking and billing all stay in the backend.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows; use .venv/bin/python on macOS/Linux
```

Create an API key at https://snapgen.ai/profile/integration/api-keys, then:

| Env var | Default |
|---|---|
| `SNAPGEN_API_KEY` | required |
| `SNAPGEN_BASE_URL` | `https://api.snapgen.ai` |

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

34 image and video models in 10 families, plus 4 extend models and a storyboard, all driven by
`src/snapgen_mcp/registry.py`: nano-banana, gpt-image, grok, vela, veo (incl. omni-flash), seedance,
kling, minimax, flux, muse. Each model's options are validated locally before any credits are spent.
Model-specific settings go in `options`, e.g. `generate_video(model="seedance-2-omni", options={"duration": 8})`.

**Adding a model:** add one `ModelSpec` entry in `registry.py` and a test. Nothing else changes.

The registry was built from docs.snapgen.ai (geminigen-docs, `main`). Where the docs were ambiguous the
validation is permissive and the backend is the source of truth.

## Use with Claude Code

```bash
claude mcp add snapgen -e SNAPGEN_API_KEY=your-key -- /abs/path/to/.venv/Scripts/python.exe -m snapgen_mcp.server
```

## Use with Claude Desktop

Add to `claude_desktop_config.json`:

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
.venv/Scripts/python -m pytest
```
