"""Event-list query DTO."""

from pydantic import BaseModel, ConfigDict, Field

from .event_filters import EventFilters


class EventQuery(BaseModel):
    """Filtering and pagination requested for an event list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filters: EventFilters = Field(default_factory=EventFilters)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
