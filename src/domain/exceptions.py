"""Domain-specific errors."""


class DomainValidationError(ValueError):
    """Raised when input cannot represent a valid domain object."""


class EntityNotFoundError(LookupError):
    """Raised when a referenced domain entity does not exist."""


class EntityConflictError(RuntimeError):
    """Raised when an entity conflicts with existing state."""


class AuthorizationError(PermissionError):
    """Raised when an actor cannot perform a domain operation."""
