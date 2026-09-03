from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DEMO_USER_ID, DOC_TYPES, DONENESS_EMOJI, DONENESS_LABELS
from src.storage import Store
from src.ui_components import FOCUS_LABELS, inject_styles

st.set_page_config(page_title="Самообучение", page_icon="📊", layout="wide")
inject_styles()

st.title("📊 Дашборд самообучения аналитика")
st.caption(
    "В статистику попадают только правки со статусом «Исправлено». "
    "Отклонённые и просто просмотренные не учитываются."
)

store = Store()
stats = store.dashboard_stats(DEMO_USER_ID)

c1, c2, c3 = st.columns(3)
c1.metric("Исправлено замечаний", stats["total_fixed"])
strong = [b for b in stats["blocks_ranked"] if b["count"] == 0]
# strong sides approximated inversely later; for now use low-count from known template if empty
c2.metric("Уникальных блоков с ошибками", len(stats["blocks_ranked"]))
top_focus = max(stats["by_focus"].items(), key=lambda x: x[1])[0] if stats["by_focus"] else "—"
c3.metric("Топ фокус-зона", FOCUS_LABELS.get(top_focus, top_focus))

if stats["total_fixed"] == 0:
    st.info(
        "Пока нет исправленных замечаний. Откройте «Работа с документом», "
        "пройдите карточки и нажмите «Исправлено» — тогда здесь появится статистика."
    )
    st.stop()

st.subheader("Прожарка принятых правок")
doneness_df = pd.DataFrame(
    [
        {
            "Прожарка": f"{DONENESS_EMOJI[k]} {DONENESS_LABELS[k]}",
            "Количество": v,
        }
        for k, v in stats["by_doneness"].items()
    ]
)
st.bar_chart(doneness_df.set_index("Прожарка"))

left, right = st.columns(2)

with left:
    st.subheader("Где чаще ошибки")
    weak = stats["blocks_ranked"][:5]
    if weak:
        st.write("В этих блоках ты чаще всего допускаешь пробелы:")
        for item in weak:
            st.markdown(
                f"- **{item['block']}** — {item['count']} исправлений "
                f"(avg score {item['avg_score']})"
            )
    else:
        st.write("Недостаточно данных.")

with right:
    st.subheader("Где ты силён")
    # Сильные стороны: блоки с 1 редким rare/medium_rare или отсутствующие в топе проблем
    rare_blocks = [
        e.block
        for e in stats["events"]
        if e.doneness in ("rare", "medium_rare")
    ]
    weak_set = {b["block"] for b in stats["blocks_ranked"][:3]}
    praise_candidates = []
    for e in stats["events"]:
        if e.block not in weak_set and e.doneness in ("rare", "medium_rare"):
            praise_candidates.append(e.block)
    # также блоки с низким avg score
    for item in reversed(stats["blocks_ranked"]):
        if item["avg_score"] < 0.35:
            praise_candidates.append(item["block"])

    praise = list(dict.fromkeys(praise_candidates))[:5]
    if praise:
        st.write("Здесь заполняешь стабильно хорошо / правки были лёгкими:")
        for block in praise:
            st.markdown(f"- ✅ **{block}**")
    else:
        # fallback praise by focus areas not in top mistakes
        focus_sorted = sorted(stats["by_focus"].items(), key=lambda x: x[1])
        if focus_sorted:
            best = FOCUS_LABELS.get(focus_sorted[0][0], focus_sorted[0][0])
            st.write(f"По текущим данным меньше всего правок в зоне: **{best}** — так держать.")
        else:
            st.write("Продолжай закрывать Well done / Medium — похвала появится на контрасте.")

st.subheader("Рекомендации самообучения")
recs = []
for item in stats["blocks_ranked"][:3]:
    recs.append(
        f"Перед сдачей отдельно перечитай блок «{item['block']}» — "
        f"ты уже исправлял его {item['count']} раз."
    )
focus_top = sorted(stats["by_focus"].items(), key=lambda x: x[1], reverse=True)
for focus, cnt in focus_top[:2]:
    label = FOCUS_LABELS.get(focus, focus)
    if focus == "sources_kafka":
        recs.append("Сверь Kafka-топики/кластер со всеми регионами и таблицей приёмников.")
    elif focus == "fields_logic":
        recs.append("Для каждого поля добавь формулу и else-ветку «не найдено».")
    elif focus == "filtering":
        recs.append("Явно выпиши фильтры периода, исключений и тестовых записей.")
    elif focus == "refresh_volume":
        recs.append("Зафиксируй регламент, объём и политику late-data / refresh.")
    else:
        recs.append(f"Подтяни полноту шаблона в зоне «{label}» ({cnt} правок).")

# unique preserve order
seen = set()
final_recs = []
for r in recs:
    if r not in seen:
        seen.add(r)
        final_recs.append(r)

for i, r in enumerate(final_recs[:5], 1):
    st.markdown(f"{i}. {r}")

st.divider()
st.subheader("Лента исправлений")
rows = [
    {
        "Когда": e.fixed_at,
        "Блок": e.block,
        "Прожарка": DONENESS_LABELS.get(e.doneness, e.doneness),
        "Score": e.score,
        "Тип документа": DOC_TYPES.get(e.doc_type, e.doc_type),
        "Фокус": FOCUS_LABELS.get(e.focus_area, e.focus_area),
    }
    for e in sorted(stats["events"], key=lambda x: x.fixed_at, reverse=True)
]
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

try:
    import plotly.express as px

    st.subheader("Динамика исправлений")
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Дата"] = pd.to_datetime(df["Когда"]).dt.date.astype(str)
        daily = df.groupby("Дата").size().reset_index(name="Исправлено")
        fig = px.bar(daily, x="Дата", y="Исправлено", title="Исправления по дням")
        st.plotly_chart(fig, use_container_width=True)
except Exception:
    pass
