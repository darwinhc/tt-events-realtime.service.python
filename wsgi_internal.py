"""Administrative ASGI entry point."""

from src.entrypoints.internal.fastapi_app import create_fastapi_app

app = create_fastapi_app()
