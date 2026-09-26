// Моя статистика: трекер ставок, банк, ROI, разрезы, серии.

import { api, state } from "../api.js";
import { lineChart, ring } from "../charts.js";
import { empty, esc, haptic, money, odds, pct, segmented, onSeg, sheet, signClass, toast } from "../ui.js";
import { cardHead, info, kpi, statusChip } from "./common.js";

const SPORTS = ["Футбол", "Хоккей", "Баскетбол", "Теннис", "Киберспорт", "Другое"];
const MARKETS = ["Исход", "Двойной шанс", "Тотал", "Фора", "Обе забьют", "Экспресс", "Другое"];
let period = "30d";
let breakdownBy = "by_sport";

export async function renderStats(root, params) {
  const data = await api("/api/bets");
  const s = data.stats;
  const has = data.bets.length > 0;

  const redraw = () => renderStats(root, new URLSearchParams());

  root.innerHTML = `
    <div class="title-row">
      <h1 class="title">Моя статистика</h1>
      <button type="button" class="btn sm" data-add>+ Ставка</button>
    </div>
    ${has ? body(s, data.bets) : `<section class="card">${empty("Трекер пуст", "Записывайте ставки: приложение посчитает ROI, процент зашедших, серии и нарисует график банка.", `<button type="button" class="btn" data-add2>Добавить первую ставку</button>`)}</section>`}
  `;

  root.querySelector("[data-add]").addEventListener("click", () => addSheet(redraw));
  root.querySelector("[data-add2]")?.addEventListener("click", () => addSheet(redraw));
  if (params.get("add")) addSheet(redraw);
  if (!has) return;

  const drawPeriod = () => {
    const p = s.periods[period];
    root.querySelector("[data-period]").innerHTML = `
      <div class="stat-top">
        ${ring(p.win_rate, "var(--green)", "зашло")}
        <div class="kpis two">
          ${kpi("Прибыль", money(p.profit, true), signClass(p.profit))}
          ${kpi("ROI", pct(p.roi, 1, true), signClass(p.roi))}
          ${kpi("Ставок", p.bets)}
          ${kpi("Оборот", money(p.staked))}
        </div>
      </div>`;
  };
  onSeg(root, "period", (v) => { period = v; drawPeriod(); });
  drawPeriod();

  const values = s.curve.map((c) => c.v);
  if (values.length > 1) {
    lineChart(root.querySelector("[data-chart]"), {
      height: 140,
      yFmt: (v) => (Math.abs(v) >= 1000 ? Math.round(v / 1000) + "k" : Math.round(v)),
      series: [{ color: s.bank >= s.start_bank ? "var(--green)" : "var(--red)", values, area: true }],
      readout: root.querySelector("[data-ro]"),
      fmt: (i) => `${i ? new Date(s.curve[i].t).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : "Старт"} · <b>${money(values[i])}</b>`,
    });
  }

  const drawBreakdown = () => {
    const rows = s[breakdownBy];
    root.querySelector("[data-bd]").innerHTML = rows.length ? rows.map((r) => `
      <div class="bd">
        <div class="bd-top"><b>${esc(r.name)}</b><span class="muted">${r.bets} ст.</span><b class="${signClass(r.profit)}">${money(r.profit, true)}</b></div>
        <div class="meter slim"><div class="meter-bar"><i style="width:${r.win_rate * 100}%"></i></div><span class="muted">${pct(r.win_rate)} зашло · ROI ${pct(r.roi, 1, true)}</span></div>
      </div>`).join("") : `<p class="muted">Нет рассчитанных ставок</p>`;
  };
  onSeg(root, "bd", (v) => { breakdownBy = v; drawBreakdown(); });
  drawBreakdown();

  root.querySelector("[data-more]")?.addEventListener("click", (ev) => {
    root.querySelectorAll(".bet[hidden]").forEach((b) => (b.hidden = false));
    ev.target.remove();
  });
  root.querySelector("[data-bank]").addEventListener("click", () => bankSheet(s.start_bank, redraw));
  root.querySelectorAll("[data-bet]").forEach((el) => el.addEventListener("click", () => {
    const bet = data.bets.find((b) => b.id === +el.dataset.bet);
    settleSheet(bet, redraw);
  }));
}

