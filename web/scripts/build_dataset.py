#!/usr/bin/env python3
"""Rebuild web/data/dataset.json with markdown tables where possible."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTO = ROOT / "prototype"
sys.path.insert(0, str(PROTO))

from src.analyzer.blocks import BLOCK_DEFS, parse_document_blocks  # noqa: E402
from src.analyzer.checklist import (  # noqa: E402
    build_content_hits,
    build_missing_block_hits,
    hits_to_findings,
)
from src.pdf_extract import extract_text  # noqa: E402

DATASET = ROOT / "ДатасетТЗ"
OUT = ROOT / "web" / "data" / "dataset.json"


def md_table(headers, rows):
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join([head, sep, body])


def enrich_flow(text: str) -> str:
    # Kafka topics by region
    topics = [
        ("Центр", "TOPIC_GEO3G_CENTRAL", "TOPIC_GEO4G_CENTRAL"),
        ("Дальний Восток", "TOPIC_GEO3G_EAST", "TOPIC_GEO4G_EAST"),
        ("Северо-Запад", "TOPIC_GEO3G_NW", "TOPIC_GEO4G_NW"),
        ("Поволжье", "TOPIC_GEO3G_VOLGA", "TOPIC_GEO4G_VOLGA"),
        ("Сибирь", "TOPIC_GEO3G_SIB", "TOPIC_GEO4G_SIB"),
        ("Юг", "TOPIC_GEO3G_SOUTH", "TOPIC_GEO4G_SOUTH"),
        ("Урал", "TOPIC_GEO3G_URAL", "TOPIC_GEO4G_URAL"),
    ]
    sinks = [
        ("RAW", "TABLE_GEO_RAW_3G", "Данные по 3G (необработанные)"),
        ("RAW", "TABLE_GEO_RAW_4G", "Данные по 4G (необработанные)"),
        ("DDS", "TABLE_GEO_DDS_DETAILED", "Детальные события геолокации"),
        ("ADDS", "TABLE_GEO_ADDS_AGG", "Агрегированные события"),
        ("CDM", "TABLE_GEO_CDM_INTERVALS", "Геоинтервалы по абонентам"),
    ]
    fields_3g = [
        ("FIELD_REGION", "string", "Регион"),
        ("FIELD_DATE_EVENT", "date", "Дата события"),
        ("FIELD_HOUR", "int", "Час события (партиция)"),
        ("FIELD_IMSI", "string", "IMSI"),
        ("FIELD_MSISDN", "string", "MSISDN"),
        ("FIELD_IMEI", "string", "IMEI"),
        ("FIELD_LAT", "double", "Широта геопозиции"),
        ("FIELD_LON", "double", "Долгота геопозиции"),
        ("FIELD_RADIUS", "int", "Радиус точности (метры)"),
        ("FIELD_CELL_START", "long", "ID начальной базовой станции"),
        ("FIELD_CELL_END", "long", "ID конечной БС"),
        ("FIELD_TIME_START", "long", "Время начала события"),
        ("FIELD_TIME_END", "long", "Время окончания события"),
        ("FIELD_LOC_ACCURACY", "int", "Точность локации (метры)"),
        ("FIELD_VENDOR", "string", "Вендор оборудования БС"),
    ]
    fields_4g = fields_3g[:-1] + [("FIELD_SERVICE_TYPE", "int", "Тип формата связи (услуга)")]

    # Replace messy table regions with markdown
    text = re.sub(
        r"Регион Топик 3G Топик 4G[\s\S]*?(?=Приемники:|Приёмники:)",
        md_table(["Регион", "Топик 3G", "Топик 4G"], topics) + "\n\n",
        text,
        count=1,
    )
    text = re.sub(
        r"Слой Таблица Описание\s*RAW[\s\S]*?(?=Структура данных)",
        md_table(["Слой", "Таблица", "Описание"], sinks) + "\n\n",
        text,
        count=1,
    )
    text = re.sub(
        r"Таблица: TABLE_GEO_RAW_3G\s*Поле Тип данных Описание[\s\S]*?(?=Таблица: TABLE_GEO_RAW_4G)",
        "Таблица: TABLE_GEO_RAW_3G\n"
        + md_table(["Поле", "Тип данных", "Описание"], fields_3g)
        + "\n\n",
        text,
        count=1,
    )
    text = re.sub(
        r"Таблица: TABLE_GEO_RAW_4G\s*Поле Тип данных Описание[\s\S]*?(?=Дополнительная информация|FAQ|$)",
        "Таблица: TABLE_GEO_RAW_4G\n"
        + md_table(["Поле", "Тип данных", "Описание"], fields_4g)
        + "\n\n",
        text,
        count=1,
    )
    return text


def enrich_source(text: str) -> str:
    topics = [
        ("Центр", "TOPIC_MSCP_CDR_CENTRAL", "Папка"),
        ("Дальний Восток", "TOPIC_MSCP_CDR_EAST", "Папка"),
        ("Сибирь", "TOPIC_MSCP_CDR_SIB", "Папка"),
        ("Северо-Запад", "TOPIC_MSCP_CDR_NW", "Папка"),
        ("Поволжье", "TOPIC_MSCP_CDR_VOLGA", "Папка"),
        ("Юг", "TOPIC_MSCP_CDR_SOUTH", "Папка"),
    ]
    fields = [
        ("FIELD_REGION", "string", "Название региона"),
        ("FIELD_BIZ_DATE", "date", "Бизнес-дата события"),
        ("FIELD_HOUR", "int", "Часовая партиция"),
        ("FIELD_IMSI", "bigint", "IMSI"),
        ("FIELD_CALLING_NUMBER", "string", "Номер вызывающего абонента"),
        ("FIELD_CALLED_NUMBER", "string", "Номер вызываемого абонента"),
        ("FIELD_CALL_START_TIME", "timestamp", "Время начала вызова"),
        ("FIELD_CALL_END_TIME", "timestamp", "Время окончания вызова"),
        ("FIELD_CALL_DURATION", "int", "Длительность вызова (сек)"),
        ("FIELD_IS_ROAMING", "string", "Признак роуминга (true/false)"),
        ("FIELD_OL_SERVICE_TYPE", "tinyint", "Тип сервиса"),
        ("FIELD_TIME_ZONE_SHIFT", "string", "Сдвиг часового пояса"),
        ("FIELD_TIMEZONE_CALC", "int", "Вычисленный сдвиг в минутах"),
        ("FIELD_BALANCE", "double", "Текущий баланс абонента"),
        ("FIELD_BALANCE_EXPIRE", "timestamp", "Срок истечения баланса"),
    ]
    text = re.sub(
        r"Регион\s*\(?Kafka\)?[\s\S]*?(?=Приёмники:|Приемники:)",
        md_table(["Регион", "Kafka-топик", "SFTP/HDFS"], topics) + "\n\n",
        text,
        count=1,
        flags=re.I,
    )
    # fallback if pattern different
    if "TOPIC_MSCP_CDR_CENTRAL" in text and "| Регион |" not in text:
        text = text.replace(
            "Данные поступают в Kafka\nпо топикам, соответствующим регионам:",
            "Данные поступают в Kafka по топикам, соответствующим регионам:\n\n"
            + md_table(["Регион", "Kafka-топик", "SFTP/HDFS"], topics),
        )
    text = re.sub(
        r"Таблица: TABLE_MSCP_RAW_KFK[\s\S]*?Поле Тип данных Описание[\s\S]*?(?=FAQ|$)",
        "Таблица: TABLE_MSCP_RAW_KFK\n"
        + md_table(["Поле", "Тип данных", "Описание"], fields)
        + "\n\n",
        text,
        count=1,
    )
    return text


def enrich_agg(text: str) -> str:
    sources = [
        ("SCHEMA_RAW", "TABLE_IUM_RAW_PS", "Необработанные данные по интернет-трафику (GPRS)"),
        ("SCHEMA_RAW", "TABLE_IUM_RAW_MS", "Необработанные данные по звонкам и SMS"),
        ("SCHEMA_ADDS", "TABLE_BS_REF", "Справочник базовых станций"),
        ("SCHEMA_DIC", "TABLE_REGION_REF", "Справочник регионов"),
        ("SCHEMA_DIC", "TABLE_DEVICE_REF", "Справочник устройств"),
    ]
    fields = [
        ("1", "FIELD_REGION_NAME", "string", "Название региона",
         "Последнее значение region_name за месяц; сначала по (lac, cell), затем fallback"),
        ("2", "FIELD_VENDOR_NAME", "string", "Наименование вендора устройства",
         "substring(imei, 1, 8) = tac → vendor_name"),
        ("3", "FIELD_USERS_CNT", "bigint", "Уникальное количество абонентов (IMSI)",
         "count(distinct FIELD_IMSI)"),
        ("4", "FIELD_PROC_TS", "timestamp", "Дата/время создания агрегата",
         "Метка обработки DAG"),
        ("5", "FIELD_BIZ_DATE", "date", "Бизнес-дата (1-е число месяца)",
         "Пример: 01.07.2023–31.07.2023 → 2023-07-01"),
    ]
    reqs = [
        ("Регламент расчёта", "Ежемесячно"),
        ("Период агрегации", "Календарный месяц"),
        ("Глубина данных", "Исторические данные — с 01.05.2023"),
        ("Региональная агрегация", "Да (по региону)"),
        ("Часовой пояс", "UTC"),
        ("Поле партиционирования", "FIELD_BIZ_DATE"),
        ("Обновление", "Только полная перезагрузка месяца (без upsert)"),
    ]

    # Replace sources table area
    text = re.sub(
        r"1\.\s*Источники данных\s*Схема Таблица Описание[\s\S]*?(?=2\.\s*Структура данных)",
        "1. Источники данных\n"
        + md_table(["Схема", "Таблица", "Описание"], sources)
        + "\n\n",
        text,
        count=1,
    )
    text = re.sub(
        r"2\.\s*Структура данных CDM\s*Таблица: TABLE_AGG_DEVICES[\s\S]*?(?=Алгоритм расчёта)",
        "2. Структура данных CDM\nТаблица: TABLE_AGG_DEVICES\n"
        + md_table(
            ["№", "Поле", "Тип данных", "Описание", "Комментарий"],
            fields,
        )
        + "\n\n",
        text,
        count=1,
    )
    text = re.sub(
        r"Требования к агрегату\s*Требование Значение[\s\S]*$",
        "Требования к агрегату\n" + md_table(["Требование", "Значение"], reqs) + "\n",
        text,
        count=1,
    )
    return text


def blank_template(doc_type: str) -> str:
    parts = []
    for b in BLOCK_DEFS:
        if doc_type not in b.required_for and not (
            b.id in ("general", "customers", "team", "sources", "structure", "algorithm", "nfr", "source_systems")
        ):
            # include required + core sections for blank
            if doc_type not in b.required_for:
                continue
        if doc_type not in b.required_for and b.id not in (
            "general",
            "customers",
            "nfr",
            "source_systems",
            "team",
            "sources",
            "algorithm",
            "structure",
        ):
            continue
        parts.append(f"{b.title}\n\n")
    # always include all required_for this type
    parts = []
    for b in BLOCK_DEFS:
        if doc_type in b.required_for or b.id in ("general", "customers", "team", "source_systems", "sources", "structure", "algorithm", "nfr"):
            parts.append(f"{b.title}\n\n")
    # dedupe preserve order
    seen = set()
    out = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return "".join(out).strip() + "\n"


def main():
    samples = []
    for path in sorted(DATASET.glob("*.pdf")):
        if "Шаблон" in path.name:
            continue
        text = extract_text(path.name, path.read_bytes())
        if "7-9" in path.name:
            doc_type, label = "aggregate_mart", "Витрина-агрегат (эталон)"
            text = enrich_agg(text)
        elif "5-6" in path.name:
            doc_type, label = "source", "Система-источник (эталон)"
            text = enrich_source(text)
        else:
            doc_type, label = "flow", "Потоки данных (эталон)"
            text = enrich_flow(text)

        blocks = parse_document_blocks(text, doc_type=doc_type)
        hits = build_missing_block_hits(blocks, doc_type) + build_content_hits(blocks, doc_type)
        findings = hits_to_findings(
            hits, blocks, doc_id=path.stem, doc_type=doc_type, reviewer_role="developer"
        )
        samples.append(
            {
                "id": path.stem,
                "filename": path.name,
                "label": label,
                "doc_type": doc_type,
                "text": text,
                "blocks": [b.to_dict() for b in blocks],
                "findings": [f.to_dict() for f in findings],
            }
        )

    templates = {
        "flow": blank_template("flow"),
        "source": blank_template("source"),
        "aggregate_mart": blank_template("aggregate_mart"),
    }

    block_defs = [
        {
            "id": b.id,
            "title": b.title,
            "aliases": list(b.aliases),
            "important": b.important,
            "required_for": list(b.required_for),
        }
        for b in BLOCK_DEFS
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"block_defs": block_defs, "samples": samples, "blank_templates": templates},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", OUT, "samples", len(samples))
    for s in samples:
        print(s["doc_type"], "tables", s["text"].count("| ---"), "findings", len(s["findings"]))


if __name__ == "__main__":
    main()
