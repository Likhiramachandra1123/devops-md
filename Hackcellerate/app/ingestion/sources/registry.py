"""Factory that instantiates the right connector from a JSON config."""
from __future__ import annotations

from typing import Any, Dict, Literal

from app.ingestion.sources.base import DataSourceConnector
from app.ingestion.sources.mongo import MongoSource, MongoSourceConfig
from app.ingestion.sources.s3 import S3Source, S3SourceConfig
from app.ingestion.sources.sql import SQLSource, SQLSourceConfig


ConnectorType = Literal["sql", "mongo", "s3"]


def build_connector(kind: str, config: Dict[str, Any]) -> DataSourceConnector:
    kind = (kind or "").lower().strip()
    if kind == "sql":
        return SQLSource(SQLSourceConfig(**config))
    if kind == "mongo":
        return MongoSource(MongoSourceConfig(**config))
    if kind == "s3":
        return S3Source(S3SourceConfig(**config))
    raise ValueError(f"Unknown source type: '{kind}'. Supported: sql, mongo, s3.")
