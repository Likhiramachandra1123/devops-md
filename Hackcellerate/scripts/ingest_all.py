"""One-shot orchestrator: ingest URLs, local docs, and all connector sources at once.

Usage examples:
    # Everything with defaults
    python -m scripts.ingest_all

    # Custom drug/condition list + URL file + docs folder
    python -m scripts.ingest_all `
        --urls scripts\seed_urls.txt `
        --docs .\data\documents `
        --drugs "atorvastatin,metformin,ibuprofen" `
        --conditions "hypertension,type 2 diabetes" `
        --devices "insulin pump,pacemaker" `
        --limit 25
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import List, Tuple

from loguru import logger

from app.ingestion.connectors.clinicaltrials import ingest_trials
from app.ingestion.connectors.devices import ingest_device_510k, ingest_enforcement
from app.ingestion.connectors.openfda import ingest_adverse_events, ingest_drug_labels
from app.ingestion.connectors.orangebook import ingest_orange_book
from app.ingestion.pipeline import ingest_file, ingest_url

SUPPORTED_FILE_EXTS = {".pdf", ".txt", ".md", ".html", ".htm", ".docx"}


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


async def _safe(label: str, coro) -> Tuple[int, int]:
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[{label}] FAILED: {e}")
        return (0, 0)


async def _run(args) -> None:
    total_docs = 0
    total_chunks = 0

    # ---------- 1. URL seed list ----------
    if args.urls:
        url_path = Path(args.urls)
        if not url_path.exists():
            logger.warning(f"URL file not found: {url_path}")
        else:
            urls = [ln.strip() for ln in url_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")]
            logger.info(f"[URLS] ingesting {len(urls)} urls from {url_path}")
            for u in urls:
                try:
                    doc_id, n = await ingest_url(u, source="seed")
                    if n:
                        total_docs += 1
                        total_chunks += n
                        logger.info(f"  [URL OK] {u}  chunks={n}")
                    else:
                        logger.warning(f"  [URL empty] {u}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"  [URL FAIL] {u}: {e}")

    # ---------- 2. Local documents ----------
    if args.docs:
        docs_path = Path(args.docs)
        if not docs_path.exists():
            logger.warning(f"Docs folder not found: {docs_path}")
        else:
            files = [f for f in docs_path.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_FILE_EXTS]
            logger.info(f"[FILES] ingesting {len(files)} files from {docs_path}")
            for f in files:
                try:
                    doc_id, n = ingest_file(f, source="local")
                    if n:
                        total_docs += 1
                        total_chunks += n
                        logger.info(f"  [FILE OK] {f.name}  chunks={n}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"  [FILE FAIL] {f}: {e}")

    # ---------- 3. Drug-centric connectors ----------
    drugs = _split_csv(args.drugs)
    for drug in drugs:
        logger.info(f"[DRUG={drug}] pulling labels, FAERS, Orange Book, drug-enforcement...")
        for label, coro in [
            ("openfda-labels", ingest_drug_labels(drug, args.limit)),
            ("faers", ingest_adverse_events(drug, args.limit * 2)),
            ("orangebook", ingest_orange_book(drug, args.limit)),
            ("drug-enforcement", ingest_enforcement(drug, args.limit, kind="drug")),
        ]:
            d, c = await _safe(f"{label}:{drug}", coro)
            total_docs += d
            total_chunks += c
            logger.info(f"  [{label}] docs={d} chunks={c}")

    # ---------- 4. Condition-centric connector ----------
    conditions = _split_csv(args.conditions)
    for cond in conditions:
        logger.info(f"[CONDITION={cond}] pulling clinical trials...")
        d, c = await _safe(f"clinicaltrials:{cond}", ingest_trials(cond, args.limit))
        total_docs += d
        total_chunks += c
        logger.info(f"  [clinicaltrials] docs={d} chunks={c}")

    # ---------- 5. Device-centric connectors ----------
    devices = _split_csv(args.devices)
    for dev in devices:
        logger.info(f"[DEVICE={dev}] pulling 510(k) and device-enforcement...")
        for label, coro in [
            ("device-510k", ingest_device_510k(dev, args.limit)),
            ("device-enforcement", ingest_enforcement(dev, args.limit, kind="device")),
        ]:
            d, c = await _safe(f"{label}:{dev}", coro)
            total_docs += d
            total_chunks += c
            logger.info(f"  [{label}] docs={d} chunks={c}")

    logger.info("=" * 60)
    logger.info(f"ALL DONE. Total docs indexed: {total_docs}   Total chunks: {total_chunks}")
    logger.info("=" * 60)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", default="scripts/seed_urls.txt", help="Path to seed URLs file (one per line).")
    ap.add_argument("--docs", default="data/documents", help="Local folder to bulk-ingest (PDF/DOCX/TXT/HTML/MD).")
    ap.add_argument(
        "--drugs",
        default="atorvastatin,metformin,ibuprofen",
        help="Comma-separated drug names for labels/FAERS/Orange Book/enforcement.",
    )
    ap.add_argument(
        "--conditions",
        default="hypercholesterolemia,type 2 diabetes,hypertension",
        help="Comma-separated conditions for ClinicalTrials.gov.",
    )
    ap.add_argument(
        "--devices",
        default="insulin pump,pacemaker",
        help="Comma-separated device terms for 510(k) and device enforcement.",
    )
    ap.add_argument("--limit", type=int, default=25, help="Per-connector record cap.")
    asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    main()
