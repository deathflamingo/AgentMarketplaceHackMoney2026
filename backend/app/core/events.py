"""Event bus system for real-time SSE event streaming."""

import asyncio
from typing import Dict, Any, AsyncGenerator
from datetime import datetime


class EventBus:
    """
    In-memory event bus using asyncio.Queue for pub/sub pattern.

    Supports Server-Sent Events (SSE) streaming to multiple clients.
    """

    def __init__(self):
        """Initialize the event bus with an empty subscriber list."""
        self._subscribers: list[asyncio.Queue] = []

    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event_type: Type of event (e.g., "agent_registered", "job_created")
            data: Event payload data
        """
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Send to all active subscribers
        dead_queues = []
        for queue in self._subscribers:
            try:
                await queue.put(event)
            except Exception:
                # Mark queue as dead if it can't receive events
                dead_queues.append(queue)

        # Clean up dead queues
        for queue in dead_queues:
            self._subscribers.remove(queue)

    async def subscribe(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to events and receive them as an async generator.

        Yields:
            Event dictionaries containing type, data, and timestamp

        Usage:
            async for event in event_bus.subscribe():
                print(event)
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)

        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            # Client disconnected
            pass
        finally:
            # Clean up subscription
            if queue in self._subscribers:
                self._subscribers.remove(queue)


# Global event bus instance
event_bus = EventBus()
