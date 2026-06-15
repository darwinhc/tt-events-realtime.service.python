"""Request-scoped logging context."""

from contextvars import ContextVar, Token
from typing import Optional

_transaction_id: ContextVar[Optional[str]] = ContextVar(
    "transaction_id",
    default=None,
)


def get_transaction_id() -> Optional[str]:
    """Return the transaction identifier for the current execution context."""
    return _transaction_id.get()


def set_transaction_id(transaction_id: str) -> Token:
    """Set the transaction identifier and return its reset token."""
    return _transaction_id.set(transaction_id)


def reset_transaction_id(token: Token) -> None:
    """Restore the transaction context that preceded the supplied token."""
    _transaction_id.reset(token)
