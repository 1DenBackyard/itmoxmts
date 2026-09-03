/* eslint-disable no-unused-vars */
window.MTSAutofix = (function () {
  const MISSING_TEMPLATES = {
    data_catalog: "Data Catalog\nСсылка на карточку объекта: LINK_DATA_CATALOG\nOwner: USER_OWNER\n",
    jira: "JIRA\nLINK_JIRA_TASK\n",
    sample: "Пример данных\nregion_name | vendor_name | users_cnt | proc_ts | biz_date\nЦентр | Vendor_A | 1200 | 2023-08-01 03:00:00 | 2023-07-01\n",
    ddl: "DDL\nCREATE TABLE SCHEMA_CDM_NETS.TABLE_AGG_DEVICES (\n  FIELD_REGION_NAME string,\n  FIELD_VENDOR_NAME string,\n  FIELD_USERS_CNT bigint,\n  FIELD_PROC_TS timestamp,\n  FIELD_BIZ_DATE date\n) PARTITIONED BY (FIELD_BIZ_DATE);\n",
    changelog: "История изменений\nДата | Автор | Изменение\n2023-08-01 | USER_C | Первичная версия ТЗ\n",
    faq: "FAQ\nQ: Что делать, если region не найден?\nA: Пишем Unknown.\n",
    gitlab: "Исходники проекта / GitLab\nLINK_GITLAB_PROJECT\n",
    problem: "Решаемая проблема\nКратко опишите бизнес-проблему и зачем нужен объект.\n",
    metrics: "Продуктовые метрики\nПеречислите метрики, на которые влияет объект.\n",
    enrichment: "Источники обогащения данных\nУкажите справочники и ключи джойна.\n",
    sinks: "Приёмники данных\nОписание | Кластер | Ссылка на каталог | Сериализация\nTABLE_… | CLUSTER_… | LINK_… | parquet/orc\n",
    flow_schema: "Схема потоков данных\nsource → Kafka/batch → processing → RAW/DDS/CDM\n",
  };

  function suggestedFix(finding) {
    if (finding.kind === "missing") {
      return MISSING_TEMPLATES[finding.block_id] || `${finding.block}\nTODO: заполнить раздел по шаблону.\n`;
    }
    const rec = finding.recommendation || "";
    const m = rec.match(/например\s+[«"']([^«»"']+)[»"']/i)
      || rec.match(/замени[^«"']*[«"']([^«»"']+)[»"']/i);
    if (m) return m[1];
    if (/CLUSTER/i.test(finding.problem) || /CLUSTER/i.test((finding.anchor && finding.anchor.excerpt) || "")) {
      return "CLUSTER_CDM_NETS_PROD";
    }
    if (finding.focus_area === "filtering") {
      return "Шаг 1 / фильтрация:\n- Период = календарный месяц FIELD_BIZ_DATE\n- Исключить тестовые IMSI (если применимо)\n- MS/PS: union distinct FIELD_IMSI\n";
    }
    if (finding.focus_area === "fields_logic") {
      return "Else-branch: если region/vendor не определён → Unknown; абонент сохраняется в агрегате.\n";
    }
    if (finding.focus_area === "refresh_volume") {
      return "Политика late-data: T+5 дней возможен полный refresh месяца; далее — только по CR.\nNFR: объём и SLA готовности — указать явно.\n";
    }
    if (finding.focus_area === "sources_kafka") {
      return "Транспорт: Kafka не используется; источник — таблицы SCHEMA_RAW.*\n";
    }
    return (rec || "").trim() + "\n";
  }

  function applyFix(docText, finding) {
    const text = docText || "";
    const fix = suggestedFix(finding).replace(/\s+$/, "") + "\n";

    if (finding.kind === "missing") {
      const sep = !text || text.endsWith("\n") ? "" : "\n";
      return { text: `${text}${sep}\n${fix}\n`, note: `Добавлен блок «${finding.block}»`, before: "(блок отсутствовал)", after: fix };
    }

    if (/CLUSTER/i.test(finding.problem) || /CLUSTER/i.test((finding.anchor && finding.anchor.excerpt) || "")) {
      const replacement = (fix.match(/CLUSTER_[A-Z0-9_]+/) || ["CLUSTER_CDM_NETS_PROD"])[0];
      if (/Кластер:\s*CLUSTER\b/i.test(text)) {
        const before = (text.match(/Кластер:\s*CLUSTER\b/i) || ["Кластер: CLUSTER"])[0];
        const after = before.replace(/CLUSTER\b/i, replacement);
        return {
          text: text.replace(/Кластер:\s*CLUSTER\b/i, after),
          note: `Заменено «CLUSTER» → «${replacement}»`,
          before,
          after,
        };
      }
    }

    const excerpt = ((finding.anchor && finding.anchor.excerpt) || "").replace(/^…|…$/g, "").trim();
    if (excerpt && excerpt.length >= 12 && text.includes(excerpt.slice(0, Math.min(40, excerpt.length)))) {
      const needle = excerpt.slice(0, Math.min(40, excerpt.length));
      const idx = text.indexOf(needle);
      if (idx >= 0) {
        const end = idx + needle.length;
        return {
          text: text.slice(0, end) + "\n" + fix + text.slice(end),
          note: "Правка вставлена после цитаты",
          before: needle,
          after: needle + "\n" + fix,
        };
      }
    }

    const sep = !text || text.endsWith("\n") ? "" : "\n";
    return {
      text: `${text}${sep}\n# Правка ИИ (${finding.block})\n${fix}\n`,
      note: "Правка добавлена в конец документа",
      before: "(фрагмент не найден)",
      after: fix,
    };
  }

  return { suggestedFix, applyFix };
})();
