"""SQLAlchemy implementation of the events' repository."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from src.domain.dtos import EventFilters
from src.domain.entities import Event
from src.domain.exceptions import EntityNotFoundError
from src.domain.ports.database import EventsRepository

from .database import SQLAlchemyDatabase
from .mappers import event_model_to_entity
from .models import EventModel, LocationModel, UserModel

logger = logging.getLogger(__name__)


def _apply_status_filter(statement, filters: EventFilters):
    if filters.statuses:
        return statement.where(
            EventModel.status.in_(
                [status.value for status in filters.statuses]
            )
        )
    return statement


def _apply_name_filter(statement, filters: EventFilters):
    if filters.name is not None:
        return statement.where(
            func.lower(EventModel.title).contains(filters.name.lower())
        )
    return statement


def _apply_schedule_filter(statement, filters: EventFilters):
    if filters.scheduled_from is not None:
        statement = statement.where(
            EventModel.scheduled_at
            >= filters.scheduled_from.astimezone(timezone.utc)
        )
    if filters.scheduled_until is not None:
        statement = statement.where(
            EventModel.scheduled_at
            < filters.scheduled_until.astimezone(timezone.utc)
        )
    return statement


def _apply_deletion_filter(statement, filters: EventFilters):
    if filters.deletion_scheduled_from is not None:
        statement = statement.where(
            EventModel.deletion_scheduled_at
            >= filters.deletion_scheduled_from.astimezone(timezone.utc)
        )
    if filters.deletion_scheduled_until is not None:
        statement = statement.where(
            EventModel.deletion_scheduled_at
            < filters.deletion_scheduled_until.astimezone(timezone.utc)
        )
    return statement


def _apply_location_filter(statement, filters: EventFilters):
    if filters.location_id is not None:
        return statement.where(
            EventModel.location_id == filters.location_id
        )
    return statement


class SQLAlchemyEventsRepository(EventsRepository):
    """Persist events through SQLAlchemy."""

    def __init__(self, database: SQLAlchemyDatabase) -> None:
        self._database = database

    def create(self, event: Event) -> Event:
        try:
            with self._database.sessions.begin() as session:
                if session.get(LocationModel, event.location_id) is None:
                    raise EntityNotFoundError(
                        f"Location '{event.location_id}' does not exist."
                    )
                if session.get(UserModel, event.organizer_id) is None:
                    raise EntityNotFoundError(
                        f"User '{event.organizer_id}' does not exist."
                    )
                model = EventModel(
                    **self._model_values(event),
                )
                session.add(model)
                session.flush()
                created_event = event_model_to_entity(
                    model,
                    organizer_name=event.organizer,
                )
                logger.info(
                    "Event created",
                    extra={
                        "checkpoint_id": "event-created",
                        "event_id": created_event.id,
                        "location_id": created_event.location_id,
                        "is_scheduled": created_event.scheduled_at is not None,
                    },
                )
                return created_event
        except IntegrityError as error:
            logger.warning(
                "Event creation failed referential integrity",
                extra={"checkpoint_id": "event-create-invalid-reference"},
            )
            raise EntityNotFoundError(
                "A user or location referenced by the event does not exist."
            ) from error

    def get_by_id(self, event_id: int) -> Optional[Event]:
        with self._database.sessions() as session:
            model = session.get(EventModel, event_id)
            logger.debug(
                "Event lookup completed",
                extra={
                    "checkpoint_id": "event-lookup",
                    "event_id": event_id,
                    "entity_found": model is not None,
                },
            )
            if model is None:
                return None
            organizer = session.get(UserModel, model.organizer_id)
            return event_model_to_entity(model, organizer.name)

    def get_all(
        self,
        filters: Optional[EventFilters] = None,
    ) -> list[Event]:
        filters = filters or EventFilters()
        statement = (
            select(EventModel, UserModel.name)
            .join(UserModel, UserModel.id == EventModel.organizer_id)
            .order_by(EventModel.id)
        )
        for apply_filter in (
            _apply_status_filter,
            _apply_name_filter,
            _apply_schedule_filter,
            _apply_deletion_filter,
            _apply_location_filter,
        ):
            statement = apply_filter(statement, filters)

        with self._database.sessions() as session:
            rows = session.execute(statement).all()
            logger.debug(
                "Filtered event lookup completed",
                extra={
                    "checkpoint_id": "events-filtered-lookup",
                    "result_count": len(rows),
                },
            )
            return [
                event_model_to_entity(model, organizer_name)
                for model, organizer_name in rows
            ]

    def get_page(
        self,
        filters: Optional[EventFilters],
        offset: int,
        limit: int,
    ) -> tuple[list[Event], int]:
        filters = filters or EventFilters()
        filtered_ids = select(EventModel.id)
        for apply_filter in (
            _apply_status_filter,
            _apply_name_filter,
            _apply_schedule_filter,
            _apply_deletion_filter,
            _apply_location_filter,
        ):
            filtered_ids = apply_filter(filtered_ids, filters)
        page_statement = (
            select(EventModel, UserModel.name)
            .join(UserModel, UserModel.id == EventModel.organizer_id)
            .where(EventModel.id.in_(filtered_ids))
            .order_by(EventModel.id)
            .offset(offset)
            .limit(limit)
        )
        count_statement = select(
            func.count()  # pylint: disable=not-callable
        ).select_from(
            filtered_ids.subquery()
        )
        with self._database.sessions() as session:
            total = session.scalar(count_statement) or 0
            rows = session.execute(page_statement).all()
            return (
                [
                    event_model_to_entity(model, organizer_name)
                    for model, organizer_name in rows
                ],
                total,
            )

    def update(self, event: Event) -> Event:
        if event.id is None:
            raise ValueError("Cannot update an event without an id.")
        with self._database.sessions.begin() as session:
            model = session.get(EventModel, event.id)
            if model is None:
                raise EntityNotFoundError(f"Event '{event.id}' does not exist.")
            organizer = session.get(UserModel, event.organizer_id)
            if organizer is None:
                raise EntityNotFoundError(
                    f"User '{event.organizer_id}' does not exist."
                )
            for field, value in self._model_values(
                event,
            ).items():
                setattr(model, field, value)
            session.flush()
            updated_event = event_model_to_entity(model, organizer.name)
            logger.info(
                "Event updated",
                extra={
                    "checkpoint_id": "event-updated",
                    "event_id": updated_event.id,
                    "event_status": updated_event.status.value,
                },
            )
            return updated_event

    def delete_due(self, as_of: datetime) -> int:
        if as_of.tzinfo is None:
            raise ValueError("Deletion cutoff must include a timezone.")
        cutoff = as_of.astimezone(timezone.utc)
        with self._database.sessions.begin() as session:
            events_to_delete = session.execute(
                select(
                    EventModel.id,
                    EventModel.title,
                    EventModel.deletion_scheduled_at,
                ).where(
                    EventModel.deletion_scheduled_at.is_not(None),
                    EventModel.deletion_scheduled_at <= cutoff,
                )
            ).all()


            if not events_to_delete:
                logger.info(
                    "No expired events found for deletion",
                    extra={
                        "checkpoint_id": "no-expired-events-to-delete",
                        "deleted_count": 0,
                    },
                )
                return 0

            events_id_to_delete = []
            for event in events_to_delete:
                logger.debug(
                    "Event found for deletion: event_id=%s, title=%s, deletion_scheduled_at=%s",
                    event.id,
                    event.title,
                    event.deletion_scheduled_at,
                    extra={
                        "checkpoint_id": "event-found-for-deletion",
                        "event_id": event.id,
                        "event_title": event.title,
                        "deletion_scheduled_at": event.deletion_scheduled_at,
                    },
                )
                events_id_to_delete.append(event.id)

            session.execute(
                delete(EventModel).where(
                    EventModel.id.in_(events_id_to_delete),
                )
            )
            n = len(events_id_to_delete)
            logger.info(
                "Expired events deleted",
                extra={
                    "checkpoint_id": "expired-events-deleted",
                    "deleted_count": n,
                    "deleted_event_ids": events_id_to_delete,
                },
            )

            return n

    @staticmethod
    def _model_values(event: Event) -> dict:
        return {
            "title": event.title,
            "organizer_id": event.organizer_id,
            "scheduled_at": event.scheduled_at,
            "duration_in_minutes": event.duration_in_minutes,
            "location_id": event.location_id,
            "status": event.status.value,
            "canceled_at": event.canceled_at,
            "deletion_scheduled_at": event.deletion_scheduled_at,
        }
