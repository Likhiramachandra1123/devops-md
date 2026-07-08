"""Bulk ingestion — download EVERYTHING (or as much as APIs allow) into ChromaDB.

This is the big one. Run when you want your local library to cover the widest
possible range of questions. Anything not indexed will still be answered by
Claude's general knowledge (with a "not found in the internal knowledge base"
disclaimer added to the reply).

Coverage per source:
  * openFDA drug labels ................. up to 25,000 records (API cap)
  * openFDA 510(k) device clearances .... up to 25,000 records (API cap)
  * openFDA drug enforcement / recalls .. up to 25,000 records
  * openFDA device enforcement .......... up to 25,000 records
  * openFDA food enforcement ............ up to 25,000 records
  * FDA Orange Book ..................... ALL ~34,000 products
  * ClinicalTrials.gov v2 ............... capped at --trials-limit (default 5000)
  * Seed URLs (scripts/seed_urls.txt) ... every URL, chunk & index

FAERS adverse events are intentionally SKIPPED in bulk mode — the raw
per-event stream is in the millions and is not useful as vector chunks.
Per-drug FAERS summaries are still available via `scripts.ingest_all`.

Usage (from repo root):
    python -m scripts.ingest_bulk                     # sensible defaults
    python -m scripts.ingest_bulk --labels-max 5000   # smaller drug-label pull
    python -m scripts.ingest_bulk --trials-limit 20000
    python -m scripts.ingest_bulk --skip clinicaltrials,510k
    python -m scripts.ingest_bulk --only orangebook

Expect this to take a while and use several GB of disk (Chroma + embeddings).
"""
from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from loguru import logger

from app.config import get_settings
from app.core.vector_store import get_vector_store
from app.ingestion.connectors.clinicaltrials import ingest_all_trials
from app.ingestion.connectors.devices import (
    ingest_all_device_510k,
    ingest_all_enforcement,
)
from app.ingestion.connectors.openfda import ingest_all_drug_labels
from app.ingestion.connectors.orangebook import ingest_all_orange_book
from app.ingestion.pipeline import ingest_url

SEED_URLS_FILE = Path(__file__).parent / "seed_urls.txt"

STEPS = ["urls", "labels", "orangebook", "510k", "drug_enforce", "device_enforce", "food_enforce", "clinicaltrials"]


def _load_seed_urls() -> list[str]:
    if not SEED_URLS_FILE.exists():
        return []
    urls: list[str] = []
    for line in SEED_URLS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


async def _run_urls() -> tuple[int, int]:
    urls = _load_seed_urls()
    docs = chunks = 0
    for u in urls:
        try:
            _, n = await ingest_url(u)
            if n:
                docs += 1
                chunks += n
                logger.info(f"URL ok ({n} chunks): {u}")
        except Exception as e:
            logger.warning(f"URL failed ({e}): {u}")
    return docs, chunks


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-ingest FDA + CT.gov data into the local knowledge base.")
    parser.add_argument("--labels-max", type=int, default=25000, help="Max drug labels (openFDA cap 25000).")
    parser.add_argument("--510k-max", type=int, default=25000, help="Max 510(k) clearances (openFDA cap 25000).")
    parser.add_argument("--enforce-max", type=int, default=25000, help="Max records per enforcement kind.")
    parser.add_argument("--trials-limit", type=int, default=5000, help="Max ClinicalTrials.gov studies (no API cap).")
    parser.add_argument("--trials-query", type=str, default=None, help="Optional CT.gov filter (e.g. 'cancer').")
    parser.add_argument("--skip", type=str, default="", help=f"Comma-list of steps to skip. Available: {','.join(STEPS)}")
    parser.add_argument("--only", type=str, default="", help="Comma-list — run only these steps.")
    args = parser.parse_args()

    get_settings()  # loads .env and creates data dirs
    get_vector_store()  # warm

    if args.only:
        steps = [s.strip() for s in args.only.split(",") if s.strip()]
    else:
        skip = {s.strip() for s in args.skip.split(",") if s.strip()}
        steps = [s for s in STEPS if s not in skip]

    logger.info(f"Bulk ingest — running steps: {steps}")
    totals = {"docs": 0, "chunks": 0}
    started = time.time()

    async def run(name: str, coro):
        logger.info(f"=== {name} ===")
        t0 = time.time()
        try:
            d, c = await coro
        except Exception as e:
            logger.exception(f"{name} failed: {type(e).__name__}: {e or '(no message)'}")
            return
        totals["docs"] += d
        totals["chunks"] += c
        logger.info(f"=== {name} done in {time.time()-t0:.1f}s — {d} docs / {c} chunks ===")

    if "urls" in steps:
        await run("Seed URLs", _run_urls())
    if "labels" in steps:
        await run("openFDA drug labels", ingest_all_drug_labels(max_records=args.labels_max))
    if "orangebook" in steps:
        await run("FDA Orange Book (all products)", ingest_all_orange_book())
    if "510k" in steps:
        await run("openFDA 510(k) clearances", ingest_all_device_510k(max_records=getattr(args, "510k_max")))
    if "drug_enforce" in steps:
        await run("openFDA drug enforcement", ingest_all_enforcement(kind="drug", max_records=args.enforce_max))
    if "device_enforce" in steps:
        await run("openFDA device enforcement", ingest_all_enforcement(kind="device", max_records=args.enforce_max))
    if "food_enforce" in steps:
        await run("openFDA food enforcement", ingest_all_enforcement(kind="food", max_records=args.enforce_max))
    if "clinicaltrials" in steps:
        await run("ClinicalTrials.gov", ingest_all_trials(max_records=args.trials_limit, query=args.trials_query))

    dur = time.time() - started
    store = get_vector_store()
    logger.success(
        f"BULK INGEST COMPLETE — {totals['docs']} docs, {totals['chunks']} chunks, "
        f"{store.count()} total chunks in ChromaDB, elapsed {dur/60:.1f} min"
    )
    logger.info(
        "Reminder: anything NOT in the local library will still be answered by "
        "Claude's general knowledge, prefixed with a 'Not found in the internal "
        "knowledge base' disclaimer, with grounded=false in the API response."
    )


if __name__ == "__main__":
    asyncio.run(main())
