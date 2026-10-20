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
| `list_models` | no | Supported image and video models |
| `generate_image` | yes | Start an image job, returns a uuid |
| `generate_video` | yes | Start a Veo-family video job, returns a uuid |
| `get_generation` | no | Poll a job; returns image or video URLs when done |
| `list_generations` | no | Recent history |

Generation is async: start a job, then poll `get_generation`.

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
