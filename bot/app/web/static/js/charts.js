// Графики на чистом SVG — без библиотек, чтобы мини-апп грузился мгновенно.
// Все графики тянутся по ширине контейнера и понимают «скраббинг» пальцем.

const NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  parent?.appendChild(e);
  return e;
}

function niceTicks(min, max, count = 4) {
  const span = max - min || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const r = raw / mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-6; v += step) ticks.push(+v.toFixed(6));
  return ticks;
}

/**
 * Линейный график.
 * opts: { series: [{name, color, values, area}], labels: [...], height, fmt, yFmt, readout: HTMLElement, zero }
 */
export function lineChart(host, opts) {
  const W = 340, H = opts.height || 150, L = opts.yFmt ? 38 : 6, R = 8, T = 10, B = opts.labels ? 20 : 8;
  const all = opts.series.flatMap((s) => s.values).filter((v) => v != null);
  if (!all.length) { host.innerHTML = ""; return; }
  let min = Math.min(...all), max = Math.max(...all);
  if (opts.zero) { min = Math.min(min, 0); max = Math.max(max, 0); }
  const pad = (max - min) * 0.12 || Math.abs(max) * 0.1 || 1;
  min -= pad; max += pad;
  const ticks = opts.yFmt ? niceTicks(min, max, 3) : [];
  const n = Math.max(...opts.series.map((s) => s.values.length));
  const X = (i) => L + (n <= 1 ? (W - L - R) / 2 : (i / (n - 1)) * (W - L - R));
  const Y = (v) => T + ((max - v) / (max - min)) * (H - T - B);

  host.innerHTML = "";
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img" }, host);
  for (const t of ticks) {
    if (t < min || t > max) continue;
    svgEl("line", { x1: L, x2: W - R, y1: Y(t), y2: Y(t), class: t === 0 ? "axis0" : "grid" }, svg);
    svgEl("text", { x: L - 6, y: Y(t) + 3, class: "tick", "text-anchor": "end" }, svg).textContent = opts.yFmt(t);
  }
  if (opts.zero && !ticks.length) svgEl("line", { x1: L, x2: W - R, y1: Y(0), y2: Y(0), class: "axis0" }, svg);
  if (opts.labels) {
    const idxs = [0, Math.floor((n - 1) / 2), n - 1];
    idxs.forEach((i, k) => {
      if (opts.labels[i] == null) return;
      svgEl("text", { x: X(i), y: H - 5, class: "tick", "text-anchor": k === 0 ? "start" : k === 2 ? "end" : "middle" }, svg)
        .textContent = opts.labels[i];
    });
  }

  const dots = [];
  opts.series.forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : [X(i), Y(v)])).filter(Boolean);
    if (!pts.length) return;
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
    if (s.area) {
      const base = Y(opts.zero ? 0 : min);
      svgEl("path", { d: `${d}L${pts.at(-1)[0]},${base}L${pts[0][0]},${base}Z`, fill: s.color, "fill-opacity": 0.1 }, svg);
    }
    svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    const last = pts.at(-1);
    svgEl("circle", { cx: last[0], cy: last[1], r: 4, fill: s.color, class: "ring" }, svg);
    dots.push(svgEl("circle", { r: 4.5, fill: s.color, class: "ring", opacity: 0 }, svg));
  });

  const cross = svgEl("line", { y1: T, y2: H - B, class: "cross", opacity: 0 }, svg);
  const readout = opts.readout;
  const defaultText = readout?.innerHTML;
  const hit = svgEl("rect", { x: L, y: 0, width: W - L - R, height: H, fill: "transparent" }, svg);
  const move = (ev) => {
    const r = svg.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n - 1, Math.round(((x - L) / (W - L - R)) * (n - 1))));
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("opacity", 1);
    opts.series.forEach((s, k) => {
      const v = s.values[i];
      if (!dots[k]) return;
      if (v == null) { dots[k].setAttribute("opacity", 0); return; }
      dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(v)); dots[k].setAttribute("opacity", 1);
    });
    if (readout && opts.fmt) readout.innerHTML = opts.fmt(i);
  };
  const leave = () => {
    cross.setAttribute("opacity", 0);
    dots.forEach((d) => d.setAttribute("opacity", 0));
    if (readout) readout.innerHTML = defaultText;
  };
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerleave", leave);
  hit.addEventListener("pointerup", () => setTimeout(leave, 1200));
}

/** Мини-график без осей. */
export function sparkline(host, values, color) {
  const W = 120, H = 32;
  if (!values?.length) return;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const X = (i) => 2 + (i / Math.max(1, values.length - 1)) * (W - 6);
  const Y = (v) => 3 + ((max - v) / span) * (H - 6);
  host.innerHTML = "";
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "spark" }, host);
  const d = values.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1)).join("");
  svgEl("path", { d, fill: "none", stroke: color, "stroke-width": 1.8, "stroke-linejoin": "round" }, svg);
  svgEl("circle", { cx: X(values.length - 1), cy: Y(values.at(-1)), r: 3, fill: color, class: "ring" }, svg);
}

