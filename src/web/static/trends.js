/* Small-multiple line charts for the trends page — one per metric, no
 * charting library. Follows this project's chart conventions: thin 2px
 * line in the sequential accent hue, recessive baseline gridline, a
 * hover crosshair + tooltip, and a direct end-value label (a single
 * series needs no legend — the card header already names it).
 */
(function () {
  const DATA = JSON.parse(document.getElementById("trends-data").textContent);
  if (!DATA.has_data) return;

  const SVG_NS = "http://www.w3.org/2000/svg";
  let granularity = "daily";

  function seriesFor(mode) {
    if (mode === "weekly") return DATA.weekly.map((r) => ({ x: r.period, ...r }));
    if (mode === "monthly") return DATA.monthly.map((r) => ({ x: r.period, ...r }));
    return DATA.daily.map((r) => ({ x: r.date, ...r }));
  }

  function formatValue(v) {
    if (v === null || v === undefined) return "—";
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
  }

  function el(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, val] of Object.entries(attrs || {})) node.setAttribute(k, val);
    return node;
  }

  function renderChart(card, series, key) {
    const svg = card.querySelector("svg");
    const tooltip = card.querySelector(".chart-tooltip");
    const latestEl = card.querySelector(".chart-latest");
    const w = 600;
    const h = 120;
    const pad = { top: 10, right: 8, bottom: 14, left: 8 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;

    svg.innerHTML = "";
    const points = series.map((row, i) => ({ i, x: row.x, y: row[key] }));
    const values = points.map((p) => p.y).filter((y) => y !== null && y !== undefined);

    const lastPoint = [...points].reverse().find((p) => p.y !== null && p.y !== undefined);
    latestEl.textContent = lastPoint ? formatValue(lastPoint.y) : "—";

    if (values.length === 0) {
      svg.appendChild(
        el("text", { x: w / 2, y: h / 2, "text-anchor": "middle", class: "chart-empty" })
      ).textContent = "No data yet";
      return;
    }

    const minY = Math.min(...values);
    const maxY = Math.max(...values);
    const yRange = maxY - minY || 1;
    const xFor = (i) => pad.left + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
    const yFor = (v) => pad.top + plotH - ((v - minY) / yRange) * plotH;

    svg.appendChild(
      el("line", {
        x1: pad.left,
        x2: w - pad.right,
        y1: h - pad.bottom,
        y2: h - pad.bottom,
        class: "chart-gridline",
      })
    );

    let d = "";
    let drawing = false;
    for (const p of points) {
      if (p.y === null || p.y === undefined) {
        drawing = false;
        continue;
      }
      d += `${drawing ? "L" : "M"}${xFor(p.i).toFixed(1)},${yFor(p.y).toFixed(1)} `;
      drawing = true;
    }
    svg.appendChild(el("path", { d: d.trim(), class: "chart-line" }));

    if (lastPoint) {
      svg.appendChild(
        el("circle", {
          cx: xFor(lastPoint.i),
          cy: yFor(lastPoint.y),
          r: 4,
          class: "chart-end-dot",
        })
      );
    }

    // Hover layer: crosshair + tooltip, per this project's interaction rules.
    const crosshair = el("line", {
      y1: pad.top,
      y2: h - pad.bottom,
      class: "chart-crosshair",
    });
    crosshair.style.display = "none";
    svg.appendChild(crosshair);

    const hitArea = el("rect", {
      x: pad.left,
      y: 0,
      width: plotW,
      height: h,
      fill: "transparent",
    });
    svg.appendChild(hitArea);

    hitArea.addEventListener("mousemove", (evt) => {
      const rect = svg.getBoundingClientRect();
      const mx = ((evt.clientX - rect.left) / rect.width) * w;
      const idx = Math.round(((mx - pad.left) / plotW) * (points.length - 1));
      const p = points[Math.max(0, Math.min(points.length - 1, idx))];
      if (!p) return;
      const px = xFor(p.i);
      crosshair.setAttribute("x1", px);
      crosshair.setAttribute("x2", px);
      crosshair.style.display = "block";
      tooltip.style.display = "block";
      tooltip.style.left = `${(px / w) * 100}%`;
      tooltip.textContent = `${p.x}: ${formatValue(p.y)}`;
    });
    hitArea.addEventListener("mouseleave", () => {
      crosshair.style.display = "none";
      tooltip.style.display = "none";
    });
  }

  function renderAll() {
    const series = seriesFor(granularity);
    document.querySelectorAll(".chart-card").forEach((card) => {
      renderChart(card, series, card.dataset.metric);
    });
  }

  document.querySelectorAll(".granularity-toggle .segmented-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".granularity-toggle .segmented-option")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      granularity = btn.dataset.granularity;
      renderAll();
    });
  });

  const tableToggle = document.getElementById("toggle-table");
  if (tableToggle) {
    tableToggle.addEventListener("click", () => {
      const table = document.getElementById("trends-table");
      table.hidden = !table.hidden;
      tableToggle.setAttribute("aria-expanded", String(!table.hidden));
    });
  }

  renderAll();
})();
