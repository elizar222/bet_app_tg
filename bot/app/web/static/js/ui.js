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
