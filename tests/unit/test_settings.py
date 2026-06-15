"""Settings loading tests."""

import pytest

from src.infra.config.settings import (
    _read_bool,
    _read_choice,
    _read_non_negative_int,
    get_settings,
)


def test_environment_overrides_dotenv(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("SQLALCHEMY_ECHO", "true")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://app.example.com, https://admin.example.com",
    )
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "text"
    assert settings.sqlalchemy_echo is True
    assert settings.cors_allowed_origins == (
        "https://app.example.com",
        "https://admin.example.com",
    )
    assert settings.event_deletion_delay_minutes == 7
    assert settings.canceled_event_deletion_delay_days == 1
    get_settings.cache_clear()


@pytest.mark.parametrize("value", ["maybe", "2", "truthy"])
def test_invalid_boolean_environment_value_is_rejected(
    monkeypatch,
    value,
) -> None:
    monkeypatch.setenv("FEATURE_FLAG", value)

    with pytest.raises(ValueError, match="boolean"):
        _read_bool("FEATURE_FLAG", False)


def test_boolean_reader_supports_defaults_and_false_values(monkeypatch) -> None:
    monkeypatch.delenv("FEATURE_FLAG", raising=False)
    assert _read_bool("FEATURE_FLAG", True) is True
    monkeypatch.setenv("FEATURE_FLAG", "off")
    assert _read_bool("FEATURE_FLAG", True) is False


def test_choice_and_non_negative_integer_validation(monkeypatch) -> None:
    monkeypatch.setenv("MODE", "invalid")
    with pytest.raises(ValueError, match="one of"):
        _read_choice("MODE", "json", {"json", "text"})

    monkeypatch.setenv("COUNT", "not-a-number")
    with pytest.raises(ValueError, match="non-negative"):
        _read_non_negative_int("COUNT", 1)
    monkeypatch.setenv("COUNT", "-1")
    with pytest.raises(ValueError, match="non-negative"):
        _read_non_negative_int("COUNT", 1)


def test_empty_required_setting_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", " ")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="APP_NAME cannot be empty"):
        get_settings()

    get_settings.cache_clear()
