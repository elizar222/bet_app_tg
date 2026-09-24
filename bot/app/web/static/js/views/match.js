// Экран матча: обзор, кэфы, форма, статистика, Live.

import { api } from "../api.js";
import { compareRows, lineChart, momentum, probBar, scoreHeatmap } from "../charts.js";
import { esc, kickoff, odds, pct, segmented, onSeg } from "../ui.js";
import { cardHead, formChips, info, kpi, legend } from "./common.js";

const C = { home: "var(--c-home)", draw: "var(--c-draw)", away: "var(--c-away)" };
let lastTab = "overview";

export async function renderMatch(root, id) {
  const m = await api(`/api/matches/${id}`);
  const live = m.status === "live";
  const tabs = [["overview", "Обзор"], ["odds", "Кэфы"], ["form", "Форма"], ["stats", "Статистика"]];
  if (live) tabs.push(["live", "Live"]);
  if (!tabs.some(([t]) => t === lastTab)) lastTab = "overview";
  if (live && lastTab === "overview") lastTab = "live";

  root.innerHTML = `
    <section class="card match-head">
      <div class="mh-meta"><span>${esc(m.country)} · ${esc(m.league)}</span>
        ${live ? `<span class="chip r"><span class="live-dot"></span>${m.live.minute}'</span>` : `<span class="muted">${esc(kickoff(m.kickoff))}</span>`}</div>
      <div class="mh-teams">
        <div class="mh-team"><span class="crest" style="--c:${C.home}">${esc(m.home.short)}</span><b>${esc(m.home.name)}</b></div>
        <div class="mh-score">${live ? esc(m.live.score) : "—"}</div>
        <div class="mh-team"><span class="crest" style="--c:${C.away}">${esc(m.away.short)}</span><b>${esc(m.away.name)}</b></div>
      </div>
      <div class="oddsbox wide">
        ${[["home", "П1"], ["draw", "X"], ["away", "П2"]].map(([k, l]) =>
          `<span><small>${l}</small>${odds(live ? m.live.odds[k] : m.odds[k])}</span>`).join("")}
      </div>
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
  const a = m.analysis, mk = m.model;
  const rows = [["home", "П1", m.home.name], ["draw", "X", "Ничья"], ["away", "П2", m.away.name]];
  host.innerHTML = `
    <section class="card">
      ${cardHead("Вероятности исходов", info("«Линия» — вероятности из кэфов букмекера без его маржи. «Модель» — наш расчёт по силе атаки и обороны команд. Если модель выше линии, это value."))}
      ${legend([["var(--text-2)", "Модель"], ["var(--line-2)", "Линия БК"]])}
      ${rows.map(([k, l, name]) => `
        <div class="pr">
          <div class="pr-top"><span><b>${l}</b> <span class="muted">${esc(name)}</span></span>
            <span><b>${pct(mk[k])}</b> <span class="muted">/ ${pct(a.fair[k])}</span></span></div>
          <div class="pr-bars"><i style="width:${mk[k] * 100}%;background:${C[k]}"></i></div>
          <div class="pr-bars thin"><i style="width:${a.fair[k] * 100}%"></i></div>
        </div>`).join("")}
      <div class="kv"><span class="muted">Маржа букмекера</span><b>${pct(a.margin, 1)}</b></div>
    </section>

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
    </section>

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
      <div class="kv"><span class="muted">Кэф ТБ 2.5 / ТМ 2.5</span><b>${odds(m.odds.over25)} / ${odds(m.odds.under25)}</b></div>
    </section>
  `;
  scoreHeatmap(host.querySelector("[data-heat]"), mk.matrix, m.home.short, m.away.short);
}

function oddsTab(host, m) {
  const h = m.odds_history;
  const first = h[0], last = h.at(-1);
  const ch = (k) => (last[k] - first[k]) / first[k];
  host.innerHTML = `
    <section class="card">
      ${cardHead("Движение кэфов · 24 ч", info("Как менялись кэфы за сутки. Падение кэфа значит, что на этот исход много ставят."))}
      <div class="readout" data-ro>Проведите пальцем по графику</div>
      <div data-chart></div>
      ${legend([[C.home, "П1"], [C.draw, "X"], [C.away, "П2"]])}
    </section>
    <section class="card">
      ${cardHead("Открытие → сейчас")}
      <div class="vtable">
        ${[["home", "П1"], ["draw", "X"], ["away", "П2"]].map(([k, l]) => `
          <div class="vt-row three">
            <span><i class="sw" style="background:${C[k]}"></i><b>${l}</b></span>
            <span class="num"><span class="muted">${odds(first[k])}</span> → <b>${odds(last[k])}</b></span>
            <span class="chip ${ch(k) < -0.03 ? "r" : ch(k) > 0.03 ? "g" : "n"}">${ch(k) > 0 ? "▲" : ch(k) < 0 ? "▼" : ""} ${pct(Math.abs(ch(k)), 1)}</span>
          </div>`).join("")}
      </div>
      <p class="hint">${moveText(m, ch)}</p>
    </section>
    <section class="card">
      ${cardHead("Другие рынки")}
      <div class="kpis">
        ${kpi("ТБ 2.5", odds(m.odds.over25))}${kpi("ТМ 2.5", odds(m.odds.under25))}${kpi("Обе да", odds(m.odds.btts_yes))}
      </div>
    </section>
  `;
  const ro = host.querySelector("[data-ro]");
  lineChart(host.querySelector("[data-chart]"), {
    height: 160,
    yFmt: (v) => v.toFixed(1),
    labels: h.map((p) => (p.h ? `−${p.h}ч` : "сейчас")),
    series: [
      { color: C.home, values: h.map((p) => p.home) },
      { color: C.draw, values: h.map((p) => p.draw) },
      { color: C.away, values: h.map((p) => p.away) },
    ],
    readout: ro,
    fmt: (i) => `<span class="muted">${h[i].h ? h[i].h + " ч назад" : "Сейчас"}</span> · П1 <b>${odds(h[i].home)}</b> · X <b>${odds(h[i].draw)}</b> · П2 <b>${odds(h[i].away)}</b>`,
  });
}

