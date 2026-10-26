import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { CONFIG } from '../config.js';
export function initUI() {
  const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  $$('[data-version]').forEach((e) => (e.textContent = CONFIG.version));
  $$('[data-year]').forEach((e) => (e.textContent = new Date().getFullYear()));
  $$('[data-trial]').forEach((e) => (e.textContent = CONFIG.trialDays));
  $$('[data-download]').forEach((a) => a.setAttribute('href', CONFIG.links.download));
  $$('[data-buy]').forEach((a) => a.setAttribute('href', CONFIG.links.buy));
  $$('[data-link]').forEach((a) => a.setAttribute('href', CONFIG.links[a.dataset.link]));
  // маркиза (дублируем для бесшовности)
  const m = $('#marquee'); if (m) m.innerHTML = CONFIG.actions.concat(CONFIG.actions).concat(CONFIG.actions).concat(CONFIG.actions).map((t) => `<span>${t}</span>`).join('');
  // шапка и бургер
  const nav = $('#nav'), burger = $('#burger'), links = $('#navLinks');
  addEventListener('scroll', () => nav.classList.toggle('is-scrolled', scrollY > 24), { passive: true });
  burger.addEventListener('click', () => { const o = links.classList.toggle('is-open'); burger.setAttribute('aria-expanded', o); });
  links.addEventListener('click', () => { links.classList.remove('is-open'); burger.setAttribute('aria-expanded', false); });
  // тарифы: месяц / год
  const price = $('#proPrice'), unit = $('#proUnit'), save = $('#proSave');
  { const P = CONFIG.pricing, per = Math.round(P.yearly / 12), pct = Math.round((1 - P.yearly / (P.monthly * 12)) * 100); save.textContent = `Год: всего ${per} ${P.currency} в месяц, выгода ${pct}%`; save.hidden = true; }
  $$('.toggle button').forEach((b) => b.addEventListener('click', () => {
    $$('.toggle button').forEach((x) => x.classList.toggle('is-on', x === b));
    const y = b.dataset.period === 'yearly', val = y ? CONFIG.pricing.yearly : CONFIG.pricing.monthly;
    const o = { v: +price.textContent };
    gsap.to(o, { v: val, duration: 0.6, ease: 'power2.out', onUpdate: () => (price.textContent = Math.round(o.v)) });
    unit.textContent = `${CONFIG.pricing.currency} / ${y ? 'год' : 'мес'}`;
    save.hidden = !y;
  }));
  price.textContent = CONFIG.pricing.monthly;
  // шаги «Как работает»: закрепление и подсветка
  const steps = $$('.step');
  if (steps.length && innerWidth > 860) {
    ScrollTrigger.create({ trigger: '#how', start: 'top top', end: '+=1200', pin: '#howPin', scrub: true,
      onUpdate: (s) => steps.forEach((el, i) => el.classList.toggle('is-on', s.progress >= i / steps.length)) });
  } else steps.forEach((s) => s.classList.add('is-on'));
  // магнитные кнопки
  if (matchMedia('(hover:hover)').matches) $$('.btn').forEach((b) => {
    const x = gsap.quickTo(b, 'x', { duration: 0.4 }), y = gsap.quickTo(b, 'y', { duration: 0.4 });
    b.addEventListener('pointermove', (e) => { const r = b.getBoundingClientRect(); x((e.clientX - r.left - r.width / 2) * 0.25); y((e.clientY - r.top - r.height / 2) * 0.25); });
    b.addEventListener('pointerleave', () => { x(0); y(0); });
  });
}
