import pytest
from conftest import FakeGateway, make_issue, make_settings

from specguard.review import prompts
from specguard.review.llm import (
    REVIEWER_ROLES,
    CloudRuEvidenceCritic,
    CloudRuIssueJudge,
    CloudRuLLMReviewer,
    cloud_control_agents,
    cloud_reviewers,
)
from specguard.review.schemas import CriticResponse, JudgeResponse, Severity

DOCUMENT = "Способ загрузки: инкремент. Обновление: только полная перезагрузка месяца."


def test_every_reviewer_role_has_prompt() -> None:
    for role in REVIEWER_ROLES:
        prompt = prompts.reviewer_system_prompt(role)
        assert prompts.SHARED_REVIEWER_RULES in prompt
        assert prompts.ROLE_BRIEFS[role] in prompt
        assert prompts.CASEHOLDER_GUIDANCE in prompt


def test_reviewer_prompts_are_distinct() -> None:
    rendered = {role: prompts.reviewer_system_prompt(role) for role in REVIEWER_ROLES}
    assert len(set(rendered.values())) == len(REVIEWER_ROLES)


def test_critic_uses_caseholder_requirements() -> None:
    assert prompts.CASEHOLDER_GUIDANCE in prompts.CRITIC_SYSTEM_PROMPT
    assert "разделы не удаляются" in prompts.CASEHOLDER_GUIDANCE
    assert "10 строк" in prompts.CASEHOLDER_GUIDANCE


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(KeyError):
        prompts.reviewer_system_prompt("Дизайнер")


def test_reviewer_stamps_own_name_on_issues() -> None:
    gateway = FakeGateway(type("R", (), {"issues": [make_issue(agent="подменённое имя")]})())
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

    kept = critic.screen(DOCUMENT, [make_issue(), make_issue(category="missing_data_volume")])

    assert [item.category for item in kept] == ["load_strategy"]
    assert kept[0].confidence == pytest.approx(0.72)


def test_critic_reports_incomplete_verdicts() -> None:
    gateway = FakeGateway(CriticResponse(verdicts=[]))

    with pytest.raises(ValueError, match="ровно один"):
        CloudRuEvidenceCritic(gateway).screen(DOCUMENT, [make_issue()])


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

    kept = CloudRuIssueJudge(gateway).arbitrate(
        [make_issue(), make_issue(agent="LLM · Архитектор")]
    )

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
        [make_issue(severity=Severity.BLOCKER), make_issue(category="missing_data_volume")]
    )

    assert {item.severity for item in kept} == {Severity.BLOCKER, Severity.MINOR}


def test_control_agents_follow_settings() -> None:
    assert cloud_control_agents(make_settings()) == (None, None)
    assert cloud_reviewers(make_settings()) == []

    enabled = make_settings(llm_enabled=True, llm_api_key="key")
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
        make_settings(llm_enabled=True, llm_api_key="key", llm_control_enabled=False)
    ) == (None, None)
