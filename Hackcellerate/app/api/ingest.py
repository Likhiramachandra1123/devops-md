"""Ingestion endpoints — upload files, index URLs, or ingest raw text."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from app.core.vector_store import get_vector_store
from app.ingestion.pipeline import ingest_file, ingest_text, ingest_url
from app.ingestion.sources import build_connector, run_source
from app.models import (
    IngestResponse,
    IngestTextRequest,
    IngestUrlRequest,
    SourceIngestRequest,
    SourceIngestResponse,
)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/files", response_model=IngestResponse)
async def ingest_files(
    files: List[UploadFile] = File(..., description="PDF, DOCX, HTML, TXT, or MD files."),
    source: str = Form("upload"),
    doc_type: Optional[str] = Form(None),
    tags: Optional[str] = Form(None, description="Comma-separated tags."),
):
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    doc_ids: List[str] = []
    total_chunks = 0
    total_docs = 0
    for f in files:
        try:
            suffix = Path(f.filename or "upload").suffix or ".txt"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await f.read())
                tmp_path = Path(tmp.name)
            try:
                doc_id, n = await asyncio.to_thread(
                    ingest_file, tmp_path, source, doc_type, tag_list
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            if n:
                doc_ids.append(doc_id)
                total_docs += 1
                total_chunks += n
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Ingest failed for {f.filename}")
            raise HTTPException(500, f"ingest failed for {f.filename}: {e}") from e
    return IngestResponse(ingested_documents=total_docs, ingested_chunks=total_chunks, doc_ids=doc_ids)


@router.post("/urls", response_model=IngestResponse)
async def ingest_urls(req: IngestUrlRequest):
    doc_ids: List[str] = []
    total_chunks = 0
    total_docs = 0
    for url in req.urls:
        try:
            doc_id, n = await ingest_url(url=url, source=req.source, doc_type=req.doc_type, tags=req.tags)
            if n:
                doc_ids.append(doc_id)
                total_docs += 1
                total_chunks += n
        except Exception as e:  # noqa: BLE001
            logger.exception(f"URL ingest failed for {url}")
            raise HTTPException(502, f"failed to ingest {url}: {e}") from e
    return IngestResponse(ingested_documents=total_docs, ingested_chunks=total_chunks, doc_ids=doc_ids)


@router.post("/text", response_model=IngestResponse)
async def ingest_raw_text(req: IngestTextRequest):
    doc_id, n = await asyncio.to_thread(
        ingest_text,
        req.title,
        req.text,
        req.source,
        req.url,
        req.doc_type,
        req.tags,
        None,
    )
    return IngestResponse(
        ingested_documents=1 if n else 0,
        ingested_chunks=n,
        doc_ids=[doc_id] if doc_id else [],
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    store = get_vector_store()
    removed = store.delete_by_doc_id(doc_id)
    if removed <= 0:
        raise HTTPException(404, f"no chunks found for doc_id={doc_id}")
    return {"deleted_chunks": removed, "doc_id": doc_id}


@router.get("/stats")
async def stats():
    store = get_vector_store()
    return {"chunk_count": store.count()}


@router.post("/source", response_model=SourceIngestResponse)
async def ingest_from_source(req: SourceIngestRequest) -> SourceIngestResponse:
    """Pull records from an external SQL / NoSQL / S3 source and ingest them.

    Body:
    {
      "type": "sql" | "mongo" | "s3",
      "config": { ...connector-specific fields... },
      "max_records": 100,
      "tags": ["optional", "extra", "tags"]
    }
    """
    try:
        connector = build_connector(req.type, req.config)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001 - covers pydantic validation of nested config
        raise HTTPException(422, f"invalid connector config: {e}") from e

    try:
        summary = await run_source(connector, max_records=req.max_records, extra_tags=req.tags)
    except RuntimeError as e:
        # Missing optional dep (pymongo / boto3)
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Source ingest failed for type={req.type}")
        raise HTTPException(500, f"source ingest failed: {e}") from e

    return SourceIngestResponse(
        total_records_seen=summary.total_records_seen,
        total_records_ingested=summary.total_records_ingested,
        total_chunks=summary.total_chunks,
        doc_ids=summary.doc_ids,
        errors=summary.errors,
    )
