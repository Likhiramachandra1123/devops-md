"""Base classes for pluggable ingestion connectors."""
from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from loguru import logger

from app.ingestion.pipeline import ingest_text


@dataclass
class SourceRecord:
    """One logical document pulled from an external source."""
    title: str
    text: str
    source: str
    url: Optional[str] = None
    doc_type: Optional[str] = None
    tags: Optional[List[str]] = None
    extra_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestSummary:
    total_records_seen: int = 0
    total_records_ingested: int = 0
    total_chunks: int = 0
    doc_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class DataSourceConnector(abc.ABC):
    """Abstract base — subclass this to add a new source."""

    #: Short id used by the registry / API. Override in subclasses.
    name: str = "base"

    @abc.abstractmethod
    async def iter_records(self, max_records: int) -> AsyncIterator[SourceRecord]:
        """Yield records lazily, up to max_records."""
        raise NotImplementedError


async def run_source(
    connector: DataSourceConnector,
    max_records: int = 100,
    extra_tags: Optional[List[str]] = None,
) -> IngestSummary:
    """Iterate a connector and ingest every record via the standard pipeline."""
    summary = IngestSummary()
    async for rec in connector.iter_records(max_records=max_records):
        summary.total_records_seen += 1
        text = (rec.text or "").strip()
        if not text:
            continue
        merged_tags: Optional[List[str]] = None
        if rec.tags and extra_tags:
            merged_tags = list(dict.fromkeys([*rec.tags, *extra_tags]))
        elif rec.tags:
            merged_tags = rec.tags
        elif extra_tags:
            merged_tags = extra_tags
        try:
            doc_id, n = await asyncio.to_thread(
                ingest_text,
                rec.title,
                text,
                rec.source,
                rec.url,
                rec.doc_type,
                merged_tags,
                rec.extra_meta or None,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[{connector.name}] ingest failed for '{rec.title[:60]}'")
            summary.errors.append(f"{rec.title[:60]}: {e}")
            continue
        if n:
            summary.total_records_ingested += 1
            summary.total_chunks += n
            summary.doc_ids.append(doc_id)
    logger.info(
        f"[{connector.name}] done: seen={summary.total_records_seen} "
        f"ingested={summary.total_records_ingested} chunks={summary.total_chunks} "
        f"errors={len(summary.errors)}"
    )
    return summary
