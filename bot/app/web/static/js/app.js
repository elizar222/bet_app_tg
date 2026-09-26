// Точка входа: Telegram SDK, навигация по экранам, нижнее меню.

import { loadMe, ApiError } from "./api.js";
import { esc, haptic, loader, sheet, tg } from "./ui.js";
import { renderHome } from "./views/home.js";
import { renderMatches } from "./views/matches.js";
import { renderMatch } from "./views/match.js";
import { renderHedge } from "./views/hedge.js";
import { renderStats } from "./views/stats.js";
import { renderBonuses } from "./views/bonuses.js";

const routes = {
  home: renderHome,
  matches: renderMatches,
  match: renderMatch,
  hedge: renderHedge,
  stats: renderStats,
  bonuses: renderBonuses,
};
const TABS = ["home", "matches", "hedge", "stats", "bonuses"];
const view = document.getElementById("view");
let renderId = 0;

// Подсказки «?» на карточках
window.__info = (text) => sheet(`<p class="info-text">${esc(text)}</p><button type="button" class="btn" data-close>Понятно</button>`,
  (el, close) => el.querySelector("[data-close]").addEventListener("click", close));

function parse() {
  const raw = location.hash.replace(/^#\/?/, "") || "home";
  const [path, query = ""] = raw.split("?");
  const [name, id] = path.split("/");
  return { name: routes[name] ? name : "home", id, params: new URLSearchParams(query) };
}

async function render() {
  const { name, id, params } = parse();
  const my = ++renderId;
  document.querySelectorAll(".nav a").forEach((a) =>
    a.classList.toggle("on", a.dataset.tab === (name === "match" ? "matches" : name)));
  if (tg?.BackButton) name === "match" || !TABS.includes(name) ? tg.BackButton.show() : tg.BackButton.hide();

  view.innerHTML = loader();
  window.scrollTo(0, 0);
  try {
    const page = document.createElement("div");
    page.className = "page";
    await routes[name](page, name === "match" ? id : params);
    if (my !== renderId) return;
    view.replaceChildren(page);
    page.querySelectorAll("[data-info]").forEach((b) => b.addEventListener("click", () => window.__info(b.dataset.info)));
  } catch (e) {
    if (my !== renderId) return;
    const msg = e instanceof ApiError && e.status === 401
      ? "Откройте терминал через кнопку в Telegram-боте."
      : "Не удалось загрузить данные. Проверьте интернет и попробуйте ещё раз.";
    view.innerHTML = `<div class="empty"><div class="empty-t">Ошибка</div><p>${msg}</p><button type="button" class="btn" onclick="location.reload()">Обновить</button></div>`;
    console.error(e);
  }
}

async function start() {
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("#121212"); tg.setBackgroundColor("#121212"); tg.setBottomBarColor?.("#121212"); } catch { /* старые клиенты */ }
    tg.BackButton?.onClick(() => (history.length > 1 ? history.back() : (location.hash = "#/matches")));
  }
  document.querySelectorAll(".nav a").forEach((a) => a.addEventListener("click", () => haptic()));
  try {
    await loadMe();
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="empty-t">Нет доступа</div><p>Откройте терминал через кнопку в Telegram-боте.</p></div>`;
    return;
  }
  const tier = document.getElementById("tier");
  const me = (await import("./api.js")).state.me;
  tier.textContent = me.tier === "vip" ? "VIP" : "BASE";
  tier.classList.toggle("vip", me.tier === "vip");
  tier.hidden = false;
  tier.addEventListener("click", () => (location.hash = "#/bonuses"));
  window.addEventListener("hashchange", render);
  render();
}

start();
