"""Проверка подписи входящих событий оплаты. Провайдер не выбран, поэтому здесь только общая схема HMAC-SHA256.

Адаптеры ЮKassa и Robokassa добавлены в подэтапе 5.5 (ниже).
Адаптер должен: 1) проверить подлинность запроса по документации провайдера, 2) привести событие к виду
{"type": "payment.succeeded"|"payment.refunded", "payment_id": ..., "email": ...} и вызвать Service.handle_payment_event.
"""
import hashlib
import hmac


def sign_hmac(body, secret):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_hmac(body, signature, secret):
    """Сравнение за постоянное время. Пустой секрет всегда отклоняется (защита от забытой настройки)."""
    if not secret or not isinstance(signature, str) or not isinstance(body, (bytes, bytearray)):
        return False
    return hmac.compare_digest(sign_hmac(bytes(body), secret), signature.strip().lower())


# ---------------------------------------------------------------------------------------------------------------
# Адаптеры провайдеров (подэтап 5.5). Документация сверена веб-поиском 26.10.2026; что именно не проверено, см. server/README.md.
# Оба адаптера чистые: сеть и секреты передаются снаружи, поэтому тестируются без FastAPI.
# ---------------------------------------------------------------------------------------------------------------
import re
from decimal import Decimal, InvalidOperation

ROBOKASSA_ALGOS = ("md5", "sha1", "sha256", "sha384", "sha512")   # какие методы Robokassa реально предлагает: НЕ ПРОВЕРЕНО полностью
_PID_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")


def _same_amount(got, expected):
    """Сумма как Decimal. expected пустой: сверка отключена (возвращает True). Мусор вместо числа: False."""
    if not expected:
        return True
    try:
        return Decimal(str(got).replace(",", ".")) == Decimal(str(expected).replace(",", "."))
    except (InvalidOperation, ValueError):
        return False


def _expected_for(expected, plan):
    """expected: строка (одна цена, как раньше) или словарь {"month": "199.00", "year": "1490.00"}.
    Возвращает (сумма_для_сверки, план|None). Словарь и неизвестный план: сумма None (отказ)."""
    if isinstance(expected, dict):
        if plan not in expected or not expected[plan]:
            return None, None
        return expected[plan], plan
    return expected, (plan if plan in ("month", "year") else None)


def robokassa_signature(params, password2, algo="md5"):
    """База подписи ResultURL: OutSum:InvId:Пароль#2 и далее пользовательские Shp_* в виде Shp_имя=значение,
    через двоеточие. Порядок Shp_* принят алфавитным по имени (в документации по найденным фрагментам не подтверждён: НЕ ПРОВЕРЕНО)."""
    if algo not in ROBOKASSA_ALGOS:
        raise ValueError("algo")
    parts = [str(params.get("OutSum", "")), str(params.get("InvId", "")), password2]
    parts += ["%s=%s" % (k, params[k]) for k in sorted(k for k in params if k.lower().startswith("shp_"))]
    return hashlib.new(algo, ":".join(parts).encode("utf-8")).hexdigest()


def robokassa_event(params, password2, algo="md5", expected_sum=""):
    """params: словарь параметров ResultURL (query или тело формы). Возвращает (event|None, ответ_для_провайдера).
    Ответ при успехе: OK<InvId>. Пустой пароль, нет подписи, неверная подпись, неверная сумма: event None."""
    if not password2 or not isinstance(params, dict):
        return None, "bad request"
    sig = str(params.get("SignatureValue", "")).strip().lower()
    inv = str(params.get("InvId", ""))
    if not sig or not inv or not _PID_RE.match(inv) or algo not in ROBOKASSA_ALGOS:
        return None, "bad request"
    if not hmac.compare_digest(robokassa_signature(params, password2, algo), sig):
        return None, "bad sign"
    if not _same_amount(params.get("OutSum"), expected_sum):
        return None, "bad sum"
    email = str(params.get("Shp_email", "")).strip()[:200]
    return {"type": "payment.succeeded", "payment_id": "rk-" + inv, "email": email}, "OK" + inv


def yookassa_event(body, fetch, expected_sum="", trusted_ip=None, client_ip=""):
    """ЮKassa не подписывает уведомления (по документации и описанию SDK), поэтому решение принимается по ответу API.
    body: разобранное тело (dict). fetch(kind, object_id) -> dict объекта из API ЮKassa (kind: payment|refund) или None.
    trusted_ip: функция ip->bool, если список адресов задан владельцем (он НЕ ПРОВЕРЕН и здесь не зашит).
    Возвращает event или None."""
    if trusted_ip is not None and not trusted_ip(client_ip):
        return None
    if not isinstance(body, dict) or body.get("type") != "notification" or not isinstance(body.get("object"), dict):
        return None
    ev, oid = body.get("event"), body["object"].get("id")
    if not isinstance(oid, str) or not _PID_RE.match(oid):
        return None
    if ev == "payment.succeeded":
        pay = fetch("payment", oid)
        if not isinstance(pay, dict) or pay.get("id") != oid or pay.get("status") != "succeeded" or pay.get("paid") is not True:
            return None
        meta0 = pay.get("metadata") if isinstance(pay.get("metadata"), dict) else {}
        expected_sum, plan = _expected_for(expected_sum, str(meta0.get("plan") or ""))
        if expected_sum is None or not _same_amount((pay.get("amount") or {}).get("value"), expected_sum):
            return None
        if expected_sum and (pay.get("amount") or {}).get("currency") not in (None, "RUB"):
            return None
        meta = pay.get("metadata") if isinstance(pay.get("metadata"), dict) else {}
        rc = pay.get("receipt") if isinstance(pay.get("receipt"), dict) else {}
        cust = rc.get("customer") if isinstance(rc.get("customer"), dict) else {}
        email = str(meta.get("email") or cust.get("email") or "").strip()[:200]   # пути полей НЕ ПРОВЕРЕНЫ по документации
        ev_out = {"type": "payment.succeeded", "payment_id": "yk-" + oid, "email": email}
        if plan:
            ev_out["plan"] = plan
        return ev_out
    if ev == "refund.succeeded":
        ref = fetch("refund", oid)
        if not isinstance(ref, dict) or ref.get("id") != oid or ref.get("status") != "succeeded":
            return None
        pid = ref.get("payment_id")
        if not isinstance(pid, str) or not _PID_RE.match(pid):
            return None
        return {"type": "payment.refunded", "payment_id": "yk-" + pid, "email": ""}
    return None


