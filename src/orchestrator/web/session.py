"""In-memory session store for web pipeline runs."""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..core.context import WorkflowContext


@dataclass
class Session:
    """Represents a single pipeline run accessible from the web UI."""

    session_id: str
    prompt: str = ""
    mode: str = "GENERATE"
    project_name: str = ""
    project_type: str = "library"
    is_project_mode: bool = False
    status: str = "pending"  # pending | running | checkpoint | complete | error
    context: Optional[WorkflowContext] = None

    # Checkpoint synchronization
    checkpoint_event: asyncio.Event = field(default_factory=asyncio.Event)
    checkpoint_response: Dict[str, Any] = field(default_factory=dict)
    checkpoint_type: str = ""  # CODE_REVIEW | TEST_REVIEW | FINAL_REVIEW

    # Collected messages for the chat history
    messages: list = field(default_factory=list)


class SessionStore:
    """Thread-safe in-memory store for active sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create(self, prompt: str, mode: str = "GENERATE", **kwargs) -> Session:
        session_id = uuid.uuid4().hex[:12]
        session = Session(session_id=session_id, prompt=prompt, mode=mode, **kwargs)
        async with self._lock:
            self._sessions[session_id] = session
        return session

    async def get(self, session_id: str) -> Optional[Session]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def remove(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def list_all(self) -> list:
        async with self._lock:
            return [
                {"session_id": s.session_id, "prompt": s.prompt, "status": s.status}
                for s in self._sessions.values()
            ]


# Singleton
store = SessionStore()
