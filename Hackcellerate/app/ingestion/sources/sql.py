"""SQL data-source connector via SQLAlchemy.

Works with any SQLAlchemy-supported DB (Postgres, MySQL, SQLite, SQL Server,
Oracle, etc.) provided the driver is installed.

Config example:
{
  "connection_url": "postgresql+psycopg://user:pw@host:5432/db",
  "query": "SELECT id, name, description, updated_at, url FROM products",
  "id_column": "id",
  "title_column": "name",
  "text_columns": ["description"],
  "url_column": "url",
  "extra_columns": ["updated_at"],
  "source_label": "products_db",
  "doc_type": "product_record"
}
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from app.ingestion.sources.base import DataSourceConnector, SourceRecord


class SQLSourceConfig(BaseModel):
    connection_url: str = Field(..., description="SQLAlchemy URL, e.g. 'postgresql+psycopg://...'.")
    query: str = Field(..., description="Read-only SELECT statement.")
    id_column: Optional[str] = Field(None, description="Column that uniquely identifies a row (used for url).")
    title_column: str = Field(..., description="Column used as the document title.")
    text_columns: List[str] = Field(..., min_length=1, description="Columns concatenated to form the doc body.")
    url_column: Optional[str] = None
    doc_type_column: Optional[str] = Field(None, description="Column whose value becomes doc_type per row.")
    tags_column: Optional[str] = Field(None, description="Column holding a CSV or list of tags.")
    extra_columns: List[str] = Field(default_factory=list, description="Extra columns stored in metadata.")
    source_label: str = Field("sql", description="Logical source name.")
    doc_type: Optional[str] = None
    fetch_size: int = Field(500, ge=1, le=10000, description="Stream chunk size for the cursor.")


class SQLSource(DataSourceConnector):
    name = "sql"

    def __init__(self, cfg: SQLSourceConfig) -> None:
        self.cfg = cfg

    async def iter_records(self, max_records: int) -> AsyncIterator[SourceRecord]:
        from sqlalchemy import create_engine, text

        cfg = self.cfg
        engine = create_engine(cfg.connection_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                # Server-side cursor for large tables where the driver supports it.
                try:
                    result = conn.execution_options(stream_results=True).execute(text(cfg.query))
                except Exception:  # noqa: BLE001
                    result = conn.execute(text(cfg.query))

                yielded = 0
                for row in result:
                    if yielded >= max_records:
                        break
                    d = dict(row._mapping)
                    rec = self._row_to_record(d)
                    if rec:
                        yielded += 1
                        yield rec
        finally:
            engine.dispose()

    def _row_to_record(self, row: Dict[str, Any]) -> Optional[SourceRecord]:
        cfg = self.cfg
        title = str(row.get(cfg.title_column) or "").strip()
        if not title:
            title = f"{cfg.source_label} row"

        parts: List[str] = []
        for col in cfg.text_columns:
            v = row.get(col)
            if v is None:
                continue
            parts.append(f"{col}: {v}")
        text_body = "\n".join(parts).strip()
        if not text_body:
            return None

        url = None
        if cfg.url_column:
            u = row.get(cfg.url_column)
            if u:
                url = str(u)
        elif cfg.id_column:
            rid = row.get(cfg.id_column)
            if rid is not None:
                url = f"sql://{cfg.source_label}#{rid}"

        doc_type = cfg.doc_type
        if cfg.doc_type_column and row.get(cfg.doc_type_column):
            doc_type = str(row[cfg.doc_type_column])

        tags: Optional[List[str]] = None
        if cfg.tags_column and row.get(cfg.tags_column) is not None:
            raw = row[cfg.tags_column]
            if isinstance(raw, (list, tuple, set)):
                tags = [str(t) for t in raw if t]
            elif isinstance(raw, str):
                tags = [t.strip() for t in raw.split(",") if t.strip()]

        extra: Dict[str, Any] = {}
        for col in cfg.extra_columns:
            if col in row and row[col] is not None:
                extra[col] = _jsonable(row[col])
        if cfg.id_column and cfg.id_column in row:
            extra["row_id"] = _jsonable(row[cfg.id_column])

        return SourceRecord(
            title=title,
            text=text_body,
            source=cfg.source_label,
            url=url,
            doc_type=doc_type,
            tags=tags,
            extra_meta=extra,
        )


def _jsonable(v: Any) -> Any:
    import datetime as _dt
    from decimal import Decimal
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    return str(v)
