"""Bulk-ingest URLs (one per line) into RegView.

Usage:
    python -m scripts.ingest_urls --file urls.txt --source web
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from loguru import logger

from app.ingestion.pipeline import ingest_url


async def _run(urls, source, doc_type, tags):
    total = 0
    for u in urls:
        try:
            doc_id, n = await ingest_url(u, source=source, doc_type=doc_type, tags=tags)
            total += n
            logger.info(f"  -> {u}: doc_id={doc_id} chunks={n}")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Failed to ingest {u}: {e}")
    logger.info(f"Done. Total chunks indexed: {total}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--source", default="web")
    ap.add_argument("--doc-type", default=None)
    ap.add_argument("--tags", default=None)
    args = ap.parse_args()
    urls = [ln.strip() for ln in Path(args.file).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    asyncio.run(_run(urls, args.source, args.doc_type, tags))


if __name__ == "__main__":
    main()