function moveText(m, ch) {
  const k = ["home", "draw", "away"].reduce((a, b) => (ch(a) < ch(b) ? a : b));
  if (ch(k) > -0.03) return "Линия стабильна: крупных денег ни на один исход не заходило.";
  const who = k === "home" ? m.home.name : k === "away" ? m.away.name : "ничью";
  return `Деньги идут на ${k === "draw" ? "" : "победу "}${esc(who)}: кэф упал на ${pct(Math.abs(ch(k)), 1)}.`;
}

function form(host, m) {
  const team = (side) => {
    const f = m.form[side];
    const pts = f.slice(0, 5).reduce((s, x) => s + (x.result === "W" ? 3 : x.result === "D" ? 1 : 0), 0);
    const gf = f.reduce((s, x) => s + +x.score.split(":")[0], 0) / f.length;
    const ga = f.reduce((s, x) => s + +x.score.split(":")[1], 0) / f.length;
    return { f, pts, gf, ga };
  };
  const H = team("home"), A = team("away");
  const table = m.table;
  host.innerHTML = `
    <section class="card">
      ${cardHead("Форма · последние 5")}
      ${[[m.home, H], [m.away, A]].map(([t, d]) => `
        <div class="frow"><b>${esc(t.name)}</b>${formChips(d.f)}<span class="muted">${d.pts} из 15</span></div>`).join("")}
      <div class="kpis">
        ${kpi("Забивают", `${H.gf.toFixed(1)} / ${A.gf.toFixed(1)}`)}
        ${kpi("Пропускают", `${H.ga.toFixed(1)} / ${A.ga.toFixed(1)}`)}
        ${kpi("Очков за 5", `${H.pts} / ${A.pts}`)}
      </div>
    </section>

    ${["home", "away"].map((side) => `
    <section class="card">
      ${cardHead(`xG · ${m[side].name}`, info("xG — ожидаемые голы: сколько команда «заслужила» забить по качеству своих моментов. Честнее реального счёта."))}
      <div class="readout" data-ro="${side}">Последние 10 матчей</div>
      <div data-xg="${side}"></div>
      ${legend([["var(--green)", "xG создано"], ["var(--red)", "xG пропущено"]])}
    </section>`).join("")}

    <section class="card">
      ${cardHead("Последние матчи")}
      <div class="tabs-scroll">${segmented("fside", [["home", m.home.name], ["away", m.away.name]], "home")}</div>
      <div data-last></div>
    </section>

    <section class="card">
      ${cardHead("Личные встречи")}
      ${m.h2h.map((g) => `
        <div class="h2h"><span class="muted">${esc(g.season)}</span><span class="h2h-t">${esc(g.home)}</span><b>${esc(g.score)}</b><span class="h2h-t r">${esc(g.away)}</span></div>`).join("")}
    </section>

    <section class="card">
      ${cardHead(`Таблица · ${m.league}`)}
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>#</th><th>Команда</th><th>И</th><th>В</th><th>Н</th><th>П</th><th>Мячи</th><th>О</th></tr></thead>
        <tbody>${table.map((r) => `
          <tr class="${r.team === m.home.name || r.team === m.away.name ? "hl" : ""}">
            <td>${r.pos}</td><td>${esc(r.team)}</td><td>${r.p}</td><td>${r.w}</td><td>${r.d}</td><td>${r.l}</td><td>${r.gf}:${r.ga}</td><td><b>${r.pts}</b></td>
          </tr>`).join("")}</tbody>
      </table></div>
    </section>
  `;
  ["home", "away"].forEach((side) => {
    const f = m.form[side].slice().reverse();
    lineChart(host.querySelector(`[data-xg="${side}"]`), {
      height: 110,
      yFmt: (v) => v.toFixed(1),
      series: [
        { color: "var(--green)", values: f.map((x) => x.xg_for) },
        { color: "var(--red)", values: f.map((x) => x.xg_against) },
      ],
      readout: host.querySelector(`[data-ro="${side}"]`),
      fmt: (i) => `${f[i].home ? "дома" : "в гостях"} vs ${esc(f[i].opponent)} <b>${esc(f[i].score)}</b> · xG ${f[i].xg_for} : ${f[i].xg_against}`,
    });
  });
  const drawLast = (side) => {
    host.querySelector("[data-last]").innerHTML = m.form[side].map((g) => `
      <div class="lg"><i class="res f-${g.result}"></i><span class="muted">${g.home ? "Д" : "Г"}</span><span class="lg-t">${esc(g.opponent)}</span><b>${esc(g.score)}</b><span class="muted num">xG ${g.xg_for}–${g.xg_against}</span></div>`).join("");
  };
  onSeg(host, "fside", drawLast);
  drawLast("home");
}

