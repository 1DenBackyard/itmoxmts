window.MTSLearning = (function () {
  const STORAGE_KEY = "mts_learning_progress_v1";

  const CATEGORIES = {
    incompleteness: "Неполнота",
    ambiguity: "Неоднозначность",
    contradiction: "Противоречия",
    logic: "Ошибки логики и расчётов",
    unverifiable: "Непроверяемость",
    formatting: "Нарушения оформления и терминологии",
  };

  const BLOCKS = {
    goal_scope: "Цель и границы задачи",
    sources_structure: "Источники и структура данных",
    flows_load: "Потоки и загрузка",
    transforms: "Преобразования и расчёты",
    data_quality: "Качество данных и исключения",
    acceptance: "Результат и критерии приёмки",
    unknown: "Не определён",
  };

  const DOC_TYPE_LABELS = {
    all: "Все типы",
    flow: "Описание потоков",
    source: "Описание источника",
    aggregate_mart: "Описание витрины",
  };

  const SEV_LABELS = {
    rare: "Rare · Незначительные",
    medium: "Medium · Существенные",
    well_done: "Well Done · Критические",
  };

  const SEV_SHORT = {
    rare: "Rare",
    medium: "Medium",
    well_done: "Well Done",
  };

  const SEV_RANK = { well_done: 3, medium: 2, rare: 1 };

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadStore() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch (_) {
      return {};
    }
  }

  function saveStore(store) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }

  function hydrate(raw) {
    const store = loadStore();
    const findings = (raw.findings || []).map((f) => {
      const patch = (store.findings && store.findings[f.id]) || {};
      return { ...f, ...patch };
    });
    const checklist = store.checklist
      ? store.checklist
      : (raw.checklist_seed || []).map((c) => ({ ...c }));
    return {
      demo: !!raw.demo,
      demo_note: raw.demo_note || "Демонстрационные данные",
      documents: (raw.documents || []).slice(),
      findings,
      checklist,
    };
  }

  function persistFinding(data, finding) {
    const store = loadStore();
    store.findings = store.findings || {};
    store.findings[finding.id] = {
      confirm_status: finding.confirm_status,
      fix_status: finding.fix_status,
      reject_reason: finding.reject_reason || "",
    };
    store.checklist = data.checklist;
    saveStore(store);
  }

  function persistChecklist(data) {
    const store = loadStore();
    store.checklist = data.checklist;
    saveStore(store);
  }

  function daysAgo(n) {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - n);
    return d;
  }

  function parseDate(s) {
    const d = new Date(s + "T00:00:00");
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function docById(data, id) {
    return (data.documents || []).find((d) => d.id === id);
  }

  function filterDocs(data, filters) {
    const now = new Date();
    now.setHours(23, 59, 59, 999);
    let minDate = null;
    if (filters.period === "30") minDate = daysAgo(30);
    if (filters.period === "90") minDate = daysAgo(90);

    return (data.documents || []).filter((doc) => {
      if (filters.docType !== "all" && doc.doc_type !== filters.docType) return false;
      const dt = parseDate(doc.checked_at);
      if (minDate && dt && dt < minDate) return false;
      if (minDate && dt && dt > now) return false;
      return true;
    });
  }

  function filterFindings(data, filters) {
    const docs = filterDocs(data, filters);
    const docIds = new Set(docs.map((d) => d.id));
    return (data.findings || []).filter((f) => {
      if (!docIds.has(f.doc_id)) return false;
      if (!filters.severity[f.severity]) return false;
      return true;
    });
  }

  function confirmedFindings(list) {
    return list.filter((f) => f.confirm_status === "confirmed");
  }

  function summary(data, filters) {
    const docs = filterDocs(data, filters);
    const findings = filterFindings(data, filters);
    const confirmed = confirmedFindings(findings);
    const fixed = confirmed.filter((f) => f.fix_status === "fixed");
    return {
      docs: docs.length,
      confirmed: confirmed.length,
      fixed: fixed.length,
      findings: findings.length,
      confirmedList: confirmed,
      allFiltered: findings,
      docsList: docs,
    };
  }

  function groupByTopic(confirmed) {
    const map = {};
    confirmed.forEach((f) => {
      const key = f.topic_key || f.id;
      if (!map[key]) {
        map[key] = {
          topic_key: key,
          topic_title: f.topic_title,
          category: f.category,
          severity: f.severity,
          semantic_block: f.semantic_block,
          recommendation: f.fix_suggestion,
          checklist_rule: f.checklist_rule,
          findings: [],
          docIds: new Set(),
        };
      }
      map[key].findings.push(f);
      map[key].docIds.add(f.doc_id);
      if (SEV_RANK[f.severity] > SEV_RANK[map[key].severity]) {
        map[key].severity = f.severity;
      }
    });
    return Object.values(map).map((g) => ({
      ...g,
      docCount: g.docIds.size,
      docs: [...g.docIds],
    }));
  }

  function focusCards(data, filters, sum) {
    if (sum.docs < 2) return { mode: "single_or_empty", cards: [] };
    const groups = groupByTopic(sum.confirmedList).filter((g) => g.docCount >= 2);
    groups.sort((a, b) => {
      const sev = SEV_RANK[b.severity] - SEV_RANK[a.severity];
      if (sev) return sev;
      return b.docCount - a.docCount;
    });
    return { mode: "ok", cards: groups.slice(0, 3), totalDocs: sum.docs };
  }

  function aggregateBy(confirmed, keyFn, labelFn) {
    const map = {};
    confirmed.forEach((f) => {
      const key = keyFn(f);
      if (!map[key]) {
        map[key] = {
          key,
          label: labelFn(f, key),
          count: 0,
          docIds: new Set(),
          sev: { rare: 0, medium: 0, well_done: 0 },
          findings: [],
        };
      }
      map[key].count += 1;
      map[key].docIds.add(f.doc_id);
      map[key].sev[f.severity] = (map[key].sev[f.severity] || 0) + 1;
      map[key].findings.push(f);
    });
    return Object.values(map)
      .map((r) => ({ ...r, docCount: r.docIds.size }))
      .sort((a, b) => b.count - a.count || b.docCount - a.docCount);
  }

  function pageState(data, filters) {
    const sum = summary(data, filters);
    if (!data.documents.length) return { kind: "no_checks", sum };
    if (!sum.docs && (filters.period !== "all" || filters.docType !== "all" || !allSeverityOn(filters))) {
      return { kind: "no_filter_match", sum };
    }
    if (!sum.docs) return { kind: "no_checks", sum };
    const hasConfirmedAnywhere = (data.findings || []).some((f) => f.confirm_status === "confirmed");
    if (!hasConfirmedAnywhere) return { kind: "no_confirmed", sum };
    if (!sum.confirmed && sum.findings.length) {
      // filters hide confirmed
      const anyConfirmedInPeriod = confirmedFindings(sum.allFiltered).length;
      if (!anyConfirmedInPeriod) return { kind: "no_filter_match", sum };
    }
    return { kind: "ok", sum };
  }

  function allSeverityOn(filters) {
    return filters.severity.rare && filters.severity.medium && filters.severity.well_done;
  }

  function defaultFilters() {
    return {
      period: "all",
      docType: "all",
      severity: { rare: true, medium: true, well_done: true },
      repeatsView: "categories",
      expandedKey: null,
      drawerId: null,
      rejectPromptId: null,
    };
  }

  function addChecklistRule(data, text, sourceFindingId) {
    const normalized = String(text || "").trim();
    if (!normalized) return false;
    const exists = data.checklist.some(
      (c) => c.text.trim().toLowerCase() === normalized.toLowerCase()
    );
    if (exists) return false;
    data.checklist.push({
      id: "cl_" + Date.now(),
      text: normalized,
      source_finding_id: sourceFindingId || null,
      done: false,
    });
    persistChecklist(data);
    return true;
  }

  function resetChecklistMarks(data) {
    data.checklist.forEach((c) => {
      c.done = false;
    });
    persistChecklist(data);
  }

  function highlightExcerpt(excerpt, highlight) {
    const src = escapeHtml(excerpt || "");
    const h = String(highlight || "").trim();
    if (!h) return src;
    const eq = escapeHtml(h);
    const re = new RegExp(eq.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    return src.replace(re, (m) => `<mark class="learn-mark">${m}</mark>`);
  }

  function sevDots(sev) {
    return ["well_done", "medium", "rare"]
      .map((k) => {
        const n = sev[k] || 0;
        if (!n) return "";
        return `<span class="sev-pill ${k}">${SEV_SHORT[k]} · ${n}</span>`;
      })
      .join("");
  }

  function render(opts) {
    const {
      root,
      data,
      filters,
      toast,
      onFilters,
      onOpenDrawer,
      onCloseDrawer,
      onExpand,
      onFindingAction,
      onChecklist,
      onNavigateStart,
      onNavigateReview,
    } = opts;

    const ps = pageState(data, filters);
    const sum = ps.sum;
    const focus = focusCards(data, filters, sum);
    const confirmed = sum.confirmedList || [];
    const byCat = aggregateBy(
      confirmed,
      (f) => f.category,
      (f, key) => CATEGORIES[key] || key
    );
    const byBlock = aggregateBy(
      confirmed,
      (f) => f.semantic_block || "unknown",
      (f, key) => BLOCKS[key] || BLOCKS.unknown
    );
    const repeats = filters.repeatsView === "blocks" ? byBlock : byCat;
    const drawer = filters.drawerId
      ? data.findings.find((f) => f.id === filters.drawerId)
      : null;
    const drawerDoc = drawer ? docById(data, drawer.doc_id) : null;

    root.innerHTML = `
      <div class="shell learn-shell">
        <div class="topbar">
          <div class="brand">
            <div class="brand-mark"><img src="assets/mts_logo.png" alt="МТС" /></div>
            <div>
              <h1>Мой прогресс</h1>
              <p>Учитесь на своих проверках: находите закономерности и улучшайте следующие ТЗ</p>
            </div>
          </div>
          <div class="btn-row" style="margin:0">
            <button class="btn btn-secondary btn-sm" data-nav="start">Проверить ТЗ</button>
          </div>
        </div>

        ${data.demo ? `<div class="demo-banner">${escapeHtml(data.demo_note)}</div>` : ""}
        ${toast ? `<div class="toast">${escapeHtml(toast)}</div>` : ""}

        <section class="card learn-filters">
          <div class="learn-filters-grid">
            <div>
              <div class="filter-label">Период</div>
              <div class="seg">
                ${[["all", "Всё время"], ["30", "30 дней"], ["90", "90 дней"]].map(([v, l]) => `
                  <button class="seg-btn ${filters.period === v ? "active" : ""}" data-period="${v}">${l}</button>
                `).join("")}
              </div>
            </div>
            <div>
              <div class="filter-label">Тип документа</div>
              <select id="learn-doc-type" class="learn-select">
                ${Object.entries(DOC_TYPE_LABELS).map(([k, v]) => `
                  <option value="${k}" ${filters.docType === k ? "selected" : ""}>${v}</option>
                `).join("")}
              </select>
            </div>
          </div>
          <div class="filter-label" style="margin-top:14px">Серьёзность</div>
          <div class="sev-grid sev-grid-compact">
            ${["rare", "medium", "well_done"].map((k) => `
              <label class="sev-card ${filters.severity[k] ? "selected" : ""}">
                <input type="checkbox" data-sev="${k}" ${filters.severity[k] ? "checked" : ""} />
                <span class="sev-title">${SEV_LABELS[k]}</span>
              </label>
            `).join("")}
          </div>
        </section>

        ${ps.kind === "no_checks" ? emptyBlock(
          "Загрузите первое ТЗ — здесь появятся ваши примеры и рекомендации",
          "Проверить ТЗ",
          "start"
        ) : ""}
        ${ps.kind === "no_confirmed" ? emptyBlock(
          "Подтвердите найденные проблемы, чтобы сформировать персональные рекомендации",
          "Посмотреть замечания",
          "review"
        ) : ""}
        ${ps.kind === "no_filter_match" ? emptyBlock(
          "По выбранным фильтрам ничего не найдено",
          "Сбросить фильтры",
          "reset"
        ) : ""}

        ${ps.kind === "ok" || (sum.docs > 0 && ps.kind !== "no_checks") ? `
          <section class="stat-row learn-stats">
            <div class="stat"><div class="n">${sum.docs}</div><div class="l">Проверено ТЗ</div></div>
            <div class="stat"><div class="n">${sum.confirmed}</div><div class="l">Подтверждено замечаний</div></div>
            <div class="stat"><div class="n">${sum.fixed}</div><div class="l">Исправлено замечаний</div></div>
          </section>
          <p class="learn-footnote">Повторные проверки одного документа не увеличивают число ТЗ. Прогресс — снижение повторяемости ошибок в новых документах, а не число исправлений.</p>
        ` : ""}

        ${ps.kind === "ok" || sum.docs > 0 ? `
          <section class="card learn-section">
            <h2>Фокус на следующем ТЗ</h2>
            ${sum.docs < 2 ? `
              <p class="learn-empty-inline">Для поиска повторяющихся ошибок нужны проверки нескольких ТЗ. Сейчас доступны разбор примеров и чек-лист.</p>
            ` : focus.cards.length ? `
              <div class="focus-grid">
                ${focus.cards.map((c) => focusCardHtml(c, sum.docs)).join("")}
              </div>
            ` : `
              <p class="learn-empty-inline">В выбранных проверках повторяющиеся подтверждённые ошибки не найдены. Это не гарантия качества ТЗ.</p>
            `}
          </section>

          <section class="card learn-section">
            <div class="learn-section-head">
              <h2>Мои повторяющиеся ошибки</h2>
              <div class="seg">
                <button class="seg-btn ${filters.repeatsView === "categories" ? "active" : ""}" data-repeats="categories">По категориям</button>
                <button class="seg-btn ${filters.repeatsView === "blocks" ? "active" : ""}" data-repeats="blocks">По блокам ТЗ</button>
              </div>
            </div>
            ${confirmed.length ? `
              <div class="repeat-list">
                ${repeats.map((row) => repeatRowHtml(row, filters, data)).join("")}
              </div>
            ` : `<p class="learn-empty-inline">Нет подтверждённых замечаний в текущем срезе.</p>`}
          </section>

          <section class="card learn-section">
            <div class="learn-section-head">
              <h2>Мой чек-лист перед отправкой ТЗ</h2>
              <button class="btn btn-primary btn-sm" data-check-start>Начать проверку нового ТЗ</button>
            </div>
            <p class="learn-footnote" style="margin-top:0">Личные вопросы для самопроверки. Повторное добавление того же правила не создаёт дубликат.</p>
            <div class="checklist">
              ${data.checklist.length ? data.checklist.map((item) => `
                <div class="check-item ${item.done ? "done" : ""}" data-check-id="${item.id}">
                  <label class="check-main">
                    <input type="checkbox" data-check-toggle="${item.id}" ${item.done ? "checked" : ""} />
                    <span contenteditable="true" data-check-edit="${item.id}" spellcheck="true">${escapeHtml(item.text)}</span>
                  </label>
                  <button class="btn btn-ghost btn-sm" data-check-del="${item.id}" title="Удалить">Удалить</button>
                </div>
              `).join("") : `<p class="learn-empty-inline">Чек-лист пуст — добавьте правило из разбора ошибки.</p>`}
            </div>
            <div class="btn-row">
              <input type="text" id="check-new" class="learn-input" placeholder="Новый пункт чек-листа" />
              <button class="btn btn-secondary btn-sm" data-check-add>Добавить</button>
            </div>
          </section>
        ` : ""}
      </div>

      ${drawer ? drawerHtml(drawer, drawerDoc) : ""}
    `;

    bind({
      root,
      data,
      filters,
      onFilters,
      onOpenDrawer,
      onCloseDrawer,
      onExpand,
      onFindingAction,
      onChecklist,
      onNavigateStart,
      onNavigateReview,
    });
  }

  function emptyBlock(text, btn, action) {
    return `
      <section class="card learn-empty">
        <p>${escapeHtml(text)}</p>
        <button class="btn btn-primary" data-empty-act="${action}">${escapeHtml(btn)}</button>
      </section>
    `;
  }

  function focusCardHtml(c, totalDocs) {
    return `
      <article class="focus-card">
        <h3>${escapeHtml(c.topic_title)}</h3>
        <div class="focus-meta">
          <span>${escapeHtml(CATEGORIES[c.category] || c.category)}</span>
          <span>·</span>
          <span>${escapeHtml(BLOCKS[c.semantic_block] || BLOCKS.unknown)}</span>
          <span>·</span>
          <span class="sev-pill ${c.severity}">${SEV_SHORT[c.severity]}</span>
        </div>
        <p class="focus-count">Повторяется в ${c.docCount} из ${totalDocs} подходящих ТЗ.</p>
        <p class="focus-rec">«${escapeHtml(c.recommendation)}»</p>
            <div class="btn-row" style="margin-top:12px">
          <button class="btn btn-secondary btn-sm" data-focus-example="${c.topic_key}">Разобрать пример</button>
          <button class="btn btn-ghost btn-sm" data-focus-check-topic="${c.topic_key}">Добавить в чек-лист</button>
        </div>
      </article>
    `;
  }

  function repeatRowHtml(row, filters, data) {
    const open = filters.expandedKey === row.key;
    return `
      <div class="repeat-row ${open ? "open" : ""}">
        <button class="repeat-head" data-expand="${row.key}">
          <div>
            <strong>${escapeHtml(row.label)}</strong>
            <div class="repeat-sub">${row.count} подтверждённых · ${row.docCount} ТЗ</div>
          </div>
          <div class="sev-row">${sevDots(row.sev)}</div>
        </button>
        ${open ? `
          <div class="repeat-body">
            ${row.findings.map((f) => {
              const doc = docById(data, f.doc_id);
              return `
                <div class="repeat-finding">
                  <div>
                    <div class="rf-doc">${escapeHtml(doc ? doc.title : f.doc_id)}</div>
                    <div class="rf-excerpt">${escapeHtml(f.excerpt)}</div>
                  </div>
                  <button class="btn btn-secondary btn-sm" data-open-finding="${f.id}">Разобрать</button>
                </div>
              `;
            }).join("")}
          </div>
        ` : ""}
      </div>
    `;
  }

  function drawerHtml(f, doc) {
    return `
      <div class="drawer-backdrop" data-drawer-close>
        <aside class="drawer" role="dialog" aria-label="Разбор на моём примере">
          <div class="drawer-head">
            <div>
              <div class="eyebrow">Разбор на моём примере</div>
              <h2>${escapeHtml(f.topic_title)}</h2>
            </div>
            <button class="btn btn-ghost btn-sm" data-drawer-close>Закрыть</button>
          </div>
          <div class="drawer-body">
            <section>
              <h3>1. Где найдено</h3>
              <p>${escapeHtml(doc ? doc.title : f.doc_id)} · ${escapeHtml(f.section_title || "—")}</p>
              <p class="muted">${escapeHtml(BLOCKS[f.semantic_block] || BLOCKS.unknown)} · ${escapeHtml(CATEGORIES[f.category] || "")} · <span class="sev-pill ${f.severity}">${SEV_SHORT[f.severity]}</span></p>
              ${(f.tags || []).length ? `<div class="tag-row">${f.tags.map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>` : ""}
            </section>
            <section>
              <h3>2. Исходный фрагмент</h3>
              <blockquote class="learn-quote">${highlightExcerpt(f.excerpt, f.highlight)}</blockquote>
            </section>
            <section>
              <h3>3. Что не так</h3>
              <p>${escapeHtml(f.explanation)}</p>
            </section>
            <section>
              <h3>4. Чем грозит</h3>
              <p>${escapeHtml(f.impact)}</p>
            </section>
            <section>
              <h3>5. Как исправить</h3>
              <p>${escapeHtml(f.fix_suggestion)}</p>
              <p class="muted">Предложение не применяется к документу автоматически.</p>
            </section>
            <section>
              <h3>6. Что запомнить</h3>
              <p class="rule-box">${escapeHtml(f.checklist_rule)}</p>
            </section>
            <div class="drawer-status">
              Статус: <strong>${f.confirm_status === "confirmed" ? "подтверждено" : f.confirm_status === "rejected" ? "отклонено" : "предложено"}</strong>
              · исправление: <strong>${f.fix_status === "fixed" ? "исправлено" : "открыто"}</strong>
            </div>
            ${f.confirm_status !== "confirmed" ? `
              <div class="btn-row">
                <button class="btn btn-primary btn-sm" data-act="confirm">Подтвердить замечание</button>
              </div>
            ` : ""}
            ${f.confirm_status !== "rejected" ? `
              <div class="btn-row">
                <button class="btn btn-ghost btn-sm" data-act="reject">Не согласен</button>
              </div>
              <div id="reject-box" class="reject-box" hidden>
                <textarea id="reject-reason" placeholder="Причина (необязательно)" rows="2"></textarea>
                <button class="btn btn-secondary btn-sm" data-act="reject-submit">Отклонить</button>
              </div>
            ` : ""}
            ${f.confirm_status === "confirmed" && f.fix_status !== "fixed" ? `
              <div class="btn-row">
                <button class="btn btn-secondary btn-sm" data-act="fixed">Отметить исправленным</button>
              </div>
            ` : ""}
            <div class="btn-row">
              <button class="btn btn-secondary btn-sm" data-act="checklist">Добавить правило в чек-лист</button>
            </div>
          </div>
        </aside>
      </div>
    `;
  }

  function bind(ctx) {
    const {
      root,
      data,
      filters,
      onFilters,
      onOpenDrawer,
      onCloseDrawer,
      onExpand,
      onFindingAction,
      onChecklist,
      onNavigateStart,
      onNavigateReview,
    } = ctx;

    root.querySelectorAll("[data-period]").forEach((btn) => {
      btn.addEventListener("click", () => onFilters({ period: btn.dataset.period }));
    });
    const docType = root.querySelector("#learn-doc-type");
    if (docType) {
      docType.addEventListener("change", () => onFilters({ docType: docType.value }));
    }
    root.querySelectorAll("[data-sev]").forEach((el) => {
      el.addEventListener("change", () => {
        const severity = { ...filters.severity, [el.dataset.sev]: el.checked };
        onFilters({ severity });
      });
    });
    root.querySelectorAll("[data-repeats]").forEach((btn) => {
      btn.addEventListener("click", () => onFilters({ repeatsView: btn.dataset.repeats }));
    });
    root.querySelectorAll("[data-expand]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.expand;
        onExpand(filters.expandedKey === key ? null : key);
      });
    });
    root.querySelectorAll("[data-open-finding]").forEach((btn) => {
      btn.addEventListener("click", () => onOpenDrawer(btn.dataset.openFinding));
    });
    root.querySelectorAll("[data-focus-example]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const topic = btn.dataset.focusExample;
        const list = confirmedFindings(filterFindings(data, filters)).filter((f) => f.topic_key === topic);
        if (list[0]) onOpenDrawer(list[0].id);
      });
    });
    root.querySelectorAll("[data-focus-check-topic]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const topic = btn.dataset.focusCheckTopic;
        const sample = (data.findings || []).find((f) => f.topic_key === topic && f.checklist_rule);
        if (sample) onChecklist("add", { text: sample.checklist_rule, source: sample.id });
      });
    });
    root.querySelectorAll("[data-drawer-close]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (el.classList.contains("drawer-backdrop") && e.target !== el) return;
        onCloseDrawer();
      });
    });
    const drawer = root.querySelector(".drawer");
    if (drawer) {
      drawer.addEventListener("click", (e) => e.stopPropagation());
      const finding = data.findings.find((f) => f.id === filters.drawerId);
      drawer.querySelectorAll("[data-act]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const act = btn.dataset.act;
          if (act === "reject") {
            const box = drawer.querySelector("#reject-box");
            if (box) box.hidden = !box.hidden;
            return;
          }
          if (act === "reject-submit") {
            const reason = (drawer.querySelector("#reject-reason") || {}).value || "";
            onFindingAction(finding, "reject", { reason });
            return;
          }
          if (act === "confirm") onFindingAction(finding, "confirm");
          if (act === "fixed") onFindingAction(finding, "fixed");
          if (act === "checklist") onChecklist("add", { text: finding.checklist_rule, source: finding.id });
        });
      });
    }

    root.querySelectorAll("[data-check-toggle]").forEach((el) => {
      el.addEventListener("change", () => onChecklist("toggle", { id: el.dataset.checkToggle, done: el.checked }));
    });
    root.querySelectorAll("[data-check-del]").forEach((btn) => {
      btn.addEventListener("click", () => onChecklist("delete", { id: btn.dataset.checkDel }));
    });
    root.querySelectorAll("[data-check-edit]").forEach((el) => {
      el.addEventListener("blur", () => {
        onChecklist("edit", { id: el.dataset.checkEdit, text: el.textContent });
      });
    });
    const addBtn = root.querySelector("[data-check-add]");
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        const input = root.querySelector("#check-new");
        onChecklist("add", { text: input ? input.value : "" });
      });
    }
    const startCheck = root.querySelector("[data-check-start]");
    if (startCheck) {
      startCheck.addEventListener("click", () => onChecklist("resetMarks"));
    }

    root.querySelectorAll("[data-empty-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const a = btn.dataset.emptyAct;
        if (a === "start") onNavigateStart();
        else if (a === "review") onNavigateReview();
        else if (a === "reset") {
          onFilters({
            period: "all",
            docType: "all",
            severity: { rare: true, medium: true, well_done: true },
          });
        }
      });
    });
    root.querySelectorAll("[data-nav='start']").forEach((btn) => {
      btn.addEventListener("click", onNavigateStart);
    });
  }

  return {
    CATEGORIES,
    BLOCKS,
    hydrate,
    persistFinding,
    persistChecklist,
    defaultFilters,
    summary,
    focusCards,
    addChecklistRule,
    resetChecklistMarks,
    render,
    confirmedFindings,
    filterFindings,
  };
})();
