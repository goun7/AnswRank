"""Otonom lead prospektörü — ajanların keşfettiği adayları GERÇEK olarak doğrular.

Dürüstlük sözleşmesi:
  * Aday ancak robots.txt'si saygılanıp ana sayfası gerçekten çekilirse 'staged' olur.
  * İletişim bilgisi yalnız sayfadaki kanıttan (JSON-LD / mailto / metin) alınır;
    bulunamazsa None + DOĞRULANAMADI — asla biçim uydurulmaz.
  * Ulaşılamayan domain staged OLMAZ; ret listesinde nedeniyle birlikte görünür.
  * Mevcut (eski şemalı) veritabanları migration'siz bozulmaz.
"""
import asyncio
import json

import pytest

from answrank.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "pros.db"))


def _fetcher(pages: dict, statuses: dict = None, raise_on=()):
    """url -> (status, text); raise_on içindeki url'ler ağ hatası simüle eder."""
    statuses = statuses or {}

    async def fetch(url, timeout=10.0):
        if url in raise_on:
            raise ConnectionError("bağlanılamadı")
        for key in pages:
            if url.startswith(key):
                return statuses.get(url, 200), pages[key]
        return 404, ""
    return fetch


ROBOTS_OK = "User-agent: *\nAllow: /\n"
ROBOTS_BLOCK = "User-agent: *\nDisallow: /\n"
HOME_WITH_JSONLD = """<html><head>
<script type="application/ld+json">{"@type":"Dentist","name":"Smile Dental","telephone":"+971 4 123 4567","email":"info@smiledental.ae"}</script>
<title>Smile Dental Dubai</title></head><body></body></html>"""
HOME_PLAIN = """<html><head><title>Plain Clinic</title></head><body>
Bize ulaşın: +971 55 987 6543 · appointments@plainclinic.ae</body></html>"""
HOME_NO_CONTACT = "<html><head><title>NoContact Clinic</title></head><body>hakkımızda</body></html>"


def test_verify_extracts_jsonld_contacts_and_respects_robots(db):
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(db=db, fetch=_fetcher({
        "https://smiledental.ae/robots.txt": ROBOTS_OK,
        "https://smiledental.ae/": HOME_WITH_JSONLD,
    }))
    v = asyncio.run(p.verify({"brand": "Smile Dental", "domain": "smiledental.ae",
                              "city": "Dubai", "source_url": "https://example-dir.ae/dubai"}))
    assert v.reachable and v.http_status == 200
    assert v.phone == "+971 4 123 4567" and v.email == "info@smiledental.ae"
    assert v.contact_source == "json-ld"
    assert v.robots_disallowed is False


def test_verify_falls_back_to_page_text_contacts():
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://plainclinic.ae/robots.txt": ROBOTS_OK,
        "https://plainclinic.ae/": HOME_PLAIN,
    }))
    v = asyncio.run(p.verify({"brand": None, "domain": "plainclinic.ae",
                              "city": "Abu Dhabi", "source_url": "s"}))
    assert v.phone == "+971 55 987 6543" and v.email == "appointments@plainclinic.ae"
    assert v.contact_source == "page-text"
    assert v.brand == "Plain Clinic"  # <title>'den düştü


