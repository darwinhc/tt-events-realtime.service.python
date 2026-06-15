"""Outbound port for realtime event notifications."""

from typing import Protocol, runtime_checkable

from src.domain.entities.realtime_event import RealtimeEvent


@runtime_checkable
class RealtimeEventPublisher(Protocol):
    """Publish notifications without coupling use cases to transport."""

    def publish(self, event: RealtimeEvent) -> None:
        """Publish a domain change notification."""


class NullRealtimeEventPublisher(RealtimeEventPublisher):
    """No-op publisher used when realtime delivery is not configured."""

    def publish(self, event: RealtimeEvent) -> None:
        """Discard a realtime notification."""
        return None
