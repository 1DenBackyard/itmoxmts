import json
from datetime import datetime
from types import SimpleNamespace

from specguard.ui import CASEHOLDER_CHECKLIST, document_preview, export_review, filter_issues


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


def test_caseholder_checklist_contains_all_published_rules():
    checklist = " ".join(CASEHOLDER_CHECKLIST)
    for required in ("Data Catalog", "NULL", "Kafka", "HDFS", "справочник", "фильтр"):
        assert required in checklist


def test_document_preview_escapes_untrusted_html():
    rendered = document_preview('<script>alert(1)</script>\n<img src=x onerror="alert(1)">')
    assert "<script>" not in rendered
    assert "<img" not in rendered
    assert "&lt;script&gt;" in rendered
