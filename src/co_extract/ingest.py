"""Safe PDF/image/plain-text ingestion with optional per-page OCR fallback."""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from pathlib import Path

import fitz
from pydantic import BaseModel, Field


class IngestError(Exception):
    """Base class for typed input errors."""


class CorruptDocument(IngestError):
    """The file cannot be decoded safely."""


class EncryptedDocument(IngestError):
    """Password-protected PDFs are not silently ignored."""


class EmptyDocument(IngestError):
    """There is no readable content."""


class Page(BaseModel):
    num: int
    text: str
    tables: list[str] = Field(default_factory=list)
    source: str = "text"


class Document(BaseModel):
    pages: list[Page]
    source_hash: str
    path: str


def _clean(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\x00", "")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()).strip()


def _ocr(image) -> str:
    try:
        import pytesseract
        return _clean(pytesseract.image_to_string(image, config="--psm 6"))
    except (ImportError, OSError, RuntimeError, Exception) as exc:
        raise CorruptDocument(f"OCR unavailable or failed: {type(exc).__name__}") from exc


def load_document(path: str | Path) -> Document:
    """Decode supported formats; fail explicitly for undecodable content."""
    target = Path(path)
    ext = target.suffix.lower()
    if ext not in {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png"}:
        raise CorruptDocument(f"Unsupported file type: {ext}")
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise CorruptDocument(str(exc)) from exc
    if len(raw) > 30 * 1024 * 1024:
        raise CorruptDocument("File exceeds the 30 MB safety limit")
    source_hash = hashlib.sha256(raw).hexdigest()
    pages: list[Page] = []
    if ext in {".txt", ".md"}:
        try:
            pages = [Page(num=i+1, text=_clean(s)) for i, s in enumerate(raw.decode("utf-8-sig").split("\f"))]
        except UnicodeError as exc:
            raise CorruptDocument("Input is not UTF-8") from exc
    elif ext == ".pdf":
        try:
            import pdfplumber
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise EncryptedDocument("Encrypted PDF requires password")
                if pdf.page_count > 150:
                    raise CorruptDocument("PDF exceeds the 150-page safety limit")
                with pdfplumber.open(io.BytesIO(raw)) as parsed:
                    for idx, page in enumerate(pdf):
                        page_text = _clean(page.get_text(sort=True))
                        tables = []
                        for table in parsed.pages[idx].extract_tables() or []:
                            if table:
                                tables.append("\n".join(" | ".join(str(v or "") for v in row) for row in table))
                        noisy = sum(ch.isalnum() for ch in page_text) < 20
                        source = "text"
                        if noisy:
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                            from PIL import Image
                            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                            try:
                                page_text = _ocr(img)
                                source = "ocr"
                            except CorruptDocument:
                                source = "ocr"
                        pages.append(Page(num=idx+1, text=page_text, tables=tables, source=source))
        except EncryptedDocument:
            raise
        except (fitz.FileDataError, ValueError, OSError) as exc:
            raise CorruptDocument(f"Unreadable PDF: {type(exc).__name__}") from exc
    else:
        try:
            from PIL import Image, UnidentifiedImageError
            with Image.open(io.BytesIO(raw)) as img:
                img.verify()
            with Image.open(io.BytesIO(raw)) as img:
                page_text = _ocr(img.convert("RGB"))
            pages = [Page(num=1, text=page_text, source="ocr")]
        except (OSError, UnidentifiedImageError) as exc:
            raise CorruptDocument("Unreadable image") from exc
    if not pages or not any(page.text.strip() for page in pages):
        raise EmptyDocument("No extractable text or OCR output")
    return Document(pages=pages, source_hash=source_hash, path=str(target))
