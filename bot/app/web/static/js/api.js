// Запросы к серверу. initData подписан Telegram — по нему сервер узнаёт пользователя.

import { tg } from "./ui.js";

export class ApiError extends Error {
  constructor(status, data) {
    super(data?.detail || `Ошибка ${status}`);
    this.status = status;
    this.data = data;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Init-Data": tg?.initData || "",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* пустой ответ */ }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// Профиль грузится один раз и обновляется после расчётов хеджа.
export const state = { me: null };

export async function loadMe() {
  state.me = await api("/api/me");
  return state.me;
}
