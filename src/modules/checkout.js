import { CONFIG } from '../config.js';
// Выбранный период берётся из переключателя тарифов (month | year); сервер сам сверяет сумму.
const currentPlan = () => (document.querySelector('.toggle button.is-on')?.dataset.period === 'yearly' ? 'year' : 'month');
// Окно покупки: e-mail + согласие → POST {api}/v1/buy → переход на оплату ЮKassa
export function initCheckout() {
  const modal = document.getElementById('modal'), form = document.getElementById('buyForm');
  const email = document.getElementById('buyEmail'), ok = document.getElementById('buyOk');
  const err = document.getElementById('buyErr'), go = document.getElementById('buyGo');
  if (!modal) return;
  const close = () => { modal.hidden = true; document.body.style.overflow = ''; };
  const open = () => { const y = currentPlan() === 'year'; go.textContent = `Оплатить ${y ? CONFIG.pricing.yearly : CONFIG.pricing.monthly} ${CONFIG.pricing.currency} за ${y ? 'год' : 'месяц'}`; modal.hidden = false; document.body.style.overflow = 'hidden'; err.textContent = ''; email.focus(); };
  document.querySelectorAll('[data-buy]').forEach((a) => a.addEventListener('click', (e) => {
    if (!CONFIG.api.url) return;              // нет сервера: обычная ссылка links.buy
    e.preventDefault(); open();
  }));
  document.getElementById('modalX').addEventListener('click', close);
  modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) close(); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); err.textContent = '';
    if (!/^\S+@\S+\.\S+$/.test(email.value.trim())) { err.textContent = 'Проверь адрес почты'; return; }
    if (!ok.checked) { err.textContent = 'Нужно принять соглашение'; return; }
    const label = go.textContent; go.disabled = true; go.textContent = 'Создаём платёж…';
    try {
      const r = await fetch(CONFIG.api.url.replace(/\/$/, '') + '/v1/buy', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: email.value.trim(), plan: currentPlan() }) });
      const d = await r.json().catch(() => ({}));
      if (r.ok && typeof d.url === 'string' && d.url.startsWith('https://')) { location.href = d.url; return; }
      err.textContent = d.detail || 'Не удалось создать платёж, попробуй позже';
    } catch { err.textContent = 'Нет связи с сервером оплаты. Попробуй позже или напиши в поддержку'; }
    go.disabled = false; go.textContent = label;
  });
}
