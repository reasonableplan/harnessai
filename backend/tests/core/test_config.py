"""AppConfig validate_required 테스트."""
from __future__ import annotations

import pytest

from src.core.config import AppConfig, reset_config
from src.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _reset():
    reset_config()
    yield
    reset_config()


class TestValidateRequired:
    def test_missing_database_url(self):
        config = AppConfig(
            database_url="",
            github_token="tok",
            github_owner="owner",
            github_repo="repo",
            anthropic_api_key="key",
        )
        with pytest.raises(ConfigError, match="DATABASE_URL"):
            config.validate_required()

    def test_missing_github_token(self):
        config = AppConfig(
            database_url="postgresql://x",
            github_token="",
            github_owner="owner",
            github_repo="repo",
            anthropic_api_key="key",
        )
        with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
            config.validate_required()

    def test_missing_github_owner(self):
        config = AppConfig(
            database_url="postgresql://x",
            github_token="tok",
            github_owner="",
            github_repo="repo",
            anthropic_api_key="key",
        )
        with pytest.raises(ConfigError, match="GITHUB_OWNER"):
            config.validate_required()

    def test_missing_github_repo(self):
        config = AppConfig(
            database_url="postgresql://x",
            github_token="tok",
            github_owner="owner",
            github_repo="",
            anthropic_api_key="key",
        )
        with pytest.raises(ConfigError, match="GITHUB_REPO"):
            config.validate_required()

    def test_missing_api_key_with_cli_fallback(self):
        """API키 없고 CLI도 비활성이면 use_cli가 True가 되어 통과한다."""
        config = AppConfig(
            database_url="postgresql://x",
            github_token="tok",
            github_owner="owner",
            github_repo="repo",
            anthropic_api_key="",
            use_claude_cli=False,
            use_local_model=False,
        )
        # use_cli property: not use_local_model and (use_claude_cli or not anthropic_api_key)
        # → not False and (False or not "") → True — CLI 모드로 폴백
        assert config.use_cli is True
        config.validate_required()  # should not raise

    def test_passes_with_cli_enabled(self):
        config = AppConfig(
            database_url="postgresql://x",
            github_token="tok",
            github_owner="owner",
            github_repo="repo",
            anthropic_api_key="",
            use_claude_cli=True,
        )
        config.validate_required()  # should not raise

    def test_passes_with_local_model(self):
        config = AppConfig(
            database_url="postgresql://x",
            github_token="tok",
            github_owner="owner",
            github_repo="repo",
            anthropic_api_key="",
            use_local_model=True,
        )
        config.validate_required()  # should not raise

    def test_all_valid(self):
        config = AppConfig(
            database_url="postgresql://x",
            github_token="tok",
            github_owner="owner",
            github_repo="repo",
            anthropic_api_key="key",
        )
        config.validate_required()  # should not raise


class TestProperties:
    def test_cors_origins_list(self):
        config = AppConfig(cors_origins="http://a.com, http://b.com")
        assert config.cors_origins_list == ["http://a.com", "http://b.com"]

    def test_is_production(self):
        config = AppConfig(app_env="production")
        assert config.is_production is True

    def test_is_not_production(self):
        config = AppConfig(app_env="development")
        assert config.is_production is False

    def test_use_cli_when_no_api_key(self):
        config = AppConfig(anthropic_api_key="", use_claude_cli=False, use_local_model=False)
        assert config.use_cli is True

    def test_use_cli_when_explicit(self):
        config = AppConfig(anthropic_api_key="key", use_claude_cli=True, use_local_model=False)
        assert config.use_cli is True
