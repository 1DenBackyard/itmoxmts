from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import pdfplumber
from docx import Document
from docx.table import Table

# Имя поля или тип данных не содержит пробелов. Если после склейки ячейка выглядит
# именно так, пробелы в ней пришли от переноса строки внутри ячейки PDF
# ("FIELD_REGION_NA ME", "timesta mp") и их нужно убрать.
_IDENTIFIER = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|[a-z]+\(\d+(?:,\d+)?\))$")


def _cell_text(cell: str | None) -> str:
    text = " ".join((cell or "").split()).replace("|", "¦")
    joined = text.replace(" ", "")
    return joined if text != joined and _IDENTIFIER.match(joined) else text


def _table_text(rows: list[list[str | None]]) -> str:
    # Таблица из одной колонки — это врезка или заголовок в рамке, а не данные:
    # разметка пайпами превратила бы её в фальшивую строку таблицы.
    if all(len(row) < 2 for row in rows):
        return "\n".join(filter(None, (_cell_text(row[0] if row else None) for row in rows)))
    return "\n".join("| " + " | ".join(_cell_text(cell) for cell in row) + " |" for row in rows)


def _pdf_text(content: bytes) -> str:
    pages = []
    with pdfplumber.open(BytesIO(content)) as document:
        for page in document.pages:
            tables = page.find_tables()
            blocks = []
            for table in tables:
                blocks.append((table.bbox[1], _table_text(table.extract())))

            def outside_tables(obj):
                x = (obj.get("x0", 0) + obj.get("x1", 0)) / 2
                y = (obj.get("top", 0) + obj.get("bottom", 0)) / 2
                return not any(
                    t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3] for t in tables
                )

            for line in page.filter(outside_tables).extract_text_lines():
                blocks.append((line["top"], line["text"]))
            pages.append("\n".join(text for _, text in sorted(blocks, key=lambda b: b[0])))
            page.close()
    return "\n\n".join(pages)


class DocumentExtractionError(ValueError):
    """Raised when an uploaded document cannot be converted to text."""


def extract_text(filename: str, content: bytes, *, max_chars: int) -> str:
    suffix = Path(filename).suffix.lower()

    try:
        if suffix == ".pdf":
            text = _pdf_text(content)
        elif suffix == ".docx":
            document = Document(BytesIO(content))
            text = "\n\n".join(
                _table_text([[cell.text for cell in row.cells] for row in block.rows])
                if isinstance(block, Table)
                else block.text
                for block in document.iter_inner_content()
            )
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
