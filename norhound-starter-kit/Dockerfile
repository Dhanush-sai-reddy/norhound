# NorHound container: pins Python 3.12 + uv + project deps so the grader needs
# nothing installed locally. Two entry points:
#   1) default: offline saved-data check (first_run.py) -- no network, seconds
#   2) norhound-full: the full live pipeline via scripts/norhound_live.sh
FROM python:3.12-slim

# TLS roots: python:3.12-slim ships without ca-certificates, and every live
# stage (brreg bulk download, NAV API, company sites) is HTTPS.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# uv pinned to the version that generated uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY tests ./tests
RUN uv sync --frozen

COPY . .

RUN chmod +x scripts/*.py first_run.py scripts/norhound_live.sh && \
    ln -sf /app/scripts/norhound_live.sh /usr/local/bin/norhound_live

# Offline proof of environment + saved-data behaviour. No download, no crawl.
CMD ["uv", "run", "python", "first_run.py"]