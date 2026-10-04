"""Ağsız birim testler: takip listesi, delta hesabı, rapor üretimi."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)  # ai_gorunurluk + izleyici import edilebilsin

from izleyici import delta, takip  # noqa: E402


def snap(tarih, puan, sorgular=None, alt=None):
    return {
        "domain": "example.com",
        "tarih": tarih,
        "ai_alinti_puani": puan,
        "alt_puanlar": alt or {
            "erisim": {"puan": 50.0}, "icerik": {"puan": 40.0},
            "rekabet": {"puan": 20.0}, "siralama": {"puan": 30.0},
        },
        "siralama": {"sorgular": sorgular or []},
    }


class TakipTest(unittest.TestCase):
    def setUp(self):
        # izleyici kökü İÇİNDE geçici dosya — kaydet/yukle kapsama policy'si
        os.makedirs(os.path.join(takip.IZLE_KOK, "tests_tmp"), exist_ok=True)
        self.yol = os.path.join(takip.IZLE_KOK, "tests_tmp", "takip-test.json")

    def tearDown(self):
        if os.path.exists(self.yol):
            os.unlink(self.yol)

    def test_ekle_liste_cikar(self):
        takip.ekle("https://www.Example.com/duzenle", yol=self.yol)
        t = takip.yukle(self.yol)
        self.assertIn("example.com", t)  # normalizasyon: şema/www/yol atılır
        takip.ekle("example.com", sorgular=["a", "b", "a"], yol=self.yol)
        t = takip.yukle(self.yol)
        self.assertEqual(t["example.com"]["sorgular"], ["a", "b"])  # tekilleşti
        self.assertTrue(takip.cikar("example.com", yol=self.yol))
        self.assertFalse(takip.cikar("example.com", yol=self.yol))

    def test_gecersiz_domain_reddedilir(self):
        for kotu in ("../../etc/hosts", "..", "example..com",
                     "exa mple.com", ""):
            with self.assertRaises(ValueError):
                takip.ekle(kotu, yol=self.yol)

    def test_yol_kismi_atilir_dolayisiyla_traversal_olmez(self):
        # "example.com/../x" -> "example.com": URL yolu disk yoluna
        # ASLA taşınmaz; domain regex'i geçtikten sonra yol-elemanı
        # olarak tek segment kullanılır + kapsamda() iddiası vardır.
        takip.ekle("example.com/../x", yol=self.yol)
        self.assertIn("example.com", takip.yukle(self.yol))

    def test_kapsama_disi_yol_reddedilir(self):
        with self.assertRaises(ValueError):
            takip.kaydet({}, yol="/tmp/a11y-izleyici-evil.json")
        with self.assertRaises(ValueError):
            takip.kaydet({}, yol=os.path.join(takip.IZLE_KOK, "../../x.json"))

    def test_gecersiz_tarih_reddedilir(self):
        from izleyici import kosu
        with self.assertRaises(ValueError):
            kosu.snapshot_yolu("example.com", "../../2026-evil")
        with self.assertRaises(ValueError):
            kosu.snapshot_yolu("../../etc/hosts")


class DeltaTest(unittest.TestCase):
    def test_ilk_olcum_taban_cizgisi(self):
        yeni = snap("2026-10-05", 42.0, [{"sorgu": "q", "bulundu": True,
                                          "position": 3}])
        d = delta.hesapla(None, yeni)
        self.assertTrue(d["ilk_olcum"])
        self.assertIsNone(d["puan"]["eski"])
        self.assertIsNone(d["puan"]["degisim"])

    def test_puan_ve_alt_puan_degisimi(self):
        eski = snap("2026-10-04", 34.2)
        yeni = snap("2026-10-05", 41.0,
                    alt={"erisim": {"puan": 50.0},
                         "icerik": {"puan": 60.0},
                         "rekabet": {"puan": 20.0},
                         "siralama": {"puan": 45.0}})
        d = delta.hesapla(eski, yeni)
        self.assertAlmostEqual(d["puan"]["degisim"], 6.8)
        self.assertAlmostEqual(d["alt_puanlar"]["icerik"]["degisim"], 20.0)

    def test_sorgu_olaylari(self):
        eski = snap("2026-10-04", 30.0, [
            {"sorgu": "girdi", "bulundu": False, "position": None},
            {"sorgu": "dustu", "bulundu": True, "position": 4},
            {"sorgu": "iyilesti", "bulundu": True, "position": 9},
            {"sorgu": "kotulesti", "bulundu": True, "position": 2},
            {"sorgu": "sabit", "bulundu": True, "position": 5},
        ])
        yeni = snap("2026-10-05", 30.0, [
            {"sorgu": "girdi", "bulundu": True, "position": 7},
            {"sorgu": "dustu", "bulundu": False, "position": None},
            {"sorgu": "iyilesti", "bulundu": True, "position": 3},
            {"sorgu": "kotulesti", "bulundu": True, "position": 6},
            {"sorgu": "sabit", "bulundu": True, "position": 5},
        ])
        d = delta.hesapla(eski, yeni)
        olaylar = {o["sorgu"]: o["olay"] for o in d["olaylar"]}
        self.assertEqual(olaylar, {
            "girdi": "girdi", "dustu": "dustu",
            "iyilesti": "iyilesti", "kotulesti": "kotulesti"})

    def test_rapor_md_insana_uretiliyor(self):
        eski = snap("2026-10-04", 34.2, [
            {"sorgu": "dental implants dubai", "bulundu": False,
             "position": None}])
        yeni = snap("2026-10-05", 41.0, [
            {"sorgu": "dental implants dubai", "bulundu": True,
             "position": 4}])
        md = delta.rapor_md(eski, yeni)
        self.assertIn("34.2 → 41.0 (+6.8)", md)
        self.assertIn("★ ilk 10'a girdi", md)
        self.assertIn("| Alt puan | Önce | Sonra | Δ |", md)

    def test_bosuna_yesil_yok(self):
        # eski snapshot'taki bulgular yeni snapshot'ta SİLİNSE de
        # delta bunu olay olarak yazmalı — sessiz yeşil yasak.
        eski = snap("2026-10-04", 30.0, [
            {"sorgu": "kritik sorgu", "bulundu": True, "position": 2}])
        yeni = snap("2026-10-05", 30.0, [
            {"sorgu": "kritik sorgu", "bulundu": False, "position": None}])
        d = delta.hesapla(eski, yeni)
        self.assertEqual(d["olaylar"][0]["olay"], "dustu")


if __name__ == "__main__":
    unittest.main()
