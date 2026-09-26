// Окно VIP: лимит исчерпан или режим закрыт.

import { api, state } from "../api.js";
import { esc, haptic, openLink, sheet, toast } from "../ui.js";

export function vipSheet(text) {
  const me = state.me;
  const bk = esc(me.bookmaker || "1win");
  sheet(`
    <div class="vip-badge">VIP</div>
    <h2>${esc(text || me.vip_text)}</h2>
    <ul class="checks">
      <li>Безлимитные расчёты хеджа 24/7</li>
      <li>Режимы «Возврат ставки» и «Свой %»</li>
      <li>Расширенная аналитика и разборы</li>
    </ul>
    <button type="button" class="btn big gold" data-dep>Пополнить на ${bk}</button>
    <label class="field"><span>Уже есть депозит? Введите ваш ${bk} ID</span>
      <input id="vip-id" type="text" inputmode="numeric" placeholder="Например, 12345678" value="${esc(me.onewin_id || "")}"></label>
    <button type="button" class="btn ghost" data-send>Отправить на проверку</button>
    ${me.onewin_id ? `<p class="note">ID ${esc(me.onewin_id)} на проверке. Статус обновится после подтверждения.</p>` : ""}
  `, (el, close) => {
    el.querySelector("[data-dep]").addEventListener("click", () => openLink(me.ref_link));
    el.querySelector("[data-send]").addEventListener("click", async () => {
      const id = el.querySelector("#vip-id").value.trim();
      if (id.length < 3) return toast("Введите ID");
      try {
        await api("/api/me/onewin", { method: "POST", body: { onewin_id: id } });
        state.me.onewin_id = id;
        haptic("success");
        toast("Отправили на проверку");
        close();
      } catch (e) { toast(e.message); }
    });
  });
}
