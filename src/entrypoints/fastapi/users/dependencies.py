"""FastAPI dependencies for the HTTP inbound adapter."""

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def user_name_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """Return the visible user encoded as the bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_name = credentials.credentials.strip()
    if not user_name or len(user_name) > 64:
        raise HTTPException(
            status_code=401,
            detail="Authorization bearer token is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_name
