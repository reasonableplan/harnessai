from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.errors import ConfigError

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"


class AppConfig(BaseSettings):
    """전체 애플리케이션 설정. 환경변수에서 자동 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = ""

    # GitHub
    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""
    github_project_number: int | None = None

    # Claude / LLM
    anthropic_api_key: str = ""
    use_claude_cli: bool = False
    use_local_model: bool = False
    local_model_base_url: str = "http://localhost:11434/v1"
    local_model_name: str = "llama3.1"
    local_model_api_key: str | None = None

    # Workspace
    git_work_dir: str = "./workspace"

    # Dashboard
    dashboard_port: int = 3001
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    dashboard_auth_token: str | None = None

    # Logging
    log_level: str = "info"
    app_env: str = "development"

    @property
    def use_cli(self) -> bool:
        return not self.use_local_model and (
            self.use_claude_cli or not self.anthropic_api_key
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_required(self) -> None:
        """프로덕션 모드에서 필수 환경변수 검증."""
        if not self.database_url:
            raise ConfigError("Missing required environment variable: DATABASE_URL")
        if not self.github_token:
            raise ConfigError("Missing required environment variable: GITHUB_TOKEN")
        if not self.github_owner:
            raise ConfigError("Missing required environment variable: GITHUB_OWNER")
        if not self.github_repo:
            raise ConfigError("Missing required environment variable: GITHUB_REPO")
        if not self.use_cli and not self.use_local_model and not self.anthropic_api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is required when USE_CLAUDE_CLI and USE_LOCAL_MODEL are not enabled.\n"
                "Set ANTHROPIC_API_KEY, USE_CLAUDE_CLI=true, or USE_LOCAL_MODEL=true."
            )


_config: AppConfig | None = None


def get_config(require_all: bool = True) -> AppConfig:
    """싱글톤 설정 객체 반환. 최초 호출 시 환경변수에서 로드."""
    global _config
    if _config is None:
        _config = AppConfig()
        if require_all:
            _config.validate_required()
    return _config


def reset_config() -> None:
    """테스트에서 설정 초기화용."""
    global _config
    _config = None
