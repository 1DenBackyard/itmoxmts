from conftest import FakeGateway, make_issue, make_settings

from specguard.review.llm import CloudRuEvidenceCritic, CloudRuIssueJudge, CloudRuLLMReviewer
from specguard.review.pipeline import ReviewOrchestrator
from specguard.review.schemas import (
    AgentResponse,
    CriticResponse,
    JudgeResponse,
    ReviewIssue,
    Severity,
)

DOCUMENT = """
Способ загрузки: инкремент.
Обновление: только полная перезагрузка месяца без upsert.
"""


def reviewer_returning(issue: ReviewIssue) -> CloudRuLLMReviewer:
    gateway = FakeGateway(AgentResponse(issues=[issue]))
    return CloudRuLLMReviewer("Аналитик", gateway)


def test_no_reviewers_means_no_review_without_failing() -> None:
    result = ReviewOrchestrator(make_settings(), reviewers=[]).run(DOCUMENT)

    assert result.status == "Готово к передаче"
    assert result.issues == []
    assert any("не настроены" in warning for warning in result.warnings)


def test_status_reflects_worst_confirmed_severity() -> None:
    reviewer = reviewer_returning(make_issue(severity=Severity.BLOCKER))

    result = ReviewOrchestrator(make_settings(), reviewers=[reviewer]).run(DOCUMENT)

    assert result.status == "Не готово"
    assert len(result.issues) == 1
    assert result.issues[0].severity is Severity.BLOCKER


def test_clean_document_with_no_findings_is_ready() -> None:
    gateway = FakeGateway(AgentResponse(issues=[]))
    reviewer = CloudRuLLMReviewer("Аналитик", gateway)

    result = ReviewOrchestrator(make_settings(), reviewers=[reviewer]).run(DOCUMENT)

    assert result.status == "Готово к передаче"
    assert result.issues == []


def test_reviewer_failure_is_reported_as_warning_and_others_still_run() -> None:
    failing_gateway = FakeGateway(RuntimeError("недоступна модель"))
    failing_reviewer = CloudRuLLMReviewer("Архитектор", failing_gateway)
    ok_reviewer = reviewer_returning(make_issue())

    result = ReviewOrchestrator(
        make_settings(), reviewers=[failing_reviewer, ok_reviewer]
    ).run(DOCUMENT)

    assert len(result.issues) == 1
    assert any("проверка недоступна" in warning for warning in result.warnings)


def test_critic_and_judge_run_after_reviewers() -> None:
    # Судья пропускает единственное замечание без вызова модели (нечего сводить),
    # поэтому для проверки цепочки нужно минимум два замечания.
    gateway = FakeGateway(
        AgentResponse(issues=[make_issue(), make_issue(category="missing_data_volume")])
    )
    reviewer = CloudRuLLMReviewer("Аналитик", gateway)

    critic = CloudRuEvidenceCritic(
        FakeGateway(
            CriticResponse.model_validate(
                {
                    "verdicts": [
                        {
                            "issue_id": "i1",
                            "verdict": "confirmed",
                            "reason": "цитата на месте",
                            "confidence": 1.0,
                        },
                        {
                            "issue_id": "i2",
                            "verdict": "confirmed",
                            "reason": "цитата на месте",
                            "confidence": 1.0,
                        },
                    ]
                }
            )
        )
    )
    judge = CloudRuIssueJudge(
        FakeGateway(
            JudgeResponse.model_validate(
                {
                    "decisions": [
                        {
                            "issue_id": "i1",
                            "keep": True,
                            "severity": "blocker",
                            "duplicate_of": "",
                            "reason": "переоценено судьёй",
                        },
                        {
                            "issue_id": "i2",
                            "keep": True,
                            "severity": "minor",
                            "duplicate_of": "",
                            "reason": "оставлено",
                        },
                    ]
                }
            )
        )
    )

    orchestrator = ReviewOrchestrator(
        make_settings(), reviewers=[reviewer], llm_critic=critic, llm_judge=judge
    )
    result = orchestrator.run(DOCUMENT)

    assert result.status == "Не готово"
    assert result.issues[0].severity is Severity.BLOCKER


def test_orchestrator_degrades_when_control_agents_fail() -> None:
    reviewer = reviewer_returning(make_issue())
    orchestrator = ReviewOrchestrator(
        make_settings(),
        reviewers=[reviewer],
        llm_critic=CloudRuEvidenceCritic(FakeGateway(RuntimeError("timeout"))),
        llm_judge=CloudRuIssueJudge(FakeGateway(RuntimeError("timeout"))),
    )

    result = orchestrator.run(DOCUMENT)

    assert any(issue.category == "load_strategy" for issue in result.issues)
    assert any("перепроверка недоступна" in warning for warning in result.warnings)