function body(s, bets) {
  const st = s.streak;
  const streakText = st.now ? `${st.now} ${st.kind === "won" ? "в плюс" : "в минус"}` : "—";
  return `
    ${segmented("period", [["7d", "7 дней"], ["30d", "30 дней"], ["all", "Всё время"]], period)}
    <section class="card" data-period></section>

    <section class="card">
      ${cardHead("Банк", `<button type="button" class="link" data-bank>Стартовый: ${money(s.start_bank)}</button>`)}
      <div class="bank-row"><span class="big">${money(s.bank)}</span><span class="chip ${s.bank >= s.start_bank ? "g" : "r"}">${money(s.bank - s.start_bank, true)}</span></div>
      <div class="readout" data-ro>Проведите пальцем по графику</div>
      <div data-chart></div>
      ${s.pending_count ? `<div class="kv"><span class="muted">В игре ${s.pending_count} ст.</span><b>${money(s.pending_stake)}</b></div>` : ""}
    </section>

    <section class="card">
      ${cardHead("Показатели")}
      <div class="kpis">
        ${kpi("Средний кэф", s.avg_odds ? odds(s.avg_odds) : "—")}
        ${kpi("Серия сейчас", streakText, st.kind === "won" ? "pos" : st.kind === "lost" ? "neg" : "")}
        ${kpi("Рекорд серии", `${st.best_win} / ${st.best_lose}`)}
      </div>
      ${s.best ? `<div class="kv"><span class="muted">Лучшая: ${esc(s.best.title)}</span><b class="pos">${money(s.best.profit, true)}</b></div>` : ""}
      ${s.worst ? `<div class="kv"><span class="muted">Худшая: ${esc(s.worst.title)}</span><b class="neg">${money(s.worst.profit, true)}</b></div>` : ""}
    </section>

    <section class="card">
      ${cardHead("Хеджи", info("Разница между тем, что вы получили по хеджам, и тем, что предлагал букмекер за выкуп, — по вашим записям в трекере."))}
      <div class="kpis two">
        ${kpi("Захеджировано", s.hedged_count)}
        ${kpi("Выгода vs выкуп", money(s.hedge_saved, true), signClass(s.hedge_saved))}
      </div>
    </section>

    <section class="card">
      ${cardHead("Где вы сильнее")}
      ${segmented("bd", [["by_sport", "Спорт"], ["by_league", "Лиги"], ["by_market", "Тип ставки"]], breakdownBy)}
      <div data-bd></div>
    </section>

    <section class="card">
      ${cardHead("Ставки", `<span class="muted">${bets.length}</span>`)}
      ${bets.map((b, i) => `
        <button type="button" class="bet" ${i >= 15 ? "hidden" : ""} data-bet="${b.id}">
          <div class="bet-l"><b>${esc(b.title)}</b><span class="muted">${esc(b.sport)}${b.league ? " · " + esc(b.league) : ""} · ${esc(b.market)} · ${new Date(b.placed_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span></div>
          <div class="bet-r">${statusChip(b.status)}<span class="num">${money(b.stake)} × ${odds(b.odds)}</span>${b.status !== "pending" ? `<b class="${signClass(b.profit)}">${money(b.profit, true)}</b>` : ""}</div>
        </button>`).join("")}
      ${bets.length > 15 ? `<button type="button" class="btn ghost" data-more>Показать все ${bets.length}</button>` : ""}
    </section>
  `;
}

function addSheet(done) {
  sheet(`
    <h2>Новая ставка</h2>
    <label class="field"><span>Событие</span><input id="b-title" type="text" placeholder="Реал — Барселона, П1" maxlength="120"></label>
    <div class="row2">
      <label class="field"><span>Сумма, ₽</span><input id="b-stake" type="number" inputmode="decimal" placeholder="1000"></label>
      <label class="field"><span>Кэф</span><input id="b-odds" type="number" inputmode="decimal" step="0.01" placeholder="1.85"></label>
    </div>
    <div class="row2">
      <label class="field"><span>Спорт</span><select id="b-sport">${SPORTS.map((s) => `<option>${s}</option>`).join("")}</select></label>
      <label class="field"><span>Тип ставки</span><select id="b-market">${MARKETS.map((s) => `<option>${s}</option>`).join("")}</select></label>
    </div>
    <label class="field"><span>Лига <em>необязательно</em></span><input id="b-league" type="text" placeholder="Ла Лига" maxlength="60"></label>
    <button type="button" class="btn big" data-save>Сохранить</button>
  `, (el, close) => {
    el.querySelector("[data-save]").addEventListener("click", async () => {
      const body = {
        title: el.querySelector("#b-title").value.trim(),
        stake: +el.querySelector("#b-stake").value,
        odds: +String(el.querySelector("#b-odds").value).replace(",", "."),
        sport: el.querySelector("#b-sport").value,
        market: el.querySelector("#b-market").value,
        league: el.querySelector("#b-league").value.trim() || null,
      };
      if (!body.title) return toast("Напишите событие");
      if (!(body.stake > 0)) return toast("Введите сумму");
      if (!(body.odds > 1)) return toast("Кэф должен быть больше 1");
      try {
        await api("/api/bets", { method: "POST", body });
        haptic("success");
        close();
        if (location.hash !== "#/stats") location.hash = "#/stats";
        else done();
      } catch (e) { toast(e.message); }
    });
  });
}

function settleSheet(bet, done) {
  sheet(`
    <h2>${esc(bet.title)}</h2>
    <p class="muted">${money(bet.stake)} × ${odds(bet.odds)} = ${money(bet.stake * bet.odds)}</p>
    <div class="grid2">
      <button type="button" class="btn ok" data-st="won">Зашла</button>
      <button type="button" class="btn bad" data-st="lost">Не зашла</button>
      <button type="button" class="btn ghost" data-st="void">Возврат</button>
      <button type="button" class="btn ghost" data-st="pending">В игре</button>
    </div>
    <details class="hedged">
      <summary>Закрыл хеджем или выкупом</summary>
      <label class="field"><span>Сколько получил на руки, ₽</span><input id="s-payout" type="number" inputmode="decimal"></label>
      <label class="field"><span>Сколько предлагал выкуп, ₽ <em>необязательно</em></span><input id="s-cash" type="number" inputmode="decimal"></label>
      <button type="button" class="btn" data-hedged>Сохранить</button>
    </details>
    <button type="button" class="btn text danger" data-del>Удалить ставку</button>
  `, (el, close) => {
    const send = async (body) => {
      try {
        await api(`/api/bets/${bet.id}`, { method: "PATCH", body });
        haptic("success"); close(); done();
      } catch (e) { toast(e.message); }
    };
    el.querySelectorAll("[data-st]").forEach((b) => b.addEventListener("click", () => send({ status: b.dataset.st })));
    el.querySelector("[data-hedged]").addEventListener("click", () => {
      const payout = +el.querySelector("#s-payout").value;
      const cash = +el.querySelector("#s-cash").value;
      if (!(payout > 0)) return toast("Введите сумму");
      send({ status: "hedged", payout, hedge_saved: cash > 0 ? payout - cash : null });
    });
    let armed = false;
    el.querySelector("[data-del]").addEventListener("click", async (ev) => {
      if (!armed) { armed = true; ev.target.textContent = "Точно удалить?"; return; }
      try { await api(`/api/bets/${bet.id}`, { method: "DELETE" }); close(); done(); } catch (e) { toast(e.message); }
    });
  });
}

function bankSheet(current, done) {
  sheet(`
    <h2>Стартовый банк</h2>
    <p class="muted">С какой суммы вы начинали. От неё считается график банка.</p>
    <label class="field"><span>Сумма, ₽</span><input id="bank" type="number" inputmode="decimal" value="${current || ""}"></label>
    <button type="button" class="btn big" data-save>Сохранить</button>
  `, (el, close) => el.querySelector("[data-save]").addEventListener("click", async () => {
    const v = +el.querySelector("#bank").value;
    if (!(v >= 0)) return toast("Введите сумму");
    try {
      await api("/api/me/bank", { method: "POST", body: { start_bank: v } });
      state.me.start_bank = v;
      close(); done();
    } catch (e) { toast(e.message); }
  }));
}
