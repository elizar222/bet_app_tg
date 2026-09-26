// Поиск события «как на 1win»: пользователь пишет команды по-русски, находим матч.

import { api } from "../api.js";
import { esc, haptic } from "../ui.js";
import { matchRow } from "./common.js";

let lastQuery = "";

export function searchBox(placeholder = "Найти матч: «Словения Шотландия», «Реал»…") {
  return `
    <section class="search">
      <label class="search-field">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input id="search-q" type="search" inputmode="search" autocomplete="off" enterkeyhint="search"
               placeholder="${esc(placeholder)}" value="${esc(lastQuery)}">
        <button type="button" class="search-clear" data-clear ${lastQuery ? "" : "hidden"} aria-label="Очистить">×</button>
      </label>
      <div class="search-results" data-results hidden></div>
    </section>`;
}

export function mountSearch(root) {
  const input = root.querySelector("#search-q");
  const box = root.querySelector("[data-results]");
  const clear = root.querySelector("[data-clear]");
  if (!input) return;
  let timer = null;
  let seq = 0;

  const run = async () => {
    const q = input.value.trim();
    lastQuery = q;
    clear.hidden = !q;
    if (q.length < 2) { box.hidden = true; box.innerHTML = ""; return; }
    const my = ++seq;
    box.hidden = false;
    box.innerHTML = `<div class="search-hint">Ищу «${esc(q)}»…</div>`;
    try {
      const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
      if (my !== seq) return;
      box.innerHTML = results.length
        ? `<div class="search-hint">Найдено: ${results.length}. Выберите матч для анализа</div><div class="mlist">${results.map((m) => matchRow(m, { showLeague: true })).join("")}</div>`
        : `<div class="search-hint">Ничего не нашлось. Попробуйте одну команду или другое написание — например, «Шотландия».</div>`;
    } catch {
      if (my === seq) box.innerHTML = `<div class="search-hint">Не удалось выполнить поиск. Проверьте интернет.</div>`;
    }
  };

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 350); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { clearTimeout(timer); input.blur(); run(); } });
  clear.addEventListener("click", () => { input.value = ""; haptic(); run(); input.focus(); });
  if (lastQuery.length >= 2) run();
}
