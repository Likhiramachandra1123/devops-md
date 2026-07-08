"""FDA Orange Book connector.

Orange Book bulk files:
  https://www.fda.gov/drugs/drug-approvals-and-databases/approved-drug-products-therapeutic-equivalence-evaluations-orange-book

We use the CDER downloadable ZIP containing `products.txt`, `patent.txt`, `exclusivity.txt`.
Point ORANGE_BOOK_ZIP_URL to the current file (updates monthly).
"""
from __future__ import annotations

import io
import zipfile
from typing import Dict, List, Tuple

import httpx
from loguru import logger

from app.ingestion.pipeline import ingest_text

DEFAULT_URL = "https://www.fda.gov/media/76860/download?attachment"  # Orange Book Data Files ZIP


async def _fetch_zip(url: str) -> zipfile.ZipFile:
    async with httpx.AsyncClient(timeout=120.0, headers={"User-Agent": "RegView/1.0"}, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content))


def _parse_tilde_file(z: zipfile.ZipFile, name: str) -> List[Dict[str, str]]:
    with z.open(name) as f:
        raw = f.read().decode("utf-8", errors="ignore")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].split("~")]
    rows = []
    for ln in lines[1:]:
        parts = ln.split("~")
        row = {headers[i]: parts[i].strip() if i < len(parts) else "" for i in range(len(headers))}
        rows.append(row)
    return rows


async def ingest_orange_book(query: str, limit: int = 50, url: str = DEFAULT_URL) -> Tuple[int, int]:
    """Download Orange Book, filter products by drug/ingredient name, ingest patents+exclusivity per Appl_No."""
    z = await _fetch_zip(url)
    products, pat_by, ex_by = _load_orange_book(z)

    q = query.lower()
    matched = [
        p for p in products
        if q in p.get("Ingredient", "").lower()
        or q in p.get("Trade_Name", "").lower()
    ][:limit]
    logger.info(f"Orange Book matched {len(matched)} products for '{query}'")
    return _ingest_products(matched, pat_by, ex_by, tag=query)


async def ingest_all_orange_book(url: str = DEFAULT_URL, max_records: int | None = None) -> Tuple[int, int]:
    """Bulk-ingest EVERY product in the FDA Orange Book (~34k rows)."""
    z = await _fetch_zip(url)
    products, pat_by, ex_by = _load_orange_book(z)
    if max_records:
        products = products[:max_records]
    logger.info(f"Orange Book bulk: ingesting {len(products)} products ...")
    return _ingest_products(products, pat_by, ex_by, tag="bulk")


def _load_orange_book(z):
    names = z.namelist()
    prod_name = next((n for n in names if n.lower().endswith("products.txt")), None)
    pat_name = next((n for n in names if n.lower().endswith("patent.txt")), None)
    excl_name = next((n for n in names if n.lower().endswith("exclusivity.txt")), None)
    if not prod_name:
        raise RuntimeError("Orange Book products.txt not found in archive")
    products = _parse_tilde_file(z, prod_name)
    patents = _parse_tilde_file(z, pat_name) if pat_name else []
    excl = _parse_tilde_file(z, excl_name) if excl_name else []
    pat_by: Dict[Tuple[str, str], list] = {}
    for row in patents:
        pat_by.setdefault((row.get("Appl_No", ""), row.get("Product_No", "")), []).append(row)
    ex_by: Dict[Tuple[str, str], list] = {}
    for row in excl:
        ex_by.setdefault((row.get("Appl_No", ""), row.get("Product_No", "")), []).append(row)
    return products, pat_by, ex_by


def _ingest_products(products: List[Dict[str, str]], pat_by: Dict, ex_by: Dict, tag: str) -> Tuple[int, int]:
    docs = 0
    chunks = 0
    for i, p in enumerate(products, start=1):
        appl = p.get("Appl_No", "")
        prod_no = p.get("Product_No", "")
        title = f"Orange Book: {p.get('Trade_Name','')} ({p.get('Ingredient','')}) — {p.get('Strength','')}"
        lines: List[str] = [
            f"Application Type: {p.get('Appl_Type','')}",
            f"Application Number: {appl}",
            f"Product Number: {prod_no}",
            f"Ingredient: {p.get('Ingredient','')}",
            f"Trade Name: {p.get('Trade_Name','')}",
            f"Dosage Form / Route: {p.get('DF;Route','')}",
            f"Strength: {p.get('Strength','')}",
            f"Applicant: {p.get('Applicant','')}",
            f"Approval Date: {p.get('Approval_Date','')}",
            f"Reference Listed Drug: {p.get('RLD','')}",
            f"Reference Standard: {p.get('RS','')}",
            f"TE Code: {p.get('TE_Code','')}",
            f"Marketing Status: {p.get('Type','')}",
        ]
        pats = pat_by.get((appl, prod_no), [])
        if pats:
            lines.append("\nPatents:")
            for pt in pats:
                lines.append(
                    f"- Patent {pt.get('Patent_No','')} expires {pt.get('Patent_Expire_Date_Text','')} "
                    f"(DrugSubstance={pt.get('Drug_Substance_Flag','')}, DrugProduct={pt.get('Drug_Product_Flag','')}, "
                    f"UseCode={pt.get('Patent_Use_Code','')})"
                )
        exs = ex_by.get((appl, prod_no), [])
        if exs:
            lines.append("\nExclusivity:")
            for ex in exs:
                lines.append(f"- {ex.get('Exclusivity_Code','')} expires {ex.get('Exclusivity_Date','')}")
        _, n = ingest_text(
            title=title,
            text="\n".join(lines),
            source="OrangeBook",
            url="https://www.fda.gov/drugs/drug-approvals-and-databases/approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
            doc_type="patent_exclusivity",
            tags=[tag, appl],
            extra_meta={"appl_no": appl, "product_no": prod_no},
        )
        if n:
            docs += 1
            chunks += n
        if i % 1000 == 0:
            logger.info(f"  ... Orange Book: {i} products processed ({docs} indexed, {chunks} chunks)")
    return docs, chunks