def test_robots_disallow_means_no_page_fetch():
    from answrank.crm.prospector import LeadProspector
    fetched = []

    async def fetch(url, timeout=10.0):
        fetched.append(url)
        if url.endswith("/robots.txt"):
            return 200, ROBOTS_BLOCK
        raise AssertionError("robots disallow iken ana sayfa çekilmemeli")

    p = LeadProspector(fetch=fetch)
    v = asyncio.run(p.verify({"brand": "X", "domain": "blocked.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.robots_disallowed is True
    assert v.phone is None and v.email is None and v.contact_source is None
    assert all(u.endswith("/robots.txt") for u in fetched)


def test_unreachable_candidate_is_rejected_not_staged(db):
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(db=db, fetch=_fetcher({}, raise_on=("https://dead.ae/robots.txt",)))
    v = asyncio.run(p.verify({"brand": "Dead", "domain": "dead.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.reachable is False and v.http_status == 0
    staged, rejected = asyncio.run(p.run([{"brand": "Dead", "domain": "dead.ae",
                                           "city": "Dubai", "source_url": "s"}]))
    assert staged == 0 and rejected == 1
    with db._get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 0


def test_run_stages_verified_and_dedups(db):
    from answrank.crm.prospector import LeadProspector
    cands = [{"brand": "Smile", "domain": "smiledental.ae", "city": "Dubai", "source_url": "s"},
             {"brand": "Smile", "domain": "smiledental.ae", "city": "Dubai", "source_url": "s"}]
    p = LeadProspector(db=db, fetch=_fetcher({
        "https://smiledental.ae/robots.txt": ROBOTS_OK,
        "https://smiledental.ae/": HOME_WITH_JSONLD,
    }), politeness=0.0, country="UAE")
    staged, rejected = asyncio.run(p.run(cands))
    assert staged == 2 and rejected == 0  # iki koşu da stage başarılı (dedup DB'de)
    with db._get_connection() as c:
        row = dict(c.execute("SELECT * FROM prospects WHERE domain_ref='smiledental.ae'").fetchone())
    assert row["phone"] == "+971 4 123 4567" and row["email"] == "info@smiledental.ae"
    assert row["country"] == "UAE" and row["verified_at"]


def test_no_contact_is_staged_but_flagged_unverifiable_contacts(db):
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(db=db, fetch=_fetcher({
        "https://nocontact.ae/robots.txt": ROBOTS_OK,
        "https://nocontact.ae/": HOME_NO_CONTACT,
    }), politeness=0.0)
    staged, rejected = asyncio.run(p.run([{"brand": "NC", "domain": "nocontact.ae",
                                           "city": "Dubai", "source_url": "s"}]))
    assert staged == 1  # işletme GERÇEK; yalnız iletişim DOĞRULANAMADI
    with db._get_connection() as c:
        row = dict(c.execute("SELECT * FROM prospects WHERE domain_ref='nocontact.ae'").fetchone())
    assert row["phone"] is None and row["contact_source"] is None


def test_queue_scan_picks_staged_prospects(db):
    from answrank.crm.prospector import LeadProspector
    from answrank.queue import ApprovalQueue
    p = LeadProspector(db=db, fetch=_fetcher({
        "https://smiledental.ae/robots.txt": ROBOTS_OK,
        "https://smiledental.ae/": HOME_WITH_JSONLD,
    }), politeness=0.0)
    asyncio.run(p.run([{"brand": "Smile", "domain": "smiledental.ae",
                        "city": "Dubai", "source_url": "s"}]))
    n = ApprovalQueue(db=db).scan()
    items = ApprovalQueue(db=db).pending()
    assert n >= 1
    assert any(i["kind"] == "DM" and i["ref_id"] == "smiledental.ae" for i in items)


def test_legacy_database_migrates_columns(tmp_path):
    """Mevcut kurulumda prospects tablosu yeni sütunlardan yoksundur — bozulmamalı."""
    import sqlite3
    legacy = tmp_path / "legacy.db"
    c = sqlite3.connect(legacy)
    c.executescript("""CREATE TABLE prospects (id TEXT PRIMARY KEY, brand_name TEXT, sector TEXT,
    city TEXT, website_url TEXT, contact_person TEXT, platform TEXT, status TEXT, created_at TIMESTAMP);
    INSERT INTO prospects (id, brand_name, sector, city) VALUES ('lead_eski','Eski Klinik','dental','İstanbul');""")
    c.commit(); c.close()
    db = Database(db_path=str(legacy))  # _init_db migration'ı çalışmalı
    with db._get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
        assert {"country", "phone", "email", "source_url", "verified_at"} <= cols
        assert conn.execute("SELECT brand_name FROM prospects").fetchone()[0] == "Eski Klinik"


def test_cli_prospect_dry_run_and_report(db, monkeypatch, capsys, tmp_path):
    import sys
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(db.db_path))
    raw = tmp_path / "leads.json"
    raw.write_text(json.dumps([
        {"brand": "Smile", "domain": "smiledental.ae", "city": "Dubai", "source_url": "s"},
        {"brand": "Dead", "domain": "dead.ae", "city": "Dubai", "source_url": "s"},
    ]), encoding="utf-8")
    from answrank.cli import main
    monkeypatch.setattr(sys, "argv", ["answrank", "prospect", "--file", str(raw),
                                      "--country", "UAE", "--dry-run"])
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "smiledental.ae" in out and "dead.ae" in out and "DOĞRULANAMADI" in out
    with db._get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 0  # dry-run


def test_contact_extraction_rejects_css_and_hash_junk():
    """Canlı UAE turunda bulunan gerçek kusur: CSS unicode-range 'U+0302-0303'
    sahte telefon, hex hash sahte e-posta olarak yakalanıyordu — artık reddedilir."""
    from answrank.crm.prospector import LeadProspector
    junk_html = """<html><head><title>Real Clinic</title><style>/* latin-ext */
    @font-face{unicode-range:U+0302-0303,U+0305,U+0307-0308;}
    .cls{background:url(data:image/png;base64,bcb8c4703eae71d5)}</style></head>
    <body>iletişim: info@realclinic.ae · +971 4 555 1234</body></html>"""
    p = LeadProspector(fetch=_fetcher({
        "https://realclinic.ae/robots.txt": ROBOTS_OK,
        "https://realclinic.ae/": junk_html,
    }))
    v = asyncio.run(p.verify({"brand": "R", "domain": "realclinic.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.phone == "+971 4 555 1234", v.phone
    assert v.email == "info@realclinic.ae", v.email


def test_cli_prospect_really_writes_row(db, monkeypatch, capsys, tmp_path):
    """Yazma yolu: 'stage edildi' mesajı YALNIZ gerçek INSERT'ten sonra gelmeli
    (önceki sürüm run_verify kullanıyor, yazmıyor, yine de başarı basıyordu)."""
    import sys
    from answrank.config import settings
    from answrank.crm import prospector as pr
    monkeypatch.setattr(settings, "db_path", str(db.db_path))

    async def fake_fetch(url, timeout=10.0):
        if url.endswith("/robots.txt"):
            return 200, ROBOTS_OK
        return 200, HOME_WITH_JSONLD
    monkeypatch.setattr(pr.LeadProspector, "_httpx_fetch", staticmethod(fake_fetch))
    raw = tmp_path / "one.json"
    raw.write_text(json.dumps([{"brand": "Smile", "domain": "smiledental.ae",
                                "city": "Dubai", "source_url": "s"}]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["answrank", "prospect", "--file", str(raw),
                                      "--country", "UAE", "--politeness", "0"])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "1 lead stage edildi" in out
    with db._get_connection() as c:
        row = dict(c.execute("SELECT * FROM prospects WHERE domain_ref='smiledental.ae'").fetchone())
    assert row["phone"] == "+971 4 123 4567" and row["country"] == "UAE"


def test_challenge_page_does_not_leak_junk_contacts_or_brand():
    """Canlı UAE turundaki gerçek kusur: Cloudflare 'Checking your browser' sayfası
    marka olarak, '404: This page could not be found' marka olarak sızıyordu."""
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://cf-clinic.ae/robots.txt": ROBOTS_OK,
        "https://cf-clinic.ae/": "<html><head><title>Checking your browser before "
                                "accessing. Just a moment...</title></head><body>"
                                "Ray ID: bcb8c4703eae71d5 · flags@2x.webp</body></html>",
    }))
    v = asyncio.run(p.verify({"brand": "Gerçek Marka", "domain": "cf-clinic.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.reachable and v.http_status == 200
    assert v.brand == "Gerçek Marka"  # challenge başlığı marka olarak ALINMAZ
    assert v.phone is None and v.email is None
    assert "bot-challenge" in v.notes


def test_asset_filename_emails_rejected():
    """sprite.flags@2x.webp / hash@2x.png gibi dosya-adı e-postaları reddedilir."""
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://asset-clinic.ae/robots.txt": ROBOTS_OK,
        "https://asset-clinic.ae/": "<html><head><title>Asset Clinic</title></head>"
        "<body>logo: sprite.flags@2x.webp · ico: bcb8c4703eae71d5@2x.png · "
        "gerçek: info@assetclinic.ae · +971 4 111 2222</body></html>",
    }))
    v = asyncio.run(p.verify({"brand": None, "domain": "asset-clinic.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.email == "info@assetclinic.ae", v.email
    assert v.brand == "Asset Clinic"


def test_404_homepage_keeps_source_brand():
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://missing-clinic.ae/robots.txt": ROBOTS_OK,
    }, statuses={"https://missing-clinic.ae/": 404}))
    v = asyncio.run(p.verify({"brand": "Kaybolan Klinik", "domain": "missing-clinic.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.http_status == 404 and v.brand == "Kaybolan Klinik"
    assert v.phone is None and "404" in v.notes


def test_html_entities_decoded_in_brand():
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://ent-clinic.ae/robots.txt": ROBOTS_OK,
        "https://ent-clinic.ae/": "<html><head><title>Royal Clinic &#8211; located in "
                                 "Dubai</title></head><body></body></html>",
    }))
    v = asyncio.run(p.verify({"brand": None, "domain": "ent-clinic.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.brand == "Royal Clinic", v.brand  # &#8211; decode + son ek atılır


def await_none(coro):
    import asyncio as _a
    return _a.run(coro)


def test_invalid_domain_candidate_rejected_with_note():
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({}))
    v = asyncio.run(p.verify({"brand": "X", "domain": "gecersiz", "city": "c"}))
    assert v.reachable is False and "geçersiz domain" in v.notes


def test_http_fallback_and_total_unreachable():
    """https başarısız → http geri düşüşü; ikisi de başarısız → RET."""
    from answrank.crm.prospector import LeadProspector

    async def fetch(url, timeout=10.0):
        # robots her zaman https'den denenir (gerçek akış): https çalışıyor
        if url == "https://fallback.ae/robots.txt":
            return 200, ROBOTS_OK
        if url == "https://dead2.ae/robots.txt":
            return 200, ROBOTS_OK  # robots OK ama ana sayfa hiç erişilemez
        if url == "https://fallback.ae/":
            raise ConnectionError("https down")
        if url == "http://fallback.ae/":
            return 200, "<html><head><title>Fallback Clinic</title></head><body></body></html>"
        raise ConnectionError("http down")

    ok = asyncio.run(LeadProspector(fetch=fetch).verify(
        {"brand": None, "domain": "fallback.ae", "city": "Dubai", "source_url": "s"}))
    assert ok.reachable and ok.brand == "Fallback Clinic"

    dead = asyncio.run(LeadProspector(fetch=fetch).verify(
        {"brand": "D", "domain": "dead2.ae", "city": "Dubai", "source_url": "s"}))
    assert dead.reachable is False and "ana sayfa indirilemedi" in dead.notes


def test_email_and_robots_edge_branches():
    from answrank.crm.prospector import LeadProspector

    async def fetch(url, timeout=10.0):
        if url.endswith("/robots.txt"):
            return 200, "# yorum satırı\n\nUser-agent: *\nDisallow: /gizli/\n"
        return 200, """<html><head><title>Dental</title>
        <meta property="og:site_name" content="OG Brand Clinic" />
        <script type="application/ld+json">{"telephone":"9714111222"}</script></head>
        <body>iletişim: real@ogbrand.ae</body>
        </html>"""

    v = asyncio.run(LeadProspector(fetch=fetch).verify(
        {"brand": None, "domain": "ogbrand.ae", "city": "Dubai", "source_url": "s"}))
    assert v.brand == "OG Brand Clinic"           # og:site_name yolu
    assert v.phone == "+9714111222"               # JSON-LD digits-only normalize
    assert v.contact_source == "json-ld"          # JSON-LD öncelikli kanıt
    assert v.robots_disallowed is False           # /gizli/ Disallow tümünü kapsamaz


def test_email_filter_branches_without_jsonld():
    """Sayfa-metni e-posta filtreleri (125/129/131) ancak JSON-LD yoksa çalışır."""
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://filter.ae/robots.txt": ROBOTS_OK,
        "https://filter.ae/": "<html><head><title>Filter Clinic</title></head>"
        "<body>+971 4 555 1234 · info@example.com · a@b.png · "
        "bcb8c4703eae71d5@h.com · 12345@x.ae</body></html>",
    }))
    v = asyncio.run(p.verify({"brand": None, "domain": "filter.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.phone == "+971 4 555 1234"
    assert v.email is None  # tanesi de sahte: yasak host / asset uzantisi / heks / saf rakam


def test_extract_brand_static_branches():
    """_extract_brand'ın savunma kolları (challenge başlık + başıksız gövde)."""
    from answrank.crm.prospector import LeadProspector
    assert LeadProspector._extract_brand(
        "<html><head><title>Just a moment...</title></head></html>", "Yedek") == "Yedek"
    assert LeadProspector._extract_brand("<html><body>yok</body></html>", "Yedek") == "Yedek"


def test_titleless_body_is_not_evidence():
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(fetch=_fetcher({
        "https://notitle.ae/robots.txt": ROBOTS_OK,
        "https://notitle.ae/": "<html><body>yok</body></html>",
    }))
    v = asyncio.run(p.verify({"brand": "Kaynak Marka", "domain": "notitle.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert v.brand == "Kaynak Marka"  # başlık yok → challenge muamelesi, kaynak marka kalır


def test_httpx_fetch_path_with_stubbed_client(monkeypatch):
    """Üretim ağ katmanı (httpx) — stub'la çevrimdışı kanıtlanır."""
    from answrank.crm import prospector as pr

    class _Resp:
        status_code = 200
        text = "<html><head><title>Stub</title></head><body></body></html>"

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

    import sys as _sys, types as _types
    stub = _types.ModuleType("httpx_stub")
    stub.AsyncClient = _Client
    monkeypatch.setitem(_sys.modules, "httpx", stub)  # import httpx fonksiyon içi
    status, text = asyncio.run(pr.LeadProspector._httpx_fetch("https://stub.ae/"))
    assert status == 200 and "Stub" in text


def test_stage_without_db_is_noop():
    from answrank.crm.prospector import LeadProspector
    p = LeadProspector(db=None, fetch=_fetcher({
        "https://node.ae/robots.txt": ROBOTS_OK,
        "https://node.ae/": HOME_WITH_JSONLD,
    }), politeness=0.0)
    staged, rejected = asyncio.run(p.run([{"brand": "N", "domain": "node.ae",
                                           "city": "Dubai", "source_url": "s"}]))
    assert staged == 1 and rejected == 0  # db yoksa da doğrulama çalışır, yazmaz
    v = asyncio.run(p.verify({"brand": "N", "domain": "node.ae",
                              "city": "Dubai", "source_url": "s"}))
    assert await_none(p.stage(v)) is None


def test_cli_prospect_empty_list_does_not_fabricate(monkeypatch, capsys, tmp_path):
    """cli.py:833-834 — boş/geçersiz liste 'stage edildi' demeden reddedilir."""
    import sys
    raw = tmp_path / "empty.json"
    raw.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["answrank", "prospect", "--file", str(raw)])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "boş/geçersiz" in out and "stage edildi" not in out
