from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from conftest import make_settings

from specguard.review.llm import LLMGateway, cloud_control_agents, cloud_reviewers
from specguard.review.schemas import AgentResponse


def response(content='{"issues": []}', reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=reason, message=SimpleNamespace(content=content))]
    )


def client(result):
    call = Mock(side_effect=result if isinstance(result, Exception) else None, return_value=result)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=call)))


@pytest.mark.parametrize(
    "primary",
    [
        TimeoutError(),
        RuntimeError("rate limit"),
        response("{}"),
        response("", "stop"),
        response('{"issues": []}', "length"),
    ],
)
def test_primary_failures_fall_back_with_cloud_schema(primary):
    cloud, deepseek = client(response()), client(primary)
    settings = replace(make_settings(llm_api_key="test-cloud"), deepseek_api_key="test-deepseek")
    with patch("specguard.review.llm.OpenAI", side_effect=[cloud, deepseek]) as factory:
        gateway = LLMGateway(settings)
    assert factory.call_args_list[0].kwargs["api_key"] == settings.llm_api_key
    assert factory.call_args_list[1].kwargs["api_key"] == "test-deepseek"
    assert factory.call_args_list[1].kwargs["base_url"] == "https://api.deepseek.com"
    result = gateway.structured(
        system="test", user="synthetic", schema_name="review", schema=AgentResponse
    )
    assert result.issues == []
    assert (
        deepseek.chat.completions.create.call_args.kwargs["response_format"]["type"]
        == "json_object"
    )
    assert (
        cloud.chat.completions.create.call_args.kwargs["response_format"]["type"] == "json_schema"
    )


def test_success_never_calls_cloud_and_all_failures_raise():
    cloud, deepseek = client(RuntimeError("cloud down")), client(response())
    with patch("specguard.review.llm.OpenAI", side_effect=[cloud, deepseek]):
        gateway = LLMGateway(
            replace(make_settings(llm_api_key="test-cloud"), deepseek_api_key="test-deepseek")
        )
    gateway.structured(system="test", user="synthetic", schema_name="review", schema=AgentResponse)
    cloud.chat.completions.create.assert_not_called()
    deepseek.chat.completions.create.side_effect = TimeoutError()
    with pytest.raises(RuntimeError, match="cloud down"):
        gateway.structured(
            system="test", user="synthetic", schema_name="review", schema=AgentResponse
        )


def test_cloud_only_without_primary_secret():
    cloud = client(response())
    with patch("specguard.review.llm.OpenAI", return_value=cloud) as factory:
        gateway = LLMGateway(make_settings(llm_api_key="test-cloud"))
    assert factory.call_count == 1
    gateway.structured(system="test", user="synthetic", schema_name="review", schema=AgentResponse)
    assert cloud.chat.completions.create.call_count == 1


def test_deepseek_only_enables_all_roles():
    settings = make_settings(llm_enabled=True, deepseek_api_key="test-deepseek")
    gateway = Mock()
    assert len(cloud_reviewers(settings, gateway)) == 4
    assert all(cloud_control_agents(settings, gateway))
