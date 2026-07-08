"""ClinicalTrials.gov v2 connector.

Docs: https://clinicaltrials.gov/data-api/api
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import httpx
from loguru import logger

from app.ingestion.pipeline import ingest_text

BASE = "https://clinicaltrials.gov/api/v2/studies"


def _study_to_text(study: Dict[str, Any]) -> Tuple[str, str, str]:
    proto = study.get("protocolSection", {}) or {}
    ident = proto.get("identificationModule", {}) or {}
    status = proto.get("statusModule", {}) or {}
    design = proto.get("designModule", {}) or {}
    desc = proto.get("descriptionModule", {}) or {}
    cond = proto.get("conditionsModule", {}) or {}
    interv = proto.get("armsInterventionsModule", {}) or {}
    outcomes = proto.get("outcomesModule", {}) or {}
    sponsor = proto.get("sponsorCollaboratorsModule", {}) or {}

    nct_id = ident.get("nctId", "")
    title = ident.get("briefTitle") or ident.get("officialTitle") or nct_id
    lines: List[str] = [
        f"NCT ID: {nct_id}",
        f"Title: {title}",
        f"Overall Status: {status.get('overallStatus', '')}",
        f"Phase: {', '.join(design.get('phases', []) or [])}",
        f"Study Type: {design.get('studyType', '')}",
        f"Conditions: {', '.join(cond.get('conditions', []) or [])}",
        f"Sponsor: {(sponsor.get('leadSponsor') or {}).get('name', '')}",
    ]
    if desc.get("briefSummary"):
        lines.append(f"\nBrief Summary:\n{desc['briefSummary']}")
    if desc.get("detailedDescription"):
        lines.append(f"\nDetailed Description:\n{desc['detailedDescription']}")
    interventions = interv.get("interventions") or []
    if interventions:
        lines.append("\nInterventions:")
        for i in interventions:
            lines.append(f"- {i.get('type', '')}: {i.get('name', '')} — {i.get('description', '')}")
    primary = outcomes.get("primaryOutcomes") or []
    if primary:
        lines.append("\nPrimary Outcomes:")
        for o in primary:
            lines.append(f"- {o.get('measure', '')} ({o.get('timeFrame', '')})")

    url = f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else ""
    return title, "\n".join(lines), url


async def ingest_trials(query: str, limit: int = 20) -> Tuple[int, int]:
    params = {
        "query.term": query,
        "pageSize": min(limit, 100),
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "RegView/1.0"}) as client:
        resp = await client.get(BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

    studies = data.get("studies", []) or []
    logger.info(f"ClinicalTrials.gov returned {len(studies)} studies for '{query}'")
    docs = 0
    chunks = 0
    for study in studies:
        title, text, url = _study_to_text(study)
        _, n = ingest_text(
            title=title,
            text=text,
            source="ClinicalTrials.gov",
            url=url,
            doc_type="clinical_trial",
            tags=[query],
        )
        if n:
            docs += 1
            chunks += n
    return docs, chunks


async def ingest_all_trials(
    max_records: int = 5000,
    query: str | None = None,
    page_size: int = 100,
) -> Tuple[int, int]:
    """Bulk-ingest ClinicalTrials.gov studies using pageToken pagination.

    ClinicalTrials.gov v2 has no hard skip cap — the only limit is patience
    (and Chroma disk). Default caps at 5000 to keep first runs sane.
    Set max_records to a very large number (e.g. 999999999) to fetch everything.
    Optionally narrow with `query` (v2 `query.term`), e.g. "cancer".
    """
    docs = chunks = 0
    fetched = 0
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": "RegView/1.0"}) as client:
        while fetched < max_records:
            params: Dict[str, Any] = {
                "pageSize": min(page_size, max_records - fetched),
                "format": "json",
            }
            if query:
                params["query.term"] = query
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            studies = data.get("studies", []) or []
            if not studies:
                break
            for study in studies:
                title, text, url = _study_to_text(study)
                _, n = ingest_text(
                    title=title, text=text, source="ClinicalTrials.gov",
                    url=url, doc_type="clinical_trial", tags=["bulk"],
                )
                if n:
                    docs += 1
                    chunks += n
            fetched += len(studies)
            if docs and docs % 500 == 0:
                logger.info(f"  ... {docs} trials ingested ({chunks} chunks)")
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    logger.info(f"ClinicalTrials.gov bulk done: {docs} studies, {chunks} chunks")
    return docs, chunks
