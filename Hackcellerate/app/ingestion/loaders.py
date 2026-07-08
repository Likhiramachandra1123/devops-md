"""Text/PDF/HTML/DOCX loaders."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Tuple

import httpx
from bs4 import BeautifulSoup
from loguru import logger


def load_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:  # pragma: no cover
            logger.warning(f"PDF page extraction failed: {e}")
    return _clean("\n\n".join(parts))


def load_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return _clean("\n".join(p.text for p in doc.paragraphs))


def load_html(data: bytes | str) -> str:
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8", errors="ignore")
        except Exception:
            data = data.decode("latin-1", errors="ignore")
    soup = BeautifulSoup(data, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _clean(text)


def load_txt(data: bytes) -> str:
    return _clean(data.decode("utf-8", errors="ignore"))


def load_file(path: Path) -> Tuple[str, str]:
    """Return (title, text) from a local file."""
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".pdf":
        text = load_pdf(raw)
    elif suffix in (".docx",):
        text = load_docx(raw)
    elif suffix in (".html", ".htm"):
        text = load_html(raw)
    elif suffix in (".txt", ".md"):
        text = load_txt(raw)
    else:
        # Try as text
        text = load_txt(raw)
    return path.stem, text


async def load_url(url: str, timeout: float = 30.0) -> Tuple[str, str]:
    """Fetch a URL and return (title, text)."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": "RegView/1.0"}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()
        content = resp.content
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            text = load_pdf(content)
            title = url.rsplit("/", 1)[-1]
        elif "html" in ctype or "xml" in ctype or not ctype:
            soup = BeautifulSoup(content, "lxml")
            title = (soup.title.string.strip() if soup.title and soup.title.string else url)
            text = load_html(content)
        elif "json" in ctype:
            text = _clean(content.decode("utf-8", errors="ignore"))
            title = url
        else:
            text = load_txt(content)
            title = url
    return title, text


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
