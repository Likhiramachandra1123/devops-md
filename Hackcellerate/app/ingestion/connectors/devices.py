"""openFDA Device 510(k) and Enforcement connectors."""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from app.ingestion.pipeline import ingest_text

BASE = "https://api.fda.gov"
PAGE_SIZE = 100
OPENFDA_MAX_SKIP = 25000


async def _fetch(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": "RegView/1.0"}) as client:
        resp = await client.get(f"{BASE}{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()


async def _paginate(endpoint: str, search: Optional[str], max_records: int) -> AsyncIterator[Dict[str, Any]]:
    ceiling = min(max_records, OPENFDA_MAX_SKIP)
    skip = 0
    while skip < ceiling:
        limit = min(PAGE_SIZE, ceiling - skip)
        params: Dict[str, Any] = {"limit": limit, "skip": skip}
        if search:
            params["search"] = search
        try:
            data = await _fetch(endpoint, params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return
            raise
        results = data.get("results", []) or []
        if not results:
            return
        for rec in results:
            yield rec
        skip += len(results)
        if len(results) < limit:
            return


def _510k_to_text(rec: Dict[str, Any]) -> Tuple[str, str, str]:
    k_no = rec.get("k_number", "")
    dev = rec.get("device_name", "Unknown device")
    applicant = rec.get("applicant", "")
    title = f"510(k): {dev} ({k_no})"
    lines: List[str] = [
        f"K Number: {k_no}",
        f"Device Name: {dev}",
        f"Applicant: {applicant}",
        f"Product Code: {rec.get('product_code','')}",
        f"Advisory Committee: {rec.get('advisory_committee_description','')}",
        f"Decision: {rec.get('decision_description','')}  ({rec.get('decision_code','')})",
        f"Clearance / Decision Date: {rec.get('decision_date','')}",
        f"Date Received: {rec.get('date_received','')}",
        f"Review Panel: {rec.get('review_panel','')}",
        f"Statement / Summary: {rec.get('statement_or_summary','')}",
        f"Type: {rec.get('clearance_type','')}",
        f"Third Party Flag: {rec.get('third_party_flag','')}",
        f"Country: {rec.get('country_code','')}",
    ]
    address = ", ".join(
        v for v in [rec.get("address_1"), rec.get("city"), rec.get("state"), rec.get("postal_code"), rec.get("country_code")] if v
    )
    if address:
        lines.append(f"Applicant Address: {address}")
    url = f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={k_no}" if k_no else ""
    return title, "\n".join(lines), url


async def ingest_device_510k(query: str, limit: int = 25) -> Tuple[int, int]:
    """Ingest FDA 510(k) medical-device clearances matching a device/applicant term."""
    data = await _fetch(
        "/device/510k.json",
        {"search": query, "limit": min(limit, 100)},
    )
    results = data.get("results", []) or []
    logger.info(f"openFDA 510(k) returned {len(results)} records for '{query}'")
    docs = chunks = 0
    for rec in results:
        title, text, url = _510k_to_text(rec)
        _, n = ingest_text(
            title=title,
            text=text,
            source="openFDA-510k",
            url=url,
            doc_type="device_510k",
            tags=[query],
        )
        if n:
            docs += 1
            chunks += n
    return docs, chunks


def _enforcement_to_text(rec: Dict[str, Any]) -> Tuple[str, str, str]:
    recall_no = rec.get("recall_number", "")
    product = rec.get("product_description", "Unknown product")
    title = f"FDA Enforcement Action: {product[:80]} ({recall_no})"
    lines: List[str] = [
        f"Recall Number: {recall_no}",
        f"Product Type: {rec.get('product_type','')}",
        f"Status: {rec.get('status','')}",
        f"Classification: {rec.get('classification','')}",
        f"Reason for Recall: {rec.get('reason_for_recall','')}",
        f"Voluntary/Mandated: {rec.get('voluntary_mandated','')}",
        f"Recalling Firm: {rec.get('recalling_firm','')}",
        f"Recall Initiation Date: {rec.get('recall_initiation_date','')}",
        f"Report Date: {rec.get('report_date','')}",
        f"Distribution Pattern: {rec.get('distribution_pattern','')}",
        f"Product Description: {product}",
        f"Code Info: {rec.get('code_info','')}",
    ]
    url = f"https://api.fda.gov/drug/enforcement.json?search=recall_number:\"{recall_no}\"" if recall_no else ""
    return title, "\n".join(lines), url


async def ingest_enforcement(query: str, limit: int = 50, kind: str = "drug") -> Tuple[int, int]:
    """Ingest FDA enforcement / recall records.

    kind: one of 'drug', 'device', 'food'.
    """
    endpoint = {"drug": "/drug/enforcement.json", "device": "/device/enforcement.json", "food": "/food/enforcement.json"}[kind]
    data = await _fetch(endpoint, {"search": query, "limit": min(limit, 100)})
    results = data.get("results", []) or []
    logger.info(f"openFDA {kind}/enforcement returned {len(results)} records for '{query}'")
    docs = chunks = 0
    for rec in results:
        title, text, url = _enforcement_to_text(rec)
        _, n = ingest_text(
            title=title,
            text=text,
            source=f"openFDA-{kind}-enforcement",
            url=url,
            doc_type=f"{kind}_enforcement",
            tags=[query, kind],
        )
        if n:
            docs += 1
            chunks += n
    return docs, chunks


async def ingest_all_device_510k(max_records: int = OPENFDA_MAX_SKIP) -> Tuple[int, int]:
    """Bulk-ingest EVERY 510(k) clearance (up to openFDA's 25k cap)."""
    docs = chunks = 0
    logger.info(f"openFDA 510(k): bulk fetch up to {min(max_records, OPENFDA_MAX_SKIP)} records ...")
    async for rec in _paginate("/device/510k.json", search=None, max_records=max_records):
        title, text, url = _510k_to_text(rec)
        _, n = ingest_text(title=title, text=text, source="openFDA-510k", url=url, doc_type="device_510k", tags=["bulk"])
        if n:
            docs += 1
            chunks += n
        if docs % 500 == 0 and docs > 0:
            logger.info(f"  ... {docs} 510(k) records ingested ({chunks} chunks)")
    return docs, chunks


async def ingest_all_enforcement(kind: str = "drug", max_records: int = OPENFDA_MAX_SKIP) -> Tuple[int, int]:
    """Bulk-ingest EVERY enforcement/recall record for a given kind (drug/device/food)."""
    endpoint = {"drug": "/drug/enforcement.json", "device": "/device/enforcement.json", "food": "/food/enforcement.json"}[kind]
    docs = chunks = 0
    logger.info(f"openFDA {kind}/enforcement: bulk fetch up to {min(max_records, OPENFDA_MAX_SKIP)} records ...")
    async for rec in _paginate(endpoint, search=None, max_records=max_records):
        title, text, url = _enforcement_to_text(rec)
        _, n = ingest_text(
            title=title, text=text, source=f"openFDA-{kind}-enforcement",
            url=url, doc_type=f"{kind}_enforcement", tags=["bulk", kind],
        )
        if n:
            docs += 1
            chunks += n
        if docs % 500 == 0 and docs > 0:
            logger.info(f"  ... {docs} {kind} enforcement records ({chunks} chunks)")
    return docs, chunks

