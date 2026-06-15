"""In-memory FastAPI WebSocket publisher unit tests."""

import asyncio

from src.domain.entities import RealtimeEvent
from src.infra.events.fastapi_websocket import FastAPIWebSocketPublisher


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message) -> None:
        self.messages.append(message)


def test_queue_backpressure_keeps_the_latest_notification() -> None:
    queue = asyncio.Queue(maxsize=1)
    first = RealtimeEvent(type="first", event_id=1, payload={})
    latest = RealtimeEvent(type="latest", event_id=1, payload={})

    FastAPIWebSocketPublisher._enqueue(queue, first)
    FastAPIWebSocketPublisher._enqueue(queue, latest)

    assert queue.get_nowait() == latest


def test_connect_publish_and_disconnect_lifecycle() -> None:
    async def scenario() -> None:
        publisher = FastAPIWebSocketPublisher()
        websocket = FakeWebSocket()
        await publisher.connect(websocket)

        publisher.publish(
            RealtimeEvent(type="delivered", event_id=8, payload={})
        )
        for _ in range(3):
            await asyncio.sleep(0)
            if websocket.messages:
                break

        assert websocket.accepted is True
        assert publisher.connection_count == 1
        assert [message["type"] for message in websocket.messages] == [
            "delivered"
        ]

        await publisher.disconnect(websocket)
        await publisher.disconnect(websocket)
        assert publisher.connection_count == 0

    asyncio.run(scenario())
