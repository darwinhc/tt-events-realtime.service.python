"""SQLAlchemy user repository."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.domain.entities import User
from src.domain.exceptions import EntityConflictError
from src.domain.ports.database import UsersRepository

from .database import SQLAlchemyDatabase
from .mappers import user_model_to_entity
from .models import UserModel


class SQLAlchemyUsersRepository(UsersRepository):
    """Persist users with case-insensitive unique names."""

    def __init__(self, database: SQLAlchemyDatabase) -> None:
        self._database = database

    def create(self, user: User) -> User:
        try:
            with self._database.sessions.begin() as session:
                model = UserModel(name=user.name)
                session.add(model)
                session.flush()
                return user_model_to_entity(model)
        except IntegrityError as error:
            raise EntityConflictError(
                f"User name '{user.name}' already exists."
            ) from error

    def get_by_id(self, user_id: int) -> Optional[User]:
        with self._database.sessions() as session:
            model = session.get(UserModel, user_id)
            return user_model_to_entity(model) if model is not None else None

    def get_by_name(self, name: str) -> Optional[User]:
        statement = select(UserModel).where(
            func.lower(UserModel.name) == name.lower()
        )
        with self._database.sessions() as session:
            model = session.scalar(statement)
            return user_model_to_entity(model) if model is not None else None
