"""Event joiner entity."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Joiner(BaseModel):
    """A user participating in an event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Optional[int] = Field(default=None, gt=0)
    user_id: int = Field(gt=0)
    user_name: str
    event_id: int = Field(gt=0)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    left_at: Optional[datetime] = None

    @field_validator("user_name")
    @classmethod
    def validate_user_name(cls, value: str) -> str:
        """Normalize and validate the participant's display name."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_name cannot be empty.")
        if len(normalized) > 64:
            raise ValueError("user_name cannot exceed 64 characters.")
        return normalized

    @field_validator("left_at", "joined_at")
    @classmethod
    def normalize_left_at(
        cls,
        value: Optional[datetime],
    ) -> Optional[datetime]:
        """Require timezone information and normalize leave time to UTC."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Joiner leave or joined datetime must include a timezone.")
        return value.astimezone(timezone.utc)
