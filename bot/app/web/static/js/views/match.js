// Экран матча: обзор, кэфы, форма, статистика, Live.
// Каждый блок показывается, только если для него есть данные: у демо и у
// API-Football набор полей разный.

import { api } from "../api.js";
import { compareRows, lineChart, momentum, probBar, scoreHeatmap } from "../charts.js";
import { clubColors, crest, esc, kickoff, odds, pct, segmented, onSeg } from "../ui.js";
import { cardHead, formChips, info, kpi, legend } from "./common.js";

const C = { home: "var(--c-home)", draw: "var(--c-draw)", away: "var(--c-away)" };
const OUT = [["home", "П1"], ["draw", "X"], ["away", "П2"]];
let lastTab = "overview";

const note = (text) => `<p class="empty-card">${esc(text)}</p>`;
const hasOdds = (o) => o && o.home > 1 && o.draw > 1 && o.away > 1;

export async function renderMatch(root, id) {
  const m = await api(`/api/matches/${id}`);
  const live = m.status === "live";
  const tabs = [["overview", "Обзор"], ["odds", "Кэфы"], ["form", "Форма"], ["stats", "Статистика"]];
  if (live) tabs.push(["live", "Live"]);
  if (!tabs.some(([t]) => t === lastTab)) lastTab = "overview";
  if (live && lastTab === "overview") lastTab = "live";
  const headOdds = (live && m.live?.odds) || m.odds || {};

  root.innerHTML = `
    <section class="card match-head" style="--ha:${clubColors(m.home.name)[0]};--aa:${clubColors(m.away.name)[0]}">
      <div class="mh-meta"><span>${esc(m.country)} · ${esc(m.league)}</span>
        ${live ? `<span class="chip r"><span class="live-dot"></span>${m.live.minute}'</span>` : `<span class="muted">${esc(kickoff(m.kickoff))}</span>`}</div>
      <div class="mh-teams">
        <div class="mh-team">${crest(m.home.name, m.home.short, "lg", m.home.logo)}<b>${esc(m.home.name)}</b></div>
        <div class="mh-score">${live ? esc(m.live.score) : `<span class="vs">VS</span><small>${esc(kickoff(m.kickoff))}</small>`}</div>
        <div class="mh-team">${crest(m.away.name, m.away.short, "lg", m.away.logo)}<b>${esc(m.away.name)}</b></div>
      </div>
      ${hasOdds(headOdds) ? `<div class="oddsbox wide">
        ${OUT.map(([k, l]) => `<span><small>${l}</small>${odds(headOdds[k])}</span>`).join("")}
      </div>` : ""}
    </section>
    <div class="tabs-scroll">${segmented("mtab", tabs, lastTab)}</div>
    <div data-tab></div>
  `;

  const host = root.querySelector("[data-tab]");
  const draw = (tab) => {
    lastTab = tab;
    ({ overview, odds: oddsTab, form, stats, live: liveTab })[tab](host, m);
    host.querySelectorAll("[data-info]").forEach((b) => b.addEventListener("click", () => window.__info(b.dataset.info)));
  };
  onSeg(root, "mtab", draw);
  draw(lastTab);
}

function overview(host, m) {
  const a = m.analysis || {}, mk = m.model, o = m.odds || {};
  const names = { home: m.home.name, draw: "Ничья", away: m.away.name };
  const probsCard = mk || a.fair ? `
    <section class="card">
      ${cardHead("Вероятности исходов", info("«Линия» — вероятности из кэфов букмекера без его маржи. «Модель» — наш расчёт по статистике команд. Если модель выше линии, это value."))}
      ${legend([["var(--text-2)", mk ? "Модель" : "Линия БК"], ...(mk && a.fair ? [["var(--line-2)", "Линия БК"]] : [])])}
      ${OUT.map(([k, l]) => {
        const main = mk ? mk[k] : a.fair[k];
        return `
        <div class="pr">
          <div class="pr-top"><span><b>${l}</b> <span class="muted">${esc(names[k])}</span></span>
            <span><b>${pct(main)}</b>${mk && a.fair ? ` <span class="muted">/ ${pct(a.fair[k])}</span>` : ""}</span></div>
          <div class="pr-bars"><i style="width:${main * 100}%;background:${C[k]}"></i></div>
          ${mk && a.fair ? `<div class="pr-bars thin"><i style="width:${a.fair[k] * 100}%"></i></div>` : ""}
        </div>`;
      }).join("")}
      ${a.margin != null ? `<div class="kv"><span class="muted">Маржа букмекера${m.bookmaker ? ` · ${esc(m.bookmaker)}` : ""}</span><b>${pct(a.margin, 1)}</b></div>` : ""}
    </section>` : `<section class="card">${cardHead("Вероятности исходов")}${note("Линии Pinnacle на этот матч нет. Впишите кэфы 1win выше — приложение посчитает шансы и маржу.")}</section>`;

  const valueCard = a.value?.length ? `
    <section class="card">
      ${cardHead("Где перевес", info("Перевес = вероятность модели × кэф − 1. Плюс значит, что на дистанции ставка выгодна, минус — невыгодна."))}
      <div class="vtable">
        ${a.value.slice().sort((x, y) => y.edge - x.edge).map((v) => `
          <div class="vt-row">
            <span>${esc(v.market)} · <b>${esc(v.pick)}</b></span>
            <span class="num">${odds(v.odds)}</span>
            <span class="num muted">${pct(v.model)}</span>
            <span class="chip ${v.edge > 0.02 ? "g" : v.edge < -0.05 ? "r" : "n"}">${pct(v.edge, 1, true)}</span>
          </div>`).join("")}
      </div>
    </section>` : "";

  const bestCard = m.best_odds && m.best_odds.home ? `
    <section class="card">
      ${cardHead("Лучший кэф на рынке", info("Самый высокий кэф на каждый исход среди всех букмекеров. Чем выше кэф, тем больше выплата при той же ставке."))}
      <div class="bestodds">
        ${OUT.map(([k, l]) => m.best_odds[k] ? `<div><span>${l}</span><b>${odds(m.best_odds[k].odds)}</b><span>${esc(m.best_odds[k].bookmaker)}</span></div>` : "").join("")}
      </div>
    </section>` : "";

  host.innerHTML = myOddsCard(m) + probsCard + valueCard + bestCard + (mk ? `
    <section class="card">
      ${cardHead("Ожидаемый счёт", info("Сколько голов в среднем должна забить каждая команда, и вероятность каждого точного счёта в процентах."))}
      <div class="xg-big">
        <div><span class="muted">${esc(m.home.short)}</span><b>${mk.lambda_home.toFixed(2)}</b></div>
        <div class="likely"><span class="muted">Самый вероятный</span><b>${esc(mk.likely_score)}</b><span class="muted">${pct(mk.likely_score_prob, 1)}</span></div>
        <div><span class="muted">${esc(m.away.short)}</span><b>${mk.lambda_away.toFixed(2)}</b></div>
      </div>
      <div data-heat></div>
    </section>

    <section class="card">
      ${cardHead("Тоталы и «обе забьют»")}
      ${[["Больше 1.5", mk.over15], ["Больше 2.5", mk.over25], ["Больше 3.5", mk.over35], ["Обе забьют", mk.btts]].map(([t, p]) => `
        <div class="meter"><span>${t}</span><div class="meter-bar"><i style="width:${p * 100}%"></i></div><b>${pct(p)}</b></div>`).join("")}
      ${o.over25 ? `<div class="kv"><span class="muted">Кэф ТБ 2.5 / ТМ 2.5</span><b>${odds(o.over25)} / ${odds(o.under25)}</b></div>` : ""}
    </section>` : "");
  if (mk) scoreHeatmap(host.querySelector("[data-heat]"), mk.matrix, m.home.short, m.away.short);
  mountMyOdds(host, m);
}

// ── Кэфы пользователя с 1win ─────────────────────────────────────────────────
const storeKey = (m) => `odds1w:${m.id}`;
function loadMy(m) {
  try { return JSON.parse(localStorage.getItem(storeKey(m)) || "{}"); } catch { return {}; }
}
function saveMy(m, v) {
  try { localStorage.setItem(storeKey(m), JSON.stringify(v)); } catch { /* приватный режим */ }
}

function myOddsCard(m) {
  const v = loadMy(m);
  const field = (k, l) => `<label class="myodd"><span>${l}</span><input data-my="${k}" type="number" inputmode="decimal" step="0.01" min="1.01" placeholder="—" value="${v[k] ?? ""}"></label>`;
  return `
    <section class="card myodds">
      ${cardHead("Кэфы 1win", info("Впишите кэфы, которые видите на 1win для этого матча. Приложение покажет маржу 1win, реальные шансы и сравнит с линией Pinnacle — самого точного букмекера. Зелёный процент значит, что 1win даёт на этот исход выгодную цену."))}
      <div class="myodds-row">${field("home", "П1")}${field("draw", "X")}${field("away", "П2")}</div>
      <div data-myres></div>
    </section>`;
}

function mountMyOdds(host, m) {
  const res = host.querySelector("[data-myres]");
  const inputs = [...host.querySelectorAll("[data-my]")];
  const pin = hasOdds(m.odds) ? m.odds : null;
  const pinFair = pin ? (() => { const t = 1 / pin.home + 1 / pin.draw + 1 / pin.away; return { home: 1 / pin.home / t, draw: 1 / pin.draw / t, away: 1 / pin.away / t }; })() : null;
  const draw = () => {
    const v = {};
    inputs.forEach((i) => { const x = parseFloat(String(i.value).replace(",", ".")); if (x > 1) v[i.dataset.my] = x; });
    saveMy(m, v);
    if (!(v.home && v.draw && v.away)) {
      res.innerHTML = `<p class="hint">Введите все три кэфа — П1, X и П2.</p>`;
      return;
    }
    const book = 1 / v.home + 1 / v.draw + 1 / v.away;
    const fair = { home: 1 / v.home / book, draw: 1 / v.draw / book, away: 1 / v.away / book };
    const ref = pinFair || (m.model ? { home: m.model.home, draw: m.model.draw, away: m.model.away } : null);
    const refName = pinFair ? "Pinnacle" : "нашей модели";
    const names = { home: m.home.name, draw: "Ничья", away: m.away.name };
    res.innerHTML = `
      <div class="kv"><span class="muted">Маржа 1win</span><b class="${book - 1 > 0.08 ? "neg" : ""}">${pct(book - 1, 1)}</b></div>
      ${OUT.map(([k, l]) => {
        const edge = ref ? ref[k] * v[k] - 1 : null;
        return `<div class="myrow">
          <span><b>${l}</b> <span class="muted">${esc(names[k])}</span></span>
          <span class="num">шанс ${pct(fair[k])}</span>
          ${edge == null ? "" : `<span class="chip ${edge > 0.01 ? "g" : edge < -0.04 ? "r" : "n"}">${pct(edge, 1, true)}</span>`}
        </div>`;
      }).join("")}
      ${ref ? `<p class="hint">Процент — выгода кэфа 1win по сравнению с ${refName}. ${
        OUT.some(([k]) => ref[k] * v[k] - 1 > 0.01)
          ? "Есть исход с выгодной ценой — он отмечен зелёным."
          : "Выгодных цен нет: 1win даёт кэфы ниже честных."}</p>`
        : `<p class="hint">Для сравнения нет линии Pinnacle на этот матч — показаны шансы по кэфам 1win без маржи.</p>`}
      <a class="btn" href="#/hedge?odds=${v.away}">Открыть хедж-калькулятор</a>`;
  };
  inputs.forEach((i) => i.addEventListener("input", draw));
  draw();
}

function oddsTab(host, m) {
  const h = m.odds_history || [];
  const o = m.odds || {};
  if (h.length < 2) {
    host.innerHTML = `
      <section class="card">
        ${cardHead("Движение кэфов", info("Как менялись кэфы. Падение кэфа значит, что на этот исход много ставят."))}
        ${note(hasOdds(o) ? "Кэфы ещё не менялись с первого обновления. График появится, когда линия сдвинется." : "Линии на этот матч пока нет.")}
        ${hasOdds(o) ? `<div class="kpis">${OUT.map(([k, l]) => kpi(l, odds(o[k]))).join("")}</div>` : ""}
      </section>
      ${otherMarkets(o)}`;
    return;
  }
  const first = h[0], last = h.at(-1);
  const ch = (k) => (last[k] - first[k]) / first[k];
  const hours = Math.round(first.h);
  host.innerHTML = `
    <section class="card">
      ${cardHead(`Движение кэфов · ${hours > 0 ? hours + " ч" : "сегодня"}`, info("Как менялись кэфы. Падение кэфа значит, что на этот исход много ставят."))}
      <div class="readout" data-ro>Проведите пальцем по графику</div>
      <div data-chart></div>
      ${legend([[C.home, "П1"], [C.draw, "X"], [C.away, "П2"]])}
    </section>
    <section class="card">
      ${cardHead("Открытие → сейчас")}
      <div class="vtable">
        ${OUT.map(([k, l]) => `
          <div class="vt-row three">
            <span><i class="sw" style="background:${C[k]}"></i><b>${l}</b></span>
            <span class="num"><span class="muted">${odds(first[k])}</span> → <b>${odds(last[k])}</b></span>
            <span class="chip ${ch(k) < -0.03 ? "r" : ch(k) > 0.03 ? "g" : "n"}">${ch(k) > 0 ? "▲" : ch(k) < 0 ? "▼" : ""} ${pct(Math.abs(ch(k)), 1)}</span>
          </div>`).join("")}
      </div>
      <p class="hint">${moveText(m, ch)}</p>
    </section>
    ${otherMarkets(o)}
  `;
  const ago = (p) => (p.h >= 1 ? `${Math.round(p.h)} ч назад` : p.h > 0 ? `${Math.round(p.h * 60)} мин назад` : "Сейчас");
  lineChart(host.querySelector("[data-chart]"), {
    height: 160,
    yFmt: (v) => v.toFixed(1),
    labels: h.map((p) => (p.h >= 1 ? `−${Math.round(p.h)}ч` : "сейчас")),
    series: [
      { color: C.home, values: h.map((p) => p.home) },
      { color: C.draw, values: h.map((p) => p.draw) },
      { color: C.away, values: h.map((p) => p.away) },
    ],
    readout: host.querySelector("[data-ro]"),
    fmt: (i) => `<span class="muted">${ago(h[i])}</span> · П1 <b>${odds(h[i].home)}</b> · X <b>${odds(h[i].draw)}</b> · П2 <b>${odds(h[i].away)}</b>`,
  });
}

function otherMarkets(o) {
  if (!o.over25 && !o.btts_yes) return "";
  return `<section class="card">
    ${cardHead("Другие рынки")}
    <div class="kpis">${kpi("ТБ 2.5", odds(o.over25))}${kpi("ТМ 2.5", odds(o.under25))}${kpi("Обе да", odds(o.btts_yes))}</div>
  </section>`;
}

function moveText(m, ch) {
  const k = ["home", "draw", "away"].reduce((a, b) => (ch(a) < ch(b) ? a : b));
  if (ch(k) > -0.03) return "Линия стабильна: крупных денег ни на один исход не заходило.";
  const who = k === "home" ? m.home.name : k === "away" ? m.away.name : "ничью";
  return `Деньги идут на ${k === "draw" ? "" : "победу "}${esc(who)}: кэф упал на ${pct(Math.abs(ch(k)), 1)}.`;
}

function form(host, m) {
  const forms = m.form || {};
  const team = (side) => {
    const f = forms[side] || [];
    const five = f.slice(0, 5);
    const pts = five.reduce((s, x) => s + (x.result === "W" ? 3 : x.result === "D" ? 1 : 0), 0);
    const n = f.length || 1;
    const gf = f.reduce((s, x) => s + +x.score.split(":")[0], 0) / n;
    const ga = f.reduce((s, x) => s + +x.score.split(":")[1], 0) / n;
    return { f, pts, max: five.length * 3, gf, ga };
  };
  const H = team("home"), A = team("away");
  const hasForm = H.f.length || A.f.length;
  const hasXg = H.f.some((x) => x.xg_for != null);
  const metric = hasXg ? "xG" : "Голы";

  host.innerHTML = `
    ${hasForm ? `
    <section class="card">
      ${cardHead("Форма · последние 5")}
      ${[[m.home, H], [m.away, A]].map(([t, d]) => `
        <div class="frow"><b>${esc(t.name)}</b>${formChips(d.f)}<span class="muted">${d.pts} из ${d.max}</span></div>`).join("")}
      <div class="kpis">
        ${kpi("Забивают", `${H.gf.toFixed(1)}–${A.gf.toFixed(1)}`)}
        ${kpi("Пропускают", `${H.ga.toFixed(1)}–${A.ga.toFixed(1)}`)}
        ${kpi("Очков за 5", `${H.pts}–${A.pts}`)}
      </div>
    </section>

    ${["home", "away"].map((side) => (forms[side] || []).length > 1 ? `
    <section class="card">
      ${cardHead(`${metric} · ${m[side].name}`, info(hasXg
        ? "xG — ожидаемые голы: сколько команда «заслужила» забить по качеству своих моментов. Честнее реального счёта."
        : "Сколько команда забивала и пропускала в последних матчах."))}
      <div class="readout" data-ro="${side}">Последние ${(forms[side] || []).length} матчей</div>
      <div data-xg="${side}"></div>
      ${legend([["var(--green)", hasXg ? "xG создано" : "Забито"], ["var(--red)", hasXg ? "xG пропущено" : "Пропущено"]])}
    </section>` : "").join("")}

    <section class="card">
      ${cardHead("Последние матчи")}
      <div class="tabs-scroll">${segmented("fside", [["home", m.home.name], ["away", m.away.name]], "home")}</div>
      <div data-last></div>
    </section>` : `<section class="card">${cardHead("Форма")}${note("Нет данных о последних матчах команд.")}</section>`}

    ${m.h2h?.length ? `
    <section class="card">
      ${cardHead("Личные встречи")}
      ${m.h2h.map((g) => `
        <div class="h2h"><span class="muted">${esc(g.season)}</span><span class="h2h-t">${esc(g.home)}</span><b>${esc(g.score)}</b><span class="h2h-t r">${esc(g.away)}</span></div>`).join("")}
    </section>` : ""}

    ${m.table?.length ? `
    <section class="card">
      ${cardHead(`Таблица · ${m.league}`)}
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>#</th><th>Команда</th><th>И</th><th>В</th><th>Н</th><th>П</th><th>Мячи</th><th>О</th></tr></thead>
        <tbody>${m.table.map((r) => `
          <tr class="${r.team === m.home.name || r.team === m.away.name ? "hl" : ""}">
            <td>${r.pos}</td><td>${esc(r.team)}</td><td>${r.p}</td><td>${r.w}</td><td>${r.d}</td><td>${r.l}</td><td>${r.gf}:${r.ga}</td><td><b>${r.pts}</b></td>
          </tr>`).join("")}</tbody>
      </table></div>
    </section>` : ""}
  `;
  if (!hasForm) return;

  ["home", "away"].forEach((side) => {
    const f = (forms[side] || []).slice().reverse();
    const el = host.querySelector(`[data-xg="${side}"]`);
    if (!el) return;
    const forV = f.map((x) => (hasXg ? x.xg_for : +x.score.split(":")[0]));
    const agV = f.map((x) => (hasXg ? x.xg_against : +x.score.split(":")[1]));
    lineChart(el, {
      height: 110,
      yFmt: (v) => (hasXg ? v.toFixed(1) : String(Math.round(v))),
      series: [{ color: "var(--green)", values: forV }, { color: "var(--red)", values: agV }],
      readout: host.querySelector(`[data-ro="${side}"]`),
      fmt: (i) => `${f[i].home ? "дома" : "в гостях"} vs ${esc(f[i].opponent)} <b>${esc(f[i].score)}</b>${hasXg ? ` · xG ${f[i].xg_for} : ${f[i].xg_against}` : ""}`,
    });
  });
  const drawLast = (side) => {
    host.querySelector("[data-last]").innerHTML = (forms[side] || []).map((g) => `
      <div class="lg"><i class="res f-${g.result}"></i><span class="muted">${g.home ? "Д" : "Г"}</span><span class="lg-t">${esc(g.opponent)}</span><b>${esc(g.score)}</b><span class="muted num">${g.xg_for != null ? `xG ${g.xg_for}–${g.xg_against}` : g.date ? new Date(g.date).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : ""}</span></div>`).join("") || note("Нет данных");
  };
  onSeg(host, "fside", drawLast);
  drawLast("home");
}

const AVG_LABELS = {
  goals: ["Голы за матч", (v) => Number(v).toFixed(2)],
  conceded: ["Пропускают", (v) => Number(v).toFixed(2)],
  shots: ["Удары", (v) => v],
  corners: ["Угловые", (v) => v],
  cards: ["Жёлтые", (v) => v],
  possession: ["Владение, %", (v) => v],
  clean_sheets: ["Сухие матчи", (v) => v],
  failed_to_score: ["Не забили", (v) => v],
};

function stats(host, m) {
  const av = m.averages;
  const rows = av ? Object.entries(AVG_LABELS)
    .filter(([k]) => av.home?.[k] != null && av.away?.[k] != null)
    .map(([k, [name, f]]) => ({ name, home: f(av.home[k]), away: f(av.away[k]) })) : [];
  const r = m.referee;
  const inj = (side) => (m.injuries || []).filter((i) => i.team === side);

  host.innerHTML = `
    ${rows.length ? `
    <section class="card">
      ${cardHead("Средние за сезон")}
      <div class="cmp-head"><b>${esc(m.home.short)}</b><b>${esc(m.away.short)}</b></div>
      ${compareRows(rows)}
      ${av.home.corners != null ? `<div class="kpis">
        ${kpi("Угловые Σ", (av.home.corners + av.away.corners).toFixed(1))}
        ${kpi("Карточки Σ", (av.home.cards + av.away.cards).toFixed(1))}
        ${kpi("Удары Σ", Math.round(av.home.shots + av.away.shots))}
      </div>` : ""}
    </section>` : ""}

    ${r ? `
    <section class="card">
      ${cardHead("Судья", info("Строгий судья — больше карточек и пенальти. Полезно для ставок на карточки."))}
      <div class="ref"><b>${esc(r.name)}</b>${r.matches ? `<span class="muted">${r.matches} матчей в сезоне</span>` : ""}</div>
      ${r.yellow != null ? `
      <div class="kpis">
        ${kpi("Жёлтых", r.yellow.toFixed(1))}
        ${kpi("Красных", r.red.toFixed(2))}
        ${kpi("Пенальти", r.penalties.toFixed(2))}
      </div>
      <div class="meter"><span>Строгость</span><div class="meter-bar"><i style="width:${Math.min(100, ((r.yellow - 3) / 3) * 100)}%;background:var(--gold)"></i></div><b>${r.yellow >= 4.8 ? "высокая" : r.yellow >= 4 ? "средняя" : "низкая"}</b></div>` : ""}
    </section>` : ""}

    <section class="card">
      ${cardHead("Не сыграют")}
      ${["home", "away"].map((side) => `
        <div class="inj-team">${esc(m[side].name)}</div>
        ${inj(side).length ? inj(side).map((i) => `
          <div class="inj"><b>${esc(i.player)}</b>${i.position ? `<span class="muted">${esc(i.position)}</span>` : ""}<span class="muted">${esc(i.reason)}</span>${i.key ? `<span class="chip r">Ключевой</span>` : ""}</div>`).join("")
          : `<p class="muted">Все в строю</p>`}`).join("")}
    </section>
  `;
}

function liveTab(host, m) {
  const L = m.live || {};
  const lo = L.odds;
  host.innerHTML = `
    ${L.momentum?.length ? `
    <section class="card">
      ${cardHead("График давления", info("Столбики вверх — атакуют хозяева, вниз — гости. Чем выше столбик, тем опаснее атаки. Точки — голы."))}
      <div data-mom></div>
      ${legend([[C.home, m.home.name], [C.away, m.away.name]])}
    </section>` : ""}

    ${hasOdds(lo) ? `
    <section class="card">
      ${cardHead("Шансы сейчас")}
      ${L.probs ? probBar(L.probs) : ""}
      <div class="kpis">
        ${OUT.map(([k, l]) => kpi(`${l} · кэф ${odds(lo[k])}`, L.probs ? pct(L.probs[k]) : odds(lo[k]))).join("")}
      </div>
      ${L.remaining_goals ? `<div class="kv"><span class="muted">Ожидаем ещё голов</span><b>${(L.remaining_goals.home + L.remaining_goals.away).toFixed(2)}</b></div>` : ""}
      <a class="btn" href="#/hedge?match=${m.id}">Посчитать хедж по Live-кэфу</a>
    </section>` : ""}

    ${L.stats?.length ? `
    <section class="card">
      ${cardHead("Статистика матча")}
      <div class="cmp-head"><b>${esc(m.home.short)}</b><b>${esc(m.away.short)}</b></div>
      ${compareRows(L.stats)}
    </section>` : ""}

    <section class="card">
      ${cardHead("События")}
      ${L.events?.length ? L.events.map((e) => `
        <div class="ev ${e.team}"><span class="ev-m">${e.m}'</span><span class="ev-i ${e.type}"></span><span>${{ goal: "Гол", yellow: "Жёлтая", red: "Красная" }[e.type] || "Событие"}${e.player ? ` · ${esc(e.player)}` : ` · ${esc(m[e.team].name)}`}</span></div>`).join("")
        : `<p class="muted">Пока без событий</p>`}
    </section>
  `;
  if (L.momentum?.length) momentum(host.querySelector("[data-mom]"), L.momentum, L.events, { home: C.home, away: C.away });
}
