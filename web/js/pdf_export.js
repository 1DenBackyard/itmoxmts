window.MTSPDFExport = (function () {
  function escapeHtml(s) {
    return MTSAnalyzer.escapeHtml(s);
  }

  function splitPipeRow(line) {
    return line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
  }

  function renderMarkdownTables(text) {
    const lines = String(text || "").split(/\n/);
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const next = lines[i + 1] || "";
      const isHeader = /^\|.+\|$/.test(line.trim());
      const isSep = /^\|\s*:?-{3,}/.test(next.trim());
      if (isHeader && isSep) {
        const headers = splitPipeRow(line);
        i += 2;
        const rows = [];
        while (i < lines.length && /^\|.+\|$/.test(lines[i].trim())) {
          rows.push(splitPipeRow(lines[i]));
          i += 1;
        }
        const colCount = Math.max(headers.length, ...rows.map((r) => r.length), 1);
        let table = '<div class="pdf-table-wrap"><table class="pdf-table"><thead><tr>';
        for (let c = 0; c < colCount; c++) {
          table += `<th>${escapeHtml(headers[c] || "")}</th>`;
        }
        table += "</tr></thead><tbody>";
        rows.forEach((r) => {
          table += "<tr>";
          for (let c = 0; c < colCount; c++) {
            table += `<td>${escapeHtml(r[c] || "")}</td>`;
          }
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
      const chunk = buf.join("\n").replace(/\n{3,}/g, "\n\n").trim();
      if (chunk) html += `<div class="pdf-text">${escapeHtml(chunk)}</div>`;
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

  function formatContent(content) {
    const raw = content === "—" ? "" : content || "";
    if (!raw.trim()) return `<div class="pdf-text pdf-empty">—</div>`;
    if (!/\| ---/.test(raw) && !/\|---/.test(raw) && !/^\|.+\|/m.test(raw)) {
      return `<div class="pdf-text">${escapeHtml(raw)}</div>`;
    }
    return renderMarkdownTables(raw);
  }

  function buildExportHtml(working) {
    const title = (working.filename || "ТЗ").replace(/\.pdf$/i, "");
    const blocks = working.blocks || [];
    let body = "";
    blocks.forEach((b) => {
      if (!b.present && !b.important) return;
      body += `<section class="pdf-section">`;
      body += `<h2>${escapeHtml(b.title)}</h2>`;
      if (!b.present) {
        body += `<div class="pdf-text pdf-missing">Раздел не заполнен.</div>`;
      } else {
        body += formatContent(b.content);
      }
      body += `</section>`;
    });

    return `
      <div class="pdf-doc" id="pdf-export-root">
        <div class="pdf-brand">МТС · Документация объекта данных</div>
        <h1 class="pdf-title">${escapeHtml(title)}</h1>
        <div class="pdf-meta">Итоговая версия после ревью · ${escapeHtml(working.label || "")}</div>
        ${body}
      </div>
    `;
  }

  function exportStyles() {
    return `
      @page { size: A4; margin: 14mm 12mm; }
      * { box-sizing: border-box; }
      html, body {
        margin: 0;
        padding: 0;
        background: #fff;
        color: #1a1a1a;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }
      .pdf-doc {
        max-width: 100%;
        padding: 0;
        font-family: "PT Root UI", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      }
      .pdf-brand {
        font-size: 10px;
        font-weight: 800;
        color: #ff0032;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin: 0 0 8px;
      }
      .pdf-title {
        font-size: 20px;
        font-weight: 800;
        margin: 0 0 6px;
        padding-bottom: 8px;
        border-bottom: 2px solid #ff0032;
        line-height: 1.25;
      }
      .pdf-meta {
        font-size: 11px;
        color: #666;
        margin: 0 0 18px;
      }
      .pdf-section {
        margin: 0 0 14px;
        break-inside: auto;
        page-break-inside: auto;
      }
      .pdf-section h2 {
        font-size: 13px;
        font-weight: 800;
        margin: 0 0 6px;
        page-break-after: avoid;
      }
      .pdf-text {
        white-space: pre-wrap;
        font-size: 11.5px;
        line-height: 1.45;
        margin: 0 0 8px;
        word-break: break-word;
      }
      .pdf-empty, .pdf-missing {
        color: #888;
        font-style: italic;
      }
      .pdf-table-wrap {
        margin: 6px 0 12px;
        width: 100%;
        overflow: visible;
      }
      .pdf-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        font-size: 9.5px;
        line-height: 1.35;
      }
      .pdf-table thead { display: table-header-group; }
      .pdf-table tr { page-break-inside: avoid; break-inside: avoid; }
      .pdf-table th,
      .pdf-table td {
        border: 1px solid #bdbdbd;
        padding: 5px 6px;
        vertical-align: top;
        text-align: left;
        word-wrap: break-word;
        overflow-wrap: anywhere;
      }
      .pdf-table th {
        background: #f0f0f2 !important;
        font-weight: 700;
      }
      .pdf-hint {
        margin: 16px 0 0;
        font-size: 11px;
        color: #888;
      }
      @media print {
        .pdf-hint { display: none !important; }
        a { color: inherit; text-decoration: none; }
      }
      @media screen {
        body { padding: 24px; background: #f4f4f5; }
        .pdf-doc {
          max-width: 820px;
          margin: 0 auto;
          background: #fff;
          padding: 28px 32px 36px;
          box-shadow: 0 8px 30px rgba(0,0,0,.08);
        }
      }
    `;
  }

  function buildFullDocument(working) {
    const title = (working.filename || "ТЗ").replace(/\.pdf$/i, "");
    return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(title)} · итоговый PDF</title>
  <style>${exportStyles()}</style>
</head>
<body>
  ${buildExportHtml(working)}
  <p class="pdf-hint">В диалоге печати выберите принтер «Сохранить как PDF» / «Save as PDF», поля — по умолчанию, поля страницы — обычные.</p>
</body>
</html>`;
  }

  function downloadPdf(working) {
    const html = buildFullDocument(working);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    return new Promise((resolve, reject) => {
      const win = window.open(url, "_blank", "noopener,noreferrer,width=900,height=700");
      if (!win) {
        URL.revokeObjectURL(url);
        reject(new Error("Браузер заблокировал окно. Разрешите всплывающие окна и нажмите снова."));
        return;
      }

      let printed = false;
      const triggerPrint = () => {
        if (printed) return;
        printed = true;
        try {
          win.focus();
          win.print();
        } catch (err) {
          reject(err);
          return;
        }
        resolve((working.filename || "TZ").replace(/\.pdf$/i, "") + "_итоговый.pdf");
      };

      // ждём отрисовку документа в новом окне
      const timer = setInterval(() => {
        try {
          if (win.document && win.document.readyState === "complete") {
            clearInterval(timer);
            setTimeout(triggerPrint, 200);
          }
        } catch (_) {
          /* ignore cross-check while loading */
        }
      }, 50);

      setTimeout(() => {
        clearInterval(timer);
        triggerPrint();
      }, 1500);

      win.addEventListener("afterprint", () => {
        try { win.close(); } catch (_) { /* ignore */ }
        URL.revokeObjectURL(url);
      });

      setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
  }

  return { downloadPdf, buildExportHtml, buildFullDocument };
})();
