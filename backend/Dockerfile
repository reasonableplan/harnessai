FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 의존성 먼저 설치 (캐시 레이어)
COPY pyproject.toml .
RUN uv sync --no-dev --no-editable

# 소스 복사
COPY src/ src/

# non-root 유저
RUN groupadd -g 1001 agent && useradd -u 1001 -g agent -s /bin/sh -m agent
USER agent

ENV APP_ENV=production
EXPOSE 3001

CMD ["uv", "run", "python", "-m", "src.main"]
