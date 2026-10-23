# SnapGen MCP Server — AI Video & Image Generation for Claude Code, Codex and Cursor

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-server-8A2BE2)](https://modelcontextprotocol.io)
[![Transport](https://img.shields.io/badge/transport-stdio%20%7C%20Streamable%20HTTP-informational)](#-run--deploy)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](#deploy-with-docker)
[![CI](https://github.com/SnapGenAI/SnapGenAI-MCP-Model-Context-Protocol/actions/workflows/ci.yml/badge.svg)](https://github.com/SnapGenAI/SnapGenAI-MCP-Model-Context-Protocol/actions/workflows/ci.yml)

**SnapGen MCP Server** by SnapGen. Let your AI coding assistant create images and videos with **35 models** — Veo, Kling, Seedance, Grok, Minimax, Flux, Nano Banana, GPT Image and more — straight from the chat. Text-to-video, image-to-video, video extend and storyboards, using your existing SnapGen API key. 👉 <a href="https://snapgen.ai/profile/integration/api-keys" target="_blank">Get an API key</a> · <a href="https://snapgen.ai/pricing" target="_blank">Check Pricing</a>.

> [!NOTE]
> Want a full editor instead? Try the [SnapGen web app](https://snapgen.ai) — create and edit images and videos in a clean, easy-to-use interface. Looking for the plain REST API? See the [API documentation](https://docs.snapgen.ai).

## ✨ Features

- **🔌 Works With Your Assistant** — Connects to Claude Code, Codex, Cursor and any MCP client, locally over stdio or hosted over Streamable HTTP.
- **🎬 Text-to-Video & Image-to-Video** — 28 video models across Veo, Kling, Seedance, Grok, Minimax, Flux, Vela and Muse, from quick drafts to cinematic clips.
- **🖼️ Image Generation** — 7 image models, including the Nano Banana family, GPT Image, Grok and Vela.
- **🧩 Reference Media** — Guide a generation with images, videos, audio or earlier generations. Limits are per model and the assistant can read them.
- **⏩ Extend Video** — Continue a Veo, Grok or Seedance clip from its last frame, keeping the motion, look and lighting.
- **🎞️ Storyboards** — Chain 2–10 Grok scenes into one merged video.
- **🧠 Self-Describing** — `list_models` and `describe_model` tell the assistant which models exist, their options, limits and notes, so you do not have to explain them.
- **🛡️ Checked Before You Pay** — Every request is validated against the model's rules first. Invalid options, too many references or a wrong tool are refused with a clear message before any credit is spent.
- **🔑 Your Key, Every Request** — Over HTTP the key travels in a header, is never stored or logged, and the server never falls back to its own key. No OAuth to set up.
- **🐳 Ready to Host** — Stateless, runs as a non-root Docker image with a health check, so it works behind any load balancer.

## 🎯 Usage Guide

### 🚀 Quick Start

1. **Get an API key** — Create one at [snapgen.ai](https://snapgen.ai/profile/integration/api-keys). Make a dedicated key for MCP so you can revoke it on its own.
2. **Install** — Clone this repo and install it:

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -e ".[dev]"     # Windows; use .venv/bin/python on macOS/Linux
   ```

3. **Add it to your assistant** — Local mode (stdio), for example in Claude Code:

   ```bash
   claude mcp add snapgen -e SNAPGEN_API_KEY=your-key -- /abs/path/to/.venv/Scripts/python.exe -m snapgen_mcp.server
   ```

   Hosted or shared setups should use [Streamable HTTP](#-run--deploy) instead.
4. **Ask away** — Try *"What's my SnapGen credit balance?"* (free), then *"Make an image of a foggy street at dawn."*

### 🎬 Creating Images & Videos

1. **Describe what you want** — Plain English. Mention a model by name if you have a favourite, or let the assistant choose.
2. **Add references (optional)** — Point to images, videos or earlier generations to guide the result. Not every model accepts every kind; the assistant checks with `describe_model`.
3. **Check the cost** — Every generation returns an `estimated_credit`, and the tools tell the assistant to state the cost before spending.
4. **Generate and wait** — Generation is asynchronous: the assistant starts a job, then checks `get_generation` until it is done. Images take seconds, videos one to a few minutes.
5. **Get your files** — The finished job returns image or video links. They are signed links that expire after about 7 days, so download what you want to keep.

### ⏩ Extend Video

1. **Pick a finished video** — From a Veo, Grok or Seedance generation (storyboards cannot be extended).
2. **Describe what happens next** — The new clip starts from the last frame.
3. **Extend** — Settings such as model, aspect ratio and resolution are taken from the original video. Most models do not let you change them.

### 💡 Tips for Best Results

- ✍️ **Be specific**: The more detailed your prompt, the better the result.
- 🖼️ **Use references**: Reference images improve consistency of characters and style.
- 💰 **Start small**: Short durations and low resolutions cost the least, so test an idea cheaply first.
- 🔎 **Ask for options**: `describe_model` lists every allowed value for a model, so nothing is guesswork.

## 🧰 Tools

| Tool | Costs credits | Purpose |
|---|---|---|
| `get_account` | no | Plan and credit balance |
| `list_models` | no | Models, filterable by `kind` (image, video, extend, storyboard) or `family` |
| `describe_model` | no | One model's options with allowed values, reference limits, pricing notes |
| `generate_image` | yes | Start an image job, returns a uuid |
| `generate_video` | yes | Start a video job, returns a uuid |
| `extend_video` | yes | Continue a Veo, Grok or Seedance video from its last frame |
| `generate_storyboard` | yes | Multi-scene Grok video (2–10 scenes) |
| `get_generation` | no | Check a job; returns image or video URLs when done |
| `list_generations` | no | Recent history |

Model-specific settings go in `options`, for example `generate_video(model="seedance-2-omni", options={"duration": 8})`.

## 🎨 Supported Models

| Family | Models |
|---|---|
| **Nano Banana** | `nano-banana-pro`, `nano-banana-2`, `nano-banana-2-lite` (images) |
| **GPT Image** | `gpt-image-2`, `gpt-image-2.5-lower` (images) |
| **Veo / Omni** | `veo-3.1`, `veo-3.1-fast`, `veo-3.1-lite`, `veo-2`, `omni-flash` · extend: `veo-extend` |
| **Kling** | `kling-video-4-0`, `kling-video-4-0-flash`, `kling-video-3-0`, `kling-video-2-6`, `kling-video-2-5`, `kling-video-2-1-5s`, `kling-video-2-1-10s` · motion control: `kling-video-motion-4`, `kling-video-motion-3`, `kling-video-motion` · edit: `kling-video-3-0-edit` |
| **Seedance** | `seedance-2-omni`, `seedance-2-mini`, `seedance-2-5-omni`, `sd-2-lower`, `sd-2-5-lower` · extend: `seedance-extend` |
| **Grok** | `grok-image` (image), `grok-3`, `grok-lower`, `grok-1.5-lite` (video) · extend: `grok-extend`, `grok-1.5-lite-extend` · storyboard: `grok-storyboard` |
| **Minimax** | `minimax-h3` |
| **Flux** | `flux-3` |
| **Vela** | `vela-image` (image), `vela-ai-video` |
| **Muse** | `muse-ai-video` |

> [!NOTE]
> Some models need a Premium plan, and a model can be temporarily unavailable when the SnapGen service is under maintenance or heavy load. The error message says which. `describe_model` shows each model's plan requirement and pricing notes.

The catalog is driven by [`src/snapgen_mcp/registry.py`](src/snapgen_mcp/registry.py). **Adding a model** takes one `ModelSpec` entry and a test; nothing else changes. It was built from the [SnapGen API docs](https://docs.snapgen.ai), and where the docs were ambiguous the validation is permissive and the backend is the source of truth.

## ⚙️ Configuration

| Env var | Default | Used by |
|---|---|---|
| `SNAPGEN_API_KEY` | required for stdio | stdio only; **ignored in HTTP mode** |
| `SNAPGEN_BASE_URL` | `https://api.snapgen.ai` | both |
| `SNAPGEN_MCP_TRANSPORT` | `stdio` (or `--transport http`) | both |
| `SNAPGEN_MCP_HOST`, `SNAPGEN_MCP_PORT` | `127.0.0.1`, `8000` (or `--host`, `--port`) | HTTP |
| `SNAPGEN_MCP_ALLOWED_HOSTS` | unset | HTTP: comma-separated public hostnames, e.g. `mcp.example.com`. When set, requests whose `Host` header is not listed get `421`. |

## 🚀 Run & Deploy

### Run over HTTP (hosted)

```bash
.venv/Scripts/python -m snapgen_mcp.server --transport http --host 0.0.0.0 --port 8000
```

- MCP endpoint: `POST /mcp`. Health check: `GET /health`.
- Stateless: each request is self-contained, so it works behind any load balancer. `GET` and `DELETE` on `/mcp` answer `405` with `Allow: POST`: there is no server-initiated stream to open and no session to end.
- The key comes **only** from the request: `x-api-key: <key>` (preferred) or `Authorization: Bearer <key>`. The server never falls back to `SNAPGEN_API_KEY` for an HTTP caller, never stores keys and never logs them. A request without a key can list tools, but any tool call fails with a clear error before reaching the API.
- Host header: bound to loopback (the default) the server only accepts loopback host names. Bound to anything else (the container uses `0.0.0.0`) it accepts the public hostname a proxy forwards, so it works behind a real domain. Set `SNAPGEN_MCP_ALLOWED_HOSTS` to enforce an allow-list.
- Terminate TLS at your proxy. Keys travel in headers, so never expose this endpoint over plain HTTP.

### Deploy with Docker

```bash
docker build -t snapgen-mcp .
docker run --rm -p 8000:8000 snapgen-mcp
```

The image holds no secrets and needs no configuration. It runs as an unprivileged user, listens on `0.0.0.0:8000`, and reports health through `GET /health` (the container `HEALTHCHECK` uses it). `SNAPGEN_BASE_URL` can point it at a different API environment (for example staging); `SNAPGEN_MCP_PORT` changes the port.

What the platform in front of it must do:

- **Terminate TLS.** Keys travel in request headers, so never publish the endpoint over plain HTTP.
- **Not log request headers or bodies** at the proxy or load balancer (`x-api-key`, `Authorization`). The server itself logs neither.
- **Rate limit per client IP** at the proxy. Per-user limits and credit checks already happen in the SnapGen API.
- **Health check** `GET /health` and send traffic to `POST /mcp`. Run as many replicas as you like: the server is stateless, so no sticky sessions are needed.
- **Forward the original `Host` header** (most proxies do by default), and set `SNAPGEN_MCP_ALLOWED_HOSTS` to the public hostname if you want the server to enforce it. No special idle timeout is needed: there are no long-lived streams.
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

### Client config (stdio)

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

### Tested clients

| Client | Status | Notes |
|---|---|---|
| Claude Code 2.1.227 (Windows) | Verified 2026-10-23 against a local container over plain HTTP | `${SNAPGEN_API_KEY}` expansion inside `headers` works, and so does a literal header. One plain-English request ("make an image of ...") submitted, polled and returned the image URL in about a minute. A wrong key and a missing key both give a readable error. No OAuth probing and no keys in the server log. Rechecked after `GET /mcp` started answering `405`: Claude Code takes the 405 and carries on, and the full image flow still works. |
| Codex desktop | Worked | Added through its Streamable HTTP form and connected successfully. Tested by hand by the maintainers. |
| Cursor | Worked | Tested by hand by the maintainers. |

Claude Code was checked step by step (connect, balance, a full image request, error messages). Codex and Cursor were tested by hand against the same server.

Not yet tested: a deployed server behind TLS and a proxy.

## 🎬 Results & Examples

See what an assistant can do with these tools. We will take the example: **generate an image from one sentence**, in Claude Code.

**🎯 Prompt Example:**

> Use the snapgen tools to make one image with the nano-banana-2-lite model of: a typewriter and an ink ribbon on a wooden desk in a dim safe room, warm lamp light. Submit the job, keep checking until it is done, then tell me the credits used and the image URL.

**⚙️ What happened:**
- Tools called: `generate_image`, then `get_generation` until the job finished
- Model: **nano-banana-2-lite**
- Cost: **3 credits**, matching the estimate returned at submit time
- Time: about a minute, start to finish

**🖼️ Output:** a completed job with a signed link to the generated image.

## 🛠️ Development

```bash
npx @modelcontextprotocol/inspector .venv/Scripts/python.exe -m snapgen_mcp.server   # poke at the tools by hand
.venv/Scripts/python -m pytest        # unit tests plus end-to-end HTTP tests against a fake API
```

## 🤝 Contributing

We warmly welcome contributions in the form of:

- 💡 **Feature Suggestions** — Share ideas to improve or expand what the assistant can do.
- 🛠 **Enhancements** — Propose improvements to model coverage, validation or performance.
- 🐞 **Bug Reports** — Help us identify and fix issues to keep the experience smooth.
- 📈 **Collaboration** — We are open to discussions about partnerships or integrations.

👉 If you’d like to contribute, please reach out via **Issues** or contact us directly at [contact@geminigen.ai](mailto:contact@geminigen.ai)

## 📄 License

Licensed under the [Apache License, Version 2.0](LICENSE).

## 🔗 Links & Resources

- 👨‍💻 **Our website:** [https://snapgen.ai](https://snapgen.ai/)
- 📚 **Our API Documentation:** [https://docs.snapgen.ai](https://docs.snapgen.ai/)
- 🔑 **API keys:** [https://snapgen.ai/profile/integration/api-keys](https://snapgen.ai/profile/integration/api-keys)
- 💳 **Pricing:** [https://snapgen.ai/pricing](https://snapgen.ai/pricing)
- 🧩 **Model Context Protocol:** [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