def yookassa_http_fetch(shop_id, secret_key, timeout=8.0):
    """Реальный запрос к API (Basic-авторизация магазина). НЕ ЗАПУСКАЛСЯ: сети нет. Адреса /v3/payments и /v3/refunds
    выведены из примера /v3/webhooks в документации и НЕ ПРОВЕРЕНЫ отдельно."""
    import base64, json, urllib.request
    auth = base64.b64encode(("%s:%s" % (shop_id, secret_key)).encode()).decode()
    paths = {"payment": "payments", "refund": "refunds"}

    def fetch(kind, oid):
        if kind not in paths or not _PID_RE.match(oid or ""):
            return None
        req = urllib.request.Request("https://api.yookassa.ru/v3/%s/%s" % (paths[kind], oid),
                                     headers={"Authorization": "Basic " + auth})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read(200_000).decode("utf-8"))
        except Exception:
            return None
    return fetch


def robokassa_pay_url(login, password1, out_sum, inv_id, email="", algo="md5", description="Radial Music Pro", test=False):
    """Ссылка на оплату по документации «Интерфейс оплаты»: подпись MerchantLogin:OutSum:InvId:Пароль#1[:Shp_*].
    Чек (Receipt) и прочие модификаторы подписи НЕ поддержаны: если в кабинете включена фискализация, нужна доработка (НЕ ПРОВЕРЕНО).
    Адрес https://auth.robokassa.ru/Merchant/Index.aspx взят из документации; параметр IsTest для тестового режима НЕ ПРОВЕРЕН."""
    from urllib.parse import urlencode
    if algo not in ROBOKASSA_ALGOS or not login or not password1 or not _PID_RE.match(str(inv_id)):
        raise ValueError("параметры")
    parts = [login, str(out_sum), str(inv_id), password1]
    q = {"MerchantLogin": login, "OutSum": str(out_sum), "InvId": str(inv_id), "Description": description}
    if email:
        parts.append("Shp_email=%s" % email)
        q["Shp_email"] = email
    q["SignatureValue"] = hashlib.new(algo, ":".join(parts).encode("utf-8")).hexdigest()
    if test:
        q["IsTest"] = "1"
    return "https://auth.robokassa.ru/Merchant/Index.aspx?" + urlencode(q)


def valid_email(s):
    return isinstance(s, str) and len(s) <= 254 and re.match(r"^[^@\s<>\"',;]{1,64}@[^@\s<>\"',;]{1,190}\.[^@\s<>\"',;]{2,}$", s) is not None


def yookassa_create_payment(shop_id, secret_key, amount, email, return_url, idem_key, description="Radial Music Pro", post=None, timeout=10.0, plan=None):
    """Создаёт платёж (схема запроса сверена с документацией ЮKassa 26.10.2026: amount, capture, confirmation.redirect, description,
    metadata, заголовок Idempotence-Key). Почта кладётся в metadata.email и потом читается yookassa_event.
    Объект receipt (чек 54-ФЗ) НЕ передаётся: для самозанятого чек формируется в «Мой налог», как ЮKassa принимает такой запрос без receipt, НЕ ПРОВЕРЕНО.
    post(url, headers, payload) -> dict подставляется в тестах. Возвращает (confirmation_url, payment_id) или бросает ValueError."""
    if not valid_email(email) or not return_url.startswith("https://") or not re.match(r"^[0-9A-Za-z_-]{8,64}$", idem_key or ""):
        raise ValueError("параметры")
    try:
        if Decimal(str(amount)) <= 0:
            raise ValueError("сумма")
    except InvalidOperation:
        raise ValueError("сумма")
    payload = {"amount": {"value": "%.2f" % Decimal(str(amount)), "currency": "RUB"}, "capture": True,
               "confirmation": {"type": "redirect", "return_url": return_url},
               "description": description, "metadata": ({"email": email, "plan": plan} if plan else {"email": email})}
    if post is None:
        post = lambda u, h, pl: _http_post_json(u, h, pl, timeout)
    import base64
    headers = {"Authorization": "Basic " + base64.b64encode(("%s:%s" % (shop_id, secret_key)).encode()).decode(),
               "Idempotence-Key": idem_key, "Content-Type": "application/json"}
    obj = post("https://api.yookassa.ru/v3/payments", headers, payload)
    conf = obj.get("confirmation") if isinstance(obj, dict) else None
    url = conf.get("confirmation_url") if isinstance(conf, dict) else None
    pid = obj.get("id") if isinstance(obj, dict) else None
    if not isinstance(url, str) or not url.startswith("https://") or not isinstance(pid, str) or not _PID_RE.match(pid):
        raise ValueError("ответ")
    return url, pid


def _http_post_json(url, headers, payload, timeout=10.0):
    import json, urllib.request
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(200_000).decode("utf-8"))
