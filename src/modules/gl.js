import { CONFIG } from '../config.js';
// Необязательное 3D-кольцо за круговым меню. Любая ошибка = сайт работает без него.
export async function initGL() {
  const host = document.querySelector('.hero__demo');
  if (!host || !CONFIG.webgl || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  try {
    const THREE = await import('three');
    const cv = document.createElement('canvas'); cv.className = 'gl'; cv.setAttribute('aria-hidden', 'true'); host.prepend(cv);
    const renderer = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(40, 1, 0.1, 50); cam.position.z = 9;
    const group = new THREE.Group(); scene.add(group);
    const N = 8, mats = [];
    for (let i = 0; i < N; i++) {
      const len = (Math.PI * 2) / N * 0.9, start = (Math.PI * 2) / N * i;
      const m = new THREE.MeshBasicMaterial({ color: new THREE.Color().setHSL(0.72 + i * 0.03, 0.8, 0.6), transparent: true, opacity: 0.35, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(new THREE.RingGeometry(2.6, 3.6, 24, 1, start, len), m);
      mesh.position.z = (i % 2) * 0.25; group.add(mesh); mats.push(m);
    }
    const halo = new THREE.Mesh(new THREE.TorusGeometry(3.1, 0.015, 8, 120), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.25 }));
    group.add(halo);
    const size = () => { const { width: w, height: h } = host.getBoundingClientRect(); renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); };
    new ResizeObserver(size).observe(host); size();
    let tx = 0, ty = 0, run = true;
    host.addEventListener('pointermove', (e) => { const r = host.getBoundingClientRect(); tx = ((e.clientY - r.top) / r.height - 0.5) * 0.9; ty = ((e.clientX - r.left) / r.width - 0.5) * 0.9; });
    new IntersectionObserver(([e]) => (run = e.isIntersecting)).observe(host);
    const clock = new THREE.Clock();
    (function loop() {
      requestAnimationFrame(loop); if (!run) return;
      const t = clock.getElapsedTime();
      group.rotation.z = t * 0.12; group.rotation.x += (tx - group.rotation.x) * 0.05; group.rotation.y += (ty - group.rotation.y) * 0.05;
      mats.forEach((m, i) => (m.opacity = 0.22 + 0.25 * Math.max(0, Math.sin(t * 1.4 - i * 0.8))));
      renderer.render(scene, cam);
    })();
  } catch (e) { console.warn('WebGL отключён:', e); }
}
