// Общие помощники интерфейса: форматирование, экранирование, шторки, тосты.

export const tg = window.Telegram?.WebApp;

export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
export const money = (v, sign = false) =>
  (sign && v > 0 ? "+" : v < 0 ? "−" : "") + nf.format(Math.abs(Math.round(v))) + " ₽";
export const num = (v) => nf.format(Math.round(v));
export const pct = (v, digits = 0, sign = false) =>
  (sign && v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(digits).replace(".", ",") + "%";
export const odds = (v) => Number(v).toFixed(2);
export const compact = (v) => {
  const a = Math.abs(v), s = v < 0 ? "−" : "";
  if (a >= 1e6) return s + (a / 1e6).toFixed(1).replace(".", ",") + " млн";
  if (a >= 1e3) return s + Math.round(a / 1e3) + " тыс";
  return s + Math.round(a);
};
export const signClass = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");

export function kickoff(iso) {
  const d = new Date(iso), now = new Date();
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1);
  if (d.toDateString() === now.toDateString()) return `Сегодня ${time}`;
  if (d.toDateString() === tomorrow.toDateString()) return `Завтра ${time}`;
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) + " " + time;
}

export function haptic(kind = "light") {
  try {
    if (kind === "success" || kind === "error" || kind === "warning") tg?.HapticFeedback?.notificationOccurred(kind);
    else tg?.HapticFeedback?.impactOccurred(kind);
  } catch { /* вне Telegram */ }
}

export function toast(text) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = text;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 250); }, 2200);
}

export async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Скопировано"); haptic("success"); }
  catch {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); toast("Скопировано"); } catch { toast(text); }
    ta.remove();
  }
}

export function openLink(url) {
  if (!url) return;
  if (url.startsWith("https://t.me/") && tg?.openTelegramLink) tg.openTelegramLink(url);
  else if (tg?.openLink) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}

// Шторка снизу: html — содержимое, onMount(root, close) — навесить обработчики.
export function sheet(html, onMount) {
  const wrap = document.createElement("div");
  wrap.className = "sheet-wrap";
  wrap.innerHTML = `<div class="sheet-backdrop"></div><div class="sheet" role="dialog"><div class="sheet-grip"></div>${html}</div>`;
  document.body.appendChild(wrap);
  requestAnimationFrame(() => wrap.classList.add("open"));
  const close = () => { wrap.classList.remove("open"); setTimeout(() => wrap.remove(), 220); };
  wrap.querySelector(".sheet-backdrop").addEventListener("click", close);
  onMount?.(wrap.querySelector(".sheet"), close);
  return close;
}

export function segmented(name, options, active) {
  return `<div class="seg" role="tablist" data-seg="${name}">${options
    .map(([v, label]) => `<button type="button" data-v="${v}" class="${v === active ? "on" : ""}">${esc(label)}</button>`)
    .join("")}</div>`;
}

export function onSeg(root, name, handler) {
  root.querySelectorAll(`[data-seg="${name}"] button`).forEach((btn) =>
    btn.addEventListener("click", () => {
      root.querySelectorAll(`[data-seg="${name}"] button`).forEach((b) => b.classList.toggle("on", b === btn));
      haptic();
      handler(btn.dataset.v);
    }));
}

export const loader = () => `<div class="skeleton"><div></div><div></div><div></div></div>`;

export const empty = (title, text, action = "") =>
  `<div class="empty"><div class="empty-t">${esc(title)}</div><p>${esc(text)}</p>${action}</div>`;

export const FORM_LABEL = { W: "В", D: "Н", L: "П" };

// ── Клубные цвета и эмблемы ────────────────────────────────────────────────
const CLUB = {
  "Манчестер Сити": ["#6cabdd", "#1c2c5b"], "Арсенал": ["#ef0107", "#9c824a"], "Ливерпуль": ["#c8102e", "#00b2a9"],
  "Челси": ["#034694", "#dba111"], "Тоттенхэм": ["#e8e8ea", "#132257"], "Манчестер Юнайтед": ["#da291c", "#fbe122"],
  "Астон Вилла": ["#95bfe5", "#670e36"], "Ньюкасл": ["#e8e8ea", "#241f20"], "Реал Мадрид": ["#febe10", "#e8e8ea"],
  "Барселона": ["#a50044", "#004d98"], "Атлетико": ["#cb3524", "#272e61"], "Жирона": ["#cd2534", "#e8e8ea"],
  "Атлетик": ["#ee2523", "#e8e8ea"], "Реал Сосьедад": ["#0067b1", "#e8e8ea"], "Севилья": ["#e8e8ea", "#d6001c"],
  "Вильярреал": ["#ffe667", "#005187"], "Интер": ["#0068a8", "#1d1d1b"], "Наполи": ["#12a0d7", "#003c82"],
  "Милан": ["#fb090b", "#1d1d1b"], "Ювентус": ["#e8e8ea", "#1d1d1b"], "Аталанта": ["#1e71b8", "#1d1d1b"],
  "Рома": ["#8e1f2f", "#f0bc42"], "Лацио": ["#87d8f7", "#e8e8ea"], "Фиорентина": ["#482e92", "#e8e8ea"],
  "Бавария": ["#dc052d", "#0066b2"], "Байер": ["#e32221", "#1d1d1b"], "Боруссия Д": ["#fde100", "#1d1d1b"],
  "РБ Лейпциг": ["#dd0741", "#e8e8ea"], "Штутгарт": ["#e32219", "#e8e8ea"], "Айнтрахт": ["#e1000f", "#1d1d1b"],
  "Вольфсбург": ["#65b32e", "#e8e8ea"], "Фрайбург": ["#e2001a", "#1d1d1b"], "Зенит": ["#0093d0", "#e8e8ea"],
  "Краснодар": ["#1c9a47", "#1d1d1b"], "Спартак": ["#d0021b", "#e8e8ea"], "ЦСКА": ["#003f8a", "#d6001c"],
  "Динамо": ["#0a3a8c", "#e8e8ea"], "Локомотив": ["#d8001e", "#00843d"], "Ростов": ["#ffd200", "#0033a0"],
  "Рубин": ["#8f1b2a", "#1c7a3e"],
};

export function clubColors(name) {
  if (CLUB[name]) return CLUB[name];
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return [`hsl(${h} 60% 52%)`, `hsl(${(h + 40) % 360} 45% 30%)`];
}

export function crest(name, short, size = "") {
  const [a, b] = clubColors(name);
  const label = short || String(name).slice(0, 3).toUpperCase();
  return `<span class="crest ${size}" style="--a:${a};--b:${b}" aria-hidden="true"><span>${esc(label)}</span></span>`;
}

// ── Счётчик, докручивающийся до значения ────────────────────────────────────
export function countUp(el, to, fmt, ms = 700) {
  if (!el) return;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduce) { el.textContent = fmt(to); return; }
  const from = to * 0.82;
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / ms);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
