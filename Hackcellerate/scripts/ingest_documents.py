"""Bulk-ingest local documents into RegView's vector store.

Usage:
    python -m scripts.ingest_documents --path ./data/documents --source manual --tags "guidance,fda"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from app.ingestion.pipeline import ingest_file

SUPPORTED = {".pdf", ".txt", ".md", ".html", ".htm", ".docx"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="File or directory to ingest.")
    ap.add_argument("--source", default="manual")
    ap.add_argument("--doc-type", default=None)
    ap.add_argument("--tags", default=None, help="Comma-separated tags.")
    args = ap.parse_args()

    p = Path(args.path)
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    files = []
    if p.is_file():
        files = [p]
    else:
        files = [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED]

    logger.info(f"Ingesting {len(files)} files from {p}")
    total_chunks = 0
    for f in files:
        try:
            doc_id, n = ingest_file(f, source=args.source, doc_type=args.doc_type, tags=tags)
            total_chunks += n
            logger.info(f"  -> {f.name}: doc_id={doc_id} chunks={n}")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Failed to ingest {f}: {e}")
    logger.info(f"Done. Total chunks indexed: {total_chunks}")


if __name__ == "__main__":
    main()
