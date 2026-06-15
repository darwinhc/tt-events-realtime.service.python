"""Paginated event response DTO."""

from pydantic import BaseModel, ConfigDict, Field

from .event_details import EventDetails


class EventPage(BaseModel):
    """One page of enriched events and its pagination metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[EventDetails]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0)
