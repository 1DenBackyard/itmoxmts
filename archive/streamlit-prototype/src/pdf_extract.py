from __future__ import annotations

from pathlib import Path
from typing import Union


def extract_text_from_pdf(source: Union[str, Path, bytes]) -> str:
    """Извлечение текста PDF через pypdfium2 (кириллица ок)."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "Нужен пакет pypdfium2. Установите зависимости из requirements.txt"
        ) from exc

    if isinstance(source, (bytes, bytearray)):
        pdf = pdfium.PdfDocument(source)
    else:
        pdf = pdfium.PdfDocument(str(source))

    parts = []
    for i in range(len(pdf)):
        page = pdf[i]
        textpage = page.get_textpage()
        parts.append(textpage.get_text_bounded() or "")
    return "\n\n".join(parts).strip()


def extract_text(filename: str, raw: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(raw)
    if lower.endswith((".txt", ".md", ".csv")):
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")
    # fallback
    try:
        return extract_text_from_pdf(raw)
    except Exception:
        return raw.decode("utf-8", errors="ignore")
