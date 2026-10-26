import datetime, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
import providers
from licserver import Service


def _body(pid="pay_1"):
    return {"type": "notification", "event": "payment.succeeded", "object": {"id": pid}}


def _fetch(amount, plan, pid="pay_1"):
    return lambda kind, oid: {"id": pid, "status": "succeeded", "paid": True,
                              "amount": {"value": amount, "currency": "RUB"}, "metadata": {"email": "a@b.ru", "plan": plan}}


PRICES = {"month": "199.00", "year": "1490.00"}


class Plans(unittest.TestCase):
    def test_month_ok(self):
        ev = providers.yookassa_event(_body(), _fetch("199.00", "month"), PRICES)
        self.assertEqual(ev["plan"], "month")

    def test_year_ok(self):
        ev = providers.yookassa_event(_body(), _fetch("1490.00", "year"), PRICES)
        self.assertEqual(ev["plan"], "year")

    def test_year_paid_with_month_sum_rejected(self):
        self.assertIsNone(providers.yookassa_event(_body(), _fetch("199.00", "year"), PRICES))

    def test_unknown_plan_rejected(self):
        self.assertIsNone(providers.yookassa_event(_body(), _fetch("199.00", "forever"), PRICES))

    def test_year_disabled(self):
        self.assertIsNone(providers.yookassa_event(_body(), _fetch("1490.00", "year"), {"month": "199.00"}))

    def test_legacy_single_price(self):
        ev = providers.yookassa_event(_body(), _fetch("790.00", ""), "790.00")
        self.assertNotIn("plan", ev)

    def test_expiry_dates(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        priv = Service.new_private_key()
        now = datetime.datetime(2026, 10, 26, tzinfo=datetime.timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as d:
            sv = Service(os.path.join(d, "t.db"), priv, now=lambda: now)
            sv.handle_payment_event({"type": "payment.succeeded", "payment_id": "m1", "email": "a@b.ru", "plan": "month"})
            sv.handle_payment_event({"type": "payment.succeeded", "payment_id": "y1", "email": "c@d.ru", "plan": "year"})
            sv.handle_payment_event({"type": "payment.succeeded", "payment_id": "o1", "email": "e@f.ru"})
            exp = {r["payment_id"]: r["expires"] for r in sv.list_licenses()}
            self.assertEqual(exp["m1"], "2026-11-26")
            self.assertEqual(exp["y1"], "2027-10-27")
            self.assertIsNone(exp["o1"])


if __name__ == "__main__":
    unittest.main()
