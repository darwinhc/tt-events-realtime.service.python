"""Reusable unit-test fakes."""

from src.domain.entities import User


class FakeAuthentication:
    """Resolve names to deterministic integer users."""

    def __init__(self, users: dict[str, int] | None = None) -> None:
        self._users = dict(users or {"darwin": 1})
        self.authenticated_names = []

    def authenticate(self, user_name: str) -> User:
        normalized_name = user_name.strip()
        self.authenticated_names.append(normalized_name)
        user_id = self._users.setdefault(
            normalized_name,
            len(self._users) + 1,
        )
        return User(id=user_id, name=normalized_name)
