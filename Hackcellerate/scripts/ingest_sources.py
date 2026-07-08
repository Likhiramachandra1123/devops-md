"""Bulk-ingest data from external regulatory sources.

Usage:
    python -m scripts.ingest_sources --source openfda-labels --query "atorvastatin" --limit 20
    python -m scripts.ingest_sources --source clinicaltrials --query "psoriasis" --limit 30
    python -m scripts.ingest_sources --source faers --query "atorvastatin" --limit 50
    python -m scripts.ingest_sources --source orangebook --query "atorvastatin" --limit 50
"""
from __future__ import annotations

import argparse
import asyncio

from loguru import logger

from app.ingestion.connectors.clinicaltrials import ingest_trials
from app.ingestion.connectors.devices import ingest_device_510k, ingest_enforcement
from app.ingestion.connectors.openfda import ingest_adverse_events, ingest_drug_labels
from app.ingestion.connectors.orangebook import ingest_orange_book


async def _run(source: str, query: str, limit: int):
    if source == "openfda-labels":
        return await ingest_drug_labels(query, limit)
    if source == "faers":
        return await ingest_adverse_events(query, limit)
    if source == "clinicaltrials":
        return await ingest_trials(query, limit)
    if source == "orangebook":
        return await ingest_orange_book(query, limit)
    if source == "device-510k":
        return await ingest_device_510k(query, limit)
    if source in ("drug-enforcement", "device-enforcement", "food-enforcement"):
        kind = source.split("-")[0]
        return await ingest_enforcement(query, limit, kind=kind)
    raise SystemExit(f"Unknown source: {source}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        required=True,
        choices=[
            "openfda-labels",
            "faers",
            "clinicaltrials",
            "orangebook",
            "device-510k",
            "drug-enforcement",
            "device-enforcement",
            "food-enforcement",
        ],
    )
    ap.add_argument("--query", required=True)
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()
    docs, chunks = asyncio.run(_run(args.source, args.query, args.limit))
    logger.info(f"Ingested docs={docs} chunks={chunks} from {args.source} for '{args.query}'")


if __name__ == "__main__":
    main()
