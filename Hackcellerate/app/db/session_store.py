"""Async SQLite-backed conversation session store."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from loguru import logger
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[List["MessageRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="MessageRow.id"
    )


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[SessionRow] = relationship(back_populates="messages")


class SessionStore:
    def __init__(self, db_url: str) -> None:
        self.engine = create_async_engine(db_url, future=True)
        self.SessionLocal = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Session store initialized.")

    async def create_session(self, title: Optional[str] = None) -> str:
        sid = str(uuid.uuid4())
        async with self.SessionLocal() as s:
            s.add(SessionRow(id=sid, title=title))
            await s.commit()
        return sid

    async def ensure_session(self, session_id: Optional[str]) -> str:
        if session_id:
            async with self.SessionLocal() as s:
                row = await s.get(SessionRow, session_id)
                if row:
                    return session_id
        return await self.create_session()

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        async with self.SessionLocal() as s:
            s.add(MessageRow(session_id=session_id, role=role, content=content))
            # Bump updated_at
            row = await s.get(SessionRow, session_id)
            if row:
                row.updated_at = datetime.utcnow()
                if not row.title and role == "user":
                    row.title = content[:80]
            await s.commit()

    async def get_history(self, session_id: str, limit: int) -> List[MessageRow]:
        """Return the most recent `limit` messages in chronological order."""
        async with self.SessionLocal() as s:
            stmt = (
                select(MessageRow)
                .where(MessageRow.session_id == session_id)
                .order_by(MessageRow.id.desc())
                .limit(limit)
            )
            rows = list((await s.execute(stmt)).scalars().all())
            rows.reverse()
            return rows

    async def list_sessions(self, limit: int = 100) -> list[dict]:
        async with self.SessionLocal() as s:
            stmt = (
                select(
                    SessionRow.id,
                    SessionRow.title,
                    SessionRow.created_at,
                    SessionRow.updated_at,
                    func.count(MessageRow.id).label("msg_count"),
                )
                .join(MessageRow, MessageRow.session_id == SessionRow.id, isouter=True)
                .group_by(SessionRow.id)
                .order_by(SessionRow.updated_at.desc())
                .limit(limit)
            )
            rows = (await s.execute(stmt)).all()
            return [
                {
                    "session_id": r.id,
                    "title": r.title,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "message_count": int(r.msg_count or 0),
                }
                for r in rows
            ]

    async def delete_session(self, session_id: str) -> bool:
        async with self.SessionLocal() as s:
            row = await s.get(SessionRow, session_id)
            if not row:
                return False
            await s.execute(delete(SessionRow).where(SessionRow.id == session_id))
            await s.commit()
            return True


_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        s = get_settings()
        _store = SessionStore(s.session_db_url)
    return _store
