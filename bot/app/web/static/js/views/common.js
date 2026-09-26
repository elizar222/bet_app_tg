// Компоненты, которые используются на нескольких экранах.

import { crest, esc, kickoff, odds, pct, FORM_LABEL } from "../ui.js";
import { probBar } from "../charts.js";

export function matchRow(m, { showLeague = false } = {}) {
  const live = m.status === "live";
  const o = (live && m.live && m.live.odds) || m.odds || {};
  const badges = [];
  if (m.best_value) badges.push(`<span class="chip g">Value ${pct(m.best_value.edge, 0, true)}</span>`);
  if (m.odds_move && m.odds_move.change <= -0.06)
    badges.push(`<span class="chip r">▼ ${esc(m.odds_move.pick)} ${pct(m.odds_move.change)}</span>`);
  return `<a class="mrow" href="#/match/${m.id}">
    <div class="mrow-meta">
      ${live ? `<span class="live-dot"></span><span class="live-t">${m.live.minute}'</span>` : `<span>${esc(kickoff(m.kickoff))}</span>`}
      ${showLeague ? `<span class="muted">· ${esc(m.league)}</span>` : ""}
      <span class="mrow-badges">${badges.join("")}</span>
    </div>
    <div class="mrow-main">
      <div class="teams">
        <div>${crest(m.home.name, m.home.short, "sm", m.home.logo)}<span>${esc(m.home.name)}</span>${live ? `<b>${esc(m.live.score.split(":")[0])}</b>` : ""}</div>
        <div>${crest(m.away.name, m.away.short, "sm", m.away.logo)}<span>${esc(m.away.name)}</span>${live ? `<b>${esc(m.live.score.split(":")[1])}</b>` : ""}</div>
      </div>
      <div class="oddsbox">
        <span><small>П1</small>${odds(o.home)}</span>
        <span><small>X</small>${odds(o.draw)}</span>
        <span><small>П2</small>${odds(o.away)}</span>
      </div>
    </div>
    ${m.probs ? probBar(m.probs) : ""}
  </a>`;
}

export function formChips(form, n = 5) {
  return `<span class="form">${form.slice(0, n)
    .map((f) => `<i class="f-${f.result}" title="${esc(f.opponent)} ${esc(f.score)}">${FORM_LABEL[f.result]}</i>`)
    .join("")}</span>`;
}

export function legend(items) {
  return `<div class="legend">${items.map(([c, t]) => `<span><i style="background:${c}"></i>${esc(t)}</span>`).join("")}</div>`;
}

export function cardHead(title, right = "") {
  return `<div class="card-h"><h3>${esc(title)}</h3>${right}</div>`;
}

export function info(text) {
  return `<button type="button" class="info" data-info="${esc(text)}" aria-label="Что это?">?</button>`;
}

export function kpi(label, value, cls = "") {
  return `<div class="kpi"><span class="kpi-l">${esc(label)}</span><span class="kpi-v ${cls}">${value}</span></div>`;
}

export function statusChip(status) {
  const map = {
    pending: ["y", "В игре"], won: ["g", "Зашла"], lost: ["r", "Не зашла"],
    void: ["n", "Возврат"], hedged: ["b", "Хедж"],
  };
  const [c, t] = map[status] || ["n", status];
  return `<span class="chip ${c}">${t}</span>`;
}
