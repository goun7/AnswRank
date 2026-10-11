"""answrank.mcp.server dal-kesen testleri (LEED) — 1 fonksiyon.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — ag/MCP-sunucu YOK, sadece statik dogrulama fonksiyonu.
AnswRankMCPServer._require.
"""
import pytest

from answrank.mcp.server import AnswRankMCPServer as S


# == _require ===============================================================================

def test_require_tum_alanlar_var_hata_yok():
    S._require({"brand": "x", "domain": "y.com"}, "brand", "domain")


def test_require_tek_alan_var():
    S._require({"domain": "y.com"}, "domain")


def test_require_bos_isim_listesi():
    """ORTAM: hic isim verilmisse missing=bos liste -> hata YOK."""
    S._require({"a": 1})


def test_require_tek_eksik_valueerror():
    with pytest.raises(ValueError) as exc:
        S._require({"domain": "y.com"}, "brand")
    assert "brand" in str(exc.value)


def test_require_cok_eksik_valueerror():
    with pytest.raises(ValueError) as exc:
        S._require({}, "brand", "domain", "sector")
    msg = str(exc.value)
    assert "brand" in msg and "domain" in msg and "sector" in msg


def test_require_mesaj_formati_missing_required():
    """ORTAM: 'missing required argument(s):' friendly baslik (KeyError degil)."""
    with pytest.raises(ValueError) as exc:
        S._require({}, "brand")
    assert "missing required argument(s)" in str(exc.value)


def test_require_mesaj_saglanan_anahtarlar():
    """ORTAM: provided keys listelenir — istemci ne gonderdigini gorur."""
    with pytest.raises(ValueError) as exc:
        S._require({"domain": "y.com", "city": "z"}, "brand")
    assert "domain" in str(exc.value)
    assert "city" in str(exc.value)


def test_require_mesaj_saglanan_yoksa_none():
    with pytest.raises(ValueError) as exc:
        S._require({}, "brand")
    assert "none" in str(exc.value)


def test_require_eksik_tek_tirnak_icinde():
    """ORTAM: her eksik isim '...' icinde gosterilir."""
    with pytest.raises(ValueError) as exc:
        S._require({}, "brand", "domain")
    assert "'brand'" in str(exc.value)
    assert "'domain'" in str(exc.value)


def test_require_arguman_dict_degil_valueerror():
    with pytest.raises(ValueError) as exc:
        S._require(["brand"], "brand")
    assert "arguments must be an object" in str(exc.value)


@pytest.mark.parametrize("bad", [["a"], ("a",), "brand", 42, None, {1, 2}])
def test_require_dikti_olmayan_tip(bad):
    """ORTAM: isinstance(arguments, dict) kontrolu — liste/tuple/str/int/None/set."""
    with pytest.raises(ValueError) as exc:
        S._require(bad, "brand")
    assert "must be an object" in str(exc.value)


def test_require_tip_mesajinda_tip_adi():
    with pytest.raises(ValueError) as exc:
        S._require(42, "brand")
    assert "int" in str(exc.value)


def test_require_none_deger_olsa_da_var_sayilir():
    """ORTAM: 'in' kontrolu yapilir — deger None bile anahtar varsa gecer."""
    S._require({"brand": None}, "brand")


def test_require_bos_string_deger_gecerli():
    S._require({"brand": ""}, "brand")


def test_require_ekstra_anahtarlar_sorun_degil():
    S._require({"brand": "x", "domain": "y.com", "fazla": 1}, "brand", "domain")


def test_require_isim_tekrari_hata_yok():
    S._require({"brand": "x"}, "brand", "brand")


def test_require_eksik_ilki_degil_ortadaki():
    with pytest.raises(ValueError) as exc:
        S._require({"brand": "x"}, "brand", "domain", "sector")
    assert "'domain'" in str(exc.value) and "'sector'" in str(exc.value)


def test_require_unicode_isim():
    with pytest.raises(ValueError) as exc:
        S._require({}, "sektör")
    assert "sektör" in str(exc.value)


def test_require_sirali_mesaj_siralisi():
    """ORTAM: provided keys sorted() ile alfabetik siralanir."""
    with pytest.raises(ValueError) as exc:
        S._require({"zeta": 1, "alpha": 2}, "brand")
    msg = str(exc.value)
    assert msg.index("alpha") < msg.index("zeta")


def test_require_static_metot_sinif_uzerinden():
    """ORTAM-OGRENDI: @staticmethod erisince descriptor halihazirda cozulmustur
    (__func__ YOK) — direkt cagrilabilen bir fonksiyondur."""
    assert callable(S._require)
    S._require({"brand": "x"}, "brand")


def test_require_call_tool_entegrasyonu_eksik_arguman():
    """ORTAM: call_tool _require'i cagirir — gercek dispatch yoluyla davranis
    (answrank_citations brand+domain ister)."""
    import asyncio
    with pytest.raises(ValueError) as exc:
        asyncio.run(S().call_tool("answrank_citations", {}))
    assert "missing required argument(s)" in str(exc.value)
    assert "'brand'" in str(exc.value)


def test_require_call_tool_bilinmeyen_tool():
    """ORTAM-OGRENDI: bilinmeyen tool 'Unknown tool' ile reddedilir — _require'siz."""
    import asyncio
    with pytest.raises(ValueError) as exc:
        asyncio.run(S().call_tool("answrank_miniprobe", {}))
    assert "Unknown tool" in str(exc.value)


def test_require_call_tool_audit_eksik():
    import asyncio
    with pytest.raises(ValueError) as exc:
        asyncio.run(S().call_tool("answrank_audit", {}))
    assert "'url'" in str(exc.value)
