import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Живой фон hero: светящиеся частицы тянутся к курсору
export function initFx() {
  const cv = document.getElementById('fx'); if (!cv || reduce) return;
  const ctx = cv.getContext('2d'); let w, h, ps = [], mx = -999, my = -999, run = true;
  const size = () => { const r = cv.getBoundingClientRect(); w = cv.width = r.width; h = cv.height = r.height;
    ps = Array.from({ length: Math.min(70, Math.round(w / 18)) }, () => ({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .3, vy: (Math.random() - .5) * .3, r: Math.random() * 1.8 + .6 })); };
  size(); addEventListener('resize', size);
  cv.parentElement.addEventListener('pointermove', (e) => { const r = cv.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top; });
  new IntersectionObserver(([e]) => (run = e.isIntersecting)).observe(cv);
  (function tick() {
    if (run) {
      ctx.clearRect(0, 0, w, h);
      for (const p of ps) {
        const dx = mx - p.x, dy = my - p.y, d = Math.hypot(dx, dy);
        if (d < 160) { p.vx += dx / d * .02; p.vy += dy / d * .02; }
        p.vx *= .99; p.vy *= .99; p.x = (p.x + p.vx + w) % w; p.y = (p.y + p.vy + h) % h;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283); ctx.fillStyle = d < 160 ? 'rgba(255,107,142,.9)' : 'rgba(124,108,255,.55)'; ctx.fill();
      }
    }
    requestAnimationFrame(tick);
  })();
}

// Макет окна настроек: наклон за курсором, смена темы, мини-круг
export function initApp() {
  const app = document.getElementById('app'); if (!app) return;
  const mini = document.getElementById('mini'), N = 8;
  mini.innerHTML = Array.from({ length: N }, (_, i) => `<i style="--r:${i * 360 / N}deg"></i>`).join('') + '<b></b>';
  document.querySelectorAll('#themes button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('#themes button').forEach((x) => x.classList.toggle('is-on', x === b));
    app.style.setProperty('--a', b.dataset.a); app.style.setProperty('--b', b.dataset.b);
    gsap.fromTo(mini, { scale: .9 }, { scale: 1, duration: .6, ease: 'elastic.out(1,.5)' });
  }));
  if (!reduce && matchMedia('(hover:hover)').matches) {
    const rx = gsap.quickTo(app, 'rotationX', { duration: .6 }), ry = gsap.quickTo(app, 'rotationY', { duration: .6 });
    gsap.set(app, { transformPerspective: 1000 });
    app.addEventListener('pointermove', (e) => { const r = app.getBoundingClientRect(); ry(((e.clientX - r.left) / r.width - .5) * 10); rx(-((e.clientY - r.top) / r.height - .5) * 8); });
    app.addEventListener('pointerleave', () => { rx(0); ry(0); });
  }
  // ползунок и переключатели оживают при появлении
  gsap.from('.sl u', { width: 0, duration: 1.2, ease: 'power3.out', scrollTrigger: { trigger: app, start: 'top 75%', once: true } });
}

// Счётчики в полосе цифр
export function initCounters() {
  document.querySelectorAll('[data-count]').forEach((el) => {
    const to = +el.dataset.count, o = { v: 0 };
    gsap.to(o, { v: to, duration: 1.4, ease: 'power2.out', onUpdate: () => (el.textContent = Math.round(o.v)),
      scrollTrigger: { trigger: el, start: 'top 90%', once: true } });
  });
}
