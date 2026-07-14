"""Chat endpoints — conversational RAG with Claude, plus structured search and doc-based Q&A."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from app.config import get_settings
from app.core.claude_client import get_claude_client
from app.core.embeddings import get_embedding_model
from app.core.memory import build_history_messages
from app.core.prompts import (
    FOLLOWUP_CONTEXT_BLOCK,
    FOLLOWUP_SYSTEM_PROMPT,
    GENERAL_KNOWLEDGE_BANNER,
    GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
    OUT_OF_SCOPE_REFUSAL,
    SYSTEM_PROMPT,
    build_context_block,
    build_user_turn,
)
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
        # Preserve paragraph breaks in the full text — the table's expanded
        # row renders it with `whitespace-pre-wrap`, so readable spacing helps.
        full_text = c.text.strip()
        # Short preview for the collapsed row (single line, no newlines).
        snippet = full_text.replace("\n", " ")
        if len(snippet) > 320:
            snippet = snippet[:320].rsplit(" ", 1)[0] + "…"
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
                text=full_text,
                metadata=meta,
            )
        )
    return out


def _extract_summary(answer: str) -> str:
    """Return a compact preview of the answer for the header banner / session list.

    Strategy:
    - Strip the trailing "Sources" block (never useful in a preview).
    - Support the legacy "**Summary:**" header if present.
    - Otherwise take the answer body up to a reasonable char cap so the banner
      shows enough context to be useful without overflowing the UI. We stop at
      a paragraph boundary when we can, and cleanly ellipsize otherwise.
    """
    MAX_CHARS = 1500  # keeps the banner readable but shows real substance

    text = answer.strip()

    # Strip trailing "Sources:" section.
    body = re.split(r"(?im)^\s*\**\s*sources?\s*:?\s*\**\s*$", text, maxsplit=1)[0].strip()
    if not body:
        return ""

    # Legacy: honour explicit "Summary:" header if the model still emits one.
    m = re.search(
        r"(?is)^\s*(?:\*{0,2}summary\*{0,2}\s*[:\-]\s*)(.+?)(?:\n\s*\n|\Z)",
        body,
    )
    if m:
        return _clean_and_cap(m.group(1), MAX_CHARS)

    return _clean_and_cap(body, MAX_CHARS)


def _clean_and_cap(text: str, max_chars: int) -> str:
    """Collapse markdown bullets / whitespace and trim to max_chars at a nice boundary."""
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            lines.append("")  # preserve paragraph breaks
            continue
        # Strip leading bullet / list markers so the preview reads as prose.
        ln = re.sub(r"^[-*•]\s+", "", ln)
        ln = re.sub(r"^\d+[.)]\s+", "", ln)
        lines.append(ln)

    # Collapse to a single string: newlines within a paragraph → space,
    # blank lines → paragraph separator " · ".
    paragraphs = []
    buf: list[str] = []
    for ln in lines:
        if ln:
            buf.append(ln)
        elif buf:
            paragraphs.append(" ".join(buf))
            buf = []
    if buf:
        paragraphs.append(" ".join(buf))

    joined = " · ".join(paragraphs).strip()
    if len(joined) <= max_chars:
        return joined

    # Trim on a word boundary and add an ellipsis.
    cut = joined[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:—-·")
    return cut + "…"


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

# Cheap heuristic: short messages or ones that lead with a pronoun / follow-up cue
# almost always depend on the previous turn for their meaning. We use this to
# decide whether to expand the retrieval query with recent conversation context.
_FOLLOWUP_CUE_PAT = re.compile(
    r"^\s*(and|also|but|so|then|what about|how about|why|why\?|how|how\?|"
    r"tell me more|more|elaborate|explain|expand|continue|go on|really|"
    r"which|who|whose|whom|when|where|it|its|that|those|these|they|them|"
    r"this|the same)\b",
    re.IGNORECASE,
)

# List-style intent: "give me X", "list Y", "show all Z", "which are the ...",
# or any question that mentions a plural domain noun (trials, drugs, devices,
# approvals, applications, recalls, patents, submissions, studies, records,
# manufacturers, sponsors, indications, ingredients, terms). For these queries
# the user wants BREADTH — many distinct documents — not depth on one.
_LIST_INTENT_PAT = re.compile(
    r"(\b(list|show|give|display|find|fetch|get|enumerate|name)\s+"
    r"(me\s+|us\s+)?(some|all|any|every|the|top|first|\d+)?\s*"
    r"\w*\s*(trial|drug|device|approval|application|recall|patent|submission|"
    r"study|record|manufacturer|sponsor|indication|ingredient|term|adverse|"
    r"event|product|company|classification|enforcement|label|de\s*novo|"
    r"510\s*\(?k\)?|nda|anda|orange\s*book|meddra)s?\b)"
    r"|(\bwhich\s+(are|is)\s+the\b)"
    r"|(\bhow\s+many\b)"
    r"|(\btrials?|drugs?|devices?|approvals?|applications?|recalls?|patents?|"
    r"submissions?|studies|manufacturers?|sponsors?|indications?|ingredients?|"
    r"products?)\s+(related to|for|about|involving|regarding|on)\b",
    re.IGNORECASE,
)


def _is_list_intent(message: str) -> bool:
    """Return True when the user is asking for a list / breadth of records."""
    return bool(_LIST_INTENT_PAT.search(message))


def _build_retrieval_query(current: str, history: List[dict]) -> str:
    """Combine the current user message with recent turns so that follow-up
    questions ("tell me more", "why?", "which one has approval?") retrieve the
    same topic as the earlier turn instead of embedding two-word noise.

    We prepend the last user message (always) and the last assistant message
    (only if the current message looks like a follow-up) to the retrieval
    query. The raw current message is still what gets sent to the LLM.
    """
    if not history:
        return current

    last_user = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"),
        "",
    )
    is_followup = bool(_FOLLOWUP_CUE_PAT.match(current)) or len(current.split()) <= 4

    parts: list[str] = []
    if last_user:
        parts.append(last_user)
    if is_followup:
        last_assistant = next(
            (m["content"] for m in reversed(history) if m["role"] == "assistant"),
            "",
        )
        if last_assistant:
            # Trim assistant answer to a lead sentence or two — full answers
            # are long and dilute the embedding.
            parts.append(last_assistant[:400])
    parts.append(current)
    return "\n".join(parts).strip()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(400, "message must not be empty")

    s = get_settings()
    store = get_session_store()
    session_id = await store.ensure_session(req.session_id)

    # Pull history up front — needed both for retrieval query expansion and
    # for the follow-up "let the model use prior context" fallback below.
    history = await build_history_messages(session_id)
    has_prior_turn = any(m["role"] == "assistant" for m in history)
    retrieval_query = _build_retrieval_query(req.message, history) if req.use_rag else req.message

    chunks: List[RetrievedChunk] = []
    grounded = False
    if req.use_rag:
        # For list-style questions ("give clinical trials related to cancer",
        # "list all recalls for Bayer") pull a lot more chunks and de-duplicate
        # by document so the user sees many distinct records instead of a few
        # near-identical chunks of the same doc.
        list_intent = _is_list_intent(req.message)
        if list_intent:
            eff_top_k = req.top_k or max(s.rag_top_k * 6, 30)
            eff_final_k = max(s.rag_final_k * 5, 15)
        else:
            eff_top_k = req.top_k or s.rag_top_k
            eff_final_k = s.rag_final_k
        chunks = retrieve(
            retrieval_query,
            top_k=eff_top_k,
            final_k=eff_final_k,
            where=req.filters,
            unique_docs=list_intent,
        )
        grounded = len(chunks) > 0
        # Extra safety net: reject "chunks passed the threshold but the top one is
        # not actually close" — happens when a small KB returns everything as
        # marginally-relevant to an out-of-scope question.
        if (
            grounded
            and s.rag_top_distance_floor > 0
            and chunks[0].distance > s.rag_top_distance_floor
        ):
            logger.info(
                f"Top chunk distance {chunks[0].distance:.3f} exceeds strict floor "
                f"{s.rag_top_distance_floor:.3f} — treating as ungrounded."
            )
            chunks = []
            grounded = False

    # Strict RAG: if we searched the KB and found nothing relevant, either
    # gracefully fall back to Claude's general knowledge (with a warning
    # banner + off-topic refusal built into the prompt) or, if the fallback
    # flag is off, abstain hard.
    # EXCEPTION: if this session already had a grounded turn, the user is
    # almost certainly digging into the previous answer ("why?", "elaborate",
    # "which one?"). Let it through so Claude can respond using the prior
    # Q&A that's still in its history.
    if req.use_rag and not grounded and s.rag_strict and not has_prior_turn:
        if s.rag_allow_general_fallback and s.anthropic_api_key:
            logger.info(
                "No relevant KB chunks; using GENERAL_KNOWLEDGE_SYSTEM_PROMPT fallback."
            )
            # Fresh single-turn call — do NOT pass conversation history here, so
            # Claude judges scope solely on the current question. If it decides
            # the question is out of domain, it will emit the canonical refusal
            # per rule 1 of the fallback prompt; otherwise it emits the banner
            # + a general-knowledge answer.
            claude = get_claude_client()
            try:
                gk_result = claude.complete(
                    system=GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": req.message}],
                    model=req.model,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("General-knowledge fallback failed")
                raise HTTPException(502, f"Claude API error: {e}") from e

            gk_answer = gk_result["text"].strip()
            refused = OUT_OF_SCOPE_REFUSAL.lower()[:60] in gk_answer.lower()
            # Belt-and-braces: if the model produced a non-refusal answer but
            # forgot the banner, prepend it so the UI can always distinguish
            # fallback answers from KB-grounded ones.
            if not refused and GENERAL_KNOWLEDGE_BANNER not in gk_answer:
                gk_answer = f"{GENERAL_KNOWLEDGE_BANNER}\n\n{gk_answer}"

            await store.add_message(session_id, "user", req.message)
            await store.add_message(session_id, "assistant", gk_answer)
            return ChatResponse(
                session_id=session_id,
                answer=gk_answer,
                summary=_extract_summary(gk_answer),
                citations=[],
                used_rag=True,
                grounded=False,
                source_type="none" if refused else "general_knowledge",
                source_info={
                    "reason": "off_topic_refusal" if refused
                    else "general_knowledge_fallback",
                    "threshold": s.rag_distance_threshold,
                },
                model=gk_result["model"],
                usage=gk_result["usage"],
            )

        # Fallback disabled (or no API key): the original hard abstention.
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
    # If we let a follow-up through without new chunks, tell Claude explicitly
    # to reuse the prior turn's CONTEXT instead of refusing on empty CONTEXT.
    is_followup_reuse = (
        req.use_rag and not grounded and has_prior_turn and s.rag_strict
    )
    if is_followup_reuse:
        context_block = FOLLOWUP_CONTEXT_BLOCK
    user_turn = build_user_turn(req.message, context_block)

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
    # For follow-up drilling turns (no new chunks, but prior turns had chunks
    # in history), swap in the FOLLOWUP_SYSTEM_PROMPT which permits comparison,
    # ranking, and other reasoning across the items already listed earlier.
    active_system_prompt = FOLLOWUP_SYSTEM_PROMPT if is_followup_reuse else SYSTEM_PROMPT
    try:
        result = claude.complete(system=active_system_prompt, messages=history, model=req.model)
    except Exception as e:  # noqa: BLE001
        logger.exception("Claude call failed")
        raise HTTPException(502, f"Claude API error: {e}") from e

    answer = result["text"].strip()

    # Post-response bookkeeping. We used to force a refusal when a grounded
    # answer had no source-like attribution, but that turned out to over-fire
    # and hide legitimate answers. Now we only LOG the anomaly and mark
    # `source_info.unverified=true` so the UI can show a soft indicator if
    # desired. The user still sees the model's answer.
    _URL_PAT = re.compile(r"https?://\S+")
    _SOURCE_WORD_PAT = re.compile(r"\bsources?\b", re.IGNORECASE)
    refused_by_model = OUT_OF_SCOPE_REFUSAL.lower()[:60] in answer.lower()

    # Retry with the general-knowledge fallback when the KB answer was a
    # refusal but the question is still plausibly in-domain (e.g. we retrieved
    # chunks for "cancer" and "endoscopy" but none actually contrasted them,
    # so the strict SYSTEM_PROMPT triggered a refusal). Skip the retry for
    # follow-up reuse turns — those are handled by FOLLOWUP_SYSTEM_PROMPT and
    # shouldn't drop back to general knowledge.
    if (
        refused_by_model
        and not is_followup_reuse
        and req.use_rag
        and s.rag_allow_general_fallback
        and s.anthropic_api_key
    ):
        logger.info(
            "KB call refused; retrying with GENERAL_KNOWLEDGE_SYSTEM_PROMPT fallback."
        )
        try:
            gk_retry = claude.complete(
                system=GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": req.message}],
                model=req.model,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("General-knowledge retry failed")
            raise HTTPException(502, f"Claude API error: {e}") from e

        gk_answer = gk_retry["text"].strip()
        gk_refused = OUT_OF_SCOPE_REFUSAL.lower()[:60] in gk_answer.lower()
        if not gk_refused and GENERAL_KNOWLEDGE_BANNER not in gk_answer:
            gk_answer = f"{GENERAL_KNOWLEDGE_BANNER}\n\n{gk_answer}"

        await store.add_message(session_id, "user", req.message)
        await store.add_message(session_id, "assistant", gk_answer)
        return ChatResponse(
            session_id=session_id,
            answer=gk_answer,
            summary=_extract_summary(gk_answer),
            citations=[],
            used_rag=True,
            grounded=False,
            source_type="none" if gk_refused else "general_knowledge",
            source_info={
                "reason": "off_topic_refusal" if gk_refused
                else "general_knowledge_retry_after_kb_refusal",
                "threshold": s.rag_distance_threshold,
            },
            model=gk_retry["model"],
            usage=gk_retry["usage"],
        )

    answer_lower = answer.lower()
    has_source_mention = bool(_SOURCE_WORD_PAT.search(answer))
    has_url = bool(_URL_PAT.search(answer))
    chunk_titles = [
        str((c.metadata or {}).get("title") or "").strip().lower()
        for c in chunks
    ]
    chunk_titles = [t for t in chunk_titles if len(t) >= 5]
    chunk_doc_ids = [
        str((c.metadata or {}).get("doc_id") or "").strip().lower()
        for c in chunks
    ]
    chunk_doc_ids = [d for d in chunk_doc_ids if d]
    echoes_chunk = any(t in answer_lower for t in chunk_titles) or any(
        d in answer_lower for d in chunk_doc_ids
    )
    has_attribution = has_source_mention or has_url or echoes_chunk

    fell_back = refused_by_model
    must_cite = grounded or is_followup_reuse
    unverified = must_cite and not has_attribution and not refused_by_model
    if unverified:
        logger.info(
            f"Model {result.get('model')} returned an answer with no obvious source "
            f"attribution (grounded={grounded}, followup={is_followup_reuse}). "
            f"Allowing the response through and flagging unverified."
        )

    if grounded and fell_back:
        grounded = False
        citations: List[Citation] = []
        source_type = "general_knowledge"
        source_info: Dict[str, Any] = {}
    elif grounded:
        citations = _to_citations(chunks)
        source_type = "knowledge_base"
        source_info = {"citation_count": len(citations)}
        if unverified:
            source_info["unverified"] = True
    elif is_followup_reuse and not fell_back:
        # Follow-up answered from prior turn's context. We don't have fresh
        # chunks to attach, but the response is legitimate.
        citations = []
        source_type = "knowledge_base"
        source_info = {"reason": "followup_reuse"}
        if unverified:
            source_info["unverified"] = True
        grounded = True
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
