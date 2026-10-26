import { CONFIG } from '../config.js';
const NS = 'http://www.w3.org/2000/svg';
// Интерактивное демо кругового меню (то, что пользователь увидит в приложении)
export function initWheel() {
  const root = document.getElementById('wheel'); if (!root) return;
  const n = CONFIG.actions.length, R = 200, r = 112, gap = 0.04;
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '-210 -210 420 420');
  svg.innerHTML = `<defs><linearGradient id="wg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c6cff"/><stop offset="1" stop-color="#ff6b8e"/></linearGradient></defs>`;
  const pt = (rad, a) => [Math.cos(a) * rad, Math.sin(a) * rad];
  const paths = CONFIG.actions.map((_, i) => {
    const a0 = (i / n) * Math.PI * 2 - Math.PI / 2 - Math.PI / n + gap, a1 = ((i + 1) / n) * Math.PI * 2 - Math.PI / 2 - Math.PI / n - gap;
    const [x0, y0] = pt(R, a0), [x1, y1] = pt(R, a1), [x2, y2] = pt(r, a1), [x3, y3] = pt(r, a0);
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('d', `M${x0} ${y0}A${R} ${R} 0 0 1 ${x1} ${y1}L${x2} ${y2}A${r} ${r} 0 0 0 ${x3} ${y3}Z`);
    svg.appendChild(p); return p;
  });
  const center = document.createElement('div'); center.className = 'wheel__center'; center.textContent = 'Radial Music';
  root.append(svg, center);
  let cur = -1, auto, idle = true;
  const set = (i) => { paths.forEach((p, k) => p.classList.toggle('is-on', k === i)); center.textContent = i < 0 ? 'Radial Music' : CONFIG.actions[i]; cur = i; };
  const loop = () => { clearInterval(auto); auto = setInterval(() => idle && set((cur + 1) % n), 1400); };
  paths.forEach((p, i) => {
    p.addEventListener('pointerenter', () => { idle = false; set(i); });
    p.addEventListener('pointerleave', () => { idle = true; });
  });
  loop();
}
