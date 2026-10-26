import './styles.css';
import { initSmooth } from './modules/smooth.js';
import { initReveal } from './modules/reveal.js';
import { initWheel } from './modules/wheel.js';
import { initUI } from './modules/ui.js';
import { initFx, initApp, initCounters } from './modules/extras.js';
import { initPolish } from './modules/polish.js';
import { initCheckout } from './modules/checkout.js';
import { initGL } from './modules/gl.js';
document.documentElement.classList.add('js');
// ошибка в одной части не должна ломать остальные и прятать контент
const safe = (fn) => { try { const r = fn(); if (r && r.catch) r.catch(() => {}); } catch (e) { console.error(e); if (fn === initReveal) document.documentElement.classList.add('js-failed'); } };
[initUI, initWheel, initSmooth, initReveal, initFx, initApp, initCounters, initPolish, initCheckout, initGL].forEach(safe);
// страховка: если анимации так и не стартовали за 4 секунды, показываем всё как есть
setTimeout(() => { if (!document.documentElement.classList.contains('anim-ok')) document.documentElement.classList.add('js-failed'); }, 4000);
