import { gsap } from 'gsap';
export function initReveal() {
  // Заголовок по словам
  document.querySelectorAll('[data-split]').forEach((el) => {
    el.innerHTML = el.innerHTML.split(/(<br\s*\/?>)/i).map((p) => /^<br/i.test(p) ? p : p.split(' ').filter(Boolean)
      .map((w) => `<span class="w" style="display:inline-block">${w}</span>`).join(' ')).join('');
    gsap.fromTo(el.querySelectorAll('.w'), { y: 50, opacity: 0, rotate: 3 }, { y: 0, opacity: 1, rotate: 0, duration: 1, stagger: 0.08, ease: 'power4.out', delay: 0.1 });
  });
  gsap.utils.toArray('[data-reveal]').forEach((el, i) => {
    gsap.fromTo(el, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.9, ease: 'power3.out',
      scrollTrigger: { trigger: el, start: 'top 88%', once: true }, delay: el.closest('.hero') ? i * 0.08 : 0 });
  });
  gsap.to('#progress', { scaleX: 1, ease: 'none', scrollTrigger: { scrub: 0.2, start: 0, end: 'max' } });
  gsap.to('.marquee__track', { xPercent: -50, duration: 28, ease: 'none', repeat: -1 });
  gsap.to('.blob--a', { y: 120, scrollTrigger: { trigger: '.hero', scrub: true, start: 'top top', end: 'bottom top' } });
  document.documentElement.classList.add('anim-ok');
}
