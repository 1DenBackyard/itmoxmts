from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from specguard.config import Settings, get_settings

from .agents import Reviewer, builtin_reviewers
from .llm import (
    CloudRuEvidenceCritic,
    CloudRuIssueJudge,
    LLMGateway,
    cloud_control_agents,
    cloud_reviewers,
)
from .schemas import ReviewIssue, ReviewResult, Severity


class EvidenceCritic:
    """Детерминированный критик: замечание живёт, только если цитата есть в документе."""

    def validate(self, text: str, issue: ReviewIssue) -> bool:
        if issue.confidence < 0.55 or not issue.evidence:
            return False
        normalized_text = " ".join(text.split()).casefold()
        return any(
            " ".join(evidence.quote.split()).casefold() in normalized_text
            for evidence in issue.evidence
        )


class IssueJudge:
    """Детерминированный судья: дедупликация по категории и заголовку, сортировка по тяжести."""

    def deduplicate(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        chosen: dict[tuple[str, str], ReviewIssue] = {}
        for issue in issues:
            title_key = re.sub(r"\W+", " ", issue.title.casefold()).strip()
            key = (issue.category, title_key)
            current = chosen.get(key)
            if current is None or issue.confidence > current.confidence:
                chosen[key] = issue

        return self.sort(list(chosen.values()))

    def sort(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        rank = {
            Severity.BLOCKER: 0,
            Severity.MAJOR: 1,
            Severity.MINOR: 2,
            Severity.SUGGESTION: 3,
        }
        return sorted(
            issues,
            key=lambda item: (rank[item.severity], -item.confidence, item.category),
        )


class ReviewOrchestrator:
    """Раздаёт документ ролевым агентам и проводит их замечания через критика и судью."""

    def __init__(
        self,
        settings: Settings | None = None,
        reviewers: list[Reviewer] | None = None,
        llm_critic: CloudRuEvidenceCritic | None = None,
        llm_judge: CloudRuIssueJudge | None = None,
    ) -> None:
        self.settings = settings or get_settings()

        gateway: LLMGateway | None = None
        if self.settings.llm_enabled and self.settings.llm_api_key:
            gateway = LLMGateway(self.settings)

        self.reviewers = reviewers or [
            *builtin_reviewers(),
            *cloud_reviewers(self.settings, gateway),
        ]
        self.critic = EvidenceCritic()
        self.judge = IssueJudge()

        default_critic, default_judge = cloud_control_agents(self.settings, gateway)
        self.llm_critic = llm_critic or default_critic
        self.llm_judge = llm_judge or default_judge

    def run(self, text: str) -> ReviewResult:
        warnings: list[str] = []
        candidates = self._collect(text, warnings)

        # Первый контур критика — дешёвый и жёсткий: цитата обязана быть в документе.
        issues = [issue for issue in candidates if self.critic.validate(text, issue)]

        if self.llm_critic is not None and issues:
            try:
                issues = self.llm_critic.screen(text, issues)
            except Exception as exc:
                warnings.append(
                    f"{self.llm_critic.name}: перепроверка недоступна ({type(exc).__name__})"
                )

        issues = self.judge.deduplicate(issues)

        if self.llm_judge is not None and issues:
            try:
                issues = self.judge.sort(self.llm_judge.arbitrate(issues))
            except Exception as exc:
                warnings.append(
                    f"{self.llm_judge.name}: сведение недоступно ({type(exc).__name__})"
                )

        return ReviewResult(status=self._status(issues), issues=issues, warnings=warnings)

    def _collect(self, text: str, warnings: list[str]) -> list[ReviewIssue]:
        candidates: list[ReviewIssue] = []
        with ThreadPoolExecutor(max_workers=max(1, len(self.reviewers))) as executor:
            futures = {
                executor.submit(reviewer.review, text): reviewer for reviewer in self.reviewers
            }
            for future in as_completed(futures):
                reviewer = futures[future]
                try:
                    candidates.extend(future.result())
                except Exception as exc:
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
