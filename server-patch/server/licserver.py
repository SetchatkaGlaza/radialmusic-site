"""Ядро сервера лицензий Radial Music (1.0.17). Без веб-фреймворка: sqlite3 + cryptography. Всё покрыто тестами.

Что делает: выдаёт подписанные ключи (формат совместим с licensing.verify клиента), ведёт активации по устройствам,
проверяет и отзывает ключи, обрабатывает события оплаты (идемпотентно), подписывает ответы, чтобы клиент не верил
поддельному серверу. Устройство хранится как sha256 от идентификатора, который прислал клиент.
Отправка ключей: pending_mail/mark_mailed (сама отправка в mailer.py). Адаптеры платежей: providers.py.
"""
import base64
import hashlib
import json
import re
import sqlite3
import threading
import time
from functools import wraps
from datetime import date, datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DEFAULT_DEVICE_LIMIT = 3
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

MESSAGES = {
    "ok": "Лицензия действует.",
    "revoked": "Лицензия отозвана.",
    "expired": "Срок лицензии истёк.",
    "device_limit": "Достигнут предел устройств для этого ключа. Освободи устройство или напиши в поддержку.",
    "not_activated": "Это устройство не активировано. Введи ключ в настройках.",
    "invalid_key": "Ключ не найден или повреждён.",
    "bad_request": "Некорректный запрос.",
}


PLAN_DAYS = {"month": 31, "year": 366}   # срок ключа после разовой оплаты плана (запас в день)


def b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _locked(f):
    @wraps(f)
    def w(self, *a, **kw):
        with self._lock:                 # одно соединение SQLite и явные транзакции: запросы идут по одному
            return f(self, *a, **kw)
    return w


def device_hash(device):
    return hashlib.sha256(device.encode("utf-8")).hexdigest()


def valid_device(device):
    return isinstance(device, str) and 8 <= len(device) <= 200 and device.isprintable()


