"""Conversation memory manager — builds Anthropic-format history from stored messages."""
from __future__ import annotations

from typing import Dict, List

from app.config import get_settings
from app.db.session_store import get_session_store


async def build_history_messages(session_id: str) -> List[Dict[str, str]]:
    """Load the last N stored messages (user/assistant only) for Claude.

    We deliberately exclude system messages — the system prompt is passed via the
    `system` parameter of Anthropic's `messages.create`.
    """
    s = get_settings()
    store = get_session_store()
    rows = await store.get_history(session_id, limit=s.max_history_messages)
    history: List[Dict[str, str]] = []
    for r in rows:
        if r.role not in ("user", "assistant"):
            continue
        history.append({"role": r.role, "content": r.content})
    # Anthropic requires the first message to be from `user`; drop leading assistant turns.
    while history and history[0]["role"] != "user":
        history.pop(0)
    # Collapse consecutive same-role messages by concatenation (defensive)
    collapsed: List[Dict[str, str]] = []
    for m in history:
        if collapsed and collapsed[-1]["role"] == m["role"]:
            collapsed[-1]["content"] += "\n\n" + m["content"]
        else:
            collapsed.append(m)
    return collapsed
