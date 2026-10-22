# SnapGen MCP server, hosted over streamable HTTP.
# Build:  docker build -t snapgen-mcp .
# Run:    docker run --rm -p 8000:8000 snapgen-mcp      (MCP endpoint /mcp, health check /health)
#
# No secrets live in this image. Every caller sends their own SnapGen API key in a request header, and the
# server forwards it to the API. SNAPGEN_API_KEY is not used in HTTP mode.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SNAPGEN_MCP_TRANSPORT=http \
    SNAPGEN_MCP_HOST=0.0.0.0 \
    SNAPGEN_MCP_PORT=8000

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install . && rm -rf /app/src /app/pyproject.toml /app/build

# Run as an unprivileged user.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin snapgen
USER snapgen

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "snapgen_mcp.healthcheck"]

# Exec form so the process is PID 1 and receives SIGTERM for a clean shutdown.
CMD ["snapgen-mcp"]
