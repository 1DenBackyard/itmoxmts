from types import SimpleNamespace

import pytest
from conftest import FakeGateway

from specguard.review.fixes import FixResponse, propose_fix


def issue(evidence):
    return SimpleNamespace(
        evidence=evidence, problem="Проблема", recommendation="Уточнить", question="Как?"
    )


def test_fix_is_bound_to_unique_quote_and_does_not_mutate_source():
    source = "Строка\nТип: string\nКонец"
    gateway = FakeGateway(
        FixResponse(
            replacement="Тип: int",
            explanation="По уточнению автора",
            needs_input=False,
            question="",
        )
    )
    result = propose_fix(gateway, source, issue("Тип: string"), "Ожидается int")
    assert result["before"] == "Тип: string"
    assert result["mode"] == "replace"
    assert "Ожидается int" in gateway.calls[0]["user"]
    assert source == "Строка\nТип: string\nКонец"


def test_repeated_quote_needs_manual_selection_without_llm():
    gateway = FakeGateway()
    result = propose_fix(gateway, "id id", issue("id"))
    assert result["needs_input"] and result["mode"] == "manual"
    assert not gateway.calls


def test_missing_data_returns_question_not_invented_value():
    result = propose_fix(
        FakeGateway(
            FixResponse(
                replacement="",
                explanation="Нет имени кластера",
                needs_input=True,
                question="Какой кластер?",
            )
        ),
        "Описание",
        issue("нет"),
    )
    assert result["mode"] == "append"
    assert result["needs_input"] and not result["replacement"]


def test_clarification_never_exposes_a_speculative_replacement():
    result = propose_fix(
        FakeGateway(
            FixResponse(
                replacement="CLUSTER_GUESSED",
                explanation="Данных нет",
                needs_input=True,
                question="",
            )
        ),
        "Описание",
        issue("нет"),
    )
    assert result["needs_input"]
    assert result["replacement"] == ""
    assert result["question"]


def test_empty_success_is_rejected():
    with pytest.raises(ValueError):
        propose_fix(
            FakeGateway(
                FixResponse(replacement="", explanation="test", needs_input=False, question="")
            ),
            "text",
            issue("text"),
        )
