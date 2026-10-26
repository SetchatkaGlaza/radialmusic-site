"""HTTP-слой сервера лицензий (FastAPI). Тонкая обёртка над licserver.Service.

НЕ ЗАПУСКАЛСЯ: в среде разработки нет FastAPI и сети. Логика в licserver.py проверена тестами, этот файл только
py_compile. Первый запуск и проверку делает владелец: инструкция в server/README.md.

Запуск: uvicorn app:app --host 127.0.0.1 --port 8000   (HTTPS снимает обратный прокси, см. deploy/Caddyfile)
"""
import json
import logging
import os
import time

from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import mailer
import providers
from licserver import RateLimiter, Service

log = logging.getLogger("licserver")
MAX_WEBHOOK_BYTES = 10_000


def _make_service():
    with open(os.environ.get("RM_PRIVATE_KEY_FILE", "private.key.txt"), encoding="utf-8") as f:
        priv = f.read().strip()
    return Service(os.environ.get("RM_DB", "licenses.db"), priv, device_limit=int(os.environ.get("RM_DEVICE_LIMIT", "3")))


service = _make_service()
limiter = RateLimiter(limit=int(os.environ.get("RM_RATE_LIMIT", "30")), window=60.0)
WEBHOOK_SECRET = os.environ.get("RM_WEBHOOK_SECRET", "")
RK_PASS2 = os.environ.get("RM_ROBOKASSA_PASS2", "")
RK_ALGO = os.environ.get("RM_ROBOKASSA_ALGO", "md5").lower()
YK_SHOP = os.environ.get("RM_YOOKASSA_SHOP", "")
YK_SECRET = os.environ.get("RM_YOOKASSA_SECRET", "")
PRICE_YEAR = os.environ.get("RM_PRICE_YEAR", "")   # цена года; пусто: тариф «год» отключён
PRICE = os.environ.get("RM_PRICE", "")   # например 790.00; пусто: сумма не сверяется (не рекомендуется)
YK_IPS = [x.strip() for x in os.environ.get("RM_YOOKASSA_IPS", "").split(",") if x.strip()]   # список адресов задаёт владелец по документации
RETURN_URL = os.environ.get("RM_RETURN_URL", "")   # https-страница «Спасибо, ключ придёт на почту»
SMTP = (os.environ.get("RM_SMTP_HOST", ""), int(os.environ.get("RM_SMTP_PORT", "465")), os.environ.get("RM_SMTP_USER", ""),
        os.environ.get("RM_SMTP_PASS", ""), os.environ.get("RM_MAIL_FROM", ""))
TRUST_PROXY = os.environ.get("RM_TRUST_PROXY", "") == "1"   # включать только за своим обратным прокси

app = FastAPI(title="Radial Music licenses", docs_url=None, redoc_url=None, openapi_url=None)

SITE_ORIGIN = os.environ.get("RM_SITE_ORIGIN", "")   # https://адрес-сайта без слэша; пусто: CORS выключен
if SITE_ORIGIN:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=[SITE_ORIGIN], allow_methods=["POST"], allow_headers=["Content-Type"])


def _prices():
    """Цены планов для сверки суммы в вебхуке. Год включается только если задан RM_PRICE_YEAR."""
    d = {"month": PRICE}
    if PRICE_YEAR:
        d["year"] = PRICE_YEAR
    return d


class Req(BaseModel):
    key: str = Field(max_length=2000)
    device: str = Field(min_length=8, max_length=200)
    nonce: str = Field(default="", max_length=64)


def _ip(request: Request):
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "?"


def _limit(request: Request):
    if not limiter.allow(_ip(request), time.time()):
        raise HTTPException(status_code=429, detail="Слишком много запросов. Повтори позже.")


@app.get("/v1/health")
def health():
    return {"ok": True}


@app.post("/v1/activate")
def activate(body: Req, request: Request):
    _limit(request)
    return service.activate(body.key, body.device, body.nonce)


@app.post("/v1/check")
def check(body: Req, request: Request):
    _limit(request)
    return service.check(body.key, body.device, body.nonce)


@app.post("/v1/deactivate")
def deactivate(body: Req, request: Request):
    _limit(request)
    return service.deactivate(body.key, body.device, body.nonce)


