import pytest

from specguard.documents import DocumentExtractionError, extract_text


def test_extract_text_file() -> None:
    text = extract_text("spec.txt", "Техническое задание".encode(), max_chars=100)
    assert text == "Техническое задание"


def test_reject_empty_document() -> None:
    with pytest.raises(DocumentExtractionError, match="не найден текст"):
        extract_text("spec.md", b"   ", max_chars=100)


def test_reject_unsupported_type() -> None:
    with pytest.raises(DocumentExtractionError, match="не поддерживается"):
        extract_text("spec.xlsx", b"data", max_chars=100)
