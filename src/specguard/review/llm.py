"""LLM-агенты поверх OpenAI-совместимого API Cloud.ru Foundation Models."""

from __future__ import annotations

import json
import logging
import time
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from specguard.config import Settings

from . import prompts
from .agents import Reviewer
from .schemas import (
    AgentResponse,
    CriticResponse,
    JudgeResponse,
    ReviewIssue,
    Severity,
    Verdict,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)

REVIEWER_ROLES = (
    prompts.ANALYST,
    prompts.DATA_ENGINEER,
    prompts.ARCHITECT,
    prompts.QA,
)

logger = logging.getLogger(__name__)


class LLMGateway:
    """Один структурированный вызов модели с фолбэком на резервную модель."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    @property
    def _models(self) -> list[str]:
        models = [self._settings.llm_model]
        if self._settings.llm_fallback_model:
            models.append(self._settings.llm_fallback_model)
        return list(dict.fromkeys(models))

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: type[ResponseT],
    ) -> ResponseT:
        last_error: Exception | None = None
        for model in self._models:
            started_at = time.monotonic()
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "strict": True,
                            "schema": schema.model_json_schema(),
                        },
                    },
                )
                choice = response.choices[0]
                if choice.finish_reason != "stop" or not choice.message.content:
                    raise ValueError("Модель не вернула завершённый структурированный ответ")
                payload = choice.message.content
                result = schema.model_validate(json.loads(payload))
                logger.info(
                    "LLM call completed schema=%s model=%s seconds=%.1f",
                    schema_name,
                    model,
                    time.monotonic() - started_at,
                )
                return result
            except Exception as exc:
                logger.error(
                    "LLM call failed schema=%s model=%s seconds=%.1f error_type=%s",
                    schema_name,
                    model,
                    time.monotonic() - started_at,
                    type(exc).__name__,
                )
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("Не настроена ни одна модель LLM")


def _issues_payload(issues: list[ReviewIssue], *, with_evidence: bool) -> str:
    """Сериализует замечания с временными id, по которым отвечают критик и судья."""
    items = []
    for index, issue in enumerate(issues, start=1):
        item = {
            "issue_id": f"i{index}",
            "agent": issue.agent,
            "category": issue.category,
            "severity": issue.severity.value,
            "title": issue.title,
            "problem": issue.problem,
            "impact": issue.impact,
            "question": issue.question,
            "recommendation": issue.recommendation,
            "confidence": round(issue.confidence, 2),
        }
        if with_evidence:
            item["evidence"] = [evidence.quote for evidence in issue.evidence]
        items.append(item)
    return json.dumps(items, ensure_ascii=False, indent=2)


class CloudRuLLMReviewer(Reviewer):
    """Ролевой ревьюер: аналитик, data engineer, архитектор или QA."""

    def __init__(self, role: str, gateway: LLMGateway) -> None:
        self.role = role
        self.name = prompts.llm_agent_name(role)
        self._system = prompts.reviewer_system_prompt(role)
        self._gateway = gateway

    def review(self, text: str) -> list[ReviewIssue]:
        result = self._gateway.structured(
            system=self._system,
            user=f"Проверь ТЗ:\n\n{text}",
            schema_name="review_response",
            schema=AgentResponse,
        )
        return [issue.model_copy(update={"agent": self.name}) for issue in result.issues]


class CloudRuEvidenceCritic:
    """Критик: отбрасывает недоказанные и домысленные замечания ролевых агентов."""

    name = prompts.llm_agent_name(prompts.CRITIC)

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def screen(self, text: str, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        if not issues:
            return []

        result = self._gateway.structured(
            system=prompts.CRITIC_SYSTEM_PROMPT,
            user=(
                f"Документ ТЗ:\n\n{text}\n\n"
                f"Замечания на проверку:\n\n{_issues_payload(issues, with_evidence=True)}"
            ),
            schema_name="critic_response",
            schema=CriticResponse,
        )

        verdicts = {verdict.issue_id: verdict for verdict in result.verdicts}
        expected = {f"i{index}" for index in range(1, len(issues) + 1)}
        if set(verdicts) != expected or len(result.verdicts) != len(issues):
            raise ValueError("Критик должен вынести ровно один вердикт по каждому замечанию")
        confirmed: list[ReviewIssue] = []
        for index, issue in enumerate(issues, start=1):
            verdict = verdicts.get(f"i{index}")
            if verdict is None:
                # Пропущенное критиком замечание не считаем отклонённым:
                # молчание модели не является доказательством ложного срабатывания.
                confirmed.append(issue)
                continue
            if verdict.verdict is Verdict.REJECTED:
                continue
            confirmed.append(
                issue.model_copy(
                    update={"confidence": round(issue.confidence * verdict.confidence, 4)}
                )
            )
        return confirmed


class CloudRuIssueJudge:
    """Судья: объединяет дубли разных агентов и выставляет итоговую тяжесть."""

    name = prompts.llm_agent_name(prompts.JUDGE)

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def arbitrate(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        if not issues:
            return issues

        result = self._gateway.structured(
            system=prompts.JUDGE_SYSTEM_PROMPT,
            user=f"Замечания на сведение:\n\n{_issues_payload(issues, with_evidence=False)}",
            schema_name="judge_response",
            schema=JudgeResponse,
        )

        decisions = {decision.issue_id: decision for decision in result.decisions}
        issue_ids = [f"i{index}" for index in range(1, len(issues) + 1)]
        if set(decisions) != set(issue_ids) or len(result.decisions) != len(issues):
            raise ValueError("Судья должен вынести ровно одно решение по каждому замечанию")
        kept_ids = {
            issue_id
            for issue_id in issue_ids
            if issue_id not in decisions or decisions[issue_id].keep
        }

        for issue_id, decision in decisions.items():
            if not decision.keep and decision.duplicate_of:
                if decision.duplicate_of == issue_id or decision.duplicate_of not in kept_ids:
                    raise ValueError("Ссылка на дубль должна вести к оставленному замечанию")

        kept: list[ReviewIssue] = []
        for issue_id, issue in zip(issue_ids, issues, strict=True):
            decision = decisions.get(issue_id)
            if decision is None:
                # Пропущенное судьёй замечание сохраняем как есть.
                kept.append(issue)
                continue
            merged = issue.model_copy(update={"severity": decision.severity})
            if decision.keep:
                kept.append(merged)
                continue
            if decision.duplicate_of in kept_ids:
                # Дефект уже представлен оставленным замечанием.
                continue
            if Severity.BLOCKER in {issue.severity, decision.severity}:
                # Блокер не отбрасываем, даже если судья решил иначе.
                kept.append(merged)
        return kept


def cloud_reviewers(settings: Settings, gateway: LLMGateway | None = None) -> list[Reviewer]:
    if not settings.llm_enabled or not settings.llm_api_key:
        return []
    gateway = gateway or LLMGateway(settings)
    return [CloudRuLLMReviewer(role, gateway) for role in REVIEWER_ROLES]


def cloud_control_agents(
    settings: Settings,
    gateway: LLMGateway | None = None,
) -> tuple[CloudRuEvidenceCritic | None, CloudRuIssueJudge | None]:
    """Критик и судья с LLM. Отключаются вместе через LLM_CONTROL_ENABLED."""
    if not settings.llm_enabled or not settings.llm_api_key or not settings.llm_control_enabled:
        return None, None
    gateway = gateway or LLMGateway(settings)
    return CloudRuEvidenceCritic(gateway), CloudRuIssueJudge(gateway)
