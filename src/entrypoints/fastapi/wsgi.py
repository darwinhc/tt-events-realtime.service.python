"""ASGI entry point."""

from src.entrypoints.fastapi.users import create_fastapi_app

app = create_fastapi_app()
