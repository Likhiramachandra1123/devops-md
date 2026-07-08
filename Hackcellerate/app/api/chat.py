"""Chat endpoints — conversational RAG with Claude, plus structured search and doc-based Q&A."""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from app.config import get_settings
from app.core.claude_client import get_claude_client
from app.core.embeddings import get_embedding_model
from app.core.memory import build_history_messages
from app.core.prompts import SYSTEM_PROMPT, build_context_block, build_user_turn
from app.core.retriever import RetrievedChunk, retrieve
from app.db.session_store import get_session_store
from app.ingestion.chunker import chunk_text
from app.ingestion.loaders import load_docx, load_pdf, load_txt
from app.models import (
    ChatRequest,
    ChatResponse,
    Citation,
    SearchResponse,
    SearchResult,
)

router = APIRouter(prefix="/chat", tags=["chat"])

_DOC_SYSTEM_PROMPT = (
    "You are a regulatory research assistant. Answer the user's question using ONLY the "
    "document content provided below. The content may be either the full document or a "
    "set of excerpts selected by relevance to the question. If the answer is not present, "
    "say so plainly and do not fall back to general knowledge. When only excerpts are "
    "provided and the answer might lie in unshown portions of the document, say so "
    "explicitly rather than guessing. Cite short excerpts in quotes when useful."
)


# ---------------- helpers ----------------

_UNKNOWN_TITLE_PAT = re.compile(r"(?i)unknown\s*\(\s*\)|^\s*untitled\s*$|^\s*unknown\s*$")


def _display_title(meta: dict, chunk_id: str = "") -> str:
    """Return a human-readable title, replacing 'Unknown ()' / 'Untitled' with something useful."""
    raw = str(meta.get("title") or "").strip()
    if raw and not _UNKNOWN_TITLE_PAT.search(raw):
        return raw

    source = str(meta.get("source") or "").strip() or "Document"
    doc_type = str(meta.get("doc_type") or "").strip()
    doc_id = str(meta.get("doc_id") or "").strip()
    url = str(meta.get("url") or "").strip()
    tags = meta.get("tags") or []
    if isinstance(tags, list) and tags:
        tag_hint = str(tags[0]).strip()
    else:
        tag_hint = ""

    label_bits: List[str] = []
    if source:
        label_bits.append(source)
    if doc_type:
        pretty = doc_type.replace("_", " ").title()
        label_bits.append(pretty)
    prefix = " · ".join(label_bits) if label_bits else "Document"

    if tag_hint:
        return f"{prefix} · {tag_hint}"

    # openFDA URLs embed the id — surface a short suffix
    if url and "id:" in url:
        try:
            uid = url.split("id:", 1)[1].split("&", 1)[0][:12]
            if uid:
                return f"{prefix} · {uid}"
        except Exception:  # noqa: BLE001
            pass

    if doc_id:
        return f"{prefix} · {doc_id[:12]}"
    if chunk_id:
        return f"{prefix} · {chunk_id[:12]}"
    return prefix


def _to_citations(chunks: List[RetrievedChunk]) -> List[Citation]:
    out: List[Citation] = []
    for i, c in enumerate(chunks, start=1):
        meta = c.metadata or {}
        snippet = c.text.strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:240] + "…"
        out.append(
            Citation(
                index=i,
                title=_display_title(meta, c.chunk_id),
                source=str(meta.get("source", "unknown")),
                url=meta.get("url"),
                doc_id=meta.get("doc_id"),
                chunk_id=c.chunk_id,
                distance=c.distance,
                snippet=snippet,
            )
        )
    return out


def _to_search_results(chunks: List[RetrievedChunk]) -> List[SearchResult]:
    out: List[SearchResult] = []
    for i, c in enumerate(chunks, start=1):
        meta = c.metadata or {}
        snippet = c.text.strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:500] + "…"
        score = max(0.0, min(1.0, 1.0 - float(c.distance)))
        out.append(
            SearchResult(
                index=i,
                title=_display_title(meta, c.chunk_id),
                source=str(meta.get("source", "unknown")),
                url=meta.get("url"),
                doc_id=meta.get("doc_id"),
                chunk_id=c.chunk_id,
                distance=c.distance,
                score=score,
                snippet=snippet,
                metadata=meta,
            )
        )
    return out


