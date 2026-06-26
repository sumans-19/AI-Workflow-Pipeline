"""WebSocket connection manager — broadcasts typed JSON events to clients."""

import asyncio
import json
from collections import defaultdict, deque
from typing import Any, Dict, Deque

from fastapi import WebSocket

from ..logging_config import logger


# Maximum number of messages to buffer per session when no client is connected
_MAX_BUFFER = 200


class ConnectionManager:
    """Manages WebSocket connections grouped by session ID.

    Key behaviour:
    - Only one active connection per session (latest wins).
    - When the frontend disconnects, events emitted by the pipeline are
      buffered (up to _MAX_BUFFER per session).
    - When the frontend reconnects, all buffered events are replayed
      in order so nothing is lost.
    """

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._buffers: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=_MAX_BUFFER))
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            # If an old connection exists, close it to prevent duplicates
            old_ws = self._connections.get(session_id)
            if old_ws:
                try:
                    await old_ws.close()
                except Exception:
                    pass
            self._connections[session_id] = ws

            # Replay any buffered messages
            buf = self._buffers.get(session_id)
            if buf:
                logger.info(
                    "Replaying %d buffered messages for session=%s",
                    len(buf), session_id,
                )
                while buf:
                    msg = buf.popleft()
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        # Put remaining messages back and bail
                        buf.appendleft(msg)
                        break

        logger.info("WebSocket connected: session=%s", session_id)

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            # Only remove if this is still the active connection
            if self._connections.get(session_id) is ws:
                self._connections.pop(session_id, None)
        logger.info("WebSocket disconnected: session=%s", session_id)

    async def emit(self, session_id: str, event_type: str, data: Any = None) -> None:
        """Broadcast a typed event to the connection for a session.

        If no connection is active, the message is buffered so it can be
        replayed when the client reconnects.
        """
        message = json.dumps({"type": event_type, "data": data or {}})
        async with self._lock:
            ws = self._connections.get(session_id)

        if ws:
            try:
                await ws.send_text(message)
                return
            except Exception:
                # Connection died — remove it and fall through to buffer
                async with self._lock:
                    if self._connections.get(session_id) is ws:
                        self._connections.pop(session_id, None)

        # No active connection — buffer the message
        async with self._lock:
            self._buffers[session_id].append(message)
            logger.debug(
                "Buffered event %s for session=%s (%d in buffer)",
                event_type, session_id, len(self._buffers[session_id]),
            )

    async def cleanup(self, session_id: str) -> None:
        """Remove all data for a finished session."""
        async with self._lock:
            self._connections.pop(session_id, None)
            self._buffers.pop(session_id, None)


# Singleton
manager = ConnectionManager()

