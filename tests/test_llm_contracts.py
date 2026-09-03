from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import FakeGateway, make_issue, make_settings
from pydantic import ValidationError

from specguard.review.llm import CloudRuEvidenceCritic, CloudRuIssueJudge, LLMGateway
from specguard.review.schemas import AgentResponse, CriticResponse, JudgeResponse, Severity


@pytest.mark.parametrize("schema", [AgentResponse, CriticResponse, JudgeResponse])
def test_empty_object_is_not_a_successful_response(schema):
    with pytest.raises(ValidationError):
        schema.model_validate({})


@pytest.mark.parametrize("content,reason", [(None, "stop"), ('{"issues": []}', "length")])
def test_gateway_rejects_empty_or_truncated_generation(content, reason):
    gateway = LLMGateway.__new__(LLMGateway)
    gateway._settings = make_settings()
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=reason,
                message=SimpleNamespace(content=content),
            )
        ]
    )
    create = Mock(return_value=completion)
    gateway._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    with pytest.raises(ValueError, match="завершённый"):
        gateway.structured(
            system="system", user="document", schema_name="test", schema=AgentResponse
        )


def test_critic_rejects_duplicate_ids():
    verdict = {"issue_id": "i1", "verdict": "confirmed", "confidence": 1, "reason": "ok"}
    critic = CloudRuEvidenceCritic(
        FakeGateway(
            CriticResponse.model_validate(
                {
                    "verdicts": [verdict, verdict],
                }
            )
        )
    )
    with pytest.raises(ValueError, match="ровно один"):
        critic.screen("document", [make_issue(), make_issue()])


def test_judge_reviews_single_issue_severity():
    gateway = FakeGateway(
        JudgeResponse.model_validate(
            {
                "decisions": [
                    {
                        "issue_id": "i1",
                        "keep": True,
                        "severity": "minor",
                    }
                ]
            }
        )
    )
    result = CloudRuIssueJudge(gateway).arbitrate([make_issue()])
    assert len(gateway.calls) == 1
    assert result[0].severity is Severity.MINOR


def test_judge_rejects_circular_duplicate_links():
    judge = CloudRuIssueJudge(
        FakeGateway(
            JudgeResponse.model_validate(
                {
                    "decisions": [
                        {
                            "issue_id": "i1",
                            "keep": False,
                            "severity": "major",
                            "duplicate_of": "i2",
                        },
                        {
                            "issue_id": "i2",
                            "keep": False,
                            "severity": "major",
                            "duplicate_of": "i1",
                        },
                    ]
                }
            )
        )
    )
    with pytest.raises(ValueError, match="оставленному"):
        judge.arbitrate([make_issue(), make_issue()])
