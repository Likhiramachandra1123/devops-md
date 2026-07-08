"""S3 / S3-compatible (MinIO, R2, etc.) data-source connector.

Requires `boto3` — installed on demand:
    pip install boto3

Config example:
{
  "bucket": "my-regulatory-docs",
  "prefix": "guidance/2025/",
  "endpoint_url": null,                    // set for MinIO / R2 / non-AWS S3
  "region_name": "us-east-1",
  "aws_access_key_id": "...",              // omit to use ambient AWS creds
  "aws_secret_access_key": "...",
  "extensions": [".pdf", ".txt", ".md", ".html", ".htm", ".docx"],
  "source_label": "s3_regulatory_docs",
  "doc_type": "guidance"
}
"""
from __future__ import annotations

import io
import os
from pathlib import PurePosixPath
from typing import AsyncIterator, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from app.ingestion.loaders import load_docx, load_html, load_pdf, load_txt
from app.ingestion.sources.base import DataSourceConnector, SourceRecord


DEFAULT_EXTS = [".pdf", ".txt", ".md", ".html", ".htm", ".docx"]


class S3SourceConfig(BaseModel):
    bucket: str
    prefix: str = ""
    endpoint_url: Optional[str] = Field(None, description="Set for S3-compatible services like MinIO or R2.")
    region_name: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    extensions: List[str] = Field(default_factory=lambda: DEFAULT_EXTS)
    source_label: str = "s3"
    doc_type: Optional[str] = None
    max_object_bytes: int = Field(20 * 1024 * 1024, description="Skip objects larger than this.")


class S3Source(DataSourceConnector):
    name = "s3"

    def __init__(self, cfg: S3SourceConfig) -> None:
        self.cfg = cfg

    async def iter_records(self, max_records: int) -> AsyncIterator[SourceRecord]:
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as e:
            raise RuntimeError(
                "S3 connector requires 'boto3'. Install with `pip install boto3`."
            ) from e

        cfg = self.cfg
        allowed_exts = {e.lower() for e in (cfg.extensions or DEFAULT_EXTS)}
        client_kwargs = {}
        if cfg.endpoint_url:
            client_kwargs["endpoint_url"] = cfg.endpoint_url
        if cfg.region_name:
            client_kwargs["region_name"] = cfg.region_name
        if cfg.aws_access_key_id:
            client_kwargs["aws_access_key_id"] = cfg.aws_access_key_id
        if cfg.aws_secret_access_key:
            client_kwargs["aws_secret_access_key"] = cfg.aws_secret_access_key
        if cfg.aws_session_token:
            client_kwargs["aws_session_token"] = cfg.aws_session_token

        client = boto3.client("s3", **client_kwargs)
        paginator = client.get_paginator("list_objects_v2")
        yielded = 0
        try:
            for page in paginator.paginate(Bucket=cfg.bucket, Prefix=cfg.prefix or ""):
                for obj in page.get("Contents", []) or []:
                    if yielded >= max_records:
                        return
                    key: str = obj["Key"]
                    size = int(obj.get("Size", 0))
                    ext = PurePosixPath(key).suffix.lower()
                    if allowed_exts and ext not in allowed_exts:
                        continue
                    if size <= 0 or size > cfg.max_object_bytes:
                        continue
                    try:
                        resp = client.get_object(Bucket=cfg.bucket, Key=key)
                        raw = resp["Body"].read()
                    except (BotoCoreError, ClientError) as e:
                        logger.warning(f"S3 get {key} failed: {e}")
                        continue

                    text = _extract(raw, ext)
                    if not text.strip():
                        continue

                    title = PurePosixPath(key).stem or key
                    endpoint = cfg.endpoint_url or "https://s3.amazonaws.com"
                    url = f"{endpoint.rstrip('/')}/{cfg.bucket}/{key}"
                    yielded += 1
                    yield SourceRecord(
                        title=title,
                        text=text,
                        source=cfg.source_label,
                        url=url,
                        doc_type=cfg.doc_type or ext.lstrip("."),
                        extra_meta={
                            "s3_bucket": cfg.bucket,
                            "s3_key": key,
                            "size_bytes": size,
                            "content_type": resp.get("ContentType", ""),
                        },
                    )
        finally:
            # boto3 clients don't need explicit close but be tidy
            del client


def _extract(raw: bytes, ext: str) -> str:
    if ext == ".pdf":
        return load_pdf(raw)
    if ext == ".docx":
        return load_docx(raw)
    if ext in (".html", ".htm"):
        return load_html(raw)
    # .txt, .md, and anything else → treat as text
    return load_txt(raw)
