window.MTSPDF = (function () {
  function ensurePdfJs() {
    if (!window.pdfjsLib) {
      throw new Error("pdf.js не загружен. Проверьте интернет/CDN.");
    }
    if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdf.worker.min.js";
    }
  }

  function clusterRows(items, yTol) {
    const sorted = items
      .filter((it) => (it.str || "").trim())
      .slice()
      .sort((a, b) => b.y - a.y || a.x - b.x);
    const rows = [];
    sorted.forEach((it) => {
      const last = rows[rows.length - 1];
      if (last && Math.abs(last.y - it.y) <= yTol) {
        last.cells.push(it);
        last.y = (last.y * (last.cells.length - 1) + it.y) / last.cells.length;
      } else {
        rows.push({ y: it.y, cells: [it] });
      }
    });
    rows.forEach((r) => r.cells.sort((a, b) => a.x - b.x));
    return rows;
  }

  function mergeCloseCells(cells, xTol) {
    if (!cells.length) return [];
    const out = [];
    let cur = { ...cells[0], str: cells[0].str };
    for (let i = 1; i < cells.length; i++) {
      const c = cells[i];
      const gap = c.x - (cur.x + (cur.w || 0));
      if (gap < xTol) {
        cur.str += (gap < 1 ? "" : " ") + c.str;
        cur.w = c.x + (c.w || 0) - cur.x;
      } else {
        out.push(cur);
        cur = { ...c, str: c.str };
      }
    }
    out.push(cur);
    return out;
  }

  function rowSignature(cells) {
    // snap x to buckets for column alignment
    return cells.map((c) => Math.round(c.x / 12) * 12);
  }

  function isTableBlock(rows) {
    if (rows.length < 2) return false;
    const multi = rows.filter((r) => r.cells.length >= 2);
    if (multi.length < 2) return false;
    // column count consistency
    const counts = multi.map((r) => r.cells.length);
    const mode = counts.sort((a, b) =>
      counts.filter((v) => v === a).length - counts.filter((v) => v === b).length
    ).pop();
    const sameish = counts.filter((c) => Math.abs(c - mode) <= 1).length;
    return sameish >= Math.max(2, Math.floor(multi.length * 0.6)) && mode >= 2;
  }

  function toMarkdownTable(rows) {
    const cellsRows = rows.map((r) => r.cells.map((c) => (c.str || "").replace(/\s+/g, " ").trim()));
    const colCount = Math.max(...cellsRows.map((r) => r.length));
    const norm = cellsRows.map((r) => {
      const copy = r.slice();
      while (copy.length < colCount) copy.push("");
      return copy.slice(0, colCount);
    });
    // first row as header if looks like labels
    const header = norm[0];
    const body = norm.slice(1);
    const lines = [];
    lines.push("| " + header.join(" | ") + " |");
    lines.push("| " + header.map(() => "---").join(" | ") + " |");
    body.forEach((r) => lines.push("| " + r.join(" | ") + " |"));
    return lines.join("\n");
  }

  function pageRowsToText(rows) {
    const chunks = [];
    let i = 0;
    while (i < rows.length) {
      // try gather consecutive multi-column rows as table
      if (rows[i].cells.length >= 2) {
        let j = i;
        const block = [];
        while (j < rows.length && rows[j].cells.length >= 2) {
          block.push(rows[j]);
          j += 1;
          // allow one sparse row inside? keep strict for now
        }
        if (isTableBlock(block)) {
          chunks.push(toMarkdownTable(block));
          i = j;
          continue;
        }
      }
      chunks.push(rows[i].cells.map((c) => c.str).join(" ").replace(/\s+/g, " ").trim());
      i += 1;
    }
    return chunks.filter(Boolean).join("\n");
  }

  async function extractFromPdf(arrayBuffer) {
    ensurePdfJs();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    const parts = [];
    for (let p = 1; p <= pdf.numPages; p++) {
      const page = await pdf.getPage(p);
      const content = await page.getTextContent();
      const items = (content.items || []).map((it) => ({
        str: it.str || "",
        x: it.transform[4],
        y: it.transform[5],
        w: it.width || 0,
        h: it.height || 0,
      }));
      const rows = clusterRows(items, 3.5).map((r) => ({
        y: r.y,
        cells: mergeCloseCells(r.cells, 8),
      }));
      parts.push(pageRowsToText(rows));
    }
    return parts.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  async function extractFromFile(file) {
    const name = (file && file.name) || "";
    const lower = name.toLowerCase();
    if (lower.endsWith(".pdf")) {
      const buf = await file.arrayBuffer();
      return extractFromPdf(buf);
    }
    return file.text();
  }

  return { extractFromPdf, extractFromFile };
})();