/** График давления: столбики вверх — хозяева, вниз — гости. */
export function momentum(host, points, events, colors) {
  const W = 340, H = 120, T = 8, B = 16, mid = T + (H - T - B) / 2, half = (H - T - B) / 2;
  host.innerHTML = "";
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart" }, host);
  const X = (m) => 4 + ((m - 1) / 89) * (W - 8);
  const bw = Math.max(1.2, (W - 8) / 90 - 1);
  svgEl("line", { x1: 4, x2: W - 4, y1: mid, y2: mid, class: "axis0" }, svg);
  svgEl("line", { x1: X(45.5), x2: X(45.5), y1: T, y2: H - B, class: "grid" }, svg);
  for (const p of points) {
    const h = (Math.abs(p.v) / 100) * half;
    if (h < 0.5) continue;
    svgEl("rect", {
      x: X(p.m) - bw / 2, width: bw, y: p.v > 0 ? mid - h : mid, height: h,
      rx: 1, fill: p.v > 0 ? colors.home : colors.away,
    }, svg);
  }
  for (const e of events || []) {
    if (e.type !== "goal") continue;
    const y = e.team === "home" ? T + 2 : H - B - 2;
    svgEl("circle", { cx: X(e.m), cy: y, r: 4, fill: "var(--text)", class: "ring" }, svg);
  }
  [["1'", 1, "start"], ["45'", 45.5, "middle"], ["90'", 90, "end"]].forEach(([t, m, a]) =>
    (svgEl("text", { x: X(m), y: H - 3, class: "tick", "text-anchor": a }, svg).textContent = t));
}

/** Тепловая карта точного счёта 0..4 × 0..4. */
export function scoreHeatmap(host, matrix, homeShort, awayShort) {
  const flat = matrix.flat();
  const max = Math.max(...flat);
  let html = `<div class="heat"><div class="heat-corner">${homeShort} ↓ · ${awayShort} →</div><div></div>`;
  for (let j = 0; j < 5; j++) html += `<div class="heat-h">${j}</div>`;
  matrix.forEach((row, i) => {
    html += `<div class="heat-h">${i}</div>`;
    row.forEach((p, j) => {
      const a = 0.08 + (p / max) * 0.82;
      const strong = p / max > 0.55;
      html += `<div class="heat-c${strong ? " strong" : ""}" style="--a:${a.toFixed(2)}" title="${i}:${j}">${(p * 100).toFixed(p >= 0.1 ? 0 : 1).replace(".", ",")}</div>`;
    });
  });
  host.innerHTML = html + "</div>";
}

/** Линии «хозяева / гости» для сравнения статистики (HTML). */
export function compareRows(rows) {
  return rows.map((r) => {
    const h = Number(r.home) || 0, a = Number(r.away) || 0, total = h + a || 1;
    const hb = h >= a, ab = a >= h;
    return `<div class="cmp">
      <div class="cmp-top"><b class="${hb ? "lead" : ""}">${r.home}</b><span>${r.name}</span><b class="${ab ? "lead" : ""}">${r.away}</b></div>
      <div class="cmp-bars"><i class="h" style="width:${(h / total) * 100}%"></i><i class="a" style="width:${(a / total) * 100}%"></i></div>
    </div>`;
  }).join("");
}

/** Горизонтальная полоса вероятностей 1/X/2. */
export function probBar(p) {
  return `<div class="pbar"><i style="width:${p.home * 100}%;background:var(--c-home)"></i><i style="width:${p.draw * 100}%;background:var(--c-draw)"></i><i style="width:${p.away * 100}%;background:var(--c-away)"></i></div>`;
}

/** Кольцо-индикатор (процент зашедших и т.п.). */
export function ring(value, color = "var(--green)", label = "") {
  const deg = Math.max(0, Math.min(1, value)) * 360;
  return `<div class="ring-g" style="--deg:${deg}deg;--c:${color}"><span>${Math.round(value * 100)}%</span>${label ? `<small>${label}</small>` : ""}</div>`;
}

/** Хедж: прибыль при двух исходах в зависимости от суммы хеджа. */
export function hedgeChart(host, { payout, stake, odds, amount, readout, fmt }) {
  const eq = payout / odds, zr = stake / (odds - 1);
  const maxH = Math.max(eq, zr, amount || 0) * 1.3;
  const steps = 60;
  const xs = Array.from({ length: steps + 1 }, (_, i) => (i / steps) * maxH);
  const a = xs.map((h) => payout - stake - h);
  const b = xs.map((h) => h * (odds - 1) - stake);
  lineChart(host, {
    height: 170,
    zero: true,
    yFmt: (v) => (Math.abs(v) >= 1e3 ? Math.round(v / 1e3) + "k" : Math.round(v)),
    labels: xs.map((h) => Math.round(h / 1e3) + "k"),
    series: [
      { name: "Купон зашёл", color: "var(--c-home)", values: a },
      { name: "Зашёл хедж", color: "var(--c-away)", values: b },
    ],
    readout,
    fmt: (i) => fmt(xs[i], a[i], b[i]),
  });
  // отметки режимов
  const svg = host.querySelector("svg");
  if (!svg) return;
  const W = 340, L = 38, R = 8;
  const X = (h) => L + (h / maxH) * (W - L - R);
  [[eq, "Поровну"], [zr, "Без риска"]].forEach(([h, t]) => {
    const x = X(h);
    svgEl("line", { x1: x, x2: x, y1: 10, y2: 150, class: "mark" }, svg);
    svgEl("text", { x: x + 3, y: 20, class: "tick mark-t" }, svg).textContent = t;
  });
  if (amount) {
    const x = X(amount);
    svgEl("line", { x1: x, x2: x, y1: 10, y2: 150, stroke: "var(--gold)", "stroke-width": 1.5 }, svg);
  }
}
