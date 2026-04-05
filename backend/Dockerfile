# ---- Stage 1: 의존성 설치 ----
FROM python:3.12-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-editable --frozen

# ---- Stage 2: 런타임 ----
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 의존성 레이어 복사 (캐시 활용)
COPY --from=deps /app/.venv .venv/
COPY --from=deps /app/pyproject.toml /app/uv.lock ./

# 소스
COPY src/ src/
COPY agents/ agents/

# non-root 유저
RUN groupadd -g 1001 agent && useradd -u 1001 -g agent -s /bin/sh -m agent \
    && mkdir -p /app/workspace && chown -R agent:agent /app/workspace
USER agent

ENV APP_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 3002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3002/health')" || exit 1

CMD ["uv", "run", "python", "-m", "src.main"]
