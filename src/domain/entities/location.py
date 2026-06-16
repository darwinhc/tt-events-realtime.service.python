"""Location entity and geographic value object."""

import unicodedata
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GeoPoint(BaseModel):
    """A WGS84 point represented in latitude/longitude order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    def as_geojson(self) -> dict:
        """Return a MongoDB-compatible GeoJSON point."""
        return {
            "type": "Point",
            "coordinates": [self.longitude, self.latitude],
        }


class Location(BaseModel):
    """A venue described by a name, address, coordinates, or a combination."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    coordinates: Optional[GeoPoint] = None
    id: Optional[int] = Field(default=None, gt=0)
    created_at: Optional[datetime] = None

    @field_validator(
        "name",
        "address",
        "country",
        "city",
        "postal_code",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value):
        """Trim optional text and convert blank values to null."""
        if value is None:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: Optional[str]) -> Optional[str]:
        """Normalize and validate an ISO 3166-1 alpha-2 country code."""
        if value is None:
            return None
        normalized_value = value.upper()
        if len(normalized_value) != 2 or not normalized_value.isascii():
            raise ValueError("Location country must be a 2-character ISO code.")
        if not normalized_value.isalpha():
            raise ValueError("Location country must be a 2-character ISO code.")
        return normalized_value

    @field_validator("city")
    @classmethod
    def normalize_city(cls, value: Optional[str]) -> Optional[str]:
        """Store cities lowercase and without diacritics for matching."""
        if value is None:
            return None
        decomposed = unicodedata.normalize("NFKD", value)
        normalized_value = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        return normalized_value.lower()

    @field_validator("name")
    @classmethod
    def validate_name_length(cls, value: Optional[str]) -> Optional[str]:
        """Enforce the persisted location-name length."""
        if value is not None and len(value) > 200:
            raise ValueError("Location name cannot exceed 200 characters.")
        return value

    @field_validator("address")
    @classmethod
    def validate_address_length(cls, value: Optional[str]) -> Optional[str]:
        """Enforce the persisted address length."""
        if value is not None and len(value) > 500:
            raise ValueError("Location address cannot exceed 500 characters.")
        return value

    @field_validator("city")
    @classmethod
    def validate_city_length(cls, value: Optional[str]) -> Optional[str]:
        """Enforce the persisted city length."""
        if value is not None and len(value) > 200:
            raise ValueError("Location city cannot exceed 200 characters.")
        return value

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code_length(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """Enforce the persisted postal-code length."""
        if value is not None and len(value) > 32:
            raise ValueError(
                "Location postal code cannot exceed 32 characters."
            )
        return value

    @model_validator(mode="after")
    def validate_description(self) -> "Location":
        """Require at least one useful location representation."""
        if self.name is None and self.address is None and self.coordinates is None:
            raise ValueError(
                "A location requires a name, an address, coordinates, or a combination."
            )
        return self
