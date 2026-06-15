"""In-process WebSocket publisher for the FastAPI runtime."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from fastapi import WebSocket

from src.domain.entities import RealtimeEvent


@dataclass
class _Connection:
    websocket: WebSocket
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[RealtimeEvent]
    sender: asyncio.Task[None]


class FastAPIWebSocketPublisher:
    """Fan out notifications to WebSockets owned by this process."""

    def __init__(self, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._connections: dict[int, _Connection] = {}

    @property
    def connection_count(self) -> int:
        """Return the number of WebSockets registered in this process."""
        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
    ) -> None:
        """Accept and register a process-local WebSocket subscription."""
        await websocket.accept()
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(
            maxsize=self._queue_size
        )
        connection_key = id(websocket)
        sender = asyncio.create_task(self._send(websocket, queue))
        self._connections[connection_key] = _Connection(
            websocket=websocket,
            loop=asyncio.get_running_loop(),
            queue=queue,
            sender=sender,
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket subscription and stop its sender task."""
        connection = self._connections.pop(id(websocket), None)
        if connection is None:
            return
        connection.sender.cancel()
        with suppress(asyncio.CancelledError):
            await connection.sender

    def publish(self, event: RealtimeEvent) -> None:
        """Queue a notification for every process-local subscriber."""
        for connection in tuple(self._connections.values()):
            connection.loop.call_soon_threadsafe(
                self._enqueue,
                connection.queue,
                event,
            )

    @staticmethod
    def _enqueue(
        queue: asyncio.Queue[RealtimeEvent],
        event: RealtimeEvent,
    ) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)

    @staticmethod
    async def _send(
        websocket: WebSocket,
        queue: asyncio.Queue[RealtimeEvent],
    ) -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
