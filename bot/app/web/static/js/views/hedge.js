// Хедж-калькулятор — ядро продукта.

import { api, state, ApiError } from "../api.js";
import { hedgeChart } from "../charts.js";
import { countUp, esc, haptic, money, odds as fo, openLink, pct, segmented, onSeg, sheet, toast } from "../ui.js";
import { cardHead, info, legend } from "./common.js";
import { vipSheet } from "./vip.js";

// Противоположный исход для последнего события экспресса.
const OPPOSITE = [
  ["p1", "П1 (победа хозяев)", "X2 — ничья или победа гостей"],
  ["p2", "П2 (победа гостей)", "1X — победа хозяев или ничья"],
  ["x", "Ничья", "12 — любая победа"],
  ["tb", "Тотал больше", "Тотал меньше той же линии"],
  ["tm", "Тотал меньше", "Тотал больше той же линии"],
  ["bttsy", "Обе забьют — да", "Обе забьют — нет"],
  ["other", "Другое", "Ставка, которая выигрывает, когда ваша проигрывает"],
];

const form = { payout: 500000, stake: 50000, odds: 2.2, cashout: "", mode: "equal", ratio: 60, market: "p1" };

export async function renderHedge(root, params) {
  if (params.get("payout")) form.payout = +params.get("payout");
  if (params.get("stake")) form.stake = +params.get("stake");
  if (params.get("odds")) form.odds = +params.get("odds");

  let liveMatch = null;
  if (params.get("match")) {
    try { liveMatch = await api(`/api/matches/${params.get("match")}`); } catch { liveMatch = null; }
  }

  const me = state.me;
  const q = me.hedge;
  const vip = q.vip;
  const lock = vip ? "" : " 🔒";

  root.innerHTML = `
    <div class="title-row">
      <h1 class="title">Хедж-калькулятор</h1>
      <button type="button" class="link" data-help>Как это работает?</button>
    </div>

    <section class="card">
      ${cardHead("Ваш купон")}
      <label class="field"><span>Выплата по экспрессу, ₽</span><input id="h-payout" type="number" inputmode="decimal" value="${form.payout}"></label>
      <label class="field"><span>Сумма вашей ставки, ₽</span><input id="h-stake" type="number" inputmode="decimal" value="${form.stake}"></label>
      <label class="field"><span>Последнее событие в купоне</span>
        <select id="h-market">${OPPOSITE.map(([v, t]) => `<option value="${v}" ${v === form.market ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
      </label>
      <div class="hintbox" data-opp></div>
      ${liveMatch ? liveOdds(liveMatch) : ""}
      <label class="field"><span>Кэф на противоположный исход в Live</span><input id="h-odds" type="number" inputmode="decimal" step="0.01" value="${form.odds}"></label>
      <label class="field"><span>Сколько БК предлагает за выкуп, ₽ <em>необязательно</em></span><input id="h-cash" type="number" inputmode="decimal" placeholder="Например, 245000" value="${form.cashout}"></label>
    </section>

    <section class="card">
      ${cardHead("Стратегия", info("«Поровну» — одинаковая прибыль при любом исходе. «Без риска» — если купон не зайдёт, вы выходите в ноль, а если зайдёт — забираете максимум. «Свой %» — сами выбираете, какую часть закрыть."))}
      ${segmented("mode", [["equal", "Поровну"], ["zero", "Без риска" + lock], ["custom", "Свой %" + lock]], form.mode)}
      <div class="ratio" data-ratio ${form.mode === "custom" ? "" : "hidden"}>
        <input id="h-ratio" type="range" min="10" max="130" value="${form.ratio}">
        <span class="num"><b data-ratio-v>${form.ratio}%</b> от «Поровну»</span>
      </div>
    </section>

    <button type="button" class="btn big" data-calc>Рассчитать</button>
    <p class="note" data-quota>${quotaText(q)}</p>

    <div data-result></div>
  `;

  const $ = (s) => root.querySelector(s);
  const oppText = () => {
    const row = OPPOSITE.find((o) => o[0] === $("#h-market").value);
    $("[data-opp]").innerHTML = `Ставьте хедж на: <b>${esc(row[2])}</b>`;
  };
  oppText();
  $("#h-market").addEventListener("change", () => { form.market = $("#h-market").value; oppText(); });

  root.querySelectorAll("[data-lodds]").forEach((b) => b.addEventListener("click", () => {
    $("#h-odds").value = b.dataset.lodds;
    haptic();
    toast(`Кэф ${b.dataset.lodds} подставлен`);
  }));

  onSeg(root, "mode", (v) => {
    if (!vip && v !== "equal") {
      vipSheet("Режимы «Без риска» и «Свой %» доступны в VIP.");
      root.querySelectorAll('[data-seg="mode"] button').forEach((b) => b.classList.toggle("on", b.dataset.v === "equal"));
      form.mode = "equal";
      return;
    }
    form.mode = v;
    $("[data-ratio]").hidden = v !== "custom";
  });
  $("#h-ratio").addEventListener("input", () => {
    form.ratio = +$("#h-ratio").value;
    $("[data-ratio-v]").textContent = form.ratio + "%";
  });
  $("[data-help]").addEventListener("click", helpSheet);

  $("[data-calc]").addEventListener("click", async () => {
    form.payout = +$("#h-payout").value;
    form.stake = +$("#h-stake").value;
    form.odds = +String($("#h-odds").value).replace(",", ".");
    form.cashout = $("#h-cash").value;
    if (!(form.payout > 0 && form.stake > 0)) return toast("Введите выплату и ставку");
    if (!(form.odds > 1)) return toast("Кэф должен быть больше 1");
    if (form.payout <= form.stake) return toast("Выплата должна быть больше ставки");
    const btn = $("[data-calc]");
    btn.disabled = true;
    try {
      const res = await api("/api/hedge", {
        method: "POST",
        body: {
          payout: form.payout, stake: form.stake, odds: form.odds, mode: form.mode,
          ratio: form.ratio / 100, cashout: form.cashout ? +form.cashout : null,
        },
      });
      state.me.hedge = res.quota;
      $("[data-quota]").textContent = quotaText(res.quota);
      haptic("success");
      showResult($("[data-result]"), res.result);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        haptic("warning");
        if (e.data?.quota) { state.me.hedge = e.data.quota; $("[data-quota]").textContent = quotaText(e.data.quota); }
        vipSheet(e.data?.text);
      } else toast(e.message);
    } finally { btn.disabled = false; }
  });
}

function liveOdds(m) {
  const o = m.live?.odds || m.odds;
  const dc = (a, b) => Math.max(1.01, 1 / (1 / a + 1 / b)).toFixed(2);
  const opts = [
    ["П1", o.home], ["X", o.draw], ["П2", o.away],
    ["1X", dc(o.home, o.draw)], ["X2", dc(o.draw, o.away)], ["12", dc(o.home, o.away)],
  ];
  return `<div class="lodds">
    <span class="muted">${esc(m.home.name)} — ${esc(m.away.name)}${m.live ? ` · ${m.live.minute}' · ${esc(m.live.score)}` : ""}. Нажмите, чтобы подставить кэф:</span>
    <div class="lodds-row">${opts.map(([l, v]) => `<button type="button" data-lodds="${Number(v).toFixed(2)}"><small>${l}</small>${Number(v).toFixed(2)}</button>`).join("")}</div>
  </div>`;
}

function quotaText(q) {
  if (q.vip) return "VIP: безлимитные расчёты";
  const left = q.remaining;
  let t = `Бесплатных расчётов на этой неделе: ${left} из ${q.limit}`;
  if (!left && q.resets_at) {
    const d = new Date(q.resets_at);
    t += ` · новый ${d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}`;
  }
  return t;
}

function showResult(host, r) {
  const me = state.me;
  const bk = me.bookmaker || "1win";
  const hasCash = r.cashout != null && r.cashout > 0;
  const modeName = { equal: "Поровну", zero: "Без риска", custom: "Свой %" }[r.mode];
  host.innerHTML = `
    <section class="card result">
      ${cardHead("Результат · " + modeName)}
      <div class="res-hero">
        <span class="muted">${r.mode === "zero" ? "Максимум, если купон зайдёт" : "Гарантированная прибыль"}</span>
        <div class="res-num pos" data-res>${money(r.mode === "zero" ? r.profit_if_bet_wins : r.guaranteed, true)}</div>
      </div>
      <div class="res-stake"><span>Поставьте на противоположный исход</span><b>${money(r.hedge_amount)}</b></div>
      <div class="outcomes">
        <div><span class="muted">Если купон зашёл</span><b class="${r.profit_if_bet_wins >= 0 ? "pos" : "neg"}">${money(r.profit_if_bet_wins, true)}</b></div>
        <div><span class="muted">Если зашёл хедж</span><b class="${r.profit_if_hedge_wins >= 0 ? "pos" : "neg"}">${money(r.profit_if_hedge_wins, true)}</b></div>
      </div>
      <div class="kv"><span class="muted">Шанс, что купон зайдёт (по линии)</span><b>${pct(r.implied_prob_bet)}</b></div>
    </section>

    <section class="card">
      ${cardHead("Хедж или выкуп?", info("Выкуп (Cash Out) — букмекер забирает купон досрочно за меньшую сумму. Хедж даёт ту же «честную» сумму, но без комиссии букмекера за выкуп."))}
      ${hasCash ? `
        <div class="versus">
          <div><span class="muted">Выкуп у БК</span><b>${money(r.cashout)}</b></div>
          <div><span class="muted">Хедж, на руки</span><b>${money(r.cash_in_hand_equal)}</b></div>
        </div>
        <div class="kv"><span class="muted">Выгода хеджа</span><b class="${r.vs_cashout >= 0 ? "pos" : "neg"}">${money(r.vs_cashout, true)} · ${pct(r.vs_cashout / r.cashout, 1, true)}</b></div>
        <p class="hint">${r.vs_cashout >= 0 ? "Хедж выгоднее выкупа." : "Сейчас выгоднее выкуп: букмекер предлагает больше честной цены."}</p>`
      : `<p class="hint">Честная цена выкупа сейчас — <b>${money(r.fair_cashout)}</b>. Впишите, сколько предлагает ваш букмекер, и калькулятор покажет, что выгоднее.</p>`}
    </section>

    <section class="card">
      ${cardHead("Прибыль при разной сумме хеджа")}
      <div class="readout" data-ro>Проведите пальцем по графику</div>
      <div data-chart></div>
      ${legend([["var(--c-home)", "Купон зашёл"], ["var(--c-away)", "Зашёл хедж"], ["var(--gold)", "Ваш хедж"]])}
    </section>

    <button type="button" class="btn big gold" data-go>⚡ Поставить хедж на ${esc(bk)} · кэф ${fo(form.odds)}</button>
    <p class="note">Кэф в Live меняется быстро. Проверьте его перед ставкой и пересчитайте, если он изменился.</p>
  `;
  hedgeChart(host.querySelector("[data-chart]"), {
    payout: form.payout, stake: form.stake, odds: form.odds, amount: r.hedge_amount,
    readout: host.querySelector("[data-ro]"),
    fmt: (h, a, b) => `Хедж <b>${money(h)}</b> · купон <b class="${a >= 0 ? "pos" : "neg"}">${money(a, true)}</b> · хедж <b class="${b >= 0 ? "pos" : "neg"}">${money(b, true)}</b>`,
  });
  const resEl = host.querySelector("[data-res]");
  const target = r.mode === "zero" ? r.profit_if_bet_wins : r.guaranteed;
  countUp(resEl, target, (v) => money(v, true));
  resEl.classList.toggle("pos", target >= 0);
  resEl.classList.toggle("neg", target < 0);
  host.querySelector("[data-go]").addEventListener("click", () => openLink(me.ref_link));
  host.scrollIntoView({ behavior: "smooth", block: "start" });
}

function helpSheet() {
  sheet(`
    <h2>Как работает хедж</h2>
    <p>Вы поставили экспресс, почти все события зашли, осталось последнее. Если оно не зайдёт, пропадёт весь купон.</p>
    <p><b>Хедж</b> — вторая ставка на противоположный исход последнего события. Тогда вы в плюсе при любом результате.</p>
    <div class="example">
      <div class="kv"><span>Ставка на экспресс</span><b>50 000 ₽</b></div>
      <div class="kv"><span>Выплата, если зайдёт</span><b>500 000 ₽</b></div>
      <div class="kv"><span>Хедж на противоположный исход, кэф 2.20</span><b>227 273 ₽</b></div>
      <div class="kv"><span>Итог при любом исходе</span><b class="pos">+222 727 ₽</b></div>
    </div>
    <p><b>Кэф</b> — множитель выигрыша: ставка 1 000 ₽ на кэф 2.20 вернёт 2 200 ₽.</p>
    <p><b>Выкуп (Cash Out)</b> — букмекер предлагает забрать деньги досрочно, но берёт комиссию. Хедж обычно выгоднее на 5–15%.</p>
    <p><b>Противоположный исход</b> в футболе — это двойной шанс: против П1 ставят X2, иначе ничья «сожжёт» обе ставки.</p>
    <button type="button" class="btn" data-close>Понятно</button>
  `, (el, close) => el.querySelector("[data-close]").addEventListener("click", close));
}
