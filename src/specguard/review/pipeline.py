from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from specguard.config import Settings, get_settings

from .agents import Reviewer, builtin_reviewers
from .llm import cloud_reviewers
from .schemas import ReviewIssue, ReviewResult, Severity


class EvidenceCritic:
    def validate(self, text: str, issue: ReviewIssue) -> bool:
        if issue.confidence < 0.55 or not issue.evidence:
            return False
        normalized_text = " ".join(text.split()).casefold()
        return any(
            " ".join(evidence.quote.split()).casefold() in normalized_text
            for evidence in issue.evidence
        )


class IssueJudge:
    def deduplicate(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        chosen: dict[tuple[str, str], ReviewIssue] = {}
        for issue in issues:
            title_key = re.sub(r"\W+", " ", issue.title.casefold()).strip()
            key = (issue.category, title_key)
            current = chosen.get(key)
            if current is None or issue.confidence > current.confidence:
                chosen[key] = issue

        rank = {
            Severity.BLOCKER: 0,
            Severity.MAJOR: 1,
            Severity.MINOR: 2,
            Severity.SUGGESTION: 3,
        }
        return sorted(
            chosen.values(),
            key=lambda item: (rank[item.severity], -item.confidence, item.category),
        )


class ReviewOrchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        reviewers: list[Reviewer] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.reviewers = reviewers or [
            *builtin_reviewers(),
            *cloud_reviewers(self.settings),
        ]
        self.critic = EvidenceCritic()
        self.judge = IssueJudge()

    def run(self, text: str) -> ReviewResult:
        candidates: list[ReviewIssue] = []
        warnings: list[str] = []

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

        verified = [issue for issue in candidates if self.critic.validate(text, issue)]
        issues = self.judge.deduplicate(verified)

        if any(issue.severity == Severity.BLOCKER for issue in issues):
            status = "Не готово"
        elif any(issue.severity == Severity.MAJOR for issue in issues):
            status = "Требует уточнения"
        elif issues:
            status = "Готово с замечаниями"
        else:
            status = "Готово к передаче"

        return ReviewResult(status=status, issues=issues, warnings=warnings)
