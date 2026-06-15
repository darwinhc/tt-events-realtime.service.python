"""Authentication port."""

from typing import Protocol

from src.domain.entities import User


class AuthenticationPort(Protocol):
    """Resolve simple text identity into a persisted application user."""

    def authenticate(self, user_name: str) -> User:
        """Return the existing user or register it for this simple runtime."""