def _extract_summary(answer: str) -> str:
    text = answer.strip()
    m = re.search(r"(?is)^\s*(?:\*{0,2}summary\*{0,2}\s*[:\-]\s*)(.+?)(?:\n\s*\n|\Z)", text)
    if m:
        return m.group(1).strip()
    para = text.split("\n\n", 1)[0]
    lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
    return " ".join(lines[:4])[:600]


def _extract_upload_text(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            return load_pdf(raw)
        if name.endswith(".docx"):
            return load_docx(raw)
        return load_txt(raw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not read {filename or 'file'}: {e}") from e


def _select_relevant_excerpts(
    doc_text: str,
    question: str,
    *,
    max_chars: int,
    chunk_size: int,
    overlap: int,
) -> tuple[str, dict]:
    """For docs that exceed max_chars, chunk + embed and pull the top-K excerpts
    most relevant to the question. Fits within a char budget of ~max_chars.

    Returns (assembled_text, info_dict).
    """
    import numpy as np  # local import to keep module load cheap

    chunks = chunk_text(doc_text, chunk_size=chunk_size, overlap=overlap)
    total_chunks = len(chunks)
    if not chunks:
        return "", {"strategy": "empty", "total_chunks": 0, "chunks_used": 0}

    embedder = get_embedding_model()
    chunk_vecs = np.asarray(embedder.embed([c.text for c in chunks]), dtype=np.float32)
    q_vec = np.asarray(embedder.embed_one(question), dtype=np.float32)

    # Vectors are already L2-normalized by SentenceTransformer(normalize_embeddings=True),
    # so cosine similarity == dot product.
    sims = (chunk_vecs @ q_vec).tolist()
    ranked = sorted(range(len(chunks)), key=lambda i: sims[i], reverse=True)

    # Greedily pack top chunks in original document order (best first) until we
    # approach the char budget. Leave 10% headroom for framing + question.
    budget = int(max_chars * 0.9)
    picked_indices: list[int] = []
    used = 0
    for idx in ranked:
        piece_len = len(chunks[idx].text) + 4  # small separator overhead
        if used + piece_len > budget:
            continue
        picked_indices.append(idx)
        used += piece_len
        if used >= budget * 0.98:
            break

    # Sort picked chunks by original position so the doc reads roughly in order
    picked_indices.sort(key=lambda i: chunks[i].index)

    parts: list[str] = []
    for rank, idx in enumerate(picked_indices, start=1):
        parts.append(
            f"[Excerpt {rank} — doc position {chunks[idx].index + 1}/{total_chunks}, "
            f"relevance {sims[idx]:.2f}]\n{chunks[idx].text.strip()}"
        )

    assembled = "\n\n---\n\n".join(parts)
    info = {
        "strategy": "chunk_and_retrieve",
        "total_chunks": total_chunks,
        "chunks_used": len(picked_indices),
        "chars_selected": len(assembled),
        "top_relevance": max(sims) if sims else 0.0,
    }
    return assembled, info


# ---------------- standard chat ----------------

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(400, "message must not be empty")

    s = get_settings()
    store = get_session_store()
    session_id = await store.ensure_session(req.session_id)

    chunks: List[RetrievedChunk] = []
    grounded = False
    if req.use_rag:
        chunks = retrieve(
            req.message,
            top_k=req.top_k or s.rag_top_k,
            final_k=s.rag_final_k,
            where=req.filters,
        )
        grounded = len(chunks) > 0

    # Strict RAG: if we searched the KB and found nothing relevant, abstain
    # instead of letting Claude answer from general knowledge.
    if req.use_rag and not grounded and s.rag_strict:
        answer = (
            "I couldn't find any relevant information in the internal knowledge base "
            f"for your question. (Retrieval threshold: distance ≤ {s.rag_distance_threshold:.2f}; "
            "try rephrasing, broadening the query, or ingesting more documents.)"
        )
        await store.add_message(session_id, "user", req.message)
        await store.add_message(session_id, "assistant", answer)
        return ChatResponse(
            session_id=session_id,
            answer=answer,
            summary=answer,
            citations=[],
            used_rag=True,
            grounded=False,
            source_type="none",
            source_info={"reason": "no_relevant_chunks", "threshold": s.rag_distance_threshold},
            model="none (abstained)",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    context_block = build_context_block(chunks)
    user_turn = build_user_turn(req.message, context_block)

    history = await build_history_messages(session_id)
    history.append({"role": "user", "content": user_turn})

    # No-Claude fallback
    if not s.anthropic_api_key:
        if chunks:
            preview_lines = [
                f"[{i}] (distance={c.distance:.3f}) {c.metadata.get('title', 'Untitled')}\n"
                f"    Source: {c.metadata.get('source', 'unknown')}  URL: {c.metadata.get('url', '')}\n\n"
                f"{c.text.strip()}"
                for i, c in enumerate(chunks, start=1)
            ]
            answer = (
                "ANTHROPIC_API_KEY is not set — Claude is disabled. "
                f"Showing the top {len(chunks)} matching snippets from the local library:\n\n"
                + "\n\n---\n\n".join(preview_lines)
            )
            source_type = "knowledge_base"
        else:
            answer = (
                "ANTHROPIC_API_KEY is not set — Claude is disabled, "
                "and no matching snippets were found in the local library."
            )
            source_type = "none"
        await store.add_message(session_id, "user", req.message)
        await store.add_message(session_id, "assistant", answer)
        return ChatResponse(
            session_id=session_id,
            answer=answer,
            summary=answer.split("\n\n", 1)[0][:600],
            citations=_to_citations(chunks),
            used_rag=req.use_rag,
            grounded=grounded,
            source_type=source_type,
            source_info={"citation_count": len(chunks)} if chunks else {},
            model="none (no ANTHROPIC_API_KEY)",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    claude = get_claude_client()
    try:
        result = claude.complete(system=SYSTEM_PROMPT, messages=history, model=req.model)
    except Exception as e:  # noqa: BLE001
        logger.exception("Claude call failed")
        raise HTTPException(502, f"Claude API error: {e}") from e

    answer = result["text"].strip()

    fell_back = "not found in the internal knowledge base" in answer.lower()[:200]
    if grounded and fell_back:
        grounded = False
        citations: List[Citation] = []
        source_type = "general_knowledge"
        source_info = {}
    elif grounded:
        citations = _to_citations(chunks)
        source_type = "knowledge_base"
        source_info = {"citation_count": len(citations)}
    else:
        citations = []
        source_type = "general_knowledge" if req.use_rag else "none"
        source_info = {}

    await store.add_message(session_id, "user", req.message)
    await store.add_message(session_id, "assistant", answer)

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        summary=_extract_summary(answer),
        citations=citations,
        used_rag=req.use_rag,
        grounded=grounded,
        source_type=source_type,
        source_info=source_info,
        model=result["model"],
        usage=result["usage"],
    )


# ---------------- doc-based Q&A (skips RAG) ----------------

@router.post("/upload", response_model=ChatResponse)
async def chat_with_upload(
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),
) -> ChatResponse:
    if not message.strip():
        raise HTTPException(400, "message must not be empty")

    raw = await file.read()
    s = get_settings()
    if len(raw) > s.upload_max_bytes:
        raise HTTPException(
            413,
            f"file too large (>{s.upload_max_bytes // (1024*1024)} MB)",
        )

    doc_text = _extract_upload_text(file.filename or "", raw)
    if not doc_text.strip():
        raise HTTPException(400, "Could not extract any text from the file.")

    max_chars = s.upload_max_doc_chars
    # If the doc is small enough to fit in a single chunk there's no benefit
    # to running retrieval — just send it verbatim.
    small_doc_threshold = s.chunk_size * 2
    was_truncated = False
    selection_info: dict = {}

    if len(doc_text) <= small_doc_threshold:
        doc_payload = doc_text
        header_note = f"filename={file.filename}, chars={len(doc_text):,}"
        used_retrieval = False
    else:
        # Chunk + embed + retrieve the most relevant excerpts for this question,
        # capped at the char budget so we never send more than needed.
        budget = min(max_chars, len(doc_text))
        doc_payload, selection_info = _select_relevant_excerpts(
            doc_text,
            message,
            max_chars=budget,
            chunk_size=s.chunk_size,
            overlap=s.chunk_overlap,
        )
        used_retrieval = True
        was_truncated = selection_info.get("chars_selected", 0) < len(doc_text)
        header_note = (
            f"filename={file.filename}, total_chars={len(doc_text):,}, "
            f"selected_excerpts={selection_info.get('chunks_used', 0)}/"
            f"{selection_info.get('total_chunks', 0)}, "
            f"selected_chars={selection_info.get('chars_selected', 0):,}"
        )

    store = get_session_store()
    sid = await store.ensure_session(session_id)

    if used_retrieval:
        framing = (
            f"DOCUMENT ({header_note}) — showing the most relevant excerpts "
            f"(by semantic similarity to the question) in original document order:\n"
            f"---\n{doc_payload}\n---\n\n"
            f"QUESTION: {message}"
        )
    else:
        framing = (
            f"DOCUMENT ({header_note}):\n"
            f"---\n{doc_payload}\n---\n\n"
            f"QUESTION: {message}"
        )

    user_turn = framing
    history = await build_history_messages(sid)
    history.append({"role": "user", "content": user_turn})

    if not s.anthropic_api_key:
        preview_chars = 4000
        preview = doc_text[:preview_chars]
        preview_truncated = len(doc_text) > preview_chars
        answer = (
            "ANTHROPIC_API_KEY is not set — Claude is disabled. "
            f"Returning the raw extracted text of `{file.filename}` "
            f"({len(doc_text):,} chars total) so you can test the upload path.\n\n"
            f"QUESTION: {message}\n\n"
            f"----- DOCUMENT TEXT (first {min(preview_chars, len(doc_text)):,} chars) -----\n"
            f"{preview}"
            + ("\n\n… [truncated]" if preview_truncated else "")
        )
        await store.add_message(sid, "user", f"[uploaded: {file.filename}] {message}")
        await store.add_message(sid, "assistant", answer)
        return ChatResponse(
            session_id=sid,
            answer=answer,
            summary=f"Raw text preview of {file.filename} ({len(doc_text):,} chars).",
            citations=[],
            used_rag=False,
            grounded=True,
            source_type="uploaded_document",
            source_info={
                "filename": file.filename,
                "chars": len(doc_text),
                "truncated": was_truncated,
                "preview_chars": min(preview_chars, len(doc_text)),
                "no_api_key": True,
            },
            model="none (no ANTHROPIC_API_KEY)",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    claude = get_claude_client()
    try:
        result = claude.complete(system=_DOC_SYSTEM_PROMPT, messages=history, model=model)
    except Exception as e:  # noqa: BLE001
        logger.exception("Claude call failed (upload)")
        raise HTTPException(502, f"Claude API error: {e}") from e

    answer = result["text"].strip()

    await store.add_message(sid, "user", f"[uploaded: {file.filename}] {message}")
    await store.add_message(sid, "assistant", answer)

    return ChatResponse(
        session_id=sid,
        answer=answer,
        summary=_extract_summary(answer),
        citations=[],
        used_rag=False,
        grounded=True,
        source_type="uploaded_document",
        source_info={
            "filename": file.filename,
            "chars": len(doc_text),
            "truncated": was_truncated,
            **({"selection": selection_info} if selection_info else {}),
        },
        model=result["model"],
        usage=result["usage"],
    )


# ---------------- structured search (table view) ----------------

SEARCH_HARD_CAP = 1000  # absolute upper bound to keep response sizes sane


@router.post("/search", response_model=SearchResponse)
async def chat_search(req: ChatRequest) -> SearchResponse:
    if not req.message.strip():
        raise HTTPException(400, "message must not be empty")

    s = get_settings()
    store = get_session_store()
    sid = await store.ensure_session(req.session_id)

    # Ask for as many as the caller wants, capped at the vector store size and a hard cap.
    from app.core.vector_store import get_vector_store  # local import to avoid cycles at boot

    try:
        available = get_vector_store().count()
    except Exception:  # noqa: BLE001
        available = SEARCH_HARD_CAP

    requested = req.top_k or SEARCH_HARD_CAP
    top_k = max(1, min(requested, available or SEARCH_HARD_CAP, SEARCH_HARD_CAP))

    chunks = retrieve(
        req.message,
        top_k=top_k,
        final_k=top_k,           # keep all above threshold for the table
        where=req.filters,
    )

    return SearchResponse(
        session_id=sid,
        query=req.message,
        results=_to_search_results(chunks),
        total=len(chunks),
        summary=None,
    )
