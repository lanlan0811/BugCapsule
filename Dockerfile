FROM python:3.12.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system --gid 10001 bugcapsule \
    && useradd --system --uid 10001 --gid bugcapsule --home-dir /nonexistent bugcapsule \
    && pip install --no-cache-dir uv==0.8.13

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev \
    && chown -R bugcapsule:bugcapsule /app

USER bugcapsule

EXPOSE 8766

CMD ["uv", "run", "python", "-m", "bugcapsule.demo"]
