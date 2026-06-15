"""ASGI entry point."""

from src.entrypoints.users.fastapi_app import create_fastapi_app

app = create_fastapi_app()
