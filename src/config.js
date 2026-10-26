import OWNER from '../owner.config.json';
// ВСЁ, что владелец меняет без правки вёрстки: цены, ссылки, тексты тарифов.
export const CONFIG = {
  product: 'Radial Music',
  version: '1.0.38',
  // ЗАГЛУШКИ: подставь свои цены
  pricing: { monthly: OWNER.PRICE_MONTH, yearly: OWNER.PRICE_YEAR, currency: '₽' },
  trialDays: 14,
  api: { url: OWNER.API_URL.startsWith('http') ? OWNER.API_URL : '' },   // адрес сервера лицензий, например https://lic.example.com (пусто: кнопка ведёт на links.buy)
  webgl: true,        // 3D-кольцо в hero (three.js подгружается отдельно, при ошибке сайт работает без него)
  links: {
    download: OWNER.DOWNLOAD_URL,            // ссылка на установщик (.exe)
    buy: OWNER.BUY_URL,                 // ссылка на оплату (ЮKassa / Prodamus / Tinkoff)
    support: 'mailto:' + OWNER.SUPPORT_EMAIL,
    privacy: './privacy.html', offer: './eula.html',
    studio: 'https://setchatkaglaza.github.io/setchatkaglaza/'
  },
  actions: ['Пауза', 'Следующий', 'Лайк', 'Громче', 'Без звука', 'Тише', 'Таймер сна', 'Предыдущий']
};
