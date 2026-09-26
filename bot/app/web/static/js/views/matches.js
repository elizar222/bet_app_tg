// Список матчей с фильтрами.

import { api } from "../api.js";
import { esc, segmented, onSeg, empty, haptic } from "../ui.js";
import { matchRow } from "./common.js";
import { mountSearch, searchBox } from "./search.js";

const view = { filter: "all", league: "Все" };

export async function renderMatches(root) {
  const { matches } = await api("/api/matches");
  const leagues = ["Все", ...new Set(matches.map((m) => m.league))];

  root.innerHTML = `
    <h1 class="title">Матчи</h1>
    ${searchBox()}
    ${segmented("filter", [["all", "Все"], ["live", "Live"], ["today", "Сегодня"], ["value", "Value"]], view.filter)}
    <div class="chips-scroll">${leagues
      .map((l) => `<button type="button" class="lchip ${l === view.league ? "on" : ""}" data-league="${esc(l)}">${esc(l)}</button>`)
      .join("")}</div>
    <div data-list></div>
  `;

  const draw = () => {
    const today = new Date().toDateString();
    let rows = matches.filter((m) => view.league === "Все" || m.league === view.league);
    if (view.filter === "live") rows = rows.filter((m) => m.status === "live");
    if (view.filter === "today") rows = rows.filter((m) => new Date(m.kickoff).toDateString() === today);
    if (view.filter === "value") rows = rows.filter((m) => m.best_value);

    const list = root.querySelector("[data-list]");
    if (!rows.length) {
      list.innerHTML = matches.length
        ? empty("Ничего не найдено", "Попробуйте другой фильтр или лигу.")
        : empty("Матчей пока нет", "В ближайшую неделю топ-лиги не играют — скорее всего, пауза на игры сборных. Матчи появятся автоматически.");
      return;
    }
    const groups = new Map();
    rows.forEach((m) => {
      if (!groups.has(m.league)) groups.set(m.league, []);
      groups.get(m.league).push(m);
    });
    list.innerHTML = [...groups].map(([league, ms]) => `
      <section class="card">
        <div class="card-h"><h3>${esc(league)}</h3><span class="muted">${esc(ms[0].country)}</span></div>
        <div class="mlist">${ms.map((m) => matchRow(m)).join("")}</div>
      </section>`).join("");
  };

  mountSearch(root);
  onSeg(root, "filter", (v) => { view.filter = v; draw(); });
  root.querySelectorAll("[data-league]").forEach((b) => b.addEventListener("click", () => {
    view.league = b.dataset.league;
    root.querySelectorAll("[data-league]").forEach((x) => x.classList.toggle("on", x === b));
    haptic();
    draw();
  }));
  draw();
}
