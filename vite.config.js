import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
const __dirname = fileURLToPath(new URL('.', import.meta.url));
const OWNER = JSON.parse(readFileSync(resolve(__dirname, 'owner.config.json'), 'utf8'));
// подставляет {{КЛЮЧ}} из owner.config.json в HTML и в robots/sitemap
const fill = (s) => s.replace(/\{\{(\w+)\}\}/g, (m, k) => (k in OWNER ? String(OWNER[k]) : m));
const missing = () => Object.entries(OWNER).filter(([k, v]) => !k.startsWith('_') && String(v).startsWith('ВПИШИ')).map(([k]) => k);
const ownerPlugin = () => ({
  name: 'owner-config',
  transformIndexHtml: (html) => fill(html),
  closeBundle() {
    for (const f of ['robots.txt', 'sitemap.xml']) {
      const p = resolve(__dirname, 'dist', f);
      if (existsSync(p)) writeFileSync(p, fill(readFileSync(p, 'utf8')));
    }
    const m = missing();
    if (m.length) console.warn('\n[owner-config] НЕ ЗАПОЛНЕНО в owner.config.json: ' + m.join(', ') + '\n');
    else console.log('\n[owner-config] все поля заполнены\n');
  }
});
// base './' — работает и с GitHub Pages (подпапка), и с обычного хостинга
export default defineConfig({
  base: './',
  plugins: [ownerPlugin()],
  build: { outDir: 'dist', target: 'es2020', rollupOptions: { input: {
    main: resolve(__dirname, 'index.html'), eula: resolve(__dirname, 'eula.html'), privacy: resolve(__dirname, 'privacy.html'), thanks: resolve(__dirname, 'thanks.html') } } }
});
