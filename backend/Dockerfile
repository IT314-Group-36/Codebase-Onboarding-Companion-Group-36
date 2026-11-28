# Base images are pinned (not "latest") so an unexpected upstream change cannot silently end up in the product.
# Update them on purpose. For the strongest pin, add the digest, e.g. python:3.12-slim-bookworm@sha256:<digest>
# (get it with: docker buildx imagetools inspect python:3.12-slim-bookworm).
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.9

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE}
# git is required: indexing clones repositories
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# dependencies first (cached layer), exactly as pinned in uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ai_pipeline ./ai_pipeline
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app PYTHONUNBUFFERED=1
# Run as an unprivileged user: this container parses and clones repositories that strangers control, so a flaw in
# Git or a parser must not hand the attacker root. The code stays root-owned and read-only for this user; the only
# place it can write is its own home and the clone work directory (WORK_DIR, default /tmp/onboarding_work).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /tmp/onboarding_work && chown app:app /tmp/onboarding_work
USER app
# Apply database migrations, then start the API. Hosts such as Render set $PORT; locally it falls back to 8000.
# One uvicorn process on purpose: indexing jobs run inside it, and small hosts have little RAM.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
