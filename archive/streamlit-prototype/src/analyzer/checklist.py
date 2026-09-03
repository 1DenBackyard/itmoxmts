from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..models import Anchor, Finding, new_finding_id
from ..scoring import enrich_risk
from .blocks import BLOCK_BY_ID, DocBlock, pick_quote


@dataclass
class RuleHit:
    block_id: str
    focus_area: str
    problem: str
    guiding_questions: List[str]
    recommendation: str
    probability: float
    impact: float
    agent: str
    roles: Sequence[str]
    quote_needles: Sequence[str] = ()
    kind: str = "content"  # content | missing


def _block_map(blocks: List[DocBlock]) -> Dict[str, DocBlock]:
    return {b.id: b for b in blocks}


def _present(blocks: Dict[str, DocBlock], block_id: str) -> bool:
    b = blocks.get(block_id)
    return bool(b and b.present and (b.content or "").strip() not in ("", "—"))


def _text_of(blocks: Dict[str, DocBlock], *ids: str) -> str:
    parts = []
    for i in ids:
        b = blocks.get(i)
        if b and b.present:
            parts.append(b.content or "")
    return "\n".join(parts)


def _has_any(text: str, needles: Sequence[str]) -> bool:
    t = (text or "").lower().replace("ё", "е")
    return any(n.lower().replace("ё", "е") in t for n in needles)


def build_missing_block_hits(blocks: List[DocBlock], doc_type: str) -> List[RuleHit]:
    hits: List[RuleHit] = []
    for b in blocks:
        bdef = BLOCK_BY_ID[b.id]
        required = doc_type in bdef.required_for
        if required and not b.present:
            hits.append(
                RuleHit(
                    block_id=b.id,
                    focus_area="template",
                    kind="missing",
                    problem=f"Отсутствует информация в важном блоке «{b.title}».",
                    guiding_questions=[
                        f"Почему в ТЗ нет раздела «{b.title}»?",
                        "Где взять недостающие данные (владелец источника / каталог / команда)?",
                        "Какой минимальный состав раздела нужен для разработки и тестирования?",
                    ],
                    recommendation=(
                        f"Добавь блок «{b.title}» по эталонному шаблону документации "
                        "и заполни конкретными значениями (без заглушек)."
                    ),
                    probability=0.95,
                    impact=0.9 if b.important else 0.6,
                    agent="Agent Analyst",
                    roles=("analyst", "developer", "qa"),
                )
            )
    return hits


