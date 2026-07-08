"""openFDA connector — drug labels, enforcement, and event endpoints.

Docs: https://open.fda.gov/apis/

Note on limits: the public openFDA API caps `skip + limit` at 25000. For
"ingest everything" we walk pages up to that cap. Beyond 25k, you need to
partition the search space (e.g. per year, per first-letter) or use the
`search_after` special pagination.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from app.ingestion.pipeline import ingest_text

BASE = "https://api.fda.gov"
PAGE_SIZE = 100  # openFDA max per call
OPENFDA_MAX_SKIP = 25000  # openFDA hard cap on skip+limit


async def _fetch(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE}{endpoint}"
    async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": "RegView/1.0"}) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _paginate(
    endpoint: str,
    search: Optional[str],
    max_records: int,
) -> AsyncIterator[Dict[str, Any]]:
    """Yield records from an openFDA endpoint, walking pages until max_records or cap."""
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
            # 404 = "no results at this skip"; stop cleanly
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


def _label_to_text(rec: Dict[str, Any]) -> Tuple[str, str, str]:
    openfda = rec.get("openfda", {}) or {}
    brand = (openfda.get("brand_name") or [""])[0].strip()
    generic = (openfda.get("generic_name") or [""])[0].strip()
    manufacturer = (openfda.get("manufacturer_name") or [""])[0].strip()
    app_no = (openfda.get("application_number") or [""])[0].strip()
    substance = (openfda.get("substance_name") or [""])[0].strip()
    spl_id = str(rec.get("set_id") or rec.get("id") or "").strip()

    if brand and generic:
        title = f"FDA Label: {brand} ({generic})"
    elif brand:
        title = f"FDA Label: {brand}"
    elif generic:
        title = f"FDA Label: {generic}"
    elif manufacturer and app_no:
        title = f"FDA Label · {manufacturer} · App {app_no}"
    elif manufacturer:
        title = f"FDA Label · {manufacturer}"
    elif app_no:
        title = f"FDA Label · Application {app_no}"
    elif substance:
        title = f"FDA Label · {substance}"
    elif spl_id:
        title = f"FDA Label · SPL {spl_id[:12]}"
    else:
        title = "FDA Label · (untitled)"

    parts: List[str] = []
    if brand:
        parts.append(f"Brand: {brand}")
    if generic:
        parts.append(f"Generic: {generic}")
    if manufacturer:
        parts.append(f"Manufacturer: {manufacturer}")
    if app_no:
        parts.append(f"Application Number: {app_no}")
    if substance and substance != generic:
        parts.append(f"Substance: {substance}")

    for section in (
        "indications_and_usage",
        "dosage_and_administration",
        "warnings",
        "warnings_and_cautions",
        "contraindications",
        "adverse_reactions",
        "drug_interactions",
        "mechanism_of_action",
        "clinical_pharmacology",
        "pharmacokinetics",
        "clinical_studies",
        "how_supplied",
    ):
        val = rec.get(section)
        if isinstance(val, list) and val:
            parts.append(f"\n### {section.replace('_', ' ').title()}\n" + "\n".join(val))
    text = "\n\n".join(parts)
    doc_url = f"https://api.fda.gov/drug/label.json?search=id:{rec.get('id','')}"
    return title, text, doc_url


async def ingest_drug_labels(query: str, limit: int = 20) -> Tuple[int, int]:
    """Ingest FDA drug labels matching a search term (drug name / condition)."""
    data = await _fetch(
        "/drug/label.json",
        {"search": query, "limit": min(limit, 100)},
    )
    results = data.get("results", [])
    logger.info(f"openFDA drug/label returned {len(results)} records for '{query}'")
    docs = 0
    chunks = 0
    for rec in results:
        title, text, url = _label_to_text(rec)
        _, n = ingest_text(
            title=title,
            text=text,
            source="openFDA",
            url=url,
            doc_type="drug_label",
            tags=[query],
        )
        if n:
            docs += 1
            chunks += n
    return docs, chunks


async def ingest_all_drug_labels(max_records: int = OPENFDA_MAX_SKIP) -> Tuple[int, int]:
    """Bulk-ingest EVERY FDA drug label (up to openFDA's 25k skip cap)."""
    docs = chunks = 0
    logger.info(f"openFDA drug/label: bulk fetch up to {min(max_records, OPENFDA_MAX_SKIP)} records ...")
    async for rec in _paginate("/drug/label.json", search=None, max_records=max_records):
        title, text, url = _label_to_text(rec)
        _, n = ingest_text(title=title, text=text, source="openFDA", url=url, doc_type="drug_label", tags=["bulk"])
        if n:
            docs += 1
            chunks += n
        if docs % 200 == 0 and docs > 0:
            logger.info(f"  ... {docs} labels ingested so far ({chunks} chunks)")
    return docs, chunks


async def ingest_adverse_events(drug: str, limit: int = 50) -> Tuple[int, int]:
    """Ingest FAERS adverse-event summaries for a drug."""
    data = await _fetch(
        "/drug/event.json",
        {
            "search": f'patient.drug.medicinalproduct:"{drug}"',
            "limit": min(limit, 100),
        },
    )
    results = data.get("results", [])
    logger.info(f"FAERS returned {len(results)} events for '{drug}'")
    if not results:
        return 0, 0

    # Aggregate reactions into one summary document per drug
    from collections import Counter
    reactions: Counter[str] = Counter()
    seriousness = Counter()
    for r in results:
        for rx in r.get("patient", {}).get("reaction", []) or []:
            term = rx.get("reactionmeddrapt")
            if term:
                reactions[term] += 1
        for key in ("serious", "seriousnessdeath", "seriousnesshospitalization"):
            if str(r.get(key, "")) == "1":
                seriousness[key] += 1

    top = reactions.most_common(30)
    text_lines = [
        f"FAERS Adverse Event Summary for '{drug}'",
        f"Total reports analyzed: {len(results)}",
        "",
        "Top reported reactions (term: count):",
    ]
    text_lines.extend([f"- {term}: {count}" for term, count in top])
    text_lines.append("")
    text_lines.append("Seriousness counts:")
    text_lines.extend([f"- {k}: {v}" for k, v in seriousness.items()])
    title = f"FAERS Adverse Events: {drug}"
    url = f"https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:\"{drug}\""
    _, n = ingest_text(
        title=title,
        text="\n".join(text_lines),
        source="FAERS",
        url=url,
        doc_type="adverse_events",
        tags=[drug],
    )
    return (1 if n else 0, n)
