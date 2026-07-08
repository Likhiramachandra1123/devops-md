"""Pluggable data-source ingestion connectors.

Each connector yields SourceRecord objects that the runner feeds into the
existing `ingest_text` pipeline (chunk → embed → vector store).
"""
from app.ingestion.sources.base import DataSourceConnector, SourceRecord, run_source
from app.ingestion.sources.registry import build_connector

__all__ = ["DataSourceConnector", "SourceRecord", "run_source", "build_connector"]
