from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from specguard.config import Settings, get_settings

from .agents import Reviewer
from .llm import (
    CloudRuEvidenceCritic,
    CloudRuIssueJudge,
    LLMGateway,
    cloud_control_agents,
    cloud_reviewers,
)
from .schemas import ReviewIssue, ReviewResult, Severity

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {
    Severity.BLOCKER: 0,
    Severity.MAJOR: 1,
    Severity.MINOR: 2,
    Severity.SUGGESTION: 3,
}


def _sort_by_severity(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    return sorted(
        issues,
        key=lambda item: (_SEVERITY_RANK[item.severity], -item.confidence, item.category),
    )


class ReviewOrchestrator:
    """Раздаёт документ LLM-агентам и проводит их замечания через критика и судью.

    Все агенты — роли, критик, судья — LLM-агенты с собственными промптами
    (см. prompts.py). Без LLM_ENABLED/LLM_API_KEY агентов нет и ревью не находит
    замечаний: это единственный контур проверки, детерминированного фолбэка нет.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        reviewers: list[Reviewer] | None = None,
        llm_critic: CloudRuEvidenceCritic | None = None,
        llm_judge: CloudRuIssueJudge | None = None,
    ) -> None:
        self.settings = settings or get_settings()

        gateway: LLMGateway | None = None
        if self.settings.llm_enabled and (
            self.settings.llm_api_key or self.settings.deepseek_api_key
        ):
            gateway = LLMGateway(self.settings)

        self.reviewers = (
            reviewers if reviewers is not None else cloud_reviewers(self.settings, gateway)
        )

        default_critic, default_judge = cloud_control_agents(self.settings, gateway)
        self.llm_critic = llm_critic if llm_critic is not None else default_critic
        self.llm_judge = llm_judge if llm_judge is not None else default_judge

    def run(self, text: str) -> ReviewResult:
        warnings: list[str] = []

        if not self.reviewers:
            warnings.append(
                "LLM-агенты не настроены (LLM_ENABLED/LLM_API_KEY): ревью не выполнялось."
            )
            return ReviewResult(status="Проверка не выполнена", issues=[], warnings=warnings)

        issues = self._collect(text, warnings)

        if self.llm_critic is not None and issues:
            try:
                issues = self.llm_critic.screen(text, issues)
            except Exception as exc:
                warnings.append(
                    f"{self.llm_critic.name}: перепроверка недоступна ({type(exc).__name__})"
                )

        if self.llm_judge is not None and issues:
            try:
                issues = self.llm_judge.arbitrate(issues)
            except Exception as exc:
                warnings.append(
                    f"{self.llm_judge.name}: сведение недоступно ({type(exc).__name__})"
                )

        issues = _sort_by_severity(issues)
        status = "Проверка неполная" if warnings else self._status(issues)
        return ReviewResult(status=status, issues=issues, warnings=warnings)

    def _collect(self, text: str, warnings: list[str]) -> list[ReviewIssue]:
        candidates: list[ReviewIssue] = []
        started_at = time.monotonic()
        with ThreadPoolExecutor(max_workers=max(1, len(self.reviewers))) as executor:
            futures = {
                executor.submit(reviewer.review, text): reviewer for reviewer in self.reviewers
            }
            for future in as_completed(futures):
                reviewer = futures[future]
                try:
                    findings = future.result()
                    candidates.extend(findings)
                    logger.info(
                        "Reviewer completed agent=%s elapsed=%.1f issues=%d",
                        reviewer.name,
                        time.monotonic() - started_at,
                        len(findings),
                    )
                except Exception as exc:
                    logger.error(
                        "Reviewer failed agent=%s error_type=%s", reviewer.name, type(exc).__name__
                    )
                    warnings.append(f"{reviewer.name}: проверка недоступна ({type(exc).__name__})")
        return candidates

    @staticmethod
    def _status(issues: list[ReviewIssue]) -> str:
        if any(issue.severity == Severity.BLOCKER for issue in issues):
            return "Не готово"
        if any(issue.severity == Severity.MAJOR for issue in issues):
            return "Требует уточнения"
        if issues:
            return "Готово с замечаниями"
        return "Готово к передаче"
