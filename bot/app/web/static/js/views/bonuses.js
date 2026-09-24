// Бонусы: промокоды и каналы из админки бота, статус VIP.

import { api, state } from "../api.js";
import { copy, empty, esc, openLink } from "../ui.js";
import { cardHead } from "./common.js";
import { vipSheet } from "./vip.js";

export async function renderBonuses(root) {
  const data = await api("/api/bonuses");
  const me = state.me;
  const bk = esc(me.bookmaker || "1win");
  const [main, ...rest] = data.promos;

  root.innerHTML = `
    <h1 class="title">Бонусы</h1>

    <section class="card status ${me.tier === "vip" ? "is-vip" : ""}">
      <div><span class="muted">Ваш статус</span><b>${me.tier === "vip" ? "VIP" : "Базовый"}</b></div>
      ${me.tier === "vip"
        ? `<span class="chip y">Безлимит</span>`
        : `<button type="button" class="btn sm gold" data-vip>Получить VIP</button>`}
    </section>

    ${main ? `
    <section class="card promo-main">
      ${cardHead("Промокод недели")}
      <button type="button" class="promo" data-copy="${esc(main.code)}"><code>${esc(main.code)}</code><span>Копировать</span></button>
      ${main.description ? `<p class="muted">${esc(main.description)}</p>` : ""}
      <button type="button" class="btn big gold" data-link="${esc(main.link)}">Активировать на ${bk}</button>
    </section>` : `<section class="card">${empty("Промокодов пока нет", "Скоро здесь появятся бонусы.")}</section>`}

    ${rest.length ? `
    <section class="card">
      ${cardHead("Ещё промокоды")}
      ${rest.map((p) => `
        <div class="prow">
          <div><b>${esc(p.title)}</b>${p.description ? `<span class="muted">${esc(p.description)}</span>` : ""}</div>
          <button type="button" class="chip-btn" data-copy="${esc(p.code)}">${esc(p.code)}</button>
          <button type="button" class="chip-btn g" data-link="${esc(p.link)}">Открыть</button>
        </div>`).join("")}
    </section>` : ""}

    ${data.channels.length ? `
    <section class="card">
      ${cardHead("Промокоды за подписку")}
      <p class="muted">Подайте заявку в канал, и бот пришлёт отдельный промокод.</p>
      ${data.channels.map((c) => `
        <div class="prow">
          <div><b>${esc(c.title)}</b>${c.promo_title ? `<span class="muted">${esc(c.promo_title)}</span>` : ""}</div>
          ${c.done ? `<span class="chip n">Получено ✓</span>` : `<button type="button" class="chip-btn g" data-link="${esc(c.link)}">Получить</button>`}
        </div>`).join("")}
    </section>` : ""}
  `;

  root.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copy(b.dataset.copy)));
  root.querySelectorAll("[data-link]").forEach((b) => b.addEventListener("click", () => openLink(b.dataset.link)));
  root.querySelector("[data-vip]")?.addEventListener("click", () => vipSheet());
}