class RateLimiter:
    """Скользящее окно: не больше limit запросов за window секунд на ключ (например, IP)."""

    def __init__(self, limit=30, window=60.0, max_keys=10000):
        self.limit, self.window, self.max_keys = limit, window, max_keys
        self.hits = {}

    def allow(self, key, now):
        q = [t for t in self.hits.get(key, ()) if now - t < self.window]
        if len(q) >= self.limit:
            self.hits[key] = q
            return False
        q.append(now)
        self.hits[key] = q
        if len(self.hits) > self.max_keys:                       # защита памяти: выбрасываем самые старые ключи
            for k in sorted(self.hits, key=lambda x: self.hits[x][-1])[: self.max_keys // 10]:
                self.hits.pop(k, None)
        return True


class Service:
    def __init__(self, db_path, private_key_b64, device_limit=DEFAULT_DEVICE_LIMIT, now=time.time):
        self._lock = threading.RLock()
        self.now = now
        self.device_limit = device_limit
        self._priv = Ed25519PrivateKey.from_private_bytes(b64d(private_key_b64.strip()))
        self.public_b64 = b64(self._priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        self.db = sqlite3.connect(db_path, isolation_level=None, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS licenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, key TEXT NOT NULL DEFAULT '',
                issued INTEGER NOT NULL, expires TEXT, revoked INTEGER NOT NULL DEFAULT 0,
                payment_id TEXT UNIQUE, device_limit INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS activations(
                license_id INTEGER NOT NULL REFERENCES licenses(id), device TEXT NOT NULL,
                first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL, PRIMARY KEY(license_id, device));
            CREATE TABLE IF NOT EXISTS payments(payment_id TEXT PRIMARY KEY, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS mailed(license_id INTEGER PRIMARY KEY, ts INTEGER NOT NULL);
        """)

    # ---------- ключи ----------
    @staticmethod
    def new_private_key():
        return b64(Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))

    def _sign_key(self, payload):
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        return b64(raw) + "." + b64(self._priv.sign(raw))

    @_locked
    def issue(self, email, payment_id=None, expires=None, devices=None, note=""):
        """Выдаёт ключ. Повторный вызов с тем же payment_id возвращает тот же ключ (идемпотентность).
        Возвращает (ключ, создан_ли_новый). Бросает ValueError при неверных данных."""
        email = (email or "").strip()
        if not EMAIL_RE.match(email):
            raise ValueError("Некорректный адрес почты")
        if expires:
            try:
                date.fromisoformat(expires)
            except (TypeError, ValueError):
                raise ValueError("Срок должен быть в виде ГГГГ-ММ-ДД")
        devices = int(devices or self.device_limit)
        if not 1 <= devices <= 10:
            raise ValueError("Число устройств от 1 до 10")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if payment_id:
                row = self.db.execute("SELECT key FROM licenses WHERE payment_id=?", (payment_id,)).fetchone()
                if row:
                    self.db.execute("COMMIT")
                    return row["key"], False
                p = self.db.execute("SELECT status FROM payments WHERE payment_id=?", (payment_id,)).fetchone()
                if p and p["status"] == "refunded":
                    raise ValueError("Платёж уже возвращён")
            ts = int(self.now())
            cur = self.db.execute("INSERT INTO licenses(email, issued, expires, payment_id, device_limit, note) VALUES(?,?,?,?,?,?)",
                                  (email, ts, expires, payment_id, devices, note[:200]))
            lid = cur.lastrowid
            key = self._sign_key({"v": 1, "tier": "pro", "email": email, "lid": lid,
                                  "issued": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), "expires": expires})
            self.db.execute("UPDATE licenses SET key=? WHERE id=?", (key, lid))
            if payment_id:
                self.db.execute("INSERT OR REPLACE INTO payments(payment_id, status) VALUES(?, 'paid')", (payment_id,))
            self.db.execute("COMMIT")
            return key, True
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _parse_key(self, key):
        """Возвращает строку лицензии или None, если подпись неверна или ключа нет в базе."""
        try:
            body, sig = key.strip().split(".")
            raw = b64d(body)
            Ed25519PublicKey.from_public_bytes(b64d(self.public_b64)).verify(b64d(sig), raw)
            lid = int(json.loads(raw)["lid"])
        except (InvalidSignature, ValueError, KeyError, TypeError, AttributeError):
            return None
        row = self.db.execute("SELECT * FROM licenses WHERE id=?", (lid,)).fetchone()
        return row if row and row["key"] == key.strip() else None

    # ---------- ответы ----------
    def _reply(self, status, nonce="", **extra):
        payload = {"v": 1, "status": status, "ts": int(self.now()), "nonce": (nonce or "")[:64], **extra}
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        return {"status": status, "message": MESSAGES.get(status, ""), "payload": b64(raw), "sig": b64(self._priv.sign(raw)),
                **{k: v for k, v in extra.items()}}

    def _status_of(self, row):
        if row["revoked"]:
            return "revoked"
        if row["expires"]:
            try:
                if date.fromisoformat(row["expires"]) < datetime.fromtimestamp(self.now(), timezone.utc).date():
                    return "expired"
            except ValueError:
                return "expired"
        return "ok"

    def _count(self, lid):
        return self.db.execute("SELECT COUNT(*) c FROM activations WHERE license_id=?", (lid,)).fetchone()["c"]

    # ---------- операции клиента ----------
    def activate(self, key, device, nonce=""):
        return self._touch(key, device, nonce, add=True)

    def check(self, key, device, nonce=""):
        return self._touch(key, device, nonce, add=False)

    @_locked
    def _touch(self, key, device, nonce, add):
        if not isinstance(key, str) or not valid_device(device):
            return self._reply("bad_request", nonce)
        row = self._parse_key(key)
        if row is None:
            return self._reply("invalid_key", nonce)
        st = self._status_of(row)
        if st != "ok":
            return self._reply(st, nonce, lid=row["id"])
        dev, ts = device_hash(device), int(self.now())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            have = self.db.execute("SELECT 1 FROM activations WHERE license_id=? AND device=?", (row["id"], dev)).fetchone()
            if have:
                self.db.execute("UPDATE activations SET last_seen=? WHERE license_id=? AND device=?", (ts, row["id"], dev))
            elif not add:
                self.db.execute("COMMIT")
                return self._reply("not_activated", nonce, lid=row["id"])
            elif self._count(row["id"]) >= row["device_limit"]:
                self.db.execute("COMMIT")
                return self._reply("device_limit", nonce, lid=row["id"], limit=row["device_limit"])
            else:
                self.db.execute("INSERT INTO activations VALUES(?,?,?,?)", (row["id"], dev, ts, ts))
            n = self._count(row["id"])
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return self._reply("ok", nonce, lid=row["id"], devices=n, limit=row["device_limit"], expires=row["expires"])

    @_locked
    def deactivate(self, key, device, nonce=""):
        if not isinstance(key, str) or not valid_device(device):
            return self._reply("bad_request", nonce)
        row = self._parse_key(key)
        if row is None:
            return self._reply("invalid_key", nonce)
        self.db.execute("DELETE FROM activations WHERE license_id=? AND device=?", (row["id"], device_hash(device)))
        return self._reply("ok", nonce, lid=row["id"], devices=self._count(row["id"]), limit=row["device_limit"])

    # ---------- администрирование ----------
    def _find(self, ref):
        """ref: номер, почта или ключ. Возвращает список строк."""
        ref = str(ref).strip()
        if ref.isdigit():
            rows = self.db.execute("SELECT * FROM licenses WHERE id=?", (int(ref),)).fetchall()
        elif "@" in ref:
            rows = self.db.execute("SELECT * FROM licenses WHERE email=?", (ref,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM licenses WHERE key=?", (ref,)).fetchall()
        return rows

    @_locked
    def set_revoked(self, ref, revoked=True):
        rows = self._find(ref)
        for r in rows:
            self.db.execute("UPDATE licenses SET revoked=? WHERE id=?", (1 if revoked else 0, r["id"]))
        return len(rows)

    @_locked
    def release_devices(self, ref):
        rows = self._find(ref)
        for r in rows:
            self.db.execute("DELETE FROM activations WHERE license_id=?", (r["id"],))
        return len(rows)

    @_locked
    def list_licenses(self):
        out = []
        for r in self.db.execute("SELECT * FROM licenses ORDER BY id").fetchall():
            out.append({"id": r["id"], "email": r["email"], "status": self._status_of(r), "devices": self._count(r["id"]),
                        "limit": r["device_limit"], "expires": r["expires"], "payment_id": r["payment_id"]})
        return out

    # ---------- отправка ключей ----------
    @_locked
    def pending_mail(self):
        """Лицензии, купленные через оплату (есть payment_id), не отозванные и ещё без отметки об отправке."""
        rows = self.db.execute("SELECT id, email, key FROM licenses WHERE payment_id IS NOT NULL AND revoked=0 "
                               "AND id NOT IN (SELECT license_id FROM mailed) ORDER BY id").fetchall()
        return [(r["id"], r["email"], r["key"]) for r in rows]

    @_locked
    def mark_mailed(self, lid):
        self.db.execute("INSERT OR REPLACE INTO mailed(license_id, ts) VALUES(?, ?)", (int(lid), int(self.now())))

    # ---------- платежи ----------
    @_locked
    def handle_payment_event(self, event):
        """Универсальное событие оплаты (после проверки подписи адаптером провайдера):
        {"type": "payment.succeeded"|"payment.refunded", "payment_id": "...", "email": "..."}.
        Идемпотентно. Возвращает словарь с action: issued | duplicate | revoked | ignored | error."""
        if not isinstance(event, dict) or not isinstance(event.get("payment_id"), str) or not event["payment_id"]:
            return {"action": "error", "message": "Нет payment_id"}
        pid, typ = event["payment_id"][:100], event.get("type")
        if typ == "payment.succeeded":
            try:
                days = PLAN_DAYS.get(event.get("plan"))   # без плана: как раньше, без срока
                exp = (datetime.fromtimestamp(self.now(), timezone.utc).date() + timedelta(days=days)).isoformat() if days else None
                key, new = self.issue(event.get("email"), payment_id=pid, expires=exp)
            except ValueError as e:
                return {"action": "error", "message": str(e)}
            return {"action": "issued" if new else "duplicate", "key": key, "email": event.get("email")}
        if typ == "payment.refunded":
            self.db.execute("INSERT OR REPLACE INTO payments(payment_id, status) VALUES(?, 'refunded')", (pid,))
            cur = self.db.execute("UPDATE licenses SET revoked=1 WHERE payment_id=?", (pid,))
            return {"action": "revoked", "count": cur.rowcount}
        return {"action": "ignored"}
