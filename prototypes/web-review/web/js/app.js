(() => {
  const DONENESS = {
    well_done: "Well done",
    medium: "Medium",
    medium_rare: "Medium rare",
    rare: "Rare",
  };
  const DOC_TYPES = {
    flow: {
      title: "Описание потоков данных",
      desc: "Схема потока, Kafka/источники, алгоритм обработки и структура слоёв.",
    },
    source: {
      title: "Описание данных системы-источника",
      desc: "Система-источник, топики/файлы, фильтрация и поля сырых данных.",
    },
    aggregate_mart: {
      title: "Описание витрины-агрегата",
      desc: "Бизнес-требования, источники, расчёт полей и регламент обновления.",
    },
  };

  const state = {
    step: "start", // start | review | handoff | progress
    dataset: null,
    learningRaw: null,
    learning: null,
    learnFilters: null,
    learnToast: null,
    docType: "aggregate_mart",
    sourceMode: "blank", // blank | upload
    customText: "",
    filename: "",
    uploadStatus: "",
    severityLevels: { rare: true, medium: true, well_done: true },
    working: null,
    filter: "critical",
    activeMarker: null,
    pendingFix: null,
    showOptionalMissing: false,
    editMode: false,
    toast: null,
  };

  const app = document.getElementById("app");

  async function boot() {
    const [ds, learn] = await Promise.all([
      fetch("data/dataset.json").then((r) => r.json()),
      fetch("data/learning.json").then((r) => r.json()),
    ]);
    state.dataset = ds;
    state.learningRaw = learn;
    state.learning = MTSLearning.hydrate(learn);
    state.learnFilters = MTSLearning.defaultFilters();
    render();
  }

  function sampleForType(docType) {
    return (state.dataset.samples || []).find((s) => s.doc_type === docType);
  }

  function startReview() {
    const docType = state.docType;
    let text = "";
    let filename = "";
    let blocks;
    let findings;
    const label = DOC_TYPES[docType].title;

    if (state.sourceMode === "upload") {
      text = state.customText.trim();
      filename = state.filename || "uploaded_tz.pdf";
      const known = (state.dataset.samples || []).find((s) => s.filename === filename);
      if (known) {
        const cloned = MTSAnalyzer.cloneSample(known);
        text = cloned.text;
        blocks = MTSAnalyzer.parseDocumentBlocks(text, state.dataset.block_defs, docType);
        findings = (cloned.findings || []).map((f) => ({ ...f, status: "open" }));
      } else {
        const base = sampleForType(docType) || state.dataset.samples[0];
        const cloned = MTSAnalyzer.cloneSample(base);
        cloned.text = text;
        cloned.filename = filename;
        const refreshed = MTSAnalyzer.refreshAfterEdit(cloned, text, state.dataset.block_defs, docType);
        blocks = refreshed.blocks;
        findings = (cloned.findings || []).map((f) => ({ ...f, status: "open" }));
        const again = MTSAnalyzer.refreshAfterEdit({ blocks, findings }, text, state.dataset.block_defs, docType);
        blocks = again.blocks;
        findings = again.findings;
        if (!findings.length) findings = MTSAnalyzer.buildBlankFindings(blocks, docType);
      }
    } else {
      text = (state.dataset.blank_templates && state.dataset.blank_templates[docType]) || `${DOC_TYPES[docType].title}\n\n`;
      filename = `черновик_${docType}.txt`;
      blocks = MTSAnalyzer.parseDocumentBlocks(text, state.dataset.block_defs, docType);
      findings = MTSAnalyzer.buildBlankFindings(blocks, docType);
    }

    findings = findings.map((f) => ({ ...f, status: f.status || "open" }));
    MTSAnalyzer.ensureStableNumbers(findings, blocks);

    state.working = {
      text,
      blocks,
      findings,
      filename,
      docType,
      label,
      severityLevels: state.sourceMode === "upload"
        ? { ...state.severityLevels }
        : { rare: true, medium: true, well_done: true },
    };
    state.step = "review";
    state.activeMarker = null;
    state.pendingFix = null;
    state.filter = "critical";
    state.editMode = state.sourceMode === "blank";
    state._editBackup = text;
    render();
  }

  function severityLevels() {
    return (state.working && state.working.severityLevels) || state.severityLevels;
  }

  function matchesSeverity(f) {
    const levels = severityLevels();
    const d = f && f.doneness;
    if (d === "well_done") return !!levels.well_done;
    if (d === "medium") return !!levels.medium;
    // rare + medium_rare → «Rare · Незначительные»
    return !!levels.rare;
  }

  function scopedFindings() {
    return (state.working.findings || []).filter(matchesSeverity);
  }

  function stats() {
    const fs = scopedFindings();
    const open = fs.filter((f) => f.status === "open");
    const critical = open.filter((f) => f.doneness === "well_done" || f.doneness === "medium");
    const accepted = fs.filter((f) => f.status === "fixed");
    const rejected = fs.filter((f) => f.status === "rejected");
    const closed = accepted.length + rejected.length;
    const total = fs.length;
    const pct = total ? Math.round((closed / total) * 100) : 0;
    return {
      open: open.length,
      critical: critical.length,
      accepted: accepted.length,
      rejected: rejected.length,
      closed,
      total,
      pct,
    };
  }

  function findingNo(f, markerOf) {
    if (f && f.no != null) return f.no;
    if (markerOf && f && markerOf[f.id] != null) return markerOf[f.id];
    return "·";
  }

  function visibleFindings(ordered) {
    const scopedOpen = ordered.filter(matchesSeverity);
    if (state.filter === "all") return scopedOpen;
    if (state.filter === "done") {
      return scopedFindings().filter((f) => f.status !== "open");
    }
    const crit = scopedOpen.filter((f) => f.doneness === "well_done" || f.doneness === "medium");
    return crit.length ? crit : scopedOpen;
  }

  function topbar(step) {
    const steps = [
      { id: "start", label: "1. Старт" },
      { id: "review", label: "2. Ревью" },
      { id: "handoff", label: "3. Итог" },
    ];
    const order = ["start", "review", "handoff"];
    const idx = order.indexOf(step);
    return `
      <div class="topbar">
        <div class="brand">
          <div class="brand-mark"><img src="assets/mts_logo.png" alt="МТС" /></div>
          <div>
            <h1>Прожарка документации</h1>
            <p>МТС · ревью ТЗ</p>
          </div>
        </div>
        <div class="topbar-right">
          <button class="btn btn-ghost btn-sm" id="nav-progress">Мой прогресс</button>
          <div class="steps">
            ${steps.map((s, i) => {
              const cls = i < idx ? "done" : i === idx ? "active" : "";
              return `<span class="step-pill ${cls}">${s.label}</span>`;
            }).join("")}
          </div>
        </div>
      </div>
    `;
  }

  function bindTopNav() {
    const btn = document.getElementById("nav-progress");
    if (btn) {
      btn.addEventListener("click", () => {
        state.step = "progress";
        state.learnToast = null;
        render();
      });
    }
  }

  function canStart() {
    if (!state.docType || !state.sourceMode) return false;
    if (state.sourceMode === "upload") {
      const levels = state.severityLevels;
      const anyLevel = levels.rare || levels.medium || levels.well_done;
      return !!state.customText.trim() && anyLevel;
    }
    return true;
  }

  function renderStart() {
    const sev = state.severityLevels;
    app.innerHTML = `
      <div class="shell">
        ${topbar("start")}
        <section class="card hero hero-single">
          <div>
            <h2>Соберём ТЗ под проверку</h2>
            <p class="lead">Сначала выберите шаблон, затем способ старта.</p>

            <h3 class="section-label">1. Какое ТЗ хотите собрать?</h3>
            <div class="type-grid">
              ${Object.entries(DOC_TYPES).map(([key, meta]) => `
                <button class="type-card ${state.docType === key ? "selected" : ""}" data-type="${key}">
                  <strong>${meta.title}</strong>
                  <span>${meta.desc}</span>
                </button>
              `).join("")}
            </div>

            <h3 class="section-label">2. Как начать?</h3>
            <div class="type-grid type-grid-2">
              <button class="type-card ${state.sourceMode === "blank" ? "selected" : ""}" data-mode="blank">
                <strong>Создать с нуля</strong>
                <span>Пустой каркас по шаблону — заполняете блоки, ИИ подсветит пробелы.</span>
              </button>
              <button class="type-card ${state.sourceMode === "upload" ? "selected" : ""}" data-mode="upload">
                <strong>Подгрузить своё ТЗ</strong>
                <span>Загрузите PDF с таблицами — мы извлечём текст и покажем таблицы в документе.</span>
              </button>
            </div>

            ${state.sourceMode === "upload" ? `
              <div class="upload-box" style="margin-top:16px">
                <label>PDF вашего ТЗ</label>
                <div class="btn-row" style="margin-top:8px">
                  <label class="btn btn-secondary btn-sm" style="display:inline-flex;align-items:center;gap:6px">
                    Выбрать PDF
                    <input type="file" id="file" accept=".pdf,application/pdf" hidden />
                  </label>
                  ${state.filename ? `<span style="font-size:12px;color:var(--mts-muted)">${MTSAnalyzer.escapeHtml(state.filename)}</span>` : ""}
                  ${state.uploadStatus ? `<span style="font-size:12px;color:var(--mts-red)">${MTSAnalyzer.escapeHtml(state.uploadStatus)}</span>` : ""}
                </div>
                ${state.customText.trim() ? `<p style="margin:10px 0 0;font-size:12px;color:#0f7a3c">Файл прочитан · ${state.customText.length} символов · можно начинать ревью</p>` : `<p style="margin:10px 0 0;font-size:12px;color:var(--mts-muted)">После выбора PDF таблицы будут распознаны и отрисованы как таблицы.</p>`}
              </div>

              <h3 class="section-label">3. Какие замечания показывать?</h3>
              <p class="sev-hint">Можно выбрать несколько уровней. По умолчанию включены все.</p>
              <div class="sev-grid">
                <label class="sev-card ${sev.rare ? "selected" : ""}">
                  <input type="checkbox" data-sev="rare" ${sev.rare ? "checked" : ""} />
                  <span class="sev-title">Rare · Незначительные</span>
                  <span class="sev-desc">Мелкие правки формулировок и низкий риск</span>
                </label>
                <label class="sev-card ${sev.medium ? "selected" : ""}">
                  <input type="checkbox" data-sev="medium" ${sev.medium ? "checked" : ""} />
                  <span class="sev-title">Medium · Существенные</span>
                  <span class="sev-desc">Важные пробелы, влияют на разработку</span>
                </label>
                <label class="sev-card ${sev.well_done ? "selected" : ""}">
                  <input type="checkbox" data-sev="well_done" ${sev.well_done ? "checked" : ""} />
                  <span class="sev-title">Well Done · Критические</span>
                  <span class="sev-desc">Блокеры: без этого ТЗ нельзя отдавать в работу</span>
                </label>
              </div>
            ` : ""}

            <div class="btn-row">
              <button class="btn btn-primary" id="start" ${canStart() ? "" : "disabled"}>Начать ревью</button>
            </div>
          </div>
        </section>
      </div>
    `;

    document.querySelectorAll("[data-type]").forEach((el) => {
      el.addEventListener("click", () => {
        state.docType = el.dataset.type;
        render();
      });
    });
    document.querySelectorAll("[data-mode]").forEach((el) => {
      el.addEventListener("click", () => {
        state.sourceMode = el.dataset.mode;
        if (state.sourceMode === "upload") {
          state.severityLevels = { rare: true, medium: true, well_done: true };
        }
        render();
      });
    });
    document.querySelectorAll("[data-sev]").forEach((el) => {
      el.addEventListener("change", () => {
        const key = el.dataset.sev;
        state.severityLevels[key] = !!el.checked;
        render();
      });
    });
    document.getElementById("start").addEventListener("click", startReview);

    const file = document.getElementById("file");
    if (file) {
      file.addEventListener("change", async (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f) return;
        state.filename = f.name;
        state.uploadStatus = "Читаем PDF…";
        state.customText = "";
        render();
        try {
          // если это эталон из датасета — берём уже размеченные таблицы
          const known = (state.dataset.samples || []).find((s) => s.filename === f.name);
          let text;
          if (known) {
            text = known.text;
            state.uploadStatus = "";
          } else {
            if (!window.MTSPDF || !window.MTSPDF.extractFromFile) {
              throw new Error("Модуль PDF не загружен. Обновите страницу (Cmd+Shift+R).");
            }
            text = await window.MTSPDF.extractFromFile(f);
            state.uploadStatus = "";
          }
          state.customText = text;
          if (!text.trim()) state.uploadStatus = "Не удалось извлечь текст из PDF";
        } catch (err) {
          state.customText = "";
          state.uploadStatus = String(err.message || err);
        }
        render();
      });
    }
    bindTopNav();
  }

  function renderReview() {
    const w = state.working;
    const s = stats();
    const scoped = scopedFindings();
    const built = MTSAnalyzer.buildDocumentHtml(w.blocks, scoped, w.filename, {
      showOptionalMissing: state.showOptionalMissing,
    });
    const visible = visibleFindings(built.ordered);
    const rareHidden = built.ordered.filter((f) => f.doneness === "medium_rare" || f.doneness === "rare").length;

    app.innerHTML = `
      <div class="review-shell">
        ${topbar("review")}
        <div class="statusbar">
          <div class="status-left">
            <span class="chip">${MTSAnalyzer.escapeHtml(DOC_TYPES[w.docType].title)}</span>
            <span class="chip">${MTSAnalyzer.escapeHtml(w.filename)}</span>
            <span class="chip critical">${s.critical} критичных</span>
            <span class="chip">${s.open} открыто</span>
            <span class="chip ok">${s.accepted} принято</span>
          </div>
          <div class="status-actions">
            ${state.editMode ? `
              <button class="btn btn-primary btn-sm" id="save-recheck">Сохранить и перепроверить</button>
              <button class="btn btn-ghost btn-sm" id="cancel-edit">Отменить</button>
            ` : `
              <button class="btn btn-secondary btn-sm" id="toggle-edit">✎ Редактировать</button>
              <button class="btn btn-secondary btn-sm" id="recheck">Перепроверить</button>
              <button class="btn btn-primary btn-sm" id="to-handoff">К итогу</button>
            `}
          </div>
        </div>
        ${state.toast ? `<div class="toast" id="toast">${MTSAnalyzer.escapeHtml(state.toast)}</div>` : ""}

        <div class="workspace">
          <div class="doc-pane" id="doc-pane">
            ${state.editMode ? `
              <div class="doc-paper is-editing">
                <div class="doc-title">${MTSAnalyzer.escapeHtml(w.filename)} · редактирование</div>
                <textarea id="doc-editor" class="doc-editor" spellcheck="false" aria-label="Текст ТЗ">${MTSAnalyzer.escapeHtml(w.text)}</textarea>
              </div>
            ` : built.html}
          </div>
          <aside class="comments-pane">
            <div class="comments-head">
              <div class="comments-head-row">
                <span>Замечания · ${visible.length}${state.filter === "critical" && rareHidden ? ` · ещё ${rareHidden} ниже по риску` : ""}</span>
                <span class="fix-progress-label">${s.closed}/${s.total}</span>
              </div>
              <div class="fix-progress" title="Прогресс правок: ${s.closed} из ${s.total}">
                <div class="fix-progress-fill" style="width:${s.pct}%"></div>
              </div>
              <div class="fix-progress-caption">Прогресс правок · ${s.pct}%</div>
            </div>
            <div class="comments-filters">
              <button class="filter-btn ${state.filter === "critical" ? "active" : ""}" data-filter="critical">Сначала критичные</button>
              <button class="filter-btn ${state.filter === "all" ? "active" : ""}" data-filter="all">Все открытые</button>
              <button class="filter-btn ${state.filter === "done" ? "active" : ""}" data-filter="done">Закрытые</button>
            </div>
            <div class="comments-list" id="comments-list">
              ${state.editMode
                ? `<div style="padding:12px;color:var(--mts-muted);font-size:13px">Редактируйте текст слева. Затем нажмите «Сохранить и перепроверить».</div>`
                : (visible.length ? visible.map((f) => commentHtml(f, findingNo(f, built.markerOf))).join("") : `<div style="padding:12px;color:var(--mts-muted);font-size:13px">Нет замечаний в этом фильтре.</div>`)}
            </div>
          </aside>
        </div>
        ${state.pendingFix ? fixModal() : ""}
      </div>
    `;

    bindReview(built);
    bindTopNav();
  }

  function commentHtml(f, no) {
    const done = f.status !== "open";
    return `
      <article class="comment ${f.traffic_light || "orange"} ${done ? "done" : ""} ${state.activeMarker === no ? "active" : ""}" data-marker="${no}" data-id="${f.id}">
        <button class="comment-locate" type="button" data-act="locate" data-id="${f.id}" data-marker="${no}" title="Найти в тексте" aria-label="Найти правку в тексте">
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16.2 16.2L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
        <div class="meta">
          <span class="num">${no}</span>
          <span class="doneness ${f.doneness}">${DONENESS[f.doneness] || f.doneness}</span>
          <span>${f.status === "open" ? "открыто" : f.status === "fixed" ? "принято" : "отклонено"}</span>
        </div>
        <h4>${MTSAnalyzer.escapeHtml(f.block)}</h4>
        <p class="problem">${MTSAnalyzer.escapeHtml(f.problem)}</p>
        <details>
          <summary>детали и вопросы</summary>
          <p style="margin:6px 0">${MTSAnalyzer.escapeHtml(f.recommendation)}</p>
          <ul>${(f.guiding_questions || []).map((q) => `<li>${MTSAnalyzer.escapeHtml(q)}</li>`).join("")}</ul>
        </details>
        ${done ? "" : `
          <div class="comment-actions">
            <button class="btn btn-primary btn-sm" data-act="ai" data-id="${f.id}">ИИсправь</button>
            <button class="btn btn-secondary btn-sm" data-act="accept" data-id="${f.id}">Исправлено</button>
            <button class="btn btn-ghost btn-sm" data-act="reject" data-id="${f.id}">Отклонить</button>
          </div>
        `}
      </article>
    `;
  }

  function fixModal() {
    const p = state.pendingFix;
    return `
      <div class="modal-backdrop" id="fix-modal">
        <div class="modal">
          <h3>✨ ИИ исправляет · ${MTSAnalyzer.escapeHtml(p.finding.block)}</h3>
          <p style="margin:0;color:var(--mts-muted);font-size:13px">${MTSAnalyzer.escapeHtml(p.note || "Предлагаем заменить фрагмент")}</p>
          <div class="diff">
            <div class="diff-col before"><div class="diff-label">Было</div>${MTSAnalyzer.escapeHtml(p.before)}</div>
            <div class="diff-col after"><div class="diff-label">Станет</div>${MTSAnalyzer.escapeHtml(p.after)}</div>
          </div>
          <div class="btn-row">
            <button class="btn btn-primary" id="apply-fix">✨ Применить правку</button>
            <button class="btn btn-secondary" id="cancel-fix">Отмена</button>
          </div>
        </div>
      </div>
    `;
  }

  function recheckWorking(showToast) {
    const refreshed = MTSAnalyzer.refreshAfterEdit(
      { blocks: state.working.blocks, findings: state.working.findings },
      state.working.text,
      state.dataset.block_defs,
      state.working.docType
    );
    const prevById = Object.fromEntries(state.working.findings.map((f) => [f.id, f]));
    state.working.text = refreshed.text;
    state.working.blocks = refreshed.blocks;
    state.working.findings = refreshed.findings.map((f) => {
      const prev = prevById[f.id];
      const next = { ...f };
      if (prev && (prev.status === "fixed" || prev.status === "rejected")) next.status = prev.status;
      if (prev && prev.no != null) next.no = prev.no;
      return next;
    });
    MTSAnalyzer.ensureStableNumbers(state.working.findings, state.working.blocks);
    if (showToast) {
      state.toast = "Изменения сохранены · перепроверка выполнена";
      setTimeout(() => { state.toast = null; render(); }, 1800);
    }
  }

  function bindReview(built) {
    document.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.filter = btn.dataset.filter;
        render();
      });
    });

    const toggleEdit = document.getElementById("toggle-edit");
    if (toggleEdit) {
      toggleEdit.addEventListener("click", () => {
        state.editMode = true;
        state._editBackup = state.working.text;
        render();
        const editor = document.getElementById("doc-editor");
        if (editor) editor.focus();
      });
    }

    const cancelEdit = document.getElementById("cancel-edit");
    if (cancelEdit) {
      cancelEdit.addEventListener("click", () => {
        if (state._editBackup != null) state.working.text = state._editBackup;
        state.editMode = false;
        state._editBackup = null;
        render();
      });
    }

    const recheckBtn = document.getElementById("recheck");
    if (recheckBtn) {
      recheckBtn.addEventListener("click", () => {
        recheckWorking(true);
        render();
      });
    }

    const toHandoff = document.getElementById("to-handoff");
    if (toHandoff) {
      toHandoff.addEventListener("click", () => {
        state.step = "handoff";
        state.editMode = false;
        render();
      });
    }

    const saveRecheck = document.getElementById("save-recheck");
    if (saveRecheck) {
      saveRecheck.addEventListener("click", () => {
        const editor = document.getElementById("doc-editor");
        if (!editor) return;
        state.working.text = editor.value;
        state.editMode = false;
        state._editBackup = null;
        recheckWorking(true);
        render();
      });
    }

    if (state.editMode) return;

    const activate = (marker, opts = {}) => {
      state.activeMarker = Number(marker);
      document.querySelectorAll(".comment").forEach((el) => {
        el.classList.toggle("active", Number(el.dataset.marker) === state.activeMarker);
      });
      document.querySelectorAll("mark.cmt").forEach((el) => {
        el.classList.toggle("active", Number(el.dataset.marker) === state.activeMarker);
      });
      if (opts.scrollComment !== false) {
        const card = document.querySelector(`.comment[data-marker="${marker}"]`);
        if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      const mark =
        document.querySelector(`mark.cmt[data-marker="${marker}"]`) ||
        document.querySelector(`sup.cmt-num[data-marker="${marker}"]`);
      if (mark) {
        mark.scrollIntoView({ behavior: "smooth", block: "center" });
        return true;
      }
      return false;
    };

    const locateFinding = (finding, marker) => {
      const found = activate(marker, { scrollComment: false });
      if (found) return;
      if (finding && finding.block_id) {
        const sec = document.getElementById(`block-${finding.block_id}`);
        if (sec) {
          sec.scrollIntoView({ behavior: "smooth", block: "center" });
          sec.classList.add("flash-locate");
          setTimeout(() => sec.classList.remove("flash-locate"), 1200);
          return;
        }
      }
      state.toast = "Фрагмент в тексте не найден";
      setTimeout(() => { state.toast = null; render(); }, 1400);
    };

    document.querySelectorAll("[data-marker]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("[data-act]")) return;
        if (e.target.closest("details, summary, a, button, input, textarea, label")) return;
        const m = el.dataset.marker;
        if (!m) return;
        e.preventDefault();
        activate(m);
      });
    });

    document.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        const finding = state.working.findings.find((f) => f.id === id);
        if (!finding) return;
        const act = btn.dataset.act;
        if (act === "locate") {
          locateFinding(finding, findingNo(finding, built.markerOf));
        } else if (act === "accept") {
          finding.status = "fixed";
          state.toast = "Замечание отмечено как исправленное";
          setTimeout(() => { state.toast = null; render(); }, 1600);
          render();
        } else if (act === "reject") {
          finding.status = "rejected";
          state.toast = "Замечание отклонено";
          setTimeout(() => { state.toast = null; render(); }, 1600);
          render();
        } else if (act === "ai") {
          const result = MTSAutofix.applyFix(state.working.text, finding);
          state.pendingFix = { finding, ...result, note: result.note };
          render();
        }
      });
    });

    if (state.pendingFix) {
      document.getElementById("cancel-fix").addEventListener("click", () => {
        state.pendingFix = null;
        render();
      });
      document.getElementById("apply-fix").addEventListener("click", () => {
        const p = state.pendingFix;
        state.working.text = p.text;
        p.finding.status = "fixed";
        recheckWorking(false);
        state.pendingFix = null;
        state.toast = `✨ ${p.note}`;
        setTimeout(() => { state.toast = null; render(); }, 2000);
        render();
      });
    }

    if (state.activeMarker) {
      const card = document.querySelector(`.comment[data-marker="${state.activeMarker}"]`);
      if (card) card.classList.add("active");
      const mark = document.querySelector(`mark.cmt[data-marker="${state.activeMarker}"]`);
      if (mark) mark.classList.add("active");
    }
  }

  function renderHandoff() {
    const s = stats();
    const accepted = scopedFindings().filter((f) => f.status === "fixed");
    const rejected = scopedFindings().filter((f) => f.status === "rejected");
    const left = scopedFindings().filter((f) => f.status === "open");
    const ready = s.critical === 0;

    app.innerHTML = `
      <div class="shell">
        ${topbar("handoff")}
        ${state.toast ? `<div class="toast" id="toast">${MTSAnalyzer.escapeHtml(state.toast)}</div>` : ""}
        <section class="card handoff">
          <div class="eyebrow">${ready ? "Можно передавать дальше" : "Есть открытые критичные замечания"}</div>
          <h2>${ready ? "Готово к передаче" : "Почти готово"}</h2>
          <p class="lead">Итог ревью «${MTSAnalyzer.escapeHtml(state.working.filename)}». В самообучение попадают только принятые правки.</p>
          <div class="stat-row">
            <div class="stat"><div class="n">${s.accepted}</div><div class="l">Принято</div></div>
            <div class="stat"><div class="n">${s.rejected}</div><div class="l">Отклонено</div></div>
            <div class="stat"><div class="n">${s.open}</div><div class="l">Ещё открыто</div></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
            <div>
              <h3 style="margin:0 0 8px;font-size:15px">Что исправлено</h3>
              <ul class="list-clean">
                ${accepted.length ? accepted.map((f) => `<li>${MTSAnalyzer.escapeHtml(f.block)} — ${MTSAnalyzer.escapeHtml(f.problem)}</li>`).join("") : "<li>Пока ничего не принято</li>"}
              </ul>
            </div>
            <div>
              <h3 style="margin:0 0 8px;font-size:15px">${left.length ? "Ещё желательно" : "Отклонённые"}</h3>
              <ul class="list-clean">
                ${(left.length ? left : rejected).slice(0, 8).map((f) => `<li>${MTSAnalyzer.escapeHtml(f.block)} — ${MTSAnalyzer.escapeHtml(f.problem)}</li>`).join("") || "<li>—</li>"}
              </ul>
            </div>
          </div>
          <div class="btn-row">
            <button class="btn btn-secondary" id="back-review">Вернуться к ревью</button>
            <button class="btn btn-primary" id="download-pdf">Скачать PDF</button>
            <button class="btn btn-secondary" id="download-txt">Скачать текст</button>
            <button class="btn btn-secondary" id="to-progress">Мой прогресс</button>
            <button class="btn btn-ghost" id="restart">Новый документ</button>
          </div>
        </section>
      </div>
    `;

    document.getElementById("back-review").addEventListener("click", () => { state.step = "review"; render(); });
    document.getElementById("to-progress").addEventListener("click", () => {
      state.step = "progress";
      state.learnToast = null;
      render();
    });
    document.getElementById("restart").addEventListener("click", () => {
      state.step = "start";
      state.working = null;
      state.sourceMode = "blank";
      state.customText = "";
      state.filename = "";
      state.docType = "aggregate_mart";
      state.severityLevels = { rare: true, medium: true, well_done: true };
      render();
    });
    document.getElementById("download-txt").addEventListener("click", () => {
      const blob = new Blob([state.working.text], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = state.working.filename.replace(/\.pdf$/i, "") + "_draft.txt";
      a.click();
      URL.revokeObjectURL(a.href);
    });
    document.getElementById("download-pdf").addEventListener("click", async () => {
      const btn = document.getElementById("download-pdf");
      const prev = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Готовим PDF…";
      try {
        await window.MTSPDFExport.downloadPdf(state.working);
        state.toast = "В диалоге печати выберите «Сохранить как PDF»";
        setTimeout(() => { state.toast = null; render(); }, 3500);
        render();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = prev;
        alert(String(err.message || err));
      }
    });
    bindTopNav();
  }

  function renderProgress() {
    if (!state.learning) {
      app.innerHTML = `<div class="shell"><div class="card" style="padding:24px">Нет данных самообучения.</div></div>`;
      return;
    }
    MTSLearning.render({
      root: app,
      data: state.learning,
      filters: state.learnFilters,
      toast: state.learnToast,
      onFilters: (patch) => {
        state.learnFilters = { ...state.learnFilters, ...patch };
        state.learnToast = null;
        render();
      },
      onExpand: (key) => {
        state.learnFilters.expandedKey = key;
        render();
      },
      onOpenDrawer: (id) => {
        state.learnFilters.drawerId = id;
        render();
      },
      onCloseDrawer: () => {
        state.learnFilters.drawerId = null;
        render();
      },
      onFindingAction: (finding, act, extra) => {
        if (!finding) return;
        if (act === "confirm") finding.confirm_status = "confirmed";
        if (act === "reject") {
          finding.confirm_status = "rejected";
          finding.reject_reason = (extra && extra.reason) || "";
        }
        if (act === "fixed") finding.fix_status = "fixed";
        MTSLearning.persistFinding(state.learning, finding);
        state.learnToast =
          act === "confirm" ? "Замечание подтверждено" :
          act === "reject" ? "Замечание отклонено — не участвует в выводах" :
          "Отмечено исправленным";
        setTimeout(() => { state.learnToast = null; render(); }, 1800);
        render();
      },
      onChecklist: (act, payload) => {
        if (act === "add") {
          const ok = MTSLearning.addChecklistRule(state.learning, payload.text, payload.source);
          state.learnToast = ok ? "Правило добавлено в чек-лист" : "Такое правило уже есть в чек-листе";
        } else if (act === "toggle") {
          const item = state.learning.checklist.find((c) => c.id === payload.id);
          if (item) item.done = !!payload.done;
          MTSLearning.persistChecklist(state.learning);
        } else if (act === "delete") {
          state.learning.checklist = state.learning.checklist.filter((c) => c.id !== payload.id);
          MTSLearning.persistChecklist(state.learning);
          state.learnToast = "Пункт удалён";
        } else if (act === "edit") {
          const item = state.learning.checklist.find((c) => c.id === payload.id);
          if (item) {
            const text = String(payload.text || "").trim();
            if (text) item.text = text;
          }
          MTSLearning.persistChecklist(state.learning);
        } else if (act === "resetMarks") {
          MTSLearning.resetChecklistMarks(state.learning);
          state.learnToast = "Отметки сброшены · пункты сохранены. Можно проверять новое ТЗ.";
          setTimeout(() => {
            state.learnToast = null;
            state.step = "start";
            render();
          }, 1200);
        }
        if (act !== "resetMarks") {
          setTimeout(() => { state.learnToast = null; render(); }, 1600);
        }
        render();
      },
      onNavigateStart: () => {
        state.step = "start";
        render();
      },
      onNavigateReview: () => {
        if (state.working) {
          state.step = "review";
        } else {
          state.step = "start";
          state.learnToast = "Сначала начните проверку ТЗ";
        }
        render();
      },
    });
  }

  function render() {
    if (state.step === "start") return renderStart();
    if (state.step === "review") return renderReview();
    if (state.step === "handoff") return renderHandoff();
    if (state.step === "progress") return renderProgress();
  }

  boot().catch((err) => {
    app.innerHTML = `<div class="shell"><div class="card" style="padding:24px">Не удалось загрузить data/dataset.json. Откройте папку через локальный сервер.<br><code>${String(err)}</code></div></div>`;
  });
})();
