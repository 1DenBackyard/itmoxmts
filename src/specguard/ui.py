"""Presentation helpers; no demo data or changes to review policy."""

import json
from html import escape

STYLES = """
<style>
.stApp {background: #f5f5f6; color: #1a1a1a;}
.block-container {max-width: 1120px; padding: 1.75rem 2rem 3rem;}
[data-testid="stSidebar"] {background: white; border-right: 1px solid #e6e6e6;}
[data-testid="stSidebar"] .block-container {padding: 1.5rem 1rem;}
[data-testid="stMetric"], [data-testid="stForm"],
[data-testid="stExpander"] {background: white; border: 1px solid #e2e2e5;
 border-radius: 14px; padding: 14px; box-shadow: 0 4px 18px rgba(0,0,0,.035);}
[data-testid="stMetricValue"] {font-weight: 700;}
h1 {font-size: clamp(2rem, 4vw, 2.8rem) !important; letter-spacing: -.045em;
 line-height: 1.05 !important; margin-bottom: .4rem !important;}
h2 {font-size: 1.45rem !important; letter-spacing: -.02em;}
h3 {font-size: 1.2rem !important; letter-spacing: -.015em;}
p, label, [data-testid="stCaptionContainer"] {line-height: 1.45;}
[data-testid="stTextInput"] input {background:#f5f5f6; border:1px solid #e2e2e5;
 border-radius:8px; padding:.6rem .75rem;}
.sg-eyebrow {color: #d6002a; font-size: 12px; font-weight: 800;
 letter-spacing: .12em; margin-bottom: 8px;}
.sg-brand {display:flex; align-items:center; gap:10px; font-size:1.1rem;
 font-weight:800; margin-bottom:1.4rem;}
.sg-mark {display:inline-grid; place-items:center; width:30px; height:30px;
 border-radius:9px; color:white; background:#ff0032; font-size:14px;}
.sg-login-copy {max-width: 480px; margin: 5vh auto 1rem; text-align:center;}
.sg-login-copy p {color:#666; margin:.6rem auto 1.4rem;}
.sg-steps {display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 24px;}
.sg-steps span {border-radius: 24px; background: white; border: 1px solid #e6e6e6;
 padding: 7px 14px; font-size: 13px; font-weight:600;}
.sg-steps .active {background: #1a1a1a; color: white;}
.sg-section {margin-top:1.25rem; padding-top:.25rem; border-top:1px solid #e6e6e6;}
.sg-summary {display:flex; flex-wrap:wrap; gap:8px; margin:.4rem 0 1rem;}
.sg-summary span {background:white; border:1px solid #e2e2e5; border-radius:20px;
 padding:6px 10px; font-size:13px;}
.sg-summary b {margin-right:5px;}
.sg-document {white-space:pre-wrap; overflow-wrap:anywhere; max-height:620px; overflow:auto;
 padding:24px; background:white; border:1px solid #e2e2e5; border-radius:14px;
 font:16px/1.6 Georgia, serif; color:#252525;}
.stButton > button[kind="primary"], .stFormSubmitButton > button {font-weight:700;}
@media(max-width: 640px) {
 .block-container {padding: 1rem .8rem 2rem;}
 h1 {font-size:2rem !important;}
 .sg-login-copy {margin-top:1rem;}
}
</style>
"""

SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "suggestion": 3}

CASEHOLDER_CHECKLIST = (
    "Модель входного и выходного потока: формат, схема и сериализация",
    "Прямая ссылка на Data Catalog",
    "NULL / NOT NULL для каждого поля витрины",
    "Стандартные условия фильтрации",
    "Все разделы шаблона сохранены; неприменимые явно отмечены",
    "Kafka-кластер для потокового источника или приёмника",
    "Полный HDFS-путь и формат файлового хранилища",
    "Перечень используемых справочников",
)


def document_preview(text: str) -> str:
    """Render untrusted source as text, never as active HTML or Markdown."""
    return f'<div class="sg-document">{escape(text)}</div>'


def filter_issues(issues, severity="Все", decision="Все", query=""):
    query = query.strip().casefold()
    return sorted(
        [
            issue
            for issue in issues
            if (severity == "Все" or issue.severity == severity)
            and (decision == "Все" or issue.employee_decision == decision)
            and (
                not query
                or query
                in (f"{issue.title} {issue.category} {issue.problem} {issue.evidence}").casefold()
            )
        ],
        key=lambda issue: SEVERITY_ORDER.get(issue.severity, 99),
    )


def export_review(review):
    return json.dumps(
        {
            "document": review.filename,
            "status": review.result_status,
            "created_at": review.created_at.isoformat(),
            "issues": [
                {
                    key: getattr(issue, key)
                    for key in (
                        "agent",
                        "category",
                        "severity",
                        "title",
                        "evidence",
                        "problem",
                        "impact",
                        "question",
                        "recommendation",
                        "employee_decision",
                    )
                }
                for issue in review.issues
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
