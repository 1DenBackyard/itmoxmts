from __future__ import annotations

from specguard.config import Settings
from specguard.review.schemas import Evidence, ReviewIssue, Severity


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite:///:memory:",
        "demo_password": "demo",
        "llm_enabled": False,
        "llm_base_url": "https://example.test/v1",
        "llm_api_key": "",
        "llm_model": "test",
        "max_document_chars": 10_000,
    }
    base.update(overrides)
    return Settings(**base)


class FakeGateway:
    """Подменяет LLMGateway.structured заранее заданными ответами, в порядке вызова."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def structured(
        self, *, system: str, user: str, schema_name: str, schema: type, validate=None
    ) -> object:
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if validate:
            validate(response)
        return response


def make_issue(**overrides: object) -> ReviewIssue:
    payload: dict[str, object] = {
        "agent": "LLM · Аналитик",
        "category": "load_strategy",
        "severity": Severity.MAJOR,
        "title": "Неоднозначная стратегия загрузки",
        "evidence": [Evidence(quote="Способ загрузки: инкремент.")],
        "problem": "Инкремент и полная перезагрузка описаны одновременно.",
        "impact": "Реализация может отличаться от ожидаемой.",
        "question": "Что перезагружается при повторном запуске?",
        "recommendation": "Описать initial load, инкремент и rerun.",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return ReviewIssue(**payload)
