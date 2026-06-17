"""Joiner info data transfer object."""
from pydantic import BaseModel


class JoinerInfo(BaseModel):
    """Joiner info."""
    event_id: int
    user_id: int
    user_name: str
