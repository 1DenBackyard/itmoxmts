from __future__ import annotations

import re
from abc import ABC, abstractmethod

from .schemas import Evidence, ReviewIssue, Severity


def _fragment(text: str, pattern: str, window: int = 220) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return text[:window].strip()
    start = max(0, match.start() - window // 3)
    end = min(len(text), match.end() + window)
    return " ".join(text[start:end].split())


def _contains(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None


class Reviewer(ABC):
    name: str

    @abstractmethod
    def review(self, text: str) -> list[ReviewIssue]:
        raise NotImplementedError


class AnalystReviewer(Reviewer):
    name = "Аналитик"

    def review(self, text: str) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        if _contains(text, r"\b(CLUSTER|SCHEMA|TABLE|LINK)\b\s*(?:$|[,:;])"):
            quote = _fragment(text, r"\b(CLUSTER|SCHEMA|TABLE|LINK)\b\s*(?:$|[,:;])")
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="placeholder",
                    severity=Severity.MAJOR,
                    title="В документе осталась незаполненная заглушка",
                    evidence=[Evidence(quote=quote)],
                    problem="Технический идентификатор указан шаблонным значением.",
                    impact="Разработчик не сможет определить фактический объект или окружение.",
                    question="Какое фактическое значение должно использоваться?",
                    recommendation=(
                        "Заменить placeholder на конкретное значение или указать владельца "
                        "и срок уточнения."
                    ),
                    confidence=0.96,
                )
            )

        if len(text) > 500 and not _contains(
            text,
            r"объ[её]м\w*\s+данн|строк(?:/| в )|событи(?:й|я)/(?:сек|с)|gb|tb|гб|тб",
        ):
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="missing_data_volume",
                    severity=Severity.MINOR,
                    title="Не указан ожидаемый объём данных",
                    evidence=[Evidence(quote=_fragment(text, r"регламент|способ загрузки"))],
                    problem=(
                        "Документ описывает загрузку, но не задаёт объём или порядок его оценки."
                    ),
                    impact="Нельзя обоснованно оценить ресурсы, время расчёта и SLA.",
                    question="Каков средний и пиковый объём входных данных за период?",
                    recommendation="Добавить объём строк/байт за период и ожидаемый рост.",
                    confidence=0.78,
                )
            )
        return issues


class DataEngineerReviewer(Reviewer):
    name = "Data Engineer"

    def review(self, text: str) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        if _contains(text, r"группировк\w*\s+по") and _contains(
            text, r"FIELD_USERS_CNT\s*=\s*count\s*\("
        ):
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="aggregation_logic",
                    severity=Severity.BLOCKER,
                    title="Агрегат указан как поле группировки",
                    evidence=[Evidence(quote=_fragment(text, r"FIELD_USERS_CNT\s*=\s*count\s*\("))],
                    problem="COUNT(DISTINCT ...) является вычисляемой мерой, а не ключом GROUP BY.",
                    impact=(
                        "Буквальная реализация требования приведёт к некорректному SQL "
                        "или гранулярности."
                    ),
                    question="Должна ли группировка выполняться только по региону и вендору?",
                    recommendation=(
                        "Разделить ключи группировки и список рассчитываемых показателей."
                    ),
                    confidence=0.99,
                )
            )

        referenced_fields = set(re.findall(r"\bFIELD_[A-Z0-9_]+\b", text))
        has_input_tables = _contains(text, r"источник\w*\s+данн|источники и при[её]мники")
        has_field_contract = _contains(text, r"поле\s*[|\t ]+тип\s+данных|структура\s+данных")
        if has_input_tables and len(referenced_fields) >= 4 and not has_field_contract:
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="missing_field_contract",
                    severity=Severity.MAJOR,
                    title="Нет контракта входных полей",
                    evidence=[Evidence(quote=_fragment(text, r"FIELD_[A-Z0-9_]+"))],
                    problem=(
                        "Алгоритм использует поля, но их типы, nullability и таблицы-источники "
                        "не определены."
                    ),
                    impact="Невозможно однозначно реализовать чтение и преобразование данных.",
                    question="Из каких таблиц берётся каждое поле и каков его контракт?",
                    recommendation=(
                        "Добавить mapping source table/field → target field "
                        "с типом и правилами NULL."
                    ),
                    confidence=0.88,
                )
            )
        return issues


