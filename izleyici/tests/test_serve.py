"""serve.py testleri — ağ yok: sahte ölçüm enjeksiyonu, guard ve limit."""

import os
import sys
import unittest

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from izleyici import serve  # noqa: E402


def sahte_olc(domain):
    return {
        "domain": domain, "tarih": "2026-10-05", "ai_alinti_puani": 33.3,
        "alt_puanlar": {"erisim": {"puan": 100.0}},
        "siralama": {"sorgular": [{"sorgu": "q", "bulundu": False,
                                   "position": None}]},
    }


def temizle(yol):
    for f in (yol,):
        if os.path.exists(f):
            os.unlink(f)


class ServeTest(unittest.TestCase):
    def setUp(self):
        serve.LEADS_DOSYASI = os.path.join(
            serve.takip.IZLE_KOK, "tests_tmp", "leads-test.json")
        temizle(serve.LEADS_DOSYASI)
        self.client = TestClient(serve.create_app(olc_fn=sahte_olc,
                                                  gunluk_limit=2))

    def tearDown(self):
        temizle(serve.LEADS_DOSYASI)

    def test_landing_form_iceriyor(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("id=\"domain\"", r.text)
        self.assertIn("id=\"email\"", r.text)

    def test_uretesiz_rapor_calişiyor(self):
        r = self.client.post("/rapor", json={"domain": "example.com",
                                             "email": "a@b.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["puan"], 33.3)
        self.assertIn("ilk ölçüm", r.json()["rapor"])
        with open(serve.LEADS_DOSYASI, encoding="utf-8") as f:
            leads = __import__("json").load(f)
        self.assertEqual(leads[0]["domain"], "example.com")
        self.assertEqual(len(leads[0]["ip_hash"]), 16)  # ham IP saklanmaz

    def test_hiz_limiti(self):
        for _ in range(2):
            r = self.client.post("/rapor", json={"domain": "example.com",
                                                 "email": "a@b.com"})
            self.assertEqual(r.status_code, 200)
        r = self.client.post("/rapor", json={"domain": "example.com",
                                             "email": "a@b.com"})
        self.assertEqual(r.status_code, 429)

    def test_gecersiz_girdiler(self):
        for domain in ("../../etc/hosts", "example..com", ""):
            r = self.client.post("/rapor", json={"domain": domain,
                                                 "email": "a@b.com"})
            self.assertEqual(r.status_code, 400, domain)
        r = self.client.post("/rapor", json={"domain": "example.com",
                                             "email": "bozuk"})
        self.assertEqual(r.status_code, 400)

    def test_ip_literal_ve_ic_ag_reddi(self):
        for domain in ("127.0.0.1", "169.254.169.254", "10.0.0.1"):
            r = self.client.post("/rapor", json={"domain": domain,
                                                 "email": "a@b.com"})
            self.assertEqual(r.status_code, 400, domain)


if __name__ == "__main__":
    unittest.main()
