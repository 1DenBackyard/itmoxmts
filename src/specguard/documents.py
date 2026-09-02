from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader


class DocumentExtractionError(ValueError):
    """Raised when an uploaded document cannot be converted to text."""


def extract_text(filename: str, content: bytes, *, max_chars: int) -> str:
    suffix = Path(filename).suffix.lower()

    try:
        if suffix == ".pdf":
            reader = PdfReader(BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            document = Document(BytesIO(content))
            paragraphs = [paragraph.text for paragraph in document.paragraphs]
            tables = [
                "\n".join(" | ".join(cell.text for cell in row.cells) for row in table.rows)
                for table in document.tables
            ]
            text = "\n".join([*paragraphs, *tables])
        elif suffix in {".txt", ".md"}:
            text = content.decode("utf-8-sig")
        else:
            raise DocumentExtractionError(f"Формат {suffix or 'без расширения'} не поддерживается")
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError("Не удалось прочитать документ") from exc

    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not normalized:
        raise DocumentExtractionError("В документе не найден текст")
    if len(normalized) > max_chars:
        raise DocumentExtractionError(f"Документ превышает лимит MVP: {max_chars:,} символов")
    return normalized
