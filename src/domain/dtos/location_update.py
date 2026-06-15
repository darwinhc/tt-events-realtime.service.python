"""Editable location fields."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from ..entities import GeoPoint, Location


class LocationUpdate(BaseModel):
    """A partial location update."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    coordinates: Optional[GeoPoint] = None

    @model_validator(mode="after")
    def validate_changes(self) -> "LocationUpdate":
        """Require at least one mutable field."""
        if not self.model_fields_set:
            raise ValueError("At least one location field must be updated.")
        return self

    def apply_to(self, location: Location) -> Location:
        """Return a validated location containing the requested changes."""
        return Location.model_validate(
            {
                **location.model_dump(),
                **self.model_dump(exclude_unset=True, exclude_none=False),
            }
        )
