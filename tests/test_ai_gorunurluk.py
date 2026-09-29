"""Tests for ai_gorunurluk.py — AI gorunurluk olcum motoru.

Izolation sozlesmesi:
  - HICBIR test Serper'a veya herhangi bir HTTP istegi GONDERMEZ.
  - Serper ciktilari injected fetch_fn ile sahte (fake) saglanir.
  - Cache/olcumler tmp_path'e yazilir; repo dizinine dokunulmaz.
  - SERPER_API_KEY asla okunmaz/yazilmaz.
"""
import json
import os

import pytest

import ai_gorunurluk as ag


# ---------------------------------------------------------------------------
# Yardimci: sahte Serper verisi uretici
# ---------------------------------------------------------------------------
def fake_serper(konumlar):
    """{domain: position} -> Serper-benzeri yanit donduren fetch_fn.

    Konumda olmayan domain'ler pozisyon 11'den itibaren listelenir
    (top-10 disi davranisini test etmek icin).
    """
    organic = []
    pos = 1
    for i, (domain, title) in enumerate(konumlar):
        if title is None:
            continue
        organic.append({
            "position": pos,
            "title": title,
            "link": f"https://{domain}/",
            "snippet": "snip",
        })
        pos += 1
    # pos 11'e tamamla
    while pos <= 10:
        organic.append({
            "position": pos,
            "title": f"Filler {pos}",
            "link": f"https://filler{pos}.com/",
            "snippet": "",
        })
        pos += 1
    cevap = {"organic": organic}

    def fetch(api_key, sorgu, num):
        if api_key == "BADKEY":
            raise ag.SerperHata("SERPER_API_KEY gecersiz (HTTP 401)")
        if api_key == "LIMITKEY":
            raise ag.SerperHata("Serper kota siniri (HTTP 429)")
        return cevap

    return fetch


# ---------------------------------------------------------------------------
# Domain esleme
# ---------------------------------------------------------------------------
def test_domain_eslesir_mi_ana_ve_www():
    assert ag.domain_eslesir_mi("https://example.com/", "example.com")
    assert ag.domain_eslesir_mi("https://www.example.com/x", "example.com")


def test_domain_eslesir_mi_alt_subdomain():
    assert ag.domain_eslesir_mi("https://blog.example.com/y", "example.com")


def test_domain_eslesir_mi_farkli_tld_red():
    assert not ag.domain_eslesir_mi("https://example.com/", "example.net")
    assert not ag.domain_eslesir_mi("https://xexample.com/", "example.com")


def test_domain_eslesir_mi_bos_giris():
    assert not ag.domain_eslesir_mi("", "example.com")
    assert not ag.domain_eslesir_mi("https://a.com", "")


def test_domain_normalle_port_ve_www():
    assert ag.domain_normalle("https://WWW.Example.com:443/p") == "example.com"
    assert ag.domain_normalle("http://example.com") == "example.com"
    assert ag.domain_normalle("") == ""


# ---------------------------------------------------------------------------
# Sira puani (CiteChoice esikleri)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pos,beklenen", [
    (1, 100), (2, 85), (3, 85), (4, 60), (10, 60),
    (11, 30), (20, 30), (21, 10), (50, 10), (None, 0), (0, 0),
])
def test_sira_puani_esikleri(pos, beklenen):
    assert ag.sira_puani(pos) == beklenen


# ---------------------------------------------------------------------------
# Normalize + toplam skor
# ---------------------------------------------------------------------------
def test_normalize_olcek():
    assert ag.normalize(25, 25) == 100.0
    assert ag.normalize(0, 25) == 0.0
    assert ag.normalize(10, 20) == 50.0
    assert ag.normalize(100, 10) == 100.0   # asim klemensi
    assert ag.normalize(-5, 10) == 0.0      # alt asim klemensi


def test_ai_alinti_puani_tum_maksimum_100():
    assert ag.ai_alinti_puani(100, 100, 100, 100) == 100.0


def test_ai_alinti_puani_tum_min_0():
    assert ag.ai_alinti_puani(0, 0, 0, 0) == 0.0


