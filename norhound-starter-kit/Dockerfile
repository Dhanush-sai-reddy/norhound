# NorHound container: pins Python 3.12 + uv + project deps so the grader needs
# nothing installed locally. Two entry points:
#   1) default: offline saved-data check (first_run.py) -- no network, seconds
#   2) norhound-full: the full live pipeline via scripts/norhound_live.sh
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# uv (pinned) needs no system package manager on python:3.12-slim.
COPY --from=ghcr.io/astral-sh/uv:0.7.7 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY tests ./tests
RUN uv sync --frozen

COPY . .

RUN chmod +x scripts/*.py first_run.py scripts/norhound_live.sh && \
    ln -sf /app/scripts/norhound_live.sh /usr/local/bin/norhound_live

# Offline proof of environment + saved-data behaviour. No download, no crawl.
CMD ["uv", "run", "python", "first_run.py"]