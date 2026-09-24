// Главная: банк, активные ставки, Live, value, падения кэфов, экспресс дня, статистика канала.

import { api, state } from "../api.js";
import { lineChart, ring, sparkline } from "../charts.js";
import { esc, kickoff, money, odds, pct, signClass } from "../ui.js";
import { cardHead, info, kpi, matchRow } from "./common.js";

export async function renderHome(root) {
  const data = await api("/api/home");
  const me = state.me;
  const s = data.summary;
  const p30 = s.periods["30d"];
  const hasBets = s.curve.length > 1;
  const feed = data.feed;
  const tip = feed.tipster;

  root.innerHTML = `
    <section class="hello">
      <div><span class="muted">Привет,</span> <b>${esc(me.first_name)}</b></div>
      ${me.data_source === "demo" ? `<span class="chip n">Демо-данные матчей</span>` : ""}
    </section>

    <section class="card">
      ${cardHead("Мой банк", `<a class="link" href="#/stats">Подробнее</a>`)}
      ${hasBets ? `
        <div class="bank-row">
          <span class="big" data-readout="bank">${money(s.bank)}</span>
          <span class="chip ${p30.profit >= 0 ? "g" : "r"}">${money(p30.profit, true)} · 30 дн</span>
        </div>
        <div data-chart="bank"></div>
        <div class="kpis">
          ${kpi("ROI 30 дн", pct(p30.roi, 1, true), signClass(p30.roi))}
          ${kpi("Ставок", p30.bets)}
          ${kpi("Зашло", pct(p30.win_rate))}
        </div>` : `
        <p class="muted">Добавьте ставки в трекер, и здесь появится график банка, ROI и процент зашедших ставок.</p>
        <a class="btn ghost" href="#/stats?add=1">+ Добавить ставку</a>`}
    </section>

    ${data.pending.length ? `
    <section class="card">
      ${cardHead("Ставки в игре", `<span class="chip y">${s.pending_count}</span>`)}
      ${data.pending.map((b) => `
        <div class="pend">
          <div><b>${esc(b.title)}</b><span class="muted">Ставка ${money(b.stake)} · кэф ${odds(b.odds)}</span></div>
          <a class="btn sm" href="#/hedge?payout=${Math.round(b.stake * b.odds)}&stake=${Math.round(b.stake)}">Хедж</a>
        </div>`).join("")}
    </section>` : ""}

    ${data.live.length ? `
    <section class="card">
      ${cardHead("Live сейчас", `<span class="live-dot"></span>`)}
      <div class="mlist">${data.live.map((m) => matchRow(m, { showLeague: true })).join("")}</div>
    </section>` : ""}

    <section class="card">
      ${cardHead("Value дня", info("Value — ставка, где наша модель оценивает шанс выше, чем букмекер. Перевес показывает, сколько в среднем приносит каждый рубль на длинной дистанции."))}
      ${feed.value.length ? feed.value.map((v) => `
        <a class="vrow" href="#/match/${v.match_id}">
          <div class="vrow-l"><b>${esc(v.title)}</b><span class="muted">${esc(v.league)} · ${esc(kickoff(v.kickoff))}</span></div>
          <div class="vrow-r">
            <span class="pick">${esc(v.pick)} <b>${odds(v.odds)}</b></span>
            <span class="chip g">${pct(v.edge, 1, true)}</span>
          </div>
          <div class="vrow-bar"><span class="muted">Модель ${pct(v.model)}</span><span class="muted">Линия ${pct(v.fair)}</span></div>
        </a>`).join("") : `<p class="muted">Сегодня нет ставок с заметным перевесом.</p>`}
    </section>

    <section class="card">
      ${cardHead("Падения кэфов", info("Если кэф быстро падает, на этот исход ставят крупные суммы. Так часто ведут себя профессиональные игроки."))}
      ${feed.drops.length ? feed.drops.map((d) => `
        <a class="vrow" href="#/match/${d.match_id}">
          <div class="vrow-l"><b>${esc(d.title)}</b><span class="muted">${esc(d.league)} · ${d.status === "live" ? "Live" : esc(kickoff(d.kickoff))}</span></div>
          <div class="vrow-r">
            <span class="pick">${esc(d.pick)} <s>${odds(d.from)}</s> <b>${odds(d.to)}</b></span>
            <span class="chip r">▼ ${pct(Math.abs(d.change), 1)}</span>
          </div>
        </a>`).join("") : `<p class="muted">Резких движений линии нет.</p>`}
    </section>

    ${feed.express.picks.length ? `
    <section class="card">
      ${cardHead("Экспресс дня", `<span class="chip y">кэф ${odds(feed.express.odds)}</span>`)}
      ${feed.express.picks.map((e) => `
        <a class="xrow" href="#/match/${e.match_id}">
          <div><b>${esc(e.title)}</b><span class="muted">${esc(e.league)} · ${esc(kickoff(e.kickoff))}</span></div>
          <div class="xrow-r"><span class="pick">${esc(e.pick)}</span><b>${odds(e.odds)}</b></div>
        </a>`).join("")}
      <div class="xsum"><span class="muted">Вероятность по модели</span><b>${pct(feed.express.prob, 1)}</b></div>
    </section>` : ""}

    <section class="card">
      ${cardHead("Прогнозы канала · 30 дней")}
      <div class="tip">
        ${ring(tip.win_rate, "var(--green)", "зашло")}
        <div class="tip-r">
          <div class="kpis two">
            ${kpi("ROI", pct(tip.roi, 1, true), signClass(tip.roi))}
            ${kpi("Средний кэф", odds(tip.avg_odds))}
          </div>
          <div data-chart="tip"></div>
          <div class="dots">${tip.last.map((w) => `<i class="${w ? "w" : "l"}"></i>`).join("")}<span class="muted">последние 10</span></div>
        </div>
      </div>
    </section>

    <section class="card">
      ${cardHead("Топ-матчи", `<a class="link" href="#/matches">Все</a>`)}
      <div class="mlist">${data.top.map((m) => matchRow(m, { showLeague: true })).join("")}</div>
    </section>
  `;

  if (hasBets) {
    const values = s.curve.map((c) => c.v);
    lineChart(root.querySelector('[data-chart="bank"]'), {
      height: 110,
      series: [{ color: s.bank >= s.start_bank ? "var(--green)" : "var(--red)", values, area: true }],
      readout: root.querySelector('[data-readout="bank"]'),
      fmt: (i) => money(values[i]),
    });
  }
  sparkline(root.querySelector('[data-chart="tip"]'), tip.curve, "var(--green)");
}
