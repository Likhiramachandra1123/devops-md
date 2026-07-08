"""External-source (openFDA, ClinicalTrials, Orange Book) ingestion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.ingestion.connectors.clinicaltrials import ingest_trials
from app.ingestion.connectors.devices import ingest_device_510k, ingest_enforcement
from app.ingestion.connectors.openfda import ingest_adverse_events, ingest_drug_labels
from app.ingestion.connectors.orangebook import ingest_orange_book
from app.models import ConnectorIngestRequest, IngestResponse

router = APIRouter(prefix="/sources", tags=["sources"])


def _resp(docs: int, chunks: int) -> IngestResponse:
    return IngestResponse(ingested_documents=docs, ingested_chunks=chunks, doc_ids=[])


@router.post("/openfda/drug-labels", response_model=IngestResponse)
async def fetch_openfda_labels(req: ConnectorIngestRequest):
    try:
        docs, chunks = await ingest_drug_labels(req.query, req.limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("openFDA drug label ingestion failed")
        raise HTTPException(502, f"openFDA error: {e}") from e
    return _resp(docs, chunks)


@router.post("/openfda/faers", response_model=IngestResponse)
async def fetch_faers(req: ConnectorIngestRequest):
    try:
        docs, chunks = await ingest_adverse_events(req.query, req.limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("FAERS ingestion failed")
        raise HTTPException(502, f"FAERS error: {e}") from e
    return _resp(docs, chunks)


@router.post("/clinicaltrials", response_model=IngestResponse)
async def fetch_clinical_trials(req: ConnectorIngestRequest):
    try:
        docs, chunks = await ingest_trials(req.query, req.limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("ClinicalTrials.gov ingestion failed")
        raise HTTPException(502, f"ClinicalTrials.gov error: {e}") from e
    return _resp(docs, chunks)


@router.post("/orangebook", response_model=IngestResponse)
async def fetch_orange_book(req: ConnectorIngestRequest):
    try:
        docs, chunks = await ingest_orange_book(req.query, req.limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("Orange Book ingestion failed")
        raise HTTPException(502, f"Orange Book error: {e}") from e
    return _resp(docs, chunks)


@router.post("/openfda/device-510k", response_model=IngestResponse)
async def fetch_device_510k(req: ConnectorIngestRequest):
    try:
        docs, chunks = await ingest_device_510k(req.query, req.limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("Device 510(k) ingestion failed")
        raise HTTPException(502, f"Device 510(k) error: {e}") from e
    return _resp(docs, chunks)


@router.post("/openfda/enforcement/{kind}", response_model=IngestResponse)
async def fetch_enforcement(kind: str, req: ConnectorIngestRequest):
    if kind not in ("drug", "device", "food"):
        raise HTTPException(400, "kind must be one of: drug, device, food")
    try:
        docs, chunks = await ingest_enforcement(req.query, req.limit, kind=kind)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"{kind} enforcement ingestion failed")
        raise HTTPException(502, f"{kind} enforcement error: {e}") from e
    return _resp(docs, chunks)
