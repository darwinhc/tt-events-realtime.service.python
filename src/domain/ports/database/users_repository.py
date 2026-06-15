"""User repository port."""

from abc import abstractmethod
from typing import Optional

from src.domain.entities import User

from .repository import Repository


class UsersRepository(Repository):
    """Technology-neutral persistence operations for users."""

    @abstractmethod
    def create(self, user: User) -> User:
        """Persist a user."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]:
        """Return a user by integer identifier."""
        raise NotImplementedError

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[User]:
        """Return a user by visible name."""
        raise NotImplementedError
