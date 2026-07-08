"""One-command end-to-end demo / smoke test.

Runs the FULL flow locally:
  1. Ingest a small sample (openFDA label + FAERS + ClinicalTrials for one drug).
  2. Run a test question through the RAG pipeline.
  3. Print retrieved chunks, citations, and the final answer.

Usage:
    # Full flow (needs ANTHROPIC_API_KEY in .env)
    python -m scripts.demo

    # Custom drug + question
    python -m scripts.demo --drug "metformin" --question "What are metformin's side effects?"

    # Skip Claude — only test retrieval (no API key needed)
    python -m scripts.demo --no-claude

    # Skip ingestion (use whatever is already in Chroma)
    python -m scripts.demo --skip-ingest --question "your question here"
"""
from __future__ import annotations

import argparse
import asyncio
import textwrap

from loguru import logger

from app.config import get_settings
from app.core.retriever import retrieve
from app.core.vector_store import get_vector_store
from app.db.session_store import get_session_store
from app.ingestion.connectors.clinicaltrials import ingest_trials
from app.ingestion.connectors.openfda import ingest_adverse_events, ingest_drug_labels
from app.ingestion.connectors.orangebook import ingest_orange_book


# ANSI color helpers (work on Win 10+ terminals)
def _c(text: str, color: str) -> str:
    colors = {"cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
              "red": "\033[31m", "bold": "\033[1m", "reset": "\033[0m"}
    return f"{colors.get(color, '')}{text}{colors['reset']}"


def banner(title: str) -> None:
    line = "=" * 72
    print()
    print(_c(line, "cyan"))
    print(_c(f"  {title}", "cyan"))
    print(_c(line, "cyan"))


async def _ingest_sample(drug: str, condition: str, limit: int) -> None:
    banner(f"STEP 1 — Ingesting a small sample about '{drug}' / '{condition}'")

    for label, coro in [
        (f"openFDA drug labels ({drug})",      ingest_drug_labels(drug, limit)),
        (f"FAERS side-effects ({drug})",       ingest_adverse_events(drug, limit * 4)),
        (f"Orange Book patents ({drug})",      ingest_orange_book(drug, limit)),
        (f"ClinicalTrials ({condition})",      ingest_trials(condition, limit)),
    ]:
        try:
            print(_c(f"  → {label} ...", "yellow"))
            docs, chunks = await coro
            print(_c(f"     ok — {docs} docs, {chunks} chunks", "green"))
        except Exception as e:  # noqa: BLE001
            print(_c(f"     FAILED: {e}", "red"))


def _run_retrieval(question: str) -> list:
    banner(f"STEP 2 — Retrieval for: \"{question}\"")

    store = get_vector_store()
    print(f"  Vector store size: {store.count()} chunks")
    if store.count() == 0:
        print(_c("  ⚠ Library is empty — nothing to retrieve.", "red"))
        return []

    chunks = retrieve(question)
    if not chunks:
        print(_c("  ⚠ No chunks passed the distance threshold (nothing grounded).", "yellow"))
        return chunks

    print(_c(f"\n  Top {len(chunks)} grounded chunks:", "bold"))
    for i, c in enumerate(chunks, start=1):
        meta = c.metadata or {}
        title = meta.get("title", "Untitled")
        source = meta.get("source", "?")
        snippet = c.text.replace("\n", " ")
        snippet = textwrap.shorten(snippet, width=180, placeholder=" …")
        print(f"  [{i}] {_c(title[:60], 'green')}  ({source})  distance={c.distance:.3f}")
        print(f"      {snippet}")
    return chunks


async def _run_full_chat(question: str, chunks: list) -> None:
    banner("STEP 3 — Calling Claude with the retrieved context")

    # Delayed imports so --no-claude runs without needing the SDK / API key
    from app.core.claude_client import get_claude_client
    from app.core.memory import build_history_messages
    from app.core.prompts import SYSTEM_PROMPT, build_context_block, build_user_turn

    store = get_session_store()
    await store.init()
    session_id = await store.create_session(title="demo")

    context_block = build_context_block(chunks)
    user_turn = build_user_turn(question, context_block)

    history = await build_history_messages(session_id)
    history.append({"role": "user", "content": user_turn})

    print(_c(f"  session_id = {session_id}", "yellow"))
    print(_c(f"  grounded   = {bool(chunks)}", "yellow"))
    print(_c(f"  sending {len(history)} messages to Claude ...", "yellow"))

    try:
        client = get_claude_client()
        result = client.complete(system=SYSTEM_PROMPT, messages=history)
    except Exception as e:  # noqa: BLE001
        print(_c(f"  Claude call failed: {e}", "red"))
        print(_c("  → Check that ANTHROPIC_API_KEY is set in .env", "red"))
        return

    banner("STEP 4 — Claude's answer")
    print(result["text"])

    banner("STEP 5 — Metadata")
    print(f"  model         : {result['model']}")
    print(f"  input tokens  : {result['usage'].get('input_tokens')}")
    print(f"  output tokens : {result['usage'].get('output_tokens')}")
    print(f"  stop reason   : {result['stop_reason']}")

    # Persist the turn
    await store.add_message(session_id, "user", question)
    await store.add_message(session_id, "assistant", result["text"])
    print(_c(f"\n  Saved to conversation history (session_id={session_id})", "green"))
    print(_c("  Follow-up test:  curl http://localhost:8000/sessions/"
            f"{session_id}/messages", "yellow"))


async def _main(args) -> None:
    get_settings().ensure_dirs()

    if not args.skip_ingest:
        await _ingest_sample(args.drug, args.condition, args.limit)
    else:
        print(_c("(skipping ingestion, using whatever is already in Chroma)", "yellow"))

    chunks = _run_retrieval(args.question)

    if args.no_claude:
        banner("Done (retrieval-only mode). Skipping Claude.")
        return

    await _run_full_chat(args.question, chunks)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drug", default="atorvastatin",
                    help="Drug to ingest labels/FAERS/Orange Book for.")
    ap.add_argument("--condition", default="hypercholesterolemia",
                    help="Condition to ingest clinical trials for.")
    ap.add_argument("--question", default="What are the common side effects of atorvastatin?",
                    help="Question to ask at the end.")
    ap.add_argument("--limit", type=int, default=5,
                    help="Records per source (keep small for a smoke test).")
    ap.add_argument("--skip-ingest", action="store_true",
                    help="Skip ingestion; run retrieval + Claude on existing data.")
    ap.add_argument("--no-claude", action="store_true",
                    help="Retrieval only (no API key needed).")
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