def build_content_hits(blocks: List[DocBlock], doc_type: str) -> List[RuleHit]:
    bm = _block_map(blocks)
    hits: List[RuleHit] = []
    full = "\n".join(b.content for b in blocks if b.present)

    # --- sources / kafka / cluster ---
    nfr = _text_of(bm, "nfr")
    sinks = _text_of(bm, "sinks", "sources", "flow_schema")
    algo = _text_of(bm, "algorithm")
    structure = _text_of(bm, "structure")

    if _present(bm, "nfr") and re.search(r"Кластер:\s*CLUSTER\b", nfr, flags=re.I):
        hits.append(
            RuleHit(
                block_id="nfr",
                focus_area="sources_kafka",
                problem="Имя кластера указано как заглушка «CLUSTER» — нельзя однозначно найти объект.",
                guiding_questions=[
                    "Как называется реальный CDM/аналитический кластер?",
                    "Есть ли ссылка на Data Catalog / inventory?",
                ],
                recommendation='Замени «CLUSTER» на фактическое имя, например «CLUSTER_CDM_NETS_PROD».',
                probability=0.9,
                impact=0.92,
                agent="Agent Developer",
                roles=("developer", "qa"),
                quote_needles=("Кластер:", "CLUSTER"),
            )
        )

    transport_text = sinks + "\n" + _text_of(bm, "flow_schema", "sources")
    if _present(bm, "sources") or _present(bm, "sinks") or _present(bm, "flow_schema"):
        if not _has_any(transport_text, ["kafka", "топик", "topic"]):
            if doc_type == "aggregate_mart":
                hits.append(
                    RuleHit(
                        block_id="sources" if _present(bm, "sources") else "sinks",
                        focus_area="sources_kafka",
                        problem="Не ясно, есть ли Kafka на пути к агрегату: таблицы описаны, транспорт не зафиксирован.",
                        guiding_questions=[
                            "Агрегат читает только batch-таблицы или ещё Kafka?",
                            "Если Kafka нет — где это явно сказано?",
                        ],
                        recommendation=(
                            "Либо добавь топики/кластер, либо явную фразу: "
                            "«Kafka не используется, источник — таблицы SCHEMA_RAW.*»."
                        ),
                        probability=0.75,
                        impact=0.7,
                        agent="Agent Developer",
                        roles=("developer", "qa", "analyst"),
                        quote_needles=("TABLE_", "SCHEMA_", "Источник"),
                    )
                )
            else:
                hits.append(
                    RuleHit(
                        block_id="sinks" if _present(bm, "sinks") else "sources",
                        focus_area="sources_kafka",
                        problem="Не описаны Kafka-топики / расположение брокеров.",
                        guiding_questions=[
                            "В каком Kafka-кластере лежат топики?",
                            "Как топики разбиты по регионам?",
                            "Какой retention?",
                        ],
                        recommendation="Добавь таблицу: регион → Kafka-топик → кластер → retention.",
                        probability=0.88,
                        impact=0.95,
                        agent="Agent Developer",
                        roles=("developer", "qa", "analyst"),
                        quote_needles=("Kafka", "топик", "TOPIC"),
                    )
                )

    # --- fields / logic ---
    if _present(bm, "algorithm"):
        if _has_any(algo, ["fallback", "если lac = 0", "substring(imei"]) and not _has_any(
            algo, ["unknown", "не найден", "исключить", "else"]
        ):
            hits.append(
                RuleHit(
                    block_id="algorithm",
                    focus_area="fields_logic",
                    problem="Несостыковка: описан сложный fallback, но нет ветки «значение не найдено».",
                    guiding_questions=[
                        "Что писать в FIELD_REGION_NAME, если region_code не найден?",
                        "Что делать, если TAC отсутствует в справочнике?",
                    ],
                    recommendation=(
                        "Добавь else-branch: «если region/vendor не определён → Unknown / исключить из агрегата»."
                    ),
                    probability=0.82,
                    impact=0.9,
                    agent="Agent QA",
                    roles=("qa", "developer", "analyst"),
                    quote_needles=("fallback", "если lac = 0", "substring(imei"),
                )
            )

        if doc_type == "aggregate_mart" and not _has_any(algo, ["фильтр", "исключ", "where"]):
            hits.append(
                RuleHit(
                    block_id="algorithm",
                    focus_area="filtering",
                    problem="В алгоритме не зафиксированы критерии фильтрации кроме выбора периода.",
                    guiding_questions=[
                        "Берутся ли только активные абоненты?",
                        "Нужно ли исключать тестовые IMSI?",
                        "Как стыкуется окно месяца с FIELD_BIZ_DATE?",
                    ],
                    recommendation="Допиши в шаг 1 явные фильтры периода, исключений и правило MS/PS.",
                    probability=0.72,
                    impact=0.8,
                    agent="Agent QA",
                    roles=("qa", "analyst", "developer"),
                    quote_needles=("Шаг 1", "FIELD_IMSI", "FIELD_BIZ_DATE"),
                )
            )
    elif not _present(bm, "algorithm"):
        pass  # missing hit already covers

    if _present(bm, "structure") and _has_any(structure, ["substring(imei, 1, 8)", "tac"]):
        hits.append(
            RuleHit(
                block_id="structure",
                focus_area="fields_logic",
                problem="Логика вендора завязана на TAC=8 символов — нужно явно подтвердить соответствие справочнику.",
                guiding_questions=[
                    "TABLE_DEVICE_REF ключуется по 8-символьному TAC?",
                    "Как обрабатываются IMEI короче 8 символов?",
                ],
                recommendation="В комментарии к полю добавь: «при len(imei)<8 → Unknown».",
                probability=0.55,
                impact=0.6,
                agent="Agent QA",
                roles=("qa", "developer"),
                quote_needles=("substring(imei", "tac", "VENDOR"),
            )
        )

    # --- refresh / volume ---
    if _present(bm, "nfr"):
        if _has_any(nfr, ["полная перезагрузка", "без upsert"]) and not _has_any(
            nfr, ["late", "опоздав", "пересчёт прошл", "t+"]
        ):
            hits.append(
                RuleHit(
                    block_id="nfr",
                    focus_area="refresh_volume",
                    problem="Указана полная перезагрузка месяца, но нет политики late-data / пересчёта прошлого периода.",
                    guiding_questions=[
                        "Пересчитывается ли прошлый месяц при опоздавших данных?",
                        "Сколько дней после закрытия месяца допускается refresh?",
                    ],
                    recommendation="Добавь правило: «T+N дней возможен полный refresh месяца; далее — только по CR».",
                    probability=0.74,
                    impact=0.8,
                    agent="Agent QA",
                    roles=("qa", "developer"),
                    quote_needles=("перезагрузка", "upsert", "Обновление"),
                )
            )
        if not _has_any(nfr + full, ["объём", "объем", "событий/", "гб", "задерж", "latency"]):
            hits.append(
                RuleHit(
                    block_id="nfr",
                    focus_area="refresh_volume",
                    problem="Нет оценки объёма данных и/или допустимой задержки готовности.",
                    guiding_questions=[
                        "Какой ожидаемый объём за период?",
                        "Какая SLA-задержка готовности витрины?",
                    ],
                    recommendation="Добавь NFR: объём (строк/ГБ) и SLA готовности после окончания периода.",
                    probability=0.65,
                    impact=0.7,
                    agent="Agent Analyst",
                    roles=("analyst", "qa", "developer"),
                    quote_needles=("Регламент", "Глубина", "Инкремент"),
                )
            )

    # filtering for non-agg if algorithm present without filter section detail
    if doc_type != "aggregate_mart" and _present(bm, "algorithm"):
        if not _has_any(algo, ["фильтр", "фильтрац", "where", "услови"]):
            hits.append(
                RuleHit(
                    block_id="algorithm",
                    focus_area="filtering",
                    problem="Не описана фильтрация входных данных.",
                    guiding_questions=[
                        "Какие события отбрасываются?",
                        "Есть ли окно по времени?",
                    ],
                    recommendation="Добавь шаг «Фильтрация данных» с явными условиями.",
                    probability=0.8,
                    impact=0.85,
                    agent="Agent QA",
                    roles=("qa", "developer", "analyst"),
                    quote_needles=("Шаг", "Алгоритм"),
                )
            )

    return hits


