from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class BlockDef:
    id: str
    title: str
    aliases: Sequence[str]
    important: bool = True
    # для каких типов документа блок обязателен
    required_for: Sequence[str] = ("flow", "source", "aggregate_mart")


# Эталонные блоки по «Шаблоны документации.pdf» (+ практичные алиасы датасета)
BLOCK_DEFS: List[BlockDef] = [
    BlockDef("general", "Общие сведения", ("общие сведения",)),
    BlockDef(
        "problem",
        "Решаемая проблема",
        ("решаемая проблема",),
        required_for=("flow", "source"),
    ),
    BlockDef(
        "metrics",
        "Продуктовые метрики",
        ("продуктовые метрики",),
        required_for=("flow",),
    ),
    BlockDef("customers", "Заказчики", ("заказчики",)),
    BlockDef(
        "nfr",
        "Нефункциональные требования",
        (
            "нефункциональные требования",
            "бизнес-требования",
            "требования к агрегату",
            "способ загрузки",
            "регламент",
            "глубина данных",
        ),
    ),
    BlockDef("source_systems", "Системы-источники", ("системы-источники", "системы источники")),
    BlockDef(
        "data_catalog",
        "Data Catalog",
        ("data catalog", "каталог данных"),
        required_for=("flow", "aggregate_mart"),
    ),
    BlockDef(
        "gitlab",
        "Исходники проекта / GitLab",
        ("исходники проекта", "gitlab", "исходный код"),
        required_for=("flow",),
    ),
    BlockDef("team", "Команда", ("команда",)),
    BlockDef("jira", "JIRA", ("jira",), required_for=("flow", "aggregate_mart")),
    BlockDef(
        "sources",
        "Источники данных",
        (
            "источники данных",
            "источники и приемники данных",
            "источники и приёмники данных",
            "1. источники данных",
        ),
    ),
    BlockDef(
        "enrichment",
        "Источники обогащения данных",
        ("источники обогащения", "обогащения данных"),
        required_for=("flow",),
    ),
    BlockDef(
        "sinks",
        "Приёмники данных",
        ("приемники данных", "приёмники данных", "приемники:", "приёмники:"),
        required_for=("flow", "source"),
    ),
    BlockDef(
        "flow_schema",
        "Схема потоков данных",
        ("схема потоков данных", "схема потока"),
        required_for=("flow",),
    ),
    BlockDef(
        "algorithm",
        "Алгоритм обработки",
        (
            "алгоритм обработки потока",
            "алгоритм обработки",
            "алгоритм расчёта",
            "алгоритм расчета",
            "шаг 1. фильтрация",
        ),
    ),
    BlockDef(
        "structure",
        "Структура данных",
        ("структура данных", "2. структура данных", "структура данных cdm"),
    ),
    BlockDef(
        "sample",
        "Пример данных",
        ("пример данных",),
        required_for=("flow", "source", "aggregate_mart"),
    ),
    BlockDef("ddl", "DDL", ("ddl",), required_for=("flow", "aggregate_mart")),
    BlockDef("faq", "FAQ", ("faq",), required_for=("flow", "source")),
    BlockDef(
        "changelog",
        "История изменений",
        ("история изменений",),
        required_for=("flow", "source", "aggregate_mart"),
    ),
]

BLOCK_BY_ID: Dict[str, BlockDef] = {b.id: b for b in BLOCK_DEFS}


@dataclass
class DocBlock:
    id: str
    title: str
    content: str
    present: bool
    important: bool
    start_line: Optional[int] = None
    matched_heading: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "DocBlock":
        return cls(
            id=data["id"],
            title=data["title"],
            content=data.get("content") or "",
            present=bool(data.get("present")),
            important=bool(data.get("important", True)),
            start_line=data.get("start_line"),
            matched_heading=data.get("matched_heading") or "",
        )


