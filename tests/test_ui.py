import json
from datetime import datetime
from types import SimpleNamespace

from specguard.ui import export_review, filter_issues


def issue(**overrides):
    values = dict(
        agent="QA",
        category="Полнота",
        severity="major",
        title="Нет ключа",
        evidence="<script>sample</script>",
        problem="Не определён ключ",
        impact="Дубли",
        question="Какой ключ?",
        recommendation="Уточнить",
        employee_decision="open",
    )
    return SimpleNamespace(**(values | overrides))


def test_filters_and_priority():
    items = [issue(), issue(severity="blocker"), issue(employee_decision="fixed")]
    assert filter_issues(items)[0].severity == "blocker"
    assert len(filter_issues(items, decision="fixed")) == 1
    assert len(filter_issues(items, severity="major", query="КЛЮЧ")) == 2
    assert not filter_issues(items, query="несуществующий")


def test_export_keeps_real_decisions():
    review = SimpleNamespace(
        filename="тз.txt",
        result_status="Проверка неполная",
        created_at=datetime(2026, 9, 3),
        issues=[issue()],
    )
    report = json.loads(export_review(review))
    assert report["status"] == "Проверка неполная"
    assert report["issues"][0]["employee_decision"] == "open"
    assert "<script>" in report["issues"][0]["evidence"]
