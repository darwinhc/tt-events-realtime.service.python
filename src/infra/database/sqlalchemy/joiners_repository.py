"""SQLAlchemy implementation of the joiners repository."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.domain.entities import Joiner
from src.domain.exceptions import EntityConflictError, EntityNotFoundError
from src.domain.ports.database import JoinersRepository

from .database import SQLAlchemyDatabase
from .mappers import joiner_model_to_entity
from .models import EventModel, JoinerModel, UserModel

logger = logging.getLogger(__name__)


class SQLAlchemyJoinersRepository(JoinersRepository):
    """Persist event joiners through SQLAlchemy."""

    def __init__(self, database: SQLAlchemyDatabase) -> None:
        self._database = database

    def create(self, joiner: Joiner) -> Joiner:
        try:
            with self._database.sessions.begin() as session:
                if session.get(EventModel, joiner.event_id) is None:
                    raise EntityNotFoundError(
                        f"Event '{joiner.event_id}' does not exist."
                    )
                if session.get(UserModel, joiner.user_id) is None:
                    raise EntityNotFoundError(
                        f"User '{joiner.user_id}' does not exist."
                    )
                active = session.scalar(
                    select(JoinerModel).where(
                        JoinerModel.user_id == joiner.user_id,
                        JoinerModel.event_id == joiner.event_id,
                        JoinerModel.left_at.is_(None),
                    )
                )
                if active is not None:
                    raise EntityConflictError(
                        f"User '{joiner.user_id}' already joined "
                        f"event '{joiner.event_id}'."
                    )
                model = JoinerModel(
                    user_id=joiner.user_id,
                    event_id=joiner.event_id,
                    joined_at=joiner.joined_at,
                    left_at=None,
                )
                session.add(model)
                session.flush()
                created_joiner = joiner_model_to_entity(
                    model,
                    joiner.user_name,
                )
                logger.info(
                    "User joined event",
                    extra={
                        "checkpoint_id": "event-joined",
                        "event_id": created_joiner.event_id,
                        "user_id": created_joiner.user_id,
                    },
                )
                return created_joiner
        except IntegrityError as error:
            raise EntityConflictError(
                "The event joiner could not be created due to a conflict."
            ) from error

    def get(self, user_id: int, event_id: int) -> Optional[Joiner]:
        statement = select(JoinerModel).where(
            JoinerModel.user_id == user_id,
            JoinerModel.event_id == event_id,
            JoinerModel.left_at.is_(None),
        )
        with self._database.sessions() as session:
            model = session.scalar(statement)
            if model is None:
                return None
            user = session.get(UserModel, user_id)
            return joiner_model_to_entity(model, user.name)

    def get_all_by_event(self, event_id: int) -> list[Joiner]:
        statement = (
            select(JoinerModel, UserModel.name)
            .join(UserModel, UserModel.id == JoinerModel.user_id)
            .where(
                JoinerModel.event_id == event_id,
                JoinerModel.left_at.is_(None),
            )
            .order_by(UserModel.name)
        )
        with self._database.sessions() as session:
            return [
                joiner_model_to_entity(model, user_name)
                for model, user_name in session.execute(statement).all()
            ]

    def count_by_event(self, event_id: int) -> int:
        statement = (
            select(func.count())  # pylint: disable=not-callable
            .select_from(JoinerModel)
            .where(
                JoinerModel.event_id == event_id,
                JoinerModel.left_at.is_(None),
            )
        )
        with self._database.sessions() as session:
            return session.scalar(statement) or 0

    def count_by_events(self, event_ids: set[int]) -> dict[int, int]:
        if not event_ids:
            return {}
        statement = (
            select(
                JoinerModel.event_id,
                func.count(),  # pylint: disable=not-callable
            )
            .where(
                JoinerModel.event_id.in_(event_ids),
                JoinerModel.left_at.is_(None),
            )
            .group_by(JoinerModel.event_id)
        )
        with self._database.sessions() as session:
            return dict(session.execute(statement).all())

    def leave(
        self,
        user_id: int,
        event_id: int,
        left_at: datetime,
    ) -> Optional[Joiner]:
        if left_at.tzinfo is None:
            raise ValueError("Joiner leave datetime must include a timezone.")
        normalized_left_at = left_at.astimezone(timezone.utc)
        statement = select(JoinerModel).where(
            JoinerModel.user_id == user_id,
            JoinerModel.event_id == event_id,
            JoinerModel.left_at.is_(None),
        )
        with self._database.sessions.begin() as session:
            model = session.scalar(statement)
            if model is None:
                return None
            user = session.get(UserModel, user_id)
            model.left_at = normalized_left_at
            session.flush()
            left_joiner = joiner_model_to_entity(model, user.name)
            logger.info(
                "User left event",
                extra={
                    "checkpoint_id": "event-left",
                    "event_id": event_id,
                    "user_id": user_id,
                    "joiner_id": left_joiner.id,
                },
            )
            return left_joiner