function stats(host, m) {
  const h = m.averages.home, a = m.averages.away, r = m.referee;
  const inj = (side) => m.injuries.filter((i) => i.team === side);
  host.innerHTML = `
    <section class="card">
      ${cardHead("Средние за матч")}
      <div class="cmp-head"><b>${esc(m.home.short)}</b><b>${esc(m.away.short)}</b></div>
      ${compareRows([
        { name: "Голы (ожид.)", home: h.goals.toFixed(2), away: a.goals.toFixed(2) },
        { name: "Удары", home: h.shots, away: a.shots },
        { name: "Угловые", home: h.corners, away: a.corners },
        { name: "Жёлтые", home: h.cards, away: a.cards },
        { name: "Владение, %", home: h.possession, away: a.possession },
      ])}
      <div class="kpis">
        ${kpi("Угловых всего", (h.corners + a.corners).toFixed(1))}
        ${kpi("Карточек всего", (h.cards + a.cards).toFixed(1))}
        ${kpi("Ударов всего", Math.round(h.shots + a.shots))}
      </div>
    </section>

    <section class="card">
      ${cardHead("Судья", info("Строгий судья — больше карточек и пенальти. Полезно для ставок на карточки."))}
      <div class="ref"><b>${esc(r.name)}</b><span class="muted">${r.matches} матчей в сезоне</span></div>
      <div class="kpis">
        ${kpi("Жёлтых", r.yellow.toFixed(1))}
        ${kpi("Красных", r.red.toFixed(2))}
        ${kpi("Пенальти", r.penalties.toFixed(2))}
      </div>
      <div class="meter"><span>Строгость</span><div class="meter-bar"><i style="width:${Math.min(100, ((r.yellow - 3) / 3) * 100)}%;background:var(--gold)"></i></div><b>${r.yellow >= 4.8 ? "высокая" : r.yellow >= 4 ? "средняя" : "низкая"}</b></div>
    </section>

    <section class="card">
      ${cardHead("Не сыграют")}
      ${["home", "away"].map((side) => `
        <div class="inj-team">${esc(m[side].name)}</div>
        ${inj(side).length ? inj(side).map((i) => `
          <div class="inj"><b>${esc(i.player)}</b><span class="muted">${esc(i.position)}</span><span class="muted">${esc(i.reason)}</span>${i.key ? `<span class="chip r">Ключевой</span>` : ""}</div>`).join("")
          : `<p class="muted">Все в строю</p>`}`).join("")}
    </section>
  `;
}

function liveTab(host, m) {
  const L = m.live;
  host.innerHTML = `
    <section class="card">
      ${cardHead("График давления", info("Столбики вверх — атакуют хозяева, вниз — гости. Чем выше столбик, тем опаснее атаки. Точки — голы."))}
      <div data-mom></div>
      ${legend([[C.home, m.home.name], [C.away, m.away.name]])}
    </section>

    <section class="card">
      ${cardHead("Шансы сейчас")}
      ${probBar(L.probs)}
      <div class="kpis">
        ${kpi("П1", `${pct(L.probs.home)} · ${odds(L.odds.home)}`)}
        ${kpi("X", `${pct(L.probs.draw)} · ${odds(L.odds.draw)}`)}
        ${kpi("П2", `${pct(L.probs.away)} · ${odds(L.odds.away)}`)}
      </div>
      <div class="kv"><span class="muted">Ожидаем ещё голов</span><b>${(L.remaining_goals.home + L.remaining_goals.away).toFixed(2)}</b></div>
      <a class="btn" href="#/hedge?match=${m.id}">Посчитать хедж по Live-кэфу</a>
    </section>

    <section class="card">
      ${cardHead("Статистика матча")}
      <div class="cmp-head"><b>${esc(m.home.short)}</b><b>${esc(m.away.short)}</b></div>
      ${compareRows(L.stats)}
    </section>

    <section class="card">
      ${cardHead("События")}
      ${L.events.length ? L.events.map((e) => `
        <div class="ev ${e.team}"><span class="ev-m">${e.m}'</span><span class="ev-i ${e.type}"></span><span>${e.type === "goal" ? "Гол" : "Жёлтая"} · ${esc(m[e.team].name)}</span></div>`).join("")
        : `<p class="muted">Пока без событий</p>`}
    </section>
  `;
  momentum(host.querySelector("[data-mom]"), L.momentum, L.events, { home: C.home, away: C.away });
}