def _norm_line(line: str) -> str:
    s = (line or "").strip().lower().replace("ё", "е")
    s = re.sub(r"^[\d\.\)\-\–—]+\s*", "", s)
    s = re.sub(r"[•·]\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _match_block_def(line: str) -> Optional[BlockDef]:
    norm = _norm_line(line)
    if not norm or len(norm) > 80:
        return None
    # точное / startswith по алиасам; более длинные алиасы приоритетнее
    candidates = []
    for bdef in BLOCK_DEFS:
        for alias in bdef.aliases:
            a = alias.lower().replace("ё", "е")
            if norm == a or norm.startswith(a + " ") or norm.startswith(a + ":") or norm == a.rstrip(":"):
                candidates.append((len(a), bdef))
            # «Приемники:» как отдельная строка
            if a.endswith(":") and norm.startswith(a[:-1]):
                candidates.append((len(a), bdef))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def parse_document_blocks(text: str, doc_type: str = "aggregate_mart") -> List[DocBlock]:
    """Режет текст по эталонным блокам шаблона. Все блоки возвращаются."""
    lines = (text or "").splitlines()
    hits = []  # (line_idx, BlockDef, heading)
    for i, line in enumerate(lines):
        bdef = _match_block_def(line)
        if bdef is None:
            continue
        # не дублируем подряд один и тот же block id (берём первое вхождение)
        if hits and hits[-1][1].id == bdef.id:
            continue
        hits.append((i, bdef, line.strip()))

    found: Dict[str, DocBlock] = {}
    for idx, (start, bdef, heading) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(lines)
        body_lines = lines[start + 1 : end]
        content = "\n".join(body_lines).strip()
        present = True
        if bdef.id in found:
            prev = found[bdef.id]
            merged = prev.content
            chunk = f"{heading}\n{content}".strip() if content else heading
            if merged and merged != "—":
                merged = f"{merged}\n\n{chunk}".strip()
            else:
                merged = chunk or "—"
            found[bdef.id] = DocBlock(
                id=bdef.id,
                title=bdef.title,
                content=merged,
                present=True,
                important=bdef.important,
                start_line=prev.start_line,
                matched_heading=f"{prev.matched_heading} | {heading}",
            )
        else:
            found[bdef.id] = DocBlock(
                id=bdef.id,
                title=bdef.title,
                content=content if content else "—",
                present=present,
                important=bdef.important,
                start_line=start + 1,
                matched_heading=heading,
            )

    # спец-кейс: «Источники и приёмники» — вытащим приёмники в sinks, если отдельного блока нет
    if "sources" in found and "sinks" not in found:
        src = found["sources"].content
        m = re.search(r"(При[её]мники\s*:?\s*)([\s\S]+)$", src, flags=re.IGNORECASE)
        if m:
            sinks_body = m.group(2).strip()
            sources_body = src[: m.start()].strip()
            found["sources"] = DocBlock(
                id="sources",
                title=BLOCK_BY_ID["sources"].title,
                content=sources_body or "—",
                present=True,
                important=True,
                start_line=found["sources"].start_line,
                matched_heading=found["sources"].matched_heading,
            )
            found["sinks"] = DocBlock(
                id="sinks",
                title=BLOCK_BY_ID["sinks"].title,
                content=sinks_body or "—",
                present=bool(sinks_body),
                important=True,
                matched_heading="Приёмники",
            )

    result: List[DocBlock] = []
    for bdef in BLOCK_DEFS:
        if bdef.id in found:
            result.append(found[bdef.id])
        else:
            required = doc_type in bdef.required_for
            result.append(
                DocBlock(
                    id=bdef.id,
                    title=bdef.title,
                    content="",
                    present=False,
                    important=required,
                )
            )
    return result


def pick_quote(content: str, needles: Sequence[str], fallback_len: int = 160) -> str:
    """Достаёт конкретную цитату из блока."""
    text = (content or "").strip()
    if not text or text == "—":
        return ""
    lower = text.lower().replace("ё", "е")
    for needle in needles:
        n = (needle or "").lower().replace("ё", "е")
        if not n:
            continue
        idx = lower.find(n)
        if idx >= 0:
            start = max(0, idx - 30)
            end = min(len(text), idx + len(needle) + 100)
            snippet = text[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "…" + snippet
            if end < len(text):
                snippet = snippet + "…"
            return snippet
    # первая осмысленная строка / кусок
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:fallback_len] + ("…" if len(compact) > fallback_len else "")