class ArchitectReviewer(Reviewer):
    name = "Архитектор"

    def review(self, text: str) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        if _contains(text, r"ненулев\w*\s+FIELD_LAC\s+и\s+FIELD_CELL_ID") and (
            _contains(text, r"lac\s*=\s*0") or _contains(text, r"cell\s*=\s*0")
        ):
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="logical_contradiction",
                    severity=Severity.BLOCKER,
                    title="Fallback-ветки недостижимы после фильтрации",
                    evidence=[
                        Evidence(
                            quote=_fragment(text, r"ненулев\w*\s+FIELD_LAC\s+и\s+FIELD_CELL_ID")
                        ),
                        Evidence(quote=_fragment(text, r"(?:lac|cell)\s*=\s*0")),
                    ],
                    problem=(
                        "Основной отбор исключает записи, для которых ниже предусмотрена "
                        "fallback-логика."
                    ),
                    impact="Часть абонентов может быть потеряна или обработана вопреки ожиданиям.",
                    question=(
                        "Разрешается ли отсутствие одного идентификатора до применения fallback?"
                    ),
                    recommendation=(
                        "Описать последовательность основного join и fallback без "
                        "взаимоисключающих условий."
                    ),
                    confidence=0.99,
                )
            )

        if _contains(text, r"\bинкремент\b") and _contains(text, r"полн\w*\s+перезагрузк\w*"):
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="load_strategy",
                    severity=Severity.MAJOR,
                    title="Неоднозначно описана стратегия обновления",
                    evidence=[
                        Evidence(quote=_fragment(text, r"\bинкремент\b")),
                        Evidence(quote=_fragment(text, r"полн\w*\s+перезагрузк\w*")),
                    ],
                    problem="Одновременно указаны инкрементальная загрузка и полная перезагрузка.",
                    impact=(
                        "Неясно, требуется append, overwrite партиции или полный пересчёт таблицы."
                    ),
                    question="Что именно перезагружается при штатном и повторном запуске?",
                    recommendation="Явно определить initial load, monthly load, rerun и backfill.",
                    confidence=0.94,
                )
            )
        return issues


class QAReviewer(Reviewer):
    name = "QA"

    def review(self, text: str) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        if _contains(text, r"substring\s*\(\s*imei") and not _contains(
            text, r"imei.{0,80}(?:null|пуст|короч|невалид|не найден|unknown)"
        ):
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="missing_edge_case",
                    severity=Severity.MAJOR,
                    title="Не описаны невалидный IMEI и неизвестный TAC",
                    evidence=[Evidence(quote=_fragment(text, r"substring\s*\(\s*imei"))],
                    problem=(
                        "Правило определяет happy path, но не результат для некорректных значений."
                    ),
                    impact=(
                        "Разные реализации могут исключить запись, вернуть NULL "
                        "или присвоить UNKNOWN."
                    ),
                    question=(
                        "Как обрабатывать пустой/короткий IMEI и TAC без записи в справочнике?"
                    ),
                    recommendation="Добавить таблицу edge cases с ожидаемым результатом.",
                    confidence=0.91,
                )
            )

        if _contains(text, r"последн\w*\s+(?:запис|значен|FIELD_IMEI)") and not _contains(
            text, r"одинаков\w*\s+(?:врем|timestamp)|tie.?break|при равн"
        ):
            issues.append(
                ReviewIssue(
                    agent=self.name,
                    category="missing_tie_breaker",
                    severity=Severity.MINOR,
                    title="Не определён выбор при одинаковом времени",
                    evidence=[
                        Evidence(quote=_fragment(text, r"последн\w*\s+(?:запис|значен|FIELD_IMEI)"))
                    ],
                    problem=(
                        "Описан выбор последней записи без детерминированного "
                        "дополнительного порядка."
                    ),
                    impact=(
                        "Повторные запуски могут выбирать разные записи при одинаковом timestamp."
                    ),
                    question="Какое поле использовать как tie-breaker?",
                    recommendation=(
                        "Добавить полный порядок сортировки и правило разрешения дублей."
                    ),
                    confidence=0.76,
                )
            )
        return issues


def builtin_reviewers() -> list[Reviewer]:
    return [
        AnalystReviewer(),
        DataEngineerReviewer(),
        ArchitectReviewer(),
        QAReviewer(),
    ]