def hits_to_findings(
    hits: List[RuleHit],
    blocks: List[DocBlock],
    *,
    doc_id: str,
    doc_type: str,
    reviewer_role: str,
) -> List[Finding]:
    bm = _block_map(blocks)
    findings: List[Finding] = []
    for hit in hits:
        block = bm.get(hit.block_id)
        title = block.title if block else BLOCK_BY_ID.get(hit.block_id, hit.block_id).title if hit.block_id in BLOCK_BY_ID else hit.block_id
        content = block.content if block else ""

        if reviewer_role in hit.roles:
            impact = hit.impact
        else:
            impact = hit.impact * 0.85

        hit_p = hit.probability
        if reviewer_role == "qa" and hit.focus_area in ("filtering", "refresh_volume"):
            hit_p = min(1.0, hit_p + 0.05)
        elif reviewer_role == "developer" and hit.focus_area in ("sources_kafka", "fields_logic"):
            hit_p = min(1.0, hit_p + 0.05)

        score, doneness, traffic = enrich_risk(hit_p, impact)

        if hit.kind == "missing":
            quote = ""
        else:
            quote = pick_quote(content, hit.quote_needles)

        findings.append(
            Finding(
                id=new_finding_id(),
                doc_id=doc_id,
                doc_type=doc_type,  # type: ignore[arg-type]
                reviewer_role=reviewer_role,  # type: ignore[arg-type]
                block=title,
                block_id=hit.block_id,
                problem=hit.problem,
                guiding_questions=list(hit.guiding_questions),
                recommendation=hit.recommendation,
                probability=round(hit_p, 3),
                impact=round(impact, 3),
                score=score,
                doneness=doneness,  # type: ignore[arg-type]
                traffic_light=traffic,
                anchor=Anchor(excerpt=quote),
                agent=hit.agent,
                focus_area=hit.focus_area,
                kind=hit.kind,  # type: ignore[arg-type]
            )
        )

    findings.sort(key=lambda f: (0 if f.kind == "missing" else 1, -f.score))
    return findings


def make_doc_id(name: str, raw: bytes) -> str:
    digest = hashlib.sha1(raw).hexdigest()[:10]
    safe = re.sub(r"[^a-zA-Z0-9а-яА-Я_-]+", "_", name)[:40]
    return f"{safe}_{digest}"


from .blocks import BLOCK_DEFS

TEMPLATE_BLOCKS = [b.title for b in BLOCK_DEFS]

