from specguard.config import Settings
from specguard.review import ReviewOrchestrator


def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        demo_password="demo",
        llm_enabled=False,
        llm_base_url="https://example.test/v1",
        llm_api_key="",
        llm_model="test",
        max_document_chars=10_000,
    )


def test_detects_region_fallback_contradiction() -> None:
    document = """
    Шаг 3. Определение региона.
    Находится последняя запись с ненулевыми FIELD_LAC и FIELD_CELL_ID.
    Если lac = 0, выполняется join только по cell_id.
    """
    result = ReviewOrchestrator(settings()).run(document)

    assert result.status == "Не готово"
    assert any(issue.category == "logical_contradiction" for issue in result.issues)


def test_detects_ambiguous_load_strategy() -> None:
    document = """
    Способ загрузки: инкремент.
    Обновление: только полная перезагрузка месяца без upsert.
    """
    result = ReviewOrchestrator(settings()).run(document)

    assert result.status == "Требует уточнения"
    assert any(issue.category == "load_strategy" for issue in result.issues)


def test_clean_short_document_can_be_ready() -> None:
    result = ReviewOrchestrator(settings()).run("Однозначное короткое требование без шаблонов.")
    assert result.status == "Готово к передаче"
    assert result.issues == []
