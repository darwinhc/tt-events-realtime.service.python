"""Join-event and leave-event use-case tests."""

from datetime import datetime, timezone

import pytest

from src.domain.dtos import EventFilters
from src.domain.entities import Event, Joiner
from src.domain.exceptions import DomainValidationError, EntityNotFoundError
from src.domain.ports.database import EventsRepository, JoinersRepository
from src.domain.use_cases.join_event import join_event
from src.domain.use_cases.leave_event import leave_event
from src.domain.use_cases.get_all_guests import get_all_guests
from tests.unit.fakes import FakeAuthentication


class InMemoryEventsRepository(EventsRepository):
    def __init__(self, event: Event) -> None:
        self.event = event

    def create(self, event: Event) -> Event:
        self.event = event
        return event

    def get_by_id(self, event_id: int):
        return self.event if self.event.id == event_id else None

    def get_all(
        self,
        filters: EventFilters | None = None,
    ) -> list[Event]:
        return [self.event]

    def update(self, event: Event) -> Event:
        self.event = event
        return event

    def delete_due(self, as_of: datetime) -> int:
        return 0


class InMemoryJoinersRepository(JoinersRepository):
    def __init__(self) -> None:
        self.joiners = []

    def create(self, joiner: Joiner) -> Joiner:
        created = joiner.model_copy(update={"id": len(self.joiners) + 1})
        self.joiners.append(created)
        return created

    def get(self, user_id: int, event_id: int):
        return next(
            (
                joiner
                for joiner in self.joiners
                if joiner.user_id == user_id
                and joiner.event_id == event_id
                and joiner.left_at is None
            ),
            None,
        )

    def get_all_by_event(self, event_id: int) -> list[Joiner]:
        return sorted(
            (
                joiner
                for joiner in self.joiners
                if joiner.event_id == event_id and joiner.left_at is None
            ),
            key=lambda joiner: joiner.user_id,
        )

    def count_by_event(self, event_id: int) -> int:
        return len(self.get_all_by_event(event_id))

    def count_by_events(self, event_ids: set[int]) -> dict[int, int]:
        return {
            event_id: self.count_by_event(event_id)
            for event_id in event_ids
        }

    def leave(self, user_id: int, event_id: int, left_at: datetime):
        active = self.get(user_id, event_id)
        if active is None:
            return None
        left = active.model_copy(update={"left_at": left_at})
        self.joiners[self.joiners.index(active)] = left
        return left


def build_event() -> Event:
    return Event(
        id=1,
        title="Joinable event",
        organizer="darwin",
        organizer_id=1,
        duration_in_minutes=60,
        location_id=1,
    )


def test_user_completes_join_and_leave_event_process() -> None:
    events = InMemoryEventsRepository(build_event())
    joiners = InMemoryJoinersRepository()
    authentication = FakeAuthentication({"external-user": 2})

    assert joiners.get(2, 1) is None

    created = join_event(
        "external-user",
        1,
        events=events,
        joiners=joiners,
        authentication=authentication,
    )

    persisted = joiners.get(2, 1)
    assert created.id == 1
    assert created.user_id == 2
    assert created.user_name == "external-user"
    assert created.event_id == 1
    assert created.left_at is None
    assert persisted == created

    left_at = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    left = leave_event(
        user_name="external-user",
        event_id=1,
        joiners=joiners,
        authentication=authentication,
        clock=lambda: left_at,
    )

    assert left.id == created.id
    assert left.left_at == left_at
    assert joiners.get(2, 1) is None
    assert joiners.joiners == [left]

    rejoined = join_event(
        "external-user",
        1,
        events=events,
        joiners=joiners,
        authentication=authentication,
    )

    assert rejoined.id == 2
    assert rejoined.left_at is None
    assert len(joiners.joiners) == 2


def test_cannot_join_canceled_event() -> None:
    canceled_event = build_event().cancel(
        datetime(2026, 8, 10, tzinfo=timezone.utc),
        deletion_delay_minutes=1,
    )

    with pytest.raises(DomainValidationError):
        join_event(
            "external-user",
            1,
            events=InMemoryEventsRepository(canceled_event),
            joiners=InMemoryJoinersRepository(),
            authentication=FakeAuthentication(),
        )


def test_cannot_join_event_at_or_after_its_end_time() -> None:
    scheduled_event = build_event().model_copy(
        update={
            "scheduled_at": datetime(
                2026,
                8,
                20,
                18,
                tzinfo=timezone.utc,
            ),
            "duration_in_minutes": 120,
        }
    )

    for current_time in (
        datetime(2026, 8, 20, 20, tzinfo=timezone.utc),
        datetime(2026, 8, 20, 20, 1, tzinfo=timezone.utc),
    ):
        with pytest.raises(DomainValidationError, match="completed"):
            join_event(
                "external-user",
                1,
                events=InMemoryEventsRepository(scheduled_event),
                joiners=InMemoryJoinersRepository(),
                authentication=FakeAuthentication(),
                clock=lambda value=current_time: value,
            )


def test_can_join_before_end_or_when_event_has_no_schedule() -> None:
    current_time = datetime(2026, 8, 20, 19, 59, tzinfo=timezone.utc)
    scheduled_event = build_event().model_copy(
        update={
            "scheduled_at": datetime(
                2026,
                8,
                20,
                18,
                tzinfo=timezone.utc,
            ),
            "duration_in_minutes": 120,
        }
    )

    before_end = join_event(
        "external-user",
        1,
        events=InMemoryEventsRepository(scheduled_event),
        joiners=InMemoryJoinersRepository(),
        authentication=FakeAuthentication({"external-user": 2}),
        clock=lambda: current_time,
    )
    unscheduled = join_event(
        "another-user",
        1,
        events=InMemoryEventsRepository(build_event()),
        joiners=InMemoryJoinersRepository(),
        authentication=FakeAuthentication({"another-user": 3}),
        clock=lambda: current_time,
    )

    assert before_end.joined_at == current_time
    assert unscheduled.joined_at == current_time


def test_leave_requires_existing_joiner() -> None:
    with pytest.raises(EntityNotFoundError):
        leave_event(
            user_name="external-user",
            event_id=1,
            joiners=InMemoryJoinersRepository(),
            authentication=FakeAuthentication({"external-user": 2}),
        )


def test_gets_specific_event_joiners() -> None:
    events = InMemoryEventsRepository(build_event())
    joiners = InMemoryJoinersRepository()
    alice = joiners.create(
        Joiner(user_id=2, user_name="alice", event_id=1)
    )
    bob = joiners.create(
        Joiner(user_id=3, user_name="bob", event_id=1)
    )
    joiners.create(
        Joiner(user_id=4, user_name="other-event", event_id=2)
    )

    result = get_all_guests(
        event_id=1,
        events=events,
        joiners=joiners,
    )

    assert result == [alice, bob]
