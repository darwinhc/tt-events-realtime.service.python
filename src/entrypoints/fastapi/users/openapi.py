"""OpenAPI metadata for the FastAPI inbound adapter."""

OPENAPI_TAGS = [
    {
        "name": "Events",
        "description": "Create, read, update, cancel, and restore events.",
    },
    {
        "name": "Locations",
        "description": "List and update flexible event locations.",
    },
    {
        "name": "Joiners",
        "description": "Join events, leave events, and list event guests.",
    },
]

COMMON_ERROR_RESPONSES = {
    422: {"description": "The request violates validation rules."},
}

AUTH_ERROR_RESPONSES = {
    401: {"description": "Authorization bearer token is missing or invalid."},
    403: {"description": "The authenticated user is not allowed to perform this action."},
}

NOT_FOUND_RESPONSE = {
    404: {"description": "The requested entity was not found."},
}

CONFLICT_RESPONSE = {
    409: {"description": "The request conflicts with an existing entity."},
}
