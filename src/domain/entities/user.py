"""Application user entity."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class User(BaseModel):
    """A user identified internally by an integer and visibly by a name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Optional[int] = Field(default=None, gt=0)
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        """Trim a visible user name before validation."""
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a non-empty user name within the storage limit."""
        if not value:
            raise ValueError("User name cannot be empty.")
        if len(value) > 64:
            raise ValueError("User name cannot exceed 64 characters.")
        return value
