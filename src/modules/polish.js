import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
export function initPolish() {
  // Кольцо на фоне вращается вместе со скроллом
  if (!reduce) gsap.to('#bgring', { rotation: 360, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: 0.6 } });
  // Свечение за курсором на карточках тарифов и функций
  document.querySelectorAll('.plan,.card').forEach((el) => el.addEventListener('pointermove', (e) => {
    const r = el.getBoundingClientRect(); el.style.setProperty('--mx', e.clientX - r.left + 'px'); el.style.setProperty('--my', e.clientY - r.top + 'px');
  }));
  // Свой курсор-кольцо (только мышь)
  const cur = document.getElementById('cursor');
  if (cur && !reduce && matchMedia('(hover:hover) and (pointer:fine)').matches) {
    const x = gsap.quickTo(cur, 'x', { duration: 0.25 }), y = gsap.quickTo(cur, 'y', { duration: 0.25 });
    addEventListener('pointermove', (e) => { x(e.clientX); y(e.clientY); cur.classList.add('on'); }, { passive: true });
    document.querySelectorAll('a,button,summary,.wheel path').forEach((el) => {
      el.addEventListener('pointerenter', () => cur.classList.add('big')); el.addEventListener('pointerleave', () => cur.classList.remove('big'));
    });
  }
}
