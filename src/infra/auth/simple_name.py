"""Simple authentication by visible user name."""

from src.domain.entities import User
from src.domain.ports.authentication import AuthenticationPort
from src.domain.ports.database import UsersRepository


class SimpleNameAuthentication(AuthenticationPort):
    """Resolve or register users by name without credentials."""

    def __init__(self, users: UsersRepository) -> None:
        self._users = users

    def authenticate(self, user_name: str) -> User:
        normalized_user = User(name=user_name)
        existing_user = self._users.get_by_name(normalized_user.name)
        if existing_user is not None:
            return existing_user
        return self._users.create(normalized_user)
