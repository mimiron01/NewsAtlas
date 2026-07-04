import pytest

from app.core.config import Settings, assert_secure_for_production


def test_app_env_variable_is_read_into_environment_field(monkeypatch):
    # Regression test: Settings.environment must be reachable via the APP_ENV env var,
    # not just by keyword construction — pydantic-settings doesn't map env vars to
    # field names automatically once an alias is declared, this was previously silently
    # broken (APP_ENV=production had no effect at all).
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings()
    assert settings.environment == "production"


def test_development_mode_allows_insecure_defaults():
    settings = Settings(environment="development", jwt_secret="change-me-in-production")
    assert_secure_for_production(settings)  # must not raise


def test_production_rejects_default_jwt_secret():
    settings = Settings(
        environment="production",
        jwt_secret="change-me-in-production",
        signup_invite_code="some-code",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_secure_for_production(settings)


def test_production_rejects_short_jwt_secret():
    settings = Settings(
        environment="production", jwt_secret="short", signup_invite_code="some-code"
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_secure_for_production(settings)


def test_production_rejects_missing_invite_code():
    settings = Settings(
        environment="production",
        jwt_secret="a" * 32,
        signup_invite_code="",
    )
    with pytest.raises(RuntimeError, match="SIGNUP_INVITE_CODE"):
        assert_secure_for_production(settings)


def test_production_passes_with_secure_config():
    settings = Settings(
        environment="production",
        jwt_secret="a" * 32,
        signup_invite_code="some-code",
    )
    assert_secure_for_production(settings)  # must not raise
