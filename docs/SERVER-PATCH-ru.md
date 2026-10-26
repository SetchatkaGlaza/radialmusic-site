# Подключение оплаты к серверу лицензий (этап 4)

Сайт отправляет `POST {api.url}/v1/buy` с телом `{"email": "..."}` и ждёт `{"url": "https://..."}` (адрес оплаты ЮKassa). Эндпоинт уже есть в `RadialMusic/server/app.py`. Он не запускался владельцем, проверь на тестовом магазине ЮKassa.

## 1. CORS (обязательно)
Сайт и сервер на разных адресах, без CORS браузер заблокирует запрос. В `app.py` после `app = FastAPI(...)` добавить:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=[os.environ.get("RM_SITE_ORIGIN", "https://YOUR-DOMAIN")],
                   allow_methods=["POST"], allow_headers=["Content-Type"])
```
В окружении сервера: `RM_SITE_ORIGIN=https://адрес-сайта` (без слэша в конце, для GitHub Pages — `https://<логин>.github.io`).

## 2. Переменные окружения для оплаты
`RM_YOOKASSA_SHOP`, `RM_YOOKASSA_SECRET`, `RM_PRICE` (например `199.00`), `RM_RETURN_URL=https://адрес-сайта/thanks.html`, почта: `RM_SMTP_*`, `RM_MAIL_FROM`. Вебхук в кабинете ЮKassa: `https://lic.example.com/v1/webhook/yookassa`.

## 3. На сайте
В `src/config.js`: `api.url = 'https://lic.example.com'`. Пока пусто, кнопка «Оформить Pro» ведёт на `links.buy`.

## Тарифы месяц и год (уже в сервере)
Сервер принимает `{"email": "...", "plan": "month"|"year"}`. Цены: `RM_PRICE` (месяц) и `RM_PRICE_YEAR` (год; пусто: год отключён). Сумма платежа сверяется с ценой именно того плана, который записан в платеже, так что оплатить год по цене месяца нельзя. Ключ выдаётся со сроком: месяц 31 день, год 366 дней. Цены в `RM_PRICE*` и в `src/config.js` должны совпадать. CORS включается переменной `RM_SITE_ORIGIN` (уже вшито в `app.py`, править вручную не нужно, раздел 1 выше можно пропустить).

## Ограничения (честно)
- Автопродления нет: платёж разовый, по окончании срока ключ перестаёт действовать, покупатель оплачивает заново. Рекуррентные платежи ЮKassa требуют отдельной настройки и согласования с магазином.
- `app.py` с эндпоинтом `/v1/buy` (CORS, план) я не запускал: в среде нет fastapi. Проверены функции `providers`/`licserver` тестами `tests/test_plans.py`, синтаксис `app.py` через py_compile. Проверь на тестовом магазине ЮKassa.
- Чек самозанятого формируется в «Мой налог», сайт этого не делает.
- Тексты оферты и политики — черновики, нужна юридическая проверка.
