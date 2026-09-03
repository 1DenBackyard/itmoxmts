from __future__ import annotations

import logging
from collections import Counter

import pandas as pd
import streamlit as st

from specguard.config import get_settings
from specguard.database import IssueRecord, Review, get_repository
from specguard.documents import DocumentExtractionError, extract_text
from specguard.review import ReviewOrchestrator
from specguard.storage import DocumentStorageError, create_document_storage
from specguard.ui import (
    CASEHOLDER_CHECKLIST,
    STYLES,
    document_preview,
    export_review,
    filter_issues,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("specguard").setLevel(logging.INFO)
st.set_page_config(page_title="NET SpecGuard", page_icon="🔎", layout="wide")
st.markdown(STYLES, unsafe_allow_html=True)

SEVERITY_LABELS = {
    "blocker": "🔴 Blocker",
    "major": "🟠 Major",
    "minor": "🟡 Minor",
    "suggestion": "🔵 Suggestion",
}
DECISION_LABELS = {
    "open": "Открыто",
    "accepted": "Принято",
    "rejected": "Отклонено",
    "fixed": "Исправлено",
}


@st.cache_resource
def services():
    return get_repository(), ReviewOrchestrator(), create_document_storage(get_settings())


repository, orchestrator, document_storage = services()
settings = get_settings()


def login_page() -> None:
    _, center, _ = st.columns([1, 1.15, 1])
    with center:
        st.markdown(
            '<div class="sg-login-copy"><div class="sg-eyebrow">МТС × AI TALENT HUB</div>'
            "<h1>NET SpecGuard</h1><p>Проверка ТЗ до передачи в разработку</p></div>",
            unsafe_allow_html=True,
        )
        with st.form("login", clear_on_submit=False):
            email = st.text_input("Корпоративная почта", value="analyst@example.com")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти", type="primary", use_container_width=True)
        if settings.demo_password == "demo1234":
            st.caption("Демо-доступ: analyst@example.com / demo1234")
    with center:
        if submitted:
            user = repository.authenticate(email, password)
            if user:
                st.session_state.user_id = user.id
                st.rerun()
            st.error("Неверная почта или пароль")


def render_issue(issue: IssueRecord, user_id: str) -> None:
    label = f"{SEVERITY_LABELS.get(issue.severity, issue.severity)} · {issue.title}"
    with st.expander(label, expanded=issue.employee_decision == "open"):
        st.caption(
            f"{issue.agent} · {issue.category} · "
            f"{DECISION_LABELS.get(issue.employee_decision, issue.employee_decision)}"
        )
        st.markdown("**Основание**")
        for quote in issue.evidence.split("\n---\n"):
            st.code(quote, language=None)
        st.markdown(f"**Проблема:** {issue.problem}")
        st.markdown(f"**Влияние:** {issue.impact}")
        st.markdown(f"**Вопрос аналитику:** {issue.question}")
        st.markdown(f"**Рекомендация:** {issue.recommendation}")
        st.caption("Рекомендация ИИ — не готовое требование. Сверьте её с источниками.")

        accepted, rejected, fixed = st.columns(3)
        if accepted.button("Принять", key=f"accept-{issue.id}", use_container_width=True):
            repository.set_issue_decision(issue.id, user_id, "accepted")
            st.rerun()
        if rejected.button("Отклонить", key=f"reject-{issue.id}", use_container_width=True):
            repository.set_issue_decision(issue.id, user_id, "rejected")
            st.rerun()
        if fixed.button("Исправлено", key=f"fix-{issue.id}", use_container_width=True):
            repository.set_issue_decision(issue.id, user_id, "fixed")
            st.rerun()
        if issue.employee_decision != "open":
            if st.button("Вернуть в открытые", key=f"reopen-{issue.id}"):
                repository.set_issue_decision(issue.id, user_id, "open")
                st.rerun()


def render_review(review: Review, user_id: str) -> None:
    st.subheader(review.filename)
    if review.result_status.startswith("Проверка"):
        st.warning(f"{review.result_status}. Полнота анализа не подтверждена.")
    else:
        st.info(f"Заключение ревью: {review.result_status}")
    st.caption("Заключение относится к исходной версии ТЗ. После правок запустите новое ревью.")
    totals = Counter(issue.severity for issue in review.issues)
    badges = "".join(
        f"<span><b>{totals[severity]}</b>{label}</span>"
        for severity, label in SEVERITY_LABELS.items()
    )
    st.markdown(f'<div class="sg-summary">{badges}</div>', unsafe_allow_html=True)
    st.download_button(
        "Скачать отчёт · JSON",
        export_review(review),
        "review.json",
        "application/json",
        key=f"export-{review.id}",
    )
    if not review.issues:
        if not review.result_status.startswith("Проверка"):
            st.success("Существенных замечаний не найдено")
        return
    priority, status, search = st.columns([1, 1, 2])
    severity = priority.selectbox(
        "Приоритет",
        ["Все", *SEVERITY_LABELS],
        format_func=lambda value: SEVERITY_LABELS.get(value, value),
        key=f"severity-{review.id}",
    )
    decision = status.selectbox(
        "Решение",
        ["Все", *DECISION_LABELS],
        format_func=lambda value: DECISION_LABELS.get(value, value),
        key=f"decision-{review.id}",
    )
    query = search.text_input("Найти замечание", key=f"search-{review.id}")
    visible = filter_issues(review.issues, severity, decision, query)
    st.caption(f"Показано {len(visible)} из {len(review.issues)} замечаний")
    for issue in visible:
        render_issue(issue, user_id)


def dashboard(user_id: str) -> None:
    st.title("История проверок")
    st.caption("Ваши документы, решения и результаты — в одном месте.")
    metrics = repository.user_metrics(user_id)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Проверено ТЗ", metrics["reviews"])
    col2.metric("Открытые замечания", metrics["open"])
    col3.metric("Подтверждённые ошибки", metrics["confirmed"])
    col4.metric("Исправлено", metrics["fixed"])

    st.subheader("Последние проверки")
    recent = repository.recent_reviews(user_id)
    if not recent:
        st.info("Загрузите первое ТЗ, чтобы начать формировать персональную статистику.")
        return
    frame = pd.DataFrame(
        [
            {
                "Документ": review.filename,
                "Статус": review.result_status,
                "Замечаний": len(review.issues),
                "Дата": review.created_at.strftime("%d.%m.%Y %H:%M"),
            }
            for review in recent
        ]
    )
    st.dataframe(frame, hide_index=True, use_container_width=True)
    selected = st.selectbox(
        "Открыть результат",
        recent,
        format_func=lambda item: f"{item.created_at:%d.%m %H:%M} · {item.filename} · {item.id[:6]}",
    )
    if selected:
        render_review(selected, user_id)
    st.caption("Показаны последние 10 проверок.")


def review_form(user_id: str) -> None:
    if settings.document_storage_backend.lower() == "s3":
        st.caption("Документ хранится в приватном Cloud.ru Object Storage.")
    else:
        st.caption(f"Локальный режим хранения: {settings.document_storage_path}.")

    source = st.radio("Источник", ["Файл", "Текст"], horizontal=True)
    uploaded = None
    pasted = ""
    if source == "Файл":
        uploaded = st.file_uploader("Загрузите документ", type=["pdf", "docx", "txt", "md"])
        st.caption(
            "PDF с текстовым слоем, DOCX, TXT или Markdown. OCR сканов пока не поддерживается."
        )
    else:
        pasted = st.text_area(
            "Или вставьте текст", height=220, placeholder="Текст технического задания"
        )

    if st.button("Запустить ревью", type="primary", use_container_width=True):
        try:
            stored_document = None
            if uploaded is not None:
                filename = uploaded.name
                content = uploaded.getvalue()
                document_text = extract_text(
                    uploaded.name,
                    content,
                    max_chars=settings.max_document_chars,
                )
            elif pasted.strip():
                filename = "Вставленный текст"
                document_text = pasted.strip()
            else:
                st.warning("Загрузите документ или вставьте текст")
                return

            with st.spinner("Агенты анализируют документ…"):
                result = orchestrator.run(document_text)
                if uploaded is not None:
                    stored_document = document_storage.put_document(
                        user_id=user_id,
                        filename=filename,
                        content=content,
                        content_type=uploaded.type,
                    )
                review_id = repository.save_review(
                    user_id=user_id,
                    filename=filename,
                    document_text=document_text,
                    result=result,
                    document=stored_document,
                )
            st.session_state.last_review_id = review_id
            st.session_state.review_source_text = document_text
            st.session_state.review_warnings = result.warnings
            st.rerun()
        except DocumentExtractionError as exc:
            st.error(str(exc))
        except DocumentStorageError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Не удалось выполнить проверку: {type(exc).__name__}")


def review_page(user_id: str) -> None:
    review_id = st.session_state.get("last_review_id")
    st.title("Разбор документа" if review_id else "Новое ревью")
    st.caption("Загрузите ТЗ — четыре роли проверят его, критик и судья очистят результат.")
    stage = 3 if review_id else 1
    steps = ("Документ", "Анализ", "Разбор замечаний")
    st.markdown(
        '<div class="sg-steps">'
        + "".join(
            f'<span class="{"active" if index == stage else ""}">{index} · {label}</span>'
            for index, label in enumerate(steps, 1)
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    if review_id:
        with st.expander("Загрузить новую версию или другой документ", expanded=False):
            review_form(user_id)
    else:
        review_form(user_id)
    if st.session_state.get("review_warnings"):
        st.warning("; ".join(st.session_state.review_warnings))
    if review_id:
        review = repository.get_review(review_id, user_id)
        if review:
            st.markdown('<div class="sg-section"></div>', unsafe_allow_html=True)
            source_col, findings_col = st.columns([1.1, 0.9], gap="large")
            with source_col:
                st.subheader("Исходный текст")
                st.markdown(
                    document_preview(
                        st.session_state.get(
                            "review_source_text", "Текст недоступен в этой сессии."
                        )
                    ),
                    unsafe_allow_html=True,
                )
            with findings_col:
                render_review(review, user_id)


def errors_page(user_id: str) -> None:
    st.title("Мой прогресс")
    metrics = repository.user_metrics(user_id)
    categories: Counter[str] = metrics["categories"]
    checked, confirmed, fixed = st.columns(3)
    checked.metric("Проверок", metrics["reviews"])
    confirmed.metric("Подтверждено", metrics["confirmed"])
    fixed.metric("Исправлено", metrics["fixed"])
    if metrics["confirmed"]:
        st.progress(metrics["fixed"] / metrics["confirmed"], text="Доля исправленных замечаний")

    st.caption(
        "В профиль входят только принятые или исправленные замечания. "
        "Открытые гипотезы LLM не считаются ошибками сотрудника."
    )
    if categories:
        frame = pd.DataFrame(
            [{"Категория": category, "Количество": count} for category, count in categories.items()]
        ).sort_values("Количество", ascending=False)
        st.bar_chart(frame.set_index("Категория"))
        most_common = frame.iloc[0]["Категория"]
        st.info(f"Чаще всего повторяется категория «{most_common}».")
    else:
        st.info("Подтверждённых ошибок пока нет — показываем базовый чек-лист кейсодателя.")

    st.subheader("Чек-лист перед передачей ТЗ")
    for index, label in enumerate(CASEHOLDER_CHECKLIST):
        st.checkbox(label, key=f"caseholder-{index}")
    if categories:
        st.subheader("Повторяющиеся ошибки")
        for category, count in categories.most_common(5):
            st.checkbox(
                f"Перепроверить «{category}» · подтверждено: {count}", key=f"check-{category}"
            )
    st.caption("Отметки чек-листа сохраняются только в текущей сессии.")


def architecture_page() -> None:
    st.title("Как работает система")
    st.markdown(
        """
1. Из документа извлекается текст; полный текст получают все четыре ревьюера.
2. Аналитик, Data Engineer, архитектор и QA проверяют свои зоны параллельно.
3. Критик отбрасывает замечания без доказательства в тексте.
4. Судья объединяет дубли и назначает итоговый приоритет.
5. Сотрудник принимает или отклоняет замечания.
6. Только подтверждённые проблемы формируют персональную статистику.
"""
    )
    if settings.llm_enabled and settings.llm_api_key:
        st.info(f"Модель всех ролей: {settings.llm_model}")
        controls = "включены" if settings.llm_control_enabled else "выключены"
        st.caption(f"LLM-критик и судья: {controls}")
    else:
        st.warning("LLM не настроена: анализ недоступен. Локальных regex-агентов больше нет.")
    storage_mode = (
        f"Cloud.ru Object Storage / {settings.s3_bucket}"
        if settings.document_storage_backend.lower() == "s3"
        else f"локальный каталог {settings.document_storage_path}"
    )
    st.info(f"Хранилище исходных документов: {storage_mode}")


if "user_id" not in st.session_state:
    login_page()
    st.stop()

user = repository.get_user(st.session_state.user_id)
if not user:
    st.session_state.clear()
    st.rerun()

with st.sidebar:
    st.markdown(
        '<div class="sg-brand"><span class="sg-mark">N</span>NET SpecGuard</div>',
        unsafe_allow_html=True,
    )
    st.write(f"**{user.full_name}**")
    st.caption({"analyst": "Аналитик", "engineer": "Инженер"}.get(user.role, user.role))
    page = st.radio(
        "Рабочее пространство", ["Проверка ТЗ", "История", "Мой прогресс", "Как это работает"]
    )
    st.caption("4 ревьюера · критик · судья\n\nВаши решения формируют ваш профиль.")
    if st.button("Выйти", use_container_width=True):
        st.session_state.clear()
        st.rerun()

if page == "История":
    dashboard(user.id)
elif page == "Проверка ТЗ":
    review_page(user.id)
elif page == "Мой прогресс":
    errors_page(user.id)
else:
    architecture_page()