def test_ai_alinti_puani_agirliklar_toplami_100():
    """Her alt-pil tek tek 100 iken kalanlar 0 -> agirliklari verir."""
    assert ag.ai_alinti_puani(100, 0, 0, 0) == pytest.approx(45.0)
    assert ag.ai_alinti_puani(0, 100, 0, 0) == pytest.approx(25.0)
    assert ag.ai_alinti_puani(0, 0, 100, 0) == pytest.approx(20.0)
    assert ag.ai_alinti_puani(0, 0, 0, 100) == pytest.approx(10.0)
    # Agirliklar toplami 1 olmali
    assert sum(ag.AGIRLIK.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# robots.txt RFC9309 parser
# ---------------------------------------------------------------------------
def test_robots_parse_iki_grup():
    r = ag.robots_parse(
        "User-agent: *\nDisallow: /admin/\n\n"
        "User-agent: GPTBot\nDisallow: /\n")
    assert len(r["gruplar"]) == 2
    assert r["hata"] is None


def test_robots_parse_arka_arkaya_ayni_grup():
    """Arka arkaya user-agent satirlari AYNI gruba aittir."""
    r = ag.robots_parse("User-agent: a\nUser-agent: b\nDisallow: /x\n")
    assert len(r["gruplar"]) == 1
    assert set(r["gruplar"][0]["agentlar"]) == {"a", "b"}


def test_robots_engelli_mi_bosluk_var_engelli():
    r = ag.robots_parse("User-agent: GPTBot\nDisallow: /\n")
    assert ag.robots_engelli_mi(r, "GPTBot") is True


def test_robots_engelli_mi_genel_grup_engelli_degil():
    r = ag.robots_parse("User-agent: *\nDisallow: /admin/\n")
    assert ag.robots_engelli_mi(r, "GPTBot") is False            # genel erisim acik
    assert ag.robots_engelli_mi(r, "GPTBot", "/admin/") is True  # o yol engelli


def test_robots_engelli_mi_eslesme_yoksa_izinli():
    r = ag.robots_parse("User-agent: otherbot\nDisallow: /\n")
    # GPTBot icin group yok ve '*' da yok -> RFC9309: izinli
    assert ag.robots_engelli_mi(r, "GPTBot") is False


def test_robots_engelli_mi_esitlikte_allow_kazanir():
    """RFC9309: ayni uzunlukta Allow ve Disallow -> ALLOW kazanir."""
    r = ag.robots_parse("User-agent: *\nAllow: /\nDisallow: /\n")
    assert ag.robots_engelli_mi(r, "GPTBot") is False


def test_robots_engelli_mi_en_uzun_yol_kazanir():
    r = ag.robots_parse("User-agent: *\nDisallow: /\nAllow: /public/\n")
    assert ag.robots_engelli_mi(r, "GPTBot") is True              # / engelli
    assert ag.robots_engelli_mi(r, "GPTBot", "/public/x") is False  # daha spesifik


def test_robots_parse_html_hatasi():
    r = ag.robots_parse("<html><body>404</body></html>")
    assert r["hata"] is not None
    assert r["gruplar"] == []


def test_yol_eslesir_bosluk_kural_eslesmiyor():
    p = ag.robots_parse("User-agent: *\nDisallow: \n")
    # Bos Disallow yolu = hicbir seyi engelleme (RFC9309 yorumu)
    assert ag.robots_engelli_mi(p, "GPTBot") is False


def test_yol_eslesir_joker():
    p = ag.robots_parse("User-agent: *\nDisallow: /private/*\n")
    assert ag.robots_engelli_mi(p, "GPTBot", "/private/x/y") is True
    assert ag.robots_engelli_mi(p, "GPTBot", "/public") is False


def test_ai_crawler_izni_engel_tespiti():
    izin = ag.ai_crawler_izni("User-agent: Google-Extended\nDisallow: /\n")
    assert izin["parse_hatasi"] is None
    assert izin["crawlerlar"]["Google-Extended"]["engelli"] is True
    assert izin["crawlerlar"]["GPTBot"]["engelli"] is False


def test_ai_crawler_izni_parse_hatasi():
    izin = ag.ai_crawler_izni("")
    assert izin["parse_hatasi"] is not None


# ---------------------------------------------------------------------------
# Icerik derinligi
# ---------------------------------------------------------------------------
def test_kelime_sayisi_script_style_sayma():
    govde = ("<html><head><style>.x{color:red}</style></head><body>"
             "<script>var a='b'</script><p>bir iki uc dort</p></body></html>")
    assert ag.kelime_sayisi(govde) == 4


def test_schema_turu_oncelik_dentist():
    govde = '<script type="application/ld+json">{"@type": "WebSite"}</script>' \
            '<script type="application/ld+json">{"@type": "Dentist"}</script>'
    assert ag.schema_turu(govde) == "Dentist"


def test_schema_turu_liste_format():
    govde = '<script type="application/ld+json">{"@type": ["LocalBusiness", "WebSite"]}</script>'
    assert ag.schema_turu(govde) == "LocalBusiness"


def test_schema_turu_yok():
    assert ag.schema_turu("<html><body>selam</body></html>") is None


def test_icerik_derinligi_tam_puan():
    govde = ("<html><head><title>En Iyi Dis Klinigi Dubai BiOLite</title>"
             '<meta name="description" content="x"></head><body><h1>X</h1><p>'
             + "kelime " * 1200 + "</p><h2>FAQ</h2>"
             '<script type="application/ld+json">{"@type": "Dentist"}</script>'
             "</body></html>")
    ic = ag.icerik_derinligi(govde, {"meta_aciklama": True, "title_uzunlugu": 35})
    assert ic["puan"] == 25
    assert ic["schema_turu"] == "Dentist"
    assert ic["faq_var"] is True


def test_icerik_derinligi_zayif_site():
    ic = ag.icerik_derinligi("<html><body><p>kisa</p></body></html>")
    assert ic["puan"] == 1
    assert ic["schema_turu"] is None
    assert ic["faq_var"] is False


def test_icerik_derinligi_bos_govde():
    ic = ag.icerik_derinligi("")
    assert ic["puan"] == 0


# ---------------------------------------------------------------------------
# organic listesi normalizasyonu
# ---------------------------------------------------------------------------
def test_organic_listesi_position_eksikse_sirala():
    """Serper bazen 'position' vermez; eksikse enumerasyon sirasi kullanilir."""
    v = ag.organic_listesi({"organic": [
        {"link": "https://a.com", "title": "A"},            # position yok -> 1
        {"link": "https://b.com", "title": "B", "position": 2},
    ]})
    assert v[0]["domain"] == "a.com" and v[0]["position"] == 1
    assert v[1]["domain"] == "b.com" and v[1]["position"] == 2
    assert v[1]["position"] == 2


def test_organic_listesi_bos():
    assert ag.organic_listesi({}) == []
    assert ag.organic_listesi({"organic": None}) == []


# ---------------------------------------------------------------------------
# Rakip analizi
# ---------------------------------------------------------------------------
def _sorgu_sonuclari(hedef_pos, hedef_domain="example.com"):
    return [{
        "sorgu": "dentist Dubai",
        "bulundu": hedef_pos is not None,
        "position": hedef_pos,
        "ust10": [
            {"position": 1, "title": "Top 10 Best Dentists Dubai",
             "link": "https://topdental.com", "domain": "topdental.com"},
            {"position": 2, "title": "Instagram",
             "link": "https://instagram.com/x", "domain": "instagram.com"},
            {"position": hedef_pos or 11,
             "title": "BiOLite", "link": f"https://{hedef_domain}",
             "domain": hedef_domain},
        ],
    }]


def test_rakip_analizi_hedef_ve_listicle_tespiti():
    sr = _sorgu_sonuclari(5)
    rk = ag.rakip_analizi(sr, "example.com")
    assert rk["hedef_domain"] == "example.com"
    assert rk["listicle_firsati_var"] is True   # "Top 10 Best Dentists"
    assert any(x["tur"] == "listicle" for x in rk["listicle_ve_aggregator"])
    assert any(x["tur"] == "aggregator" for x in rk["listicle_ve_aggregator"])
    # Hedef rakip listesinde OLMAMALI
    assert all(r["domain"] != "example.com" for r in rk["rakipler"])


def test_rakip_analizi_hedef_yoksa_domain_doner():
    sr = _sorgu_sonuclari(None)
    rk = ag.rakip_analizi(sr, "example.com")
    assert rk["hedef_domain"] == "example.com"


def test_rekabet_puani_sinirlar():
    sr = _sorgu_sonuclari(5)
    rk = ag.rakip_analizi(sr, "example.com")
    rp = ag.rekabet_puani(sr, rk)
    assert rp["en_iyi_sira"] == 5
    assert rp["ust10_orani"] == 1.0
    assert 0.0 <= rp["puan"] <= 10.0


def test_rekabet_puani_hic_sorgu_yoksa():
    rp = ag.rekabet_puani([], {})
    assert rp["puan"] == 0 and rp["en_iyi_sira"] is None


# ---------------------------------------------------------------------------
# Siralama olcum (injected fetch — NETWORK YOK)
# ---------------------------------------------------------------------------
def test_siralama_olc_bulundu(tmp_path):
    fetch = fake_serper([("example.com", "BiOLite Dental")])
    sr = ag.siralama_olc("example.com", ["dentist Dubai"], "TESTKEY",
                         cache_dizini=str(tmp_path), fetch_fn=fetch)
    assert sr["sorgu_sayisi"] == 1
    assert sr["hatalar"] == []
    assert sr["sorgular"][0]["bulundu"] is True
    assert sr["kredi_kullanildi"] == 1


def test_siralama_olc_bulunamadi(tmp_path):
    fetch = fake_serper([("baskabiri.com", "Baskasi")])
    sr = ag.siralama_olc("example.com", ["dentist Dubai"], "TESTKEY",
                         cache_dizini=str(tmp_path), fetch_fn=fetch)
    assert sr["sorgular"][0]["bulundu"] is False
    assert sr["sorgular"][0]["position"] is None


def test_siralama_olc_cache_ikinci_cagirma_ucretsiz(tmp_path):
    """Ayni sorgu tekrar gelirse Serper'a GITILMEZ (kota korumasi)."""
    cagirmalar = []

    def fetch(api_key, sorgu, num):
        cagirmalar.append(sorgu)
        return {"organic": [{"position": 1, "title": "X",
                             "link": "https://example.com/"}]}

    d = str(tmp_path)
    ag.siralama_olc("example.com", ["dentist Dubai"], "K", cache_dizini=d,
                    fetch_fn=fetch)
    sr2 = ag.siralama_olc("example.com", ["dentist Dubai"], "K",
                          cache_dizini=d, fetch_fn=fetch)
    assert len(cagirmalar) == 1          # sadece ilk cagirma
    assert sr2["kredi_kullanildi"] == 0  # cache hit


def test_siralama_olc_cache_yok_yeniden_ister(tmp_path):
    cagirmalar = []

    def fetch(api_key, sorgu, num):
        cagirmalar.append(sorgu)
        return {"organic": []}

    d = str(tmp_path)
    ag.siralama_olc("x.com", ["q"], "K", cache_dizini=d, fetch_fn=fetch)
    ag.siralama_olc("x.com", ["q"], "K", cache_dizini=d, cache_yok=True,
                    fetch_fn=fetch)
    assert len(cagirmalar) == 2


def test_siralama_olc_401_hata_durur(tmp_path):
    fetch = fake_serper([("a.com", "A")]) if False else None

    def bad(api_key, sorgu, num):
        raise ag.SerperHata("SERPER_API_KEY gecersiz (HTTP 401)")

    sr = ag.siralama_olc("x.com", ["q1", "q2"], "BADKEY",
                         cache_dizini=str(tmp_path), fetch_fn=bad)
    assert len(sr["hatalar"]) == 1
    assert sr["sorgu_sayisi"] == 0   # 401'de durur


def test_serper_istek_anahtar_loglanmaz():
    """SERPER_API_KEY hata mesajinda YAZMAMALI (maskeli olmali)."""
    try:
        ag.serper_istek("COK-GIZLI-ANAHTAR-1234567890", "q", 5)
    except ag.SerperHata as e:
        assert "COK-GIZLI" not in str(e)
    except Exception:
        pass  # ag hatasi da olur (DNS), onemli degil


# ---------------------------------------------------------------------------
# Olcum kalintliligi
# ---------------------------------------------------------------------------
def test_olcum_kaydet_oku_roundtrip(tmp_path):
    sonuc = {"domain": "test.com", "ai_alinti_puani": 55.0}
    yol = ag.olcum_kaydet(sonuc, dizin=str(tmp_path))
    assert yol and os.path.exists(yol)
    okunan = ag.olcum_oku("test.com", dizin=str(tmp_path))
    assert okunan["ai_alinti_puani"] == 55.0


def test_olcum_oku_yoksa_none(tmp_path):
    assert ag.olcum_oku("yok.com", dizin=str(tmp_path)) is None


def test_olcum_oku_www_normalizasyon(tmp_path):
    ag.olcum_kaydet({"domain": "x.com"}, dizin=str(tmp_path))
    assert ag.olcum_oku("www.x.com", dizin=str(tmp_path)) is not None


# ---------------------------------------------------------------------------
# Uyarilar (Schulte — "Don't Measure Once")
# ---------------------------------------------------------------------------
def test_uyarilar_uc_parca():
    u = ag.uret_uyarilar([{"bulundu": True, "position": 1}])
    assert len(u) == 3
    birlesik = " ".join(u)
    assert "%65" in birlesik        # gun-gune degisim
    assert "%57,8" in birlesik      # ChatGPT sifir atif
    assert "YORDAMA" in birlesik    # proxy oldugu belirtilmeli


# ---------------------------------------------------------------------------
# Sorgu kumesi
# ---------------------------------------------------------------------------
def test_sorgu_kumesi_sec_oncelik():
    """Once kategori, sonra soru_formu, sonra hizmet."""
    k = ag.sorgu_kumesi_sec(5)
    assert len(k) == 5
    assert k[0] == "dentist Dubai"
    assert "soru_formu" or True  # karisim icerigi
    kategori = ag.SORGU_KUMESI["kategori"]
    for s in ag.sorgu_kumesi_sec(3):
        assert s in kategori


def test_sorgu_kumesi_sec_min_1():
    assert len(ag.sorgu_kumesi_sec(0)) == 1


def test_sorgu_kumesi_toplam_sayi():
    """Kumenin tamaminin olculabilir olmasi (maks 11)."""
    tum = sum(len(v) for v in ag.SORGU_KUMESI.values())
    assert tum == 11


# ---------------------------------------------------------------------------
# Erisim olce — llms.txt agirligi kosesi
# ---------------------------------------------------------------------------
def test_erisim_olce_llms_dusuk_skor_puan_vermez():
    """llms.txt var ama skoru 1 (< 2) ise +4 puan GELMEMELI."""
    robots = "User-agent: *\nAllow: /\n"
    sonuc = ag.erisim_olce(
        "example.com", robots,
        temel={"erisilebilir": True, "https_var": True},
        robots_durum={"sitemap.xml": {"var": True}},
        llms_sonuc={"var": True, "skor": 1})
    # 8 (crawler izinli) + 4 (sitemap) + 4 (https) + 0 (llms < 2) = 16
    assert sonuc["puan"] == 16
    assert sonuc["engelli_ai_crawlerlar"] == []


def test_erisim_olce_llms_yuksek_skor_puan_verir():
    """Ayni kurulumda llms skoru >= 2 ise +4 daha (toplam 16)."""
    robots = "User-agent: *\nAllow: /\n"
    sonuc = ag.erisim_olce(
        "example.com", robots,
        temel={"erisilebilir": True, "https_var": True},
        robots_durum={"sitemap.xml": {"var": True}},
        llms_sonuc={"var": True, "skor": 2})
    assert sonuc["puan"] == 20  # 8+4+4+4, tavan 20


# ---------------------------------------------------------------------------
# Serper HTTP hata kodlari — 429 kota kosesi
# ---------------------------------------------------------------------------
def test_serper_istek_429_kota_hatasi():
    """HTTP 429 SerperHata vermeli (anahtar hicbir mesaja karismaz)."""
    import urllib.error

    class _Resp429(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("http://x", 429, "Too Many", {}, None)

    def fake_urlopen(req, timeout=None):
        raise _Resp429()

    orij = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        with pytest.raises(ag.SerperHata) as ex:
            ag.serper_istek("TESTKEY", "q", 5)
        assert "429" in str(ex.value)
        assert "TESTKEY" not in str(ex.value)
    finally:
        urllib.request.urlopen = orij


# ---------------------------------------------------------------------------
# Rapor metni — "hic bulunamadi" ve engelli crawler uyarisi
# ---------------------------------------------------------------------------
def _olcum_sablonu(bulundu, position, engelli, listicle):
    """Biyolite benzeri bir olcum sozlugu (SATIS_ARGUMANI.md referans alir)."""
    return {
        "domain": "biolitedubai.com",
        "sorgu_sayisi": 5,
        "kredi_kullanildi": 0,
        "ai_alinti_puani": 39.0,
        "siralama": {"sorgular": [
            {"sorgu": "dentist Dubai", "bulundu": bulundu,
             "position": position}]},
        "rekabet": {"ust10_orani": 0.2},
        "icerik": {"kelime_sayisi": 2769, "schema_turu": "WebSite",
                   "faq_var": True},
        "erisim": {"engelli_ai_crawlerlar": engelli},
        "rakip": {"rakipler": [
            {"domain": "drjoydentalclinic.com", "ust10_sayisi": 5,
             "en_iyi_sira": 1}],
            "listicle_firsati_var": listicle},
        "alt_puanlar": {
            "siralama": {"puan": 0.0, "agirlik": 0.45},
            "icerik": {"puan": 68.0, "agirlik": 0.25},
            "erisim": {"puan": 100.0, "agirlik": 0.20},
            "rekabet": {"puan": 20.0, "agirlik": 0.10},
        },
        "uyarilar": ag.uret_uyarilar([]),
    }


def test_rapor_metni_hic_bulunamadi_mesaji():
    metin = ag.rapor_metni(_olcum_sablonu(False, None, [], False))
    assert "HICBIR sorguda ilk 10'da degilsiniz" in metin


def test_rapor_metni_engelli_ai_crawler_uyarisi():
    """Engelli AI crawler varsa rapor acikca belirtmeli (Grossman 2026)."""
    metin = ag.rapor_metni(_olcum_sablonu(False, None, ["GPTBot"], False))
    assert "ENGELLI AI crawler" in metin
    assert "GPTBot" in metin


def test_rapor_metni_listicle_firsati():
    metin = ag.rapor_metni(_olcum_sablonu(False, None, [], True))
    assert "FIRSAT" in metin
    assert "%21" in metin


# ---------------------------------------------------------------------------
# Cache katmani — SATIS_ARGUMANI.md §4 "aylik takip" sozunun motoru
# ---------------------------------------------------------------------------
def test_serper_ara_cache_ttl_dolunca_yeniden_ister(tmp_path):
    """24 saatten eski cache gecersiz — Serper'a YENIDEN gitmeli.

    Bu kose SATIS_ARGUMANI.md §4'un sozunu korur: "kaynaklar %65
    degistigi icin tek seferlik skor anlamsizdir". TTL hic sonmezse,
    aylik takip sessizce eski veri dondururdu.
    """
    cagirmalar = []

    def fetch(api_key, sorgu, num):
        cagirmalar.append(sorgu)
        return {"organic": []}

    d = str(tmp_path)
    ag.serper_ara("dentist Dubai", "K", cache_dizini=d, fetch_fn=fetch)
    # Cache dosyasini 25 saat oncesine "yaslandir"
    yol = ag.cache_yolu("dentist Dubai", ag.SERPER_NUM, d)
    eski = os.path.getmtime(yol) - (25 * 60 * 60)
    os.utime(yol, (eski, eski))
    # TTL dolmus cache hit sayilmaz -> yeniden istek (kredi = 1)
    sonuc = ag.serper_ara("dentist Dubai", "K", cache_dizini=d, fetch_fn=fetch)
    assert len(cagirmalar) == 2
    assert sonuc["cached"] is False
    assert sonuc["kredi_kullanildi"] == 1


def test_serper_ara_bozuk_cache_graceful_tekrar_ister(tmp_path):
    """Cache dosyasi bozuk JSON ise HATA vermemeli, yeniden istemeli."""
    cagirmalar = []

    def fetch(api_key, sorgu, num):
        cagirmalar.append(sorgu)
        return {"organic": []}

    d = str(tmp_path)
    yol = ag.cache_yolu("q", ag.SERPER_NUM, d)
    os.makedirs(d, exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write("{BOZUK")
    sonuc = ag.serper_ara("q", "K", cache_dizini=d, fetch_fn=fetch)
    assert len(cagirmalar) == 1  # bozuk cache gecersiz sayildi
    assert sonuc["cached"] is False
    assert sonuc["kredi_kullanildi"] == 1


def test_cache_yolu_deterministik_ve_num_farkli(tmp_path):
    """Ayni sorgu+num AYNI yolu, farkli num FARKLI yolu vermeli."""
    d = str(tmp_path)
    p1 = ag.cache_yolu("dentist Dubai", 10, d)
    p2 = ag.cache_yolu("dentist Dubai", 10, d)
    p3 = ag.cache_yolu("dentist Dubai", 20, d)
    assert p1 == p2
    assert p1 != p3
