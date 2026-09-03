"""Presentation helpers; no demo data or changes to review policy."""

import json

STYLES = """
<style>
.stApp {background: #f4f4f5; color: #1a1a1a;}
.block-container {max-width: 1280px; padding-top: 2rem;}
[data-testid="stSidebar"] {background: white; border-right: 1px solid #e6e6e6;}
[data-testid="stMetric"], [data-testid="stForm"],
[data-testid="stExpander"] {background: white; border: 1px solid #e6e6e6;
 border-radius: 16px; padding: 16px;}
[data-testid="stMetricValue"] {font-weight: 700;}
h1 {letter-spacing: -.04em;}
.sg-eyebrow {color: #d6002a; font-size: 12px; font-weight: 700;
 letter-spacing: .12em; margin-bottom: 8px;}
.sg-steps {display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 24px;}
.sg-steps span {border-radius: 24px; background: white; border: 1px solid #e6e6e6;
 padding: 7px 14px; font-size: 13px;}
.sg-steps .active {background: #1a1a1a; color: white;}
@media(max-width: 640px) {.block-container {padding: 1rem;}}
</style>
"""

SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "suggestion": 3}


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
