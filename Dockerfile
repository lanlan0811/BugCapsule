FROM python:3.12.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy

WORKDIR /app

ARG BUGCAPSULE_DEMO_CONTAINER_TELEMETRY_DIR=/var/lib/bugcapsule

RUN groupadd --system --gid 10001 bugcapsule \
    && useradd --system --uid 10001 --gid bugcapsule --home-dir /nonexistent bugcapsule \
    && pip install --no-cache-dir uv==0.8.13

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev \
    && mkdir --parents "$BUGCAPSULE_DEMO_CONTAINER_TELEMETRY_DIR" \
    && chown -R bugcapsule:bugcapsule /app "$BUGCAPSULE_DEMO_CONTAINER_TELEMETRY_DIR"

USER bugcapsule

EXPOSE 8766

CMD ["/app/.venv/bin/python", "-m", "bugcapsule.demo"]
