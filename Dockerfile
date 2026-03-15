# 루트 Dockerfile — Python 백엔드 빌드
FROM python:3.12-slim AS runtime

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 의존성 먼저 설치 (캐시 레이어)
COPY backend/pyproject.toml backend/
RUN cd backend && uv sync --no-dev --no-editable

# 소스 복사
COPY backend/ backend/
COPY prompts/ prompts/

# non-root 유저
RUN groupadd -g 1001 agent && useradd -u 1001 -g agent -s /bin/sh -m agent
USER agent

ENV APP_ENV=production
EXPOSE 3001

CMD ["uv", "run", "--project", "backend", "python", "-m", "src.main"]