@app.post("/v1/webhook/generic")
async def webhook_generic(request: Request, x_signature: str = Header(default="")):
    """Универсальное событие (HMAC-SHA256 тела общим секретом). Адаптеры ЮKassa и Robokassa не реализованы."""
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Слишком большой запрос")
    if not providers.verify_hmac(raw, x_signature, WEBHOOK_SECRET):
        log.warning("вебхук: неверная подпись с %s", _ip(request))
        raise HTTPException(status_code=401, detail="Неверная подпись")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Не JSON")
    res = service.handle_payment_event(event)
    log.info("вебхук: %s (payment %s)", res.get("action"), (event or {}).get("payment_id") if isinstance(event, dict) else "?")
    res.pop("key", None)   # ключ в ответ провайдеру не отдаём: покупателю его отправляет владелец (admin.py show), почта не реализована
    return res


def _send_pending():
    """Отправляет неотправленные ключи. Без настроенной почты ничего не делает (ключ тогда берёт владелец: admin.py show)."""
    if not SMTP[0] or not SMTP[4]:
        return 0, 0
    return mailer.deliver_pending(service, mailer.smtp_sender(*SMTP))


def _apply(event, ip, source):
    if event is None:
        log.warning("вебхук %s отклонён (%s)", source, ip)
        return None
    res = service.handle_payment_event(event)
    log.info("вебхук %s: %s (payment %s)", source, res.get("action"), event.get("payment_id"))
    try:
        _send_pending()   # также повторяет прежние неудачные отправки
    except Exception:
        log.exception("отправка ключей")
    return res


@app.api_route("/v1/webhook/robokassa", methods=["GET", "POST"])
async def webhook_robokassa(request: Request):
    """ResultURL Robokassa. Подпись по паролю №2 (RM_ROBOKASSA_PASS2). Ответ OK<InvId>. НЕ ЗАПУСКАЛСЯ."""
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Слишком большой запрос")
    params = dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True)) if raw else {}
    params.update(dict(request.query_params))
    event, answer = providers.robokassa_event(params, RK_PASS2, RK_ALGO, PRICE)
    if _apply(event, _ip(request), "robokassa") is None:
        return PlainTextResponse(answer, status_code=400)
    return PlainTextResponse(answer)


@app.post("/v1/webhook/yookassa")
async def webhook_yookassa(request: Request):
    """Уведомление ЮKassa. Тело не подписано, статус платежа перепроверяется запросом к API ЮKassa. НЕ ЗАПУСКАЛСЯ."""
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Слишком большой запрос")
    if not YK_SHOP or not YK_SECRET:
        raise HTTPException(status_code=503, detail="ЮKassa не настроена")
    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Не JSON")
    ip = _ip(request)
    fetch = providers.yookassa_http_fetch(YK_SHOP, YK_SECRET)
    trusted = (lambda x: x in YK_IPS) if YK_IPS else None
    event = await run_in_threadpool(providers.yookassa_event, body, fetch, _prices(), trusted, ip)
    if _apply(event, ip, "yookassa") is None:
        raise HTTPException(status_code=400, detail="Не подтверждено")
    return {"ok": True}


class Buy(BaseModel):
    email: str = Field(max_length=254)
    plan: str = Field(default="month", max_length=10)   # month | year


@app.post("/v1/buy")
async def buy(body: Buy, request: Request):
    """Создаёт платёж ЮKassa и отдаёт адрес оплаты. Ключ придёт на указанную почту после подтверждения оплаты. НЕ ЗАПУСКАЛСЯ."""
    _limit(request)
    if not (YK_SHOP and YK_SECRET and PRICE and RETURN_URL):
        raise HTTPException(status_code=503, detail="Оплата не настроена")
    email = body.email.strip()
    if not providers.valid_email(email):
        raise HTTPException(status_code=400, detail="Проверь адрес почты")
    import secrets
    amount = _prices().get(body.plan)
    if not amount:
        raise HTTPException(status_code=400, detail="Этот тариф недоступен")
    desc = "Radial Music Pro, " + ("год" if body.plan == "year" else "месяц")
    try:
        url, pid = await run_in_threadpool(providers.yookassa_create_payment, YK_SHOP, YK_SECRET, amount, email, RETURN_URL, secrets.token_urlsafe(24), desc, None, 10.0, body.plan)
    except Exception:
        log.exception("создание платежа")
        raise HTTPException(status_code=502, detail="Не удалось создать платёж, попробуй позже")
    log.info("создан платёж %s", pid)
    return {"url": url}
