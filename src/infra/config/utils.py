"""Utils for reading configuration values."""
import os


def read_bool(name: str, default: bool) -> bool:
    """Read a boolean value."""
    value = os.getenv(name)
    if value is None:
        return default
    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def read_choice(name: str, default: str, choices: set[str]) -> str:
    """Read a value that must be one of the given choices."""
    value = os.getenv(name, default).strip().lower()
    if value not in choices:
        expected_values = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {expected_values}.")
    return value


def read_non_negative_int(name: str, default: int) -> int:
    """Read an integer value that must be non-negative."""
    value = os.getenv(name, str(default)).strip()
    try:
        parsed_value = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a non-negative integer.") from error
    if parsed_value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return parsed_value
