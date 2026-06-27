"""FastAPI application — REST + WebSocket endpoints for the web UI."""

import asyncio
import os
from typing import Optional

# pyrefly: ignore [missing-import]
import uvicorn
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
import warnings

# Suppress Paramiko CryptographyDeprecationWarning which pollutes the logs
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="paramiko",
    message=".*CryptographyDeprecationWarning.*"
)
try:
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass

from ..logging_config import logger
from .session import Session, store
from .web_workflow import WebWorkflowOrchestrator
from .ws_manager import manager as ws_manager

app = FastAPI(
    title="AI Development Orchestrator — Web API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    prompt: str
    mode: str = "GENERATE"
    project_name: str = ""
    project_type: str = "library"
    is_project_mode: bool = False
    test_execution_mode: str = "docker"


class CheckpointActionRequest(BaseModel):
    action: str  # approve | reject | skip | edit
    feedback: str = ""


# ──────────────────────────────────────────────────────────────────────
# REST endpoints
# ──────────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint — silences browser 404s when users hit the API host directly."""
    return {
        "name": "AI Development Orchestrator — Web API",
        "version": "0.2.0",
        "frontend": "http://localhost:5173",
        "endpoints": {
            "health": "/api/health",
            "docs": "/docs",
            "sessions": "/api/sessions",
            "websocket": "/ws/{session_id}",
            "docker_status": "/api/docker/status",
        },
        "status": "running",
    }


@app.get("/favicon.ico")
async def favicon():
    """Silence browser favicon 404 noise."""
    from fastapi.responses import Response
    return Response(status_code=204)


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Create a new pipeline session and start the orchestrator in the background."""
    session = await store.create(
        prompt=req.prompt,
        mode=req.mode,
        project_name=req.project_name,
        project_type=req.project_type,
        is_project_mode=req.is_project_mode,
        test_execution_mode=req.test_execution_mode,
    )

    # Launch pipeline as a background task
    asyncio.create_task(_run_pipeline(session))

    return {
        "session_id": session.session_id,
        "status": session.status,
    }


@app.get("/api/sessions")
async def list_sessions():
    return await store.list_all()


@app.get("/api/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    session = await store.get(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    ctx = session.context
    return {
        "session_id": session.session_id,
        "status": session.status,
        "checkpoint_type": session.checkpoint_type if session.status == "checkpoint" else None,
        "stage": ctx.stage if ctx else None,
        "retry_count": ctx.retry_count if ctx else 0,
    }


@app.get("/api/sessions/{session_id}/files")
async def list_session_files(session_id: str):
    session = await store.get(session_id)
    if not session or not session.context:
        return {"files": []}

    files = []
    for filename, code in session.context.source_code.items():
        files.append({
            "path": filename,
            "lines": len(code.splitlines()),
            "size": len(code),
        })
    return {"files": files}


@app.get("/api/sessions/{session_id}/files/{path:path}")
async def get_session_file(session_id: str, path: str):
    session = await store.get(session_id)
    if not session or not session.context:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    content = session.context.source_code.get(path)
    if content is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")

    return {"path": path, "content": content}

class SaveFileRequest(BaseModel):
    path: str
    content: str

@app.post("/api/sessions/{session_id}/files/save")
async def save_session_file(session_id: str, req: SaveFileRequest):
    session = await store.get(session_id)
    if not session or not session.context:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.context.source_code[req.path] = req.content
    
    from pathlib import Path
    abs_path = Path(session.context.workspace_path) / req.path
    # Write the file, ensuring parent dirs exist
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(req.content, encoding="utf-8")
    
    # Broadcast to websocket
    await ws_manager.emit(session_id, "file_updated", {
        "path": req.path,
        "content": req.content,
        "language": "python"
    })
    
    return {"status": "ok"}


@app.post("/api/sessions/{session_id}/action")
async def checkpoint_action(session_id: str, req: CheckpointActionRequest):
    """Respond to a pending checkpoint (approve / reject / skip)."""
    logger.info(
        "REST action received: session=%s action=%s status_before=%s",
        session_id, req.action, "unknown",
    )
    session = await store.get(session_id)
    if not session:
        logger.warning("Action for unknown session: %s", session_id)
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(
        "Session state: status=%s checkpoint_type=%s event_is_set=%s",
        session.status, session.checkpoint_type, session.checkpoint_event.is_set(),
    )

    if session.status != "checkpoint":
        # Checkpoint was likely already resolved
        logger.info("Action received but no pending checkpoint (status=%s) — already resolved", session.status)
        return {"status": "already_resolved", "action": req.action}

    # Guard: if the event was already set (by WS handler), don't double-set
    if session.checkpoint_event.is_set():
        logger.info("Checkpoint event already set for session %s — skipping REST duplicate", session_id)
        return {"status": "already_resolved", "action": req.action}

    session.checkpoint_response = {
        "action": req.action,
        "feedback": req.feedback,
    }
    session.checkpoint_event.set()
    logger.info("Checkpoint event SET for session=%s action=%s", session_id, req.action)

    return {"status": "ok", "action": req.action}


@app.get("/api/docker/status")
async def get_docker_status():
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return {"status": "available"}
    except Exception as e:
        logger.warning(f"Docker status check failed: {e}")
        return {"status": "unavailable", "reason": str(e)}


# ──────────────────────────────────────────────────────────────────────
# WebSocket endpoint
# ──────────────────────────────────────────────────────────────────────


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            # Keep connection alive; frontend sends pings/checkpoint responses
            data = await websocket.receive_text()
            # Handle inline checkpoint responses via WS (alternative to REST)
            try:
                import json
                msg = json.loads(data)
                if msg.get("type") == "checkpoint_response":
                    session = await store.get(session_id)
                    if session and session.status == "checkpoint":
                        session.checkpoint_response = {
                            "action": msg.get("action", "approve"),
                            "feedback": msg.get("feedback", ""),
                        }
                        session.checkpoint_event.set()
            except Exception:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(session_id, websocket)


# ──────────────────────────────────────────────────────────────────────
# Background pipeline runner
# ──────────────────────────────────────────────────────────────────────


async def _run_pipeline(session: Session) -> None:
    """Run the orchestrator pipeline as a background coroutine."""
    try:
        orchestrator = WebWorkflowOrchestrator()
        await orchestrator.run(session)
    except Exception as e:
        logger.exception("Pipeline crashed for session %s", session.session_id)
        session.status = "error"
        await ws_manager.emit(session.session_id, "pipeline_complete", {
            "status": "error",
            "message": str(e),
        })


# ──────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────


def start():
    """Entry point for `ai-orchestrator-web` CLI command."""
    port = int(os.getenv("WEB_PORT", "8000"))
    uvicorn.run(
        "orchestrator.web.app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_excludes=[
            "output/*",
            "workspace/*",
            "generated/*",
            "temp/*",
            "cache/*",
            "test_artifacts/*"
        ],
    )


if __name__ == "__main__":
    start()
