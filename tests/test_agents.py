import pytest

from specguard.config import Settings
from specguard.review import prompts
from specguard.review.llm import (
    REVIEWER_ROLES,
    CloudRuEvidenceCritic,
    CloudRuIssueJudge,
    CloudRuLLMReviewer,
    cloud_control_agents,
    cloud_reviewers,
)
from specguard.review.pipeline import ReviewOrchestrator
from specguard.review.schemas import (
    CriticResponse,
    Evidence,
    JudgeResponse,
    ReviewIssue,
    Severity,
)

DOCUMENT = "Способ загрузки: инкремент. Обновление: только полная перезагрузка месяца."


def settings(**overrides: object) -> Settings:
    base = {
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
    """Подменяет вызов модели заранее заданными ответами."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def structured(self, *, system: str, user: str, schema_name: str, schema: type) -> object:
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def issue(**overrides: object) -> ReviewIssue:
    payload = {
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


def test_every_reviewer_role_has_prompt() -> None:
    for role in REVIEWER_ROLES:
        prompt = prompts.reviewer_system_prompt(role)
        assert prompts.SHARED_REVIEWER_RULES in prompt
        assert prompts.ROLE_BRIEFS[role] in prompt


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(KeyError):
        prompts.reviewer_system_prompt("Дизайнер")


def test_reviewer_stamps_own_name_on_issues() -> None:
    gateway = FakeGateway(type("R", (), {"issues": [issue(agent="подменённое имя")]})())
    reviewer = CloudRuLLMReviewer(prompts.QA, gateway)

    result = reviewer.review(DOCUMENT)

    assert reviewer.name == "LLM · QA"
    assert [item.agent for item in result] == ["LLM · QA"]
    assert gateway.calls[0]["system"] == prompts.reviewer_system_prompt(prompts.QA)


def test_critic_drops_rejected_and_scales_confidence() -> None:
    gateway = FakeGateway(
        CriticResponse.model_validate(
            {
                "verdicts": [
                    {
                        "issue_id": "i1",
                        "verdict": "confirmed",
                        "reason": "Оба условия процитированы.",
                        "confidence": 0.8,
                    },
                    {
                        "issue_id": "i2",
                        "verdict": "rejected",
                        "reason": "Требование уже описано в разделе 4.",
                        "confidence": 0.9,
                    },
                ]
            }
        )
    )
    critic = CloudRuEvidenceCritic(gateway)

    kept = critic.screen(DOCUMENT, [issue(), issue(category="missing_data_volume")])

    assert [item.category for item in kept] == ["load_strategy"]
    assert kept[0].confidence == pytest.approx(0.72)


def test_critic_keeps_issue_missing_from_verdicts() -> None:
    gateway = FakeGateway(CriticResponse(verdicts=[]))

    kept = CloudRuEvidenceCritic(gateway).screen(DOCUMENT, [issue()])

    assert len(kept) == 1


def test_judge_merges_duplicates_and_reassigns_severity() -> None:
    gateway = FakeGateway(
        JudgeResponse.model_validate(
            {
                "decisions": [
                    {
                        "issue_id": "i1",
                        "keep": True,
                        "severity": "blocker",
                        "duplicate_of": "",
                        "reason": "Реализация невозможна.",
                    },
                    {
                        "issue_id": "i2",
                        "keep": False,
                        "severity": "major",
                        "duplicate_of": "i1",
                        "reason": "Тот же дефект другими словами.",
                    },
                ]
            }
        )
    )

    kept = CloudRuIssueJudge(gateway).arbitrate([issue(), issue(agent="LLM · Архитектор")])

    assert len(kept) == 1
    assert kept[0].severity is Severity.BLOCKER


def test_judge_never_silently_drops_blocker() -> None:
    gateway = FakeGateway(
        JudgeResponse.model_validate(
            {
                "decisions": [
                    {
                        "issue_id": "i1",
                        "keep": False,
                        "severity": "blocker",
                        "duplicate_of": "",
                        "reason": "Менее значимо.",
                    },
                    {
                        "issue_id": "i2",
                        "keep": True,
                        "severity": "minor",
                        "duplicate_of": "",
                        "reason": "Оставляем.",
                    },
                ]
            }
        )
    )

    kept = CloudRuIssueJudge(gateway).arbitrate(
        [issue(severity=Severity.BLOCKER), issue(category="missing_data_volume")]
    )

    assert {item.severity for item in kept} == {Severity.BLOCKER, Severity.MINOR}


def test_control_agents_follow_settings() -> None:
    assert cloud_control_agents(settings()) == (None, None)
    assert cloud_reviewers(settings()) == []

    enabled = settings(llm_enabled=True, llm_api_key="key")
    critic, judge = cloud_control_agents(enabled)
    assert isinstance(critic, CloudRuEvidenceCritic)
    assert isinstance(judge, CloudRuIssueJudge)
    assert [reviewer.name for reviewer in cloud_reviewers(enabled)] == [
        "LLM · Аналитик",
        "LLM · Data Engineer",
        "LLM · Архитектор",
        "LLM · QA",
    ]

    assert cloud_control_agents(
        settings(llm_enabled=True, llm_api_key="key", llm_control_enabled=False)
    ) == (None, None)


def test_orchestrator_degrades_when_control_agents_fail() -> None:
    document = """
    Способ загрузки: инкремент.
    Обновление: только полная перезагрузка месяца без upsert.
    """
    orchestrator = ReviewOrchestrator(
        settings(),
        llm_critic=CloudRuEvidenceCritic(FakeGateway(RuntimeError("timeout"))),
        llm_judge=CloudRuIssueJudge(FakeGateway(RuntimeError("timeout"))),
    )

    result = orchestrator.run(document)

    assert any(issue.category == "load_strategy" for issue in result.issues)
    assert any("перепроверка недоступна" in warning for warning in result.warnings)
