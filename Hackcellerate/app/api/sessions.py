"""Session management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.session_store import get_session_store
from app.models import Message, SessionInfo, SessionListResponse, SessionMessagesResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionInfo)
async def create_session():
    store = get_session_store()
    sid = await store.create_session()
    sessions = await store.list_sessions(limit=1)
    row = next((s for s in sessions if s["session_id"] == sid), None)
    if not row:
        raise HTTPException(500, "session creation failed")
    return SessionInfo(**row)


@router.get("", response_model=SessionListResponse)
async def list_sessions(limit: int = 100):
    store = get_session_store()
    rows = await store.list_sessions(limit=limit)
    return SessionListResponse(sessions=[SessionInfo(**r) for r in rows])


@router.get("/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_messages(session_id: str, limit: int = 200):
    store = get_session_store()
    rows = await store.get_history(session_id, limit=limit)
    if not rows:
        # empty history is not an error, but confirm session exists via list
        sessions = await store.list_sessions(limit=500)
        if not any(s["session_id"] == session_id for s in sessions):
            raise HTTPException(404, "session not found")
    return SessionMessagesResponse(
        session_id=session_id,
        messages=[Message(role=r.role, content=r.content, created_at=r.created_at) for r in rows],
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    store = get_session_store()
    ok = await store.delete_session(session_id)
    if not ok:
        raise HTTPException(404, "session not found")
    return {"deleted": session_id}
