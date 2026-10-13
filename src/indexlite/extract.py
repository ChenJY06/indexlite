from pathlib import Path

from .models import IndexLiteError

SUPPORTED = {".txt", ".md", ".pdf"}


def extract_text(path: Path) -> str:
    try:
        if path.suffix.lower() in {".txt", ".md"}:
            return path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise IndexLiteError("PDF support requires: pip install 'indexlite[pdf]'") from exc
            reader = PdfReader(path, strict=True)
            if reader.is_encrypted and not reader.decrypt(""):
                raise IndexLiteError("encrypted PDF requires a password; decrypt it first")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not text.strip():
                raise IndexLiteError("PDF has no extractable text; OCR is outside version one")
            return text
        raise IndexLiteError(f"unsupported extension: {path.suffix or '(none)'}")
    except IndexLiteError:
        raise
    except Exception as exc:
        raise IndexLiteError(f"cannot extract {path.name}: {type(exc).__name__}: {exc}") from exc


def document_title(text: str, path: str) -> str:
    for line in text.splitlines():
        title = line.strip().lstrip("#").strip()
        if title:
            return title[:120]
    return Path(path).stem
