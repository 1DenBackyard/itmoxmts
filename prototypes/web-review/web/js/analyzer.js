window.MTSAnalyzer = (function () {
  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function donenessFromScore(score) {
    if (score >= 0.75) return "well_done";
    if (score >= 0.45) return "medium";
    if (score >= 0.25) return "medium_rare";
    return "rare";
  }

  function traffic(doneness) {
    return ({ well_done: "red", medium: "orange", medium_rare: "yellow", rare: "green" })[doneness];
  }

  function normLine(line) {
    return String(line || "")
      .trim()
      .toLowerCase()
      .replace(/ё/g, "е")
      .replace(/^[\d.\)\-\–—]+\s*/, "")
      .replace(/[•·]\s*/g, "")
      .replace(/\s+/g, " ");
  }

  function matchBlockDef(line, blockDefs) {
    const norm = normLine(line);
    if (!norm || norm.length > 80) return null;
    let best = null;
    let bestLen = 0;
    (blockDefs || []).forEach((bdef) => {
      (bdef.aliases || []).forEach((alias) => {
        const a = String(alias).toLowerCase().replace(/ё/g, "е");
        if (!a) return;
        const ok =
          norm === a ||
          norm.startsWith(a + " ") ||
          norm.startsWith(a + ":") ||
          norm === a.replace(/:$/, "") ||
          (a.endsWith(":") && norm.startsWith(a.slice(0, -1)));
        if (ok && a.length > bestLen) {
          best = bdef;
          bestLen = a.length;
        }
      });
    });
    return best;
  }

  function parseDocumentBlocks(text, blockDefs, docType) {
    const lines = String(text || "").split(/\r?\n/);
    const hits = [];
    lines.forEach((line, i) => {
      const bdef = matchBlockDef(line, blockDefs);
      if (!bdef) return;
      if (hits.length && hits[hits.length - 1].bdef.id === bdef.id) return;
      hits.push({ start: i, bdef, heading: line.trim() });
    });

    const found = {};
    hits.forEach((hit, idx) => {
      const end = idx + 1 < hits.length ? hits[idx + 1].start : lines.length;
      const content = lines.slice(hit.start + 1, end).join("\n").trim();
      const chunk = content || "—";
      if (found[hit.bdef.id]) {
        const prev = found[hit.bdef.id];
        const extra = content ? `${hit.heading}\n${content}` : hit.heading;
        found[hit.bdef.id] = {
          ...prev,
          content: prev.content && prev.content !== "—" ? `${prev.content}\n\n${extra}`.trim() : extra,
          matched_heading: `${prev.matched_heading} | ${hit.heading}`,
          present: prev.present || (!!content && content !== "—"),
        };
      } else {
        found[hit.bdef.id] = {
          id: hit.bdef.id,
          title: hit.bdef.title,
          content: chunk,
          present: !!content && content !== "—",
          important: true,
          start_line: hit.start + 1,
          matched_heading: hit.heading,
        };
      }
    });

    if (found.sources && !found.sinks) {
      const src = found.sources.content || "";
      const m = src.match(/(При[её]мники\s*:?\s*)([\s\S]+)$/i);
      if (m) {
        found.sources = {
          ...found.sources,
          content: src.slice(0, m.index).trim() || "—",
        };
        found.sinks = {
          id: "sinks",
          title: (blockDefs.find((b) => b.id === "sinks") || {}).title || "Приёмники данных",
          content: m[2].trim() || "—",
          present: !!m[2].trim(),
          important: true,
          matched_heading: "Приёмники",
        };
      }
    }

    return (blockDefs || []).map((bdef) => {
      if (found[bdef.id]) {
        return {
          ...found[bdef.id],
          important: (bdef.required_for || []).includes(docType) || !!bdef.important,
        };
      }
      const required = (bdef.required_for || []).includes(docType);
      return {
        id: bdef.id,
        title: bdef.title,
        content: "",
        present: false,
        important: required,
        matched_heading: "",
      };
    });
  }

  function markQuotes(escapedBody, findings, markerOf) {
    let body = escapedBody;
    findings.forEach((f) => {
      if (f.status !== "open" || f.kind === "missing") return;
      const no = markerOf[f.id];
      if (!no) return;
      const quote = ((f.anchor && f.anchor.excerpt) || "").replace(/^…|…$/g, "").trim();
      const candidates = [];
      if (quote) candidates.push(quote, quote.slice(-60), quote.slice(0, 80));
      ["Кластер: CLUSTER", "CLUSTER", "substring(imei, 1, 8)", "если lac = 0", "fallback", "без upsert", "полная перезагрузка", "FIELD_BIZ_DATE", "Шаг 1"].forEach((t) => {
        if (quote.toLowerCase().includes(t.toLowerCase()) || (f.problem || "").includes(t)) candidates.push(t);
      });
      for (const cand of candidates.sort((a, b) => b.length - a.length)) {
        if (!cand || cand.length < 4) continue;
        const eq = escapeHtml(cand);
        const re = new RegExp(eq.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
        if (re.test(body)) {
          body = body.replace(re, (m) => `<mark class="cmt" data-marker="${no}">${m}</mark><sup class="cmt-num" data-marker="${no}">[${no}]</sup>`);
          break;
        }
      }
    });
    return body;
  }

  function renderMarkdownTables(text) {
    const lines = String(text || "").split(/\n/);
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const next = lines[i + 1] || "";
      const isHeader = /^\|.+\|$/.test(line.trim());
      const isSep = /^\|\s*:?---/.test(next.trim());
      if (isHeader && isSep) {
        const headers = line.trim().slice(1, -1).split("|").map((c) => c.trim());
        i += 2;
        const rows = [];
        while (i < lines.length && /^\|.+\|$/.test(lines[i].trim())) {
          rows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
          i += 1;
        }
        let table = '<div class="table-wrap"><table class="doc-table"><thead><tr>';
        headers.forEach((h) => { table += `<th>${escapeHtml(h)}</th>`; });
        table += "</tr></thead><tbody>";
        rows.forEach((r) => {
          table += "<tr>";
          headers.forEach((_, idx) => {
            table += `<td>${escapeHtml(r[idx] || "")}</td>`;
          });
          table += "</tr>";
        });
        table += "</tbody></table></div>";
        out.push({ type: "table", html: table });
        continue;
      }
      out.push({ type: "line", text: line });
      i += 1;
    }

    let html = "";
    let buf = [];
    const flush = () => {
      if (!buf.length) return;
      html += `<div class="body-text">${buf.map(escapeHtml).join("\n")}</div>`;
      buf = [];
    };
    out.forEach((chunk) => {
      if (chunk.type === "table") {
        flush();
        html += chunk.html;
      } else {
        buf.push(chunk.text);
      }
    });
    flush();
    return html;
  }

  function formatBlockHtml(content, findings, markerOf) {
    const raw = content === "—" ? "" : (content || "");
    if (!/\| ---/.test(raw) && !/\|---/.test(raw)) {
      return `<div class="body">${markQuotes(escapeHtml(raw), findings, markerOf)}</div>`;
    }
    const tables = [];
    let marked = raw.replace(/(^\|.+\|(?:\n\|\s*:?---.*\|)(?:\n\|.+\|)*)/gm, (m) => {
      tables.push(m);
      return `\n%%TABLE${tables.length - 1}%%\n`;
    });
    marked = markQuotes(escapeHtml(marked), findings, markerOf);
    marked = marked.replace(/%%TABLE(\d+)%%/g, (_, idx) => {
      return `</div>${renderMarkdownTables(tables[Number(idx)])}<div class="body-text">`;
    });
    return `<div class="body"><div class="body-text">${marked}</div></div>`;
  }

  function orderOpenFindings(blocks, findings) {
    const open = findings.filter((f) => f.status === "open");
    const byBlock = {};
    open.forEach((f) => {
      (byBlock[f.block_id] = byBlock[f.block_id] || []).push(f);
    });
    const ordered = [];
    blocks.forEach((b) => {
      const items = (byBlock[b.id] || []).slice().sort((a, b) => b.score - a.score);
      ordered.push(...items);
    });
    return ordered;
  }

  function ensureStableNumbers(findings, blocks) {
    const list = findings || [];
    let max = 0;
    list.forEach((f) => {
      const n = Number(f.no);
      if (Number.isFinite(n) && n > 0) max = Math.max(max, n);
    });
    const assign = (f) => {
      const n = Number(f.no);
      if (!Number.isFinite(n) || n <= 0) {
        max += 1;
        f.no = max;
      } else {
        f.no = n;
      }
    };
    if (blocks && blocks.length) {
      orderOpenFindings(blocks, list).forEach(assign);
    }
    list.forEach(assign);
    return list;
  }

  function buildDocumentHtml(blocks, findings, filename, opts = {}) {
    ensureStableNumbers(findings, blocks);
    const ordered = orderOpenFindings(blocks, findings);
    const markerOf = {};
    findings.forEach((f) => {
      if (f && f.id != null && f.no != null) markerOf[f.id] = f.no;
    });
    const byBlock = {};
    findings.forEach((f) => {
      (byBlock[f.block_id] = byBlock[f.block_id] || []).push(f);
    });

    let html = `<div class="doc-paper"><div class="doc-title">${escapeHtml(filename)}</div>`;
    blocks.forEach((b) => {
      if (!b.present && !b.important && !opts.showOptionalMissing) return;
      const cls = !b.present ? `doc-section missing${b.important ? "" : " optional-missing"}` : "doc-section";
      html += `<section class="${cls}" id="block-${b.id}"><h3>${escapeHtml(b.title)}</h3>`;
      if (!b.present) {
        const msg = b.important
          ? "Отсутствует информация в важном блоке."
          : "Раздел не заполнен (необязателен для этого типа ТЗ).";
        const miss = (byBlock[b.id] || []).filter((f) => f.kind === "missing" && f.status === "open");
        const marks = miss.map((f) => `<sup class="cmt-num" data-marker="${markerOf[f.id]}">[${markerOf[f.id]}]</sup>`).join("");
        html += `<div class="body missing-body">${msg}${marks}</div>`;
      } else {
        const openContent = (byBlock[b.id] || []).filter((f) => f.status === "open");
        html += formatBlockHtml(b.content, openContent, markerOf);
      }
      html += `</section>`;
    });
    html += `</div>`;
    return { html, ordered, markerOf };
  }

  function refreshAfterEdit(sample, text, blockDefs, docType) {
    const blocks = parseDocumentBlocks(text, blockDefs, docType);
    const byId = Object.fromEntries(blocks.map((b) => [b.id, b]));

    const findings = (sample.findings || []).map((f) => {
      const copy = { ...f, anchor: { ...(f.anchor || {}) } };
      const statusKeep = f.status;

      if (statusKeep === "open") {
        if (/CLUSTER/i.test(copy.problem || "")) {
          if (/Кластер:\s*CLUSTER_CDM/i.test(text) || (!/Кластер:\s*CLUSTER\b/i.test(text) && /CLUSTER_CDM/i.test(text))) {
            copy.status = "fixed";
          }
        }
        if (copy.kind === "missing") {
          const block = byId[copy.block_id];
          if (block && block.present && block.content && block.content.trim() && block.content !== "—") {
            copy.status = "fixed";
          }
        }
      } else {
        copy.status = statusKeep;
      }

      const block = byId[copy.block_id];
      if (block && block.present && copy.kind === "content" && copy.status === "open") {
        const body = block.content || "";
        if (/CLUSTER/i.test(copy.problem || "") && /Кластер:\s*CLUSTER/i.test(body)) {
          copy.anchor = {
            ...(copy.anchor || {}),
            excerpt: (body.match(/[^\n]*Кластер:\s*CLUSTER[^\n]*/i) || ["Кластер: CLUSTER"])[0],
          };
        }
      }

      copy.doneness = donenessFromScore(copy.score);
      copy.traffic_light = traffic(copy.doneness);
      return copy;
    });

    return { blocks, findings, text };
  }

  function buildBlankFindings(blocks, docType) {
    return blocks
      .filter((b) => !b.present && b.important)
      .map((b, i) => {
        const probability = 0.95;
        const impact = 0.9;
        const score = Number((probability * impact).toFixed(4));
        const doneness = donenessFromScore(score);
        return {
          id: `blank_${b.id}_${i}`,
          doc_id: "blank",
          doc_type: docType,
          reviewer_role: "developer",
          block: b.title,
          block_id: b.id,
          problem: `Отсутствует информация в важном блоке «${b.title}».`,
          guiding_questions: [
            `Что должно быть в разделе «${b.title}»?`,
            "Где взять недостающие данные?",
          ],
          recommendation: `Заполните блок «${b.title}» по шаблону документации.`,
          probability,
          impact,
          score,
          doneness,
          traffic_light: traffic(doneness),
          status: "open",
          anchor: { excerpt: "" },
          agent: "Agent Analyst",
          focus_area: "template",
          kind: "missing",
        };
      });
  }

  function cloneSample(sample) {
    return JSON.parse(JSON.stringify(sample));
  }

  return {
    escapeHtml,
    ensureStableNumbers,
    buildDocumentHtml,
    orderOpenFindings,
    refreshAfterEdit,
    parseDocumentBlocks,
    buildBlankFindings,
    cloneSample,
    donenessFromScore,
    traffic,
  };
})();
