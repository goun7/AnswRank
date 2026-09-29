"""Net-kar buyback kurali testleri ( DCBM Solvency Actuator).

KANIT komutu:
  cd /home/gokun/projects/02_sahis/85-AnswRank
  .venv/bin/python -m pytest tests/test_net_kar_buyback.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from answrank.finance.net_kar_buyback import (  # noqa: E402
    BuybackHesaplayici, ServisGelirKaydi)


class TestNetKarKurali:
    """KURAL: buyback SADECE net kar ile ( brut DEGIL)."""

    def test_net_kar_hesabi_dogru(self):
        """net_kar = brut - ( llm + api + altyapi + transfer)."""
        k = ServisGelirKaydi(
            servis="answrank",
            brut_gelir_usd=1.20,
            llm_maliyet_usd=0.36,
            api_maliyet_usd=0.0,
            altyapi_maliyet_usd=0.01,
            gelir_transferi_usd=0.02,
        )
        assert k.net_kar_usd == pytest.approx(0.81)
        assert k.toplam_maliyet_usd == pytest.approx(0.39)

    def test_buyback_net_kari_asamaz(self):
        """En kritik kural: buyback <= net_kar."""
        k = ServisGelirKaydi(servis="x", brut_gelir_usd=10.0,
                             llm_maliyet_usd=2.0, altyapi_maliyet_usd=0.01)
        sonuc = BuybackHesaplayici.hesapla([k])
        o = sonuc["oneriler"][0]
        assert o.izin_verilen_buyback_usd <= o.net_kar_usd
        assert o.izin_verilen_buyback_usd > 0
        assert not o.reddedildi

    def test_negatif_net_kar_buyback_yok(self):
        """Zarar eden servis buyback YAPAMAZ ( iflas-korumasi)."""
        k = ServisGelirKaydi(servis="zarar", brut_gelir_usd=0.10,
                             llm_maliyet_usd=0.50)
        assert k.net_kar_usd < 0
        sonuc = BuybackHesaplayici.hesapla([k])
        o = sonuc["oneriler"][0]
        assert o.izin_verilen_buyback_usd == 0.0
        assert o.reddedildi is True
        assert "net-kar <= 0" in (o.red_nedeni or "")

    def test_sifir_net_kar_da_reddedilir(self):
        """Sifir net kar = buyback yok ( sinir durumu)."""
        k = ServisGelirKaydi(servis="sifir", brut_gelir_usd=1.0,
                             llm_maliyet_usd=1.0)
        sonuc = BuybackHesaplayici.hesapla([k])
        assert sonuc["oneriler"][0].reddedildi is True

    def test_brut_kar_buyback_olamaz(self):
        """KULLANICI KURALI: brut-kar yakma YASAK.

        Eger algoritma brut geliri alip maliyetleri cikarmasaydi,
        buyback 10.0 olurdu ( brut) — ama dogru deger net kardir.
        """
        k = ServisGelirKaydi(servis="yanlis", brut_gelir_usd=10.0,
                             llm_maliyet_usd=8.0, altyapi_maliyet_usd=0.01)
        sonuc = BuybackHesaplayici.hesapla([k])
        o = sonuc["oneriler"][0]
        # brut 10.0 ama net ~1.99 -> buyback <= 1.99*0.5 ~ 1.0
        assert o.izin_verilen_buyback_usd < k.brut_gelir_usd
        assert o.izin_verilen_buyback_usd < o.net_kar_usd + 0.01

    def test_static_yuzde_kural_degil(self):
        """'%4.8' gibi STATIC yuzde YOK — rezerv bir EMNIYET payidir.

        DCBM ( arXiv:2601.09961) static heuristics'i elestirir
        ( bang-bang kontrol -> salinim). Rezerv_orani bir sabit-kural
        degil, emniyet marjidir; buyback yine de NET KAR ile sinirlidir.
        """
        k1 = ServisGelirKaydi(servis="a", brut_gelir_usd=10.0, llm_maliyet_usd=1.0)
        k2 = ServisGelirKaydi(servis="b", brut_gelir_usd=20.0, llm_maliyet_usd=15.0)
        sonuc = BuybackHesaplayici.hesapla([k1, k2])
        o1, o2 = sonuc["oneriler"]
        # buyback'ler gelirle ORANTILI degil, NET KAR ile orantili
        assert o2.izin_verilen_buyback_usd < o1.izin_verilen_buyback_usd, \
            "k2'nin geliri fazla ama net kari az -> buyback'i az olmali"
        assert sonuc["rezerv_orani"] == 0.5

    def test_toplamlar_tutarli(self):
        """Toplam izin verilen <= toplam net kar."""
        kayitlar = [
            ServisGelirKaydi(servis="a", brut_gelir_usd=5.0, llm_maliyet_usd=1.0),
            ServisGelirKaydi(servis="b", brut_gelir_usd=3.0, llm_maliyet_usd=0.5),
        ]
        sonuc = BuybackHesaplayici.hesapla(kayitlar)
        assert sonuc["toplam_izin_verilen_buyback_usd"] <= \
            sonuc["toplam_net_kar_usd"]
        assert sonuc["toplam_net_kar_usd"] == pytest.approx(6.49, abs=0.01)

    def test_emniyet_payi_uygulanir(self):
        """DCBM gamma: buyback net karanin TAMAMI olamaz."""
        k = ServisGelirKaydi(servis="x", brut_gelir_usd=100.0,
                             llm_maliyet_usd=0.0, altyapi_maliyet_usd=0.0)
        sonuc = BuybackHesaplayici.hesapla([k], rezerv_orani=0.5)
        o = sonuc["oneriler"][0]
        assert o.izin_verilen_buyback_usd < o.net_kar_usd
        assert o.izin_verilen_buyback_usd == pytest.approx(50.0)

    def test_kar_zarar_karisik(self):
        """Portföyde zarar eden olsa bile kar edenler buyback yapabilir."""
        kayitlar = [
            ServisGelirKaydi(servis="kar", brut_gelir_usd=10.0, altyapi_maliyet_usd=0.01),
            ServisGelirKaydi(servis="zarar", brut_gelir_usd=0.5, llm_maliyet_usd=5.0),
        ]
        sonuc = BuybackHesaplayici.hesapla(kayitlar)
        kar_o = next(o for o in sonuc["oneriler"] if o.servis == "kar")
        zarar_o = next(o for o in sonuc["oneriler"] if o.servis == "zarar")
        assert kar_o.izin_verilen_buyback_usd > 0
        assert zarar_o.izin_verilen_buyback_usd == 0.0
        # toplam: sadece kar eden katki saglar
        assert sonuc["toplam_izin_verilen_buyback_usd"] == pytest.approx(
            kar_o.izin_verilen_buyback_usd)
