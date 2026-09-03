from __future__ import annotations

import re
from typing import Optional, Tuple

from .models import Finding


MISSING_TEMPLATES = {
    "data_catalog": (
        "Data Catalog\n"
        "Ссылка на карточку объекта: LINK_DATA_CATALOG\n"
        "Owner: USER_OWNER\n"
    ),
    "jira": ("JIRA\nLINK_JIRA_TASK\n"),
    "sample": (
        "Пример данных\n"
        "region_name | vendor_name | users_cnt | proc_ts | biz_date\n"
        "Центр | Vendor_A | 1200 | 2023-08-01 03:00:00 | 2023-07-01\n"
    ),
    "ddl": (
        "DDL\n"
        "CREATE TABLE SCHEMA_CDM_NETS.TABLE_AGG_DEVICES (\n"
        "  FIELD_REGION_NAME string,\n"
        "  FIELD_VENDOR_NAME string,\n"
        "  FIELD_USERS_CNT bigint,\n"
        "  FIELD_PROC_TS timestamp,\n"
        "  FIELD_BIZ_DATE date\n"
        ") PARTITIONED BY (FIELD_BIZ_DATE);\n"
    ),
    "changelog": (
        "История изменений\n"
        "Дата | Автор | Изменение\n"
        "2023-08-01 | USER_C | Первичная версия ТЗ\n"
    ),
    "faq": (
        "FAQ\n"
        "Q: Что делать, если region не найден?\n"
        "A: Пишем Unknown и не исключаем абонента из COUNT, либо фиксируем иное правило.\n"
    ),
    "gitlab": ("Исходники проекта / GitLab\nLINK_GITLAB_PROJECT\n"),
    "problem": ("Решаемая проблема\nКратко опишите бизнес-проблему и зачем нужен объект.\n"),
    "metrics": ("Продуктовые метрики\nПеречислите метрики, на которые влияет объект.\n"),
    "enrichment": ("Источники обогащения данных\nУкажите справочники и ключи джойна.\n"),
    "sinks": (
        "Приёмники данных\n"
        "Описание | Кластер | Ссылка на каталог | Сериализация\n"
        "TABLE_… | CLUSTER_… | LINK_… | parquet/orc\n"
    ),
    "flow_schema": (
        "Схема потоков данных\n"
        "source → Kafka/batch → processing → RAW/DDS/CDM\n"
    ),
}


def _extract_quoted_fix(recommendation: str) -> Optional[str]:
    """Достаёт вариант из формулировок вида: замени на «X» / например «X»."""
    patterns = [
        r"например\s+[«\"']([^«»\"']+)[»\"']",
        r"замени[^\n«\"']*[«\"']([^«»\"']+)[»\"']",
        r"исправь на\s*[«\"']([^«»\"']+)[»\"']",
        r"→\s*[«\"']([^«»\"']+)[»\"']",
    ]
    low = recommendation or ""
    for p in patterns:
        m = re.search(p, low, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def build_suggested_fix(finding: Finding) -> str:
    if finding.kind == "missing":
        return MISSING_TEMPLATES.get(
            finding.block_id,
            f"{finding.block}\nTODO: заполнить раздел по шаблону.\n",
        )
    extracted = _extract_quoted_fix(finding.recommendation)
    if extracted and finding.anchor and finding.anchor.excerpt and "CLUSTER" in finding.anchor.excerpt:
        return extracted
    if extracted:
        return extracted
    # эвристики по известным кейсам
    if "CLUSTER" in (finding.anchor.excerpt or "") or "CLUSTER" in finding.problem:
        return "CLUSTER_CDM_NETS_PROD"
    if finding.focus_area == "filtering":
        return (
            "Шаг 1. Выбор пользователей / фильтрация\n"
            "- Период = календарный месяц FIELD_BIZ_DATE\n"
            "- Исключить тестовые IMSI (если применимо)\n"
            "- Источник истины при пересечении MS/PS: union distinct FIELD_IMSI\n"
        )
    if finding.focus_area == "fields_logic" and "не найден" in finding.problem.lower():
        return (
            "Else-branch: если region/vendor не определён → значение Unknown; "
            "абонент сохраняется в агрегате.\n"
        )
    if finding.focus_area == "refresh_volume" and "late" in finding.problem.lower():
        return (
            "Политика late-data: в течение T+5 дней после закрытия месяца "
            "допускается полный refresh периода; далее — только по change-request.\n"
        )
    if finding.focus_area == "sources_kafka":
        return (
            "Транспорт: Kafka не используется; источник — таблицы SCHEMA_RAW.* "
            "(явная фиксация в ТЗ).\n"
        )
    if finding.focus_area == "fields_logic" and "TAC" in finding.problem:
        return "TAC = substring(imei,1,8); при len(imei)<8 → Unknown.\n"
    if finding.focus_area == "refresh_volume":
        return (
            "NFR: ожидаемый объём — уточнить строк/ГБ в месяц; "
            "SLA готовности витрины — T+1 день после окончания периода.\n"
        )
    return (finding.recommendation or "").strip() + "\n"


def apply_finding_fix(doc_text: str, finding: Finding) -> Tuple[str, str]:
    """
    Вносит правку в текст ТЗ.
    Возвращает (новый_текст, описание_изменения).
    """
    text = doc_text or ""
    fix = build_suggested_fix(finding).rstrip() + "\n"

    if finding.kind == "missing":
        # вставляем блок в конец документа
        sep = "" if text.endswith("\n") or not text else "\n"
        new_text = f"{text}{sep}\n{fix}\n"
        return new_text, f"Добавлен блок «{finding.block}»"

    # замена CLUSTER-заглушки
    if "CLUSTER" in finding.problem or (finding.anchor and "CLUSTER" in (finding.anchor.excerpt or "")):
        replacement = _extract_quoted_fix(finding.recommendation) or "CLUSTER_CDM_NETS_PROD"
        if re.search(r"Кластер:\s*CLUSTER\b", text, flags=re.I):
            new_text = re.sub(
                r"(Кластер:\s*)CLUSTER\b",
                rf"\1{replacement}",
                text,
                count=1,
                flags=re.I,
            )
            return new_text, f"Заменено «CLUSTER» → «{replacement}»"

    excerpt = (finding.anchor.excerpt or "").strip().strip("…")
    if excerpt and len(excerpt) >= 12:
        # ищем устойчивый кусок цитаты в тексте
        candidates = [
            excerpt,
            re.sub(r"\s+", " ", excerpt).strip(),
        ]
        # короткие якоря из цитаты
        for token in re.findall(r".{12,60}", excerpt):
            candidates.append(token.strip())
        for cand in candidates:
            if cand and cand in text:
                # вставляем исправление сразу после найденного фрагмента
                idx = text.find(cand) + len(cand)
                new_text = text[:idx] + "\n" + fix + text[idx:]
                return new_text, "Вставлена правка ИИ после цитаты"

    # fallback — в конец соответствующего раздела по заголовку блока
    title = finding.block
    # пробуем найти заголовок
    pattern = re.compile(rf"(?im)^({re.escape(title)}.*)$")
    m = pattern.search(text)
    if m:
        # вставим после следующего пустого разрыва или через 1 абзац — проще после заголовка
        insert_at = m.end()
        new_text = text[:insert_at] + "\n" + fix + text[insert_at:]
        return new_text, f"Правка ИИ добавлена в блок «{title}»"

    sep = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{sep}\n# Правка ИИ ({title})\n{fix}\n", f"Правка ИИ добавлена в конец документа"
