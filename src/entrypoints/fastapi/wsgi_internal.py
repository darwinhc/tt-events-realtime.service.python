"""Administrative ASGI entry point."""

from src.entrypoints.fastapi.internal import create_fastapi_app

app = create_fastapi_app()
