"""MongoDB data-source connector (pymongo).

Requires `pymongo` — installed on demand:
    pip install pymongo

Config example:
{
  "connection_url": "mongodb://user:pw@host:27017",
  "database": "mydb",
  "collection": "products",
  "filter": {"status": "active"},
  "title_field": "name",
  "text_fields": ["description", "notes"],
  "id_field": "_id",
  "url_field": "detail_url",
  "extra_fields": ["updated_at", "category"],
  "source_label": "mongo_products"
}
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from app.ingestion.sources.base import DataSourceConnector, SourceRecord


class MongoSourceConfig(BaseModel):
    connection_url: str
    database: str
    collection: str
    filter: Dict[str, Any] = Field(default_factory=dict)
    projection: Optional[Dict[str, int]] = None
    title_field: str
    text_fields: List[str] = Field(..., min_length=1)
    id_field: str = "_id"
    url_field: Optional[str] = None
    doc_type_field: Optional[str] = None
    tags_field: Optional[str] = None
    extra_fields: List[str] = Field(default_factory=list)
    source_label: str = "mongo"
    doc_type: Optional[str] = None
    batch_size: int = Field(200, ge=1, le=5000)


class MongoSource(DataSourceConnector):
    name = "mongo"

    def __init__(self, cfg: MongoSourceConfig) -> None:
        self.cfg = cfg

    async def iter_records(self, max_records: int) -> AsyncIterator[SourceRecord]:
        try:
            from pymongo import MongoClient
        except ImportError as e:
            raise RuntimeError(
                "MongoDB connector requires the 'pymongo' package. Install with `pip install pymongo`."
            ) from e

        cfg = self.cfg
        client = MongoClient(cfg.connection_url, serverSelectionTimeoutMS=10_000)
        try:
            coll = client[cfg.database][cfg.collection]
            cursor = coll.find(cfg.filter or {}, projection=cfg.projection, batch_size=cfg.batch_size).limit(
                max_records
            )
            for doc in cursor:
                rec = self._doc_to_record(doc)
                if rec:
                    yield rec
        finally:
            client.close()

    def _doc_to_record(self, doc: Dict[str, Any]) -> Optional[SourceRecord]:
        cfg = self.cfg
        title = str(_get_nested(doc, cfg.title_field) or "").strip() or f"{cfg.source_label} doc"

        parts: List[str] = []
        for f in cfg.text_fields:
            v = _get_nested(doc, f)
            if v in (None, "", [], {}):
                continue
            parts.append(f"{f}: {v}")
        text_body = "\n".join(parts).strip()
        if not text_body:
            return None

        url = None
        if cfg.url_field:
            u = _get_nested(doc, cfg.url_field)
            if u:
                url = str(u)
        else:
            _id = _get_nested(doc, cfg.id_field)
            if _id is not None:
                url = f"mongo://{cfg.database}.{cfg.collection}#{_id}"

        doc_type = cfg.doc_type
        if cfg.doc_type_field:
            dt = _get_nested(doc, cfg.doc_type_field)
            if dt:
                doc_type = str(dt)

        tags: Optional[List[str]] = None
        if cfg.tags_field:
            raw = _get_nested(doc, cfg.tags_field)
            if isinstance(raw, (list, tuple, set)):
                tags = [str(t) for t in raw if t]
            elif isinstance(raw, str):
                tags = [t.strip() for t in raw.split(",") if t.strip()]

        extra: Dict[str, Any] = {}
        for f in cfg.extra_fields:
            v = _get_nested(doc, f)
            if v is not None:
                extra[f] = _jsonable(v)
        _id = _get_nested(doc, cfg.id_field)
        if _id is not None:
            extra["doc_id_source"] = str(_id)

        return SourceRecord(
            title=title,
            text=text_body,
            source=cfg.source_label,
            url=url,
            doc_type=doc_type,
            tags=tags,
            extra_meta=extra,
        )


def _get_nested(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _jsonable(v: Any) -> Any:
    import datetime as _dt
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(val) for k, val in v.items()}
    return str(v)
