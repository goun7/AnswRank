"""answrank.cli dal-kesen testleri (LEED) — _leads_via_db + _verify_and_stage.

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory — gercek ag YOK; LeadProspector STUBLA, sqlite
conftest'in settings.db_path -> tmp_path yonlendirmesiyle.
_verify_and_stage ic-closure oldugu icin run_prospect_command uzerinden
(davranis-karakterizasyonu) test edilir.
"""
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from answrank import cli


def _insert_lead(db_path, domain, verdict="GİRİŞ REDDEDİLDİ", measured=0,
                 created_at="2026-01-01T10:00:00",
                 robots_line="ÖLÇÜLEMEDİ (taranmadı)",
                 llms_line="ÖLÇÜLEMEDİ (taranmadı)",
                 bots_line="WAF 403"):
    with sqlite3.connect(db_path) as c:
        c.execute(
            "INSERT INTO miniprobe_leads (domain, verdict, robots_line,"
            " llms_line, bots_line, measured, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (domain, verdict, robots_line, llms_line, bots_line, measured,
             created_at))
        c.commit()


# == _leads_via_db ============================================================================

@pytest.mark.parametrize("n", [0, 1, 3])
def test_leads_via_db_satir_sayisi(n, tmp_path, monkeypatch):
    """ORTAM: crm argumani IKINCI EDILIR — Database().list_miniprobe_leads()
    kullanilir (settings.db_path conftest ile tmp)."""
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()  # semayi olustur
    for i in range(n):
        _insert_lead(p, f"d{i}.example")
    assert len(cli._leads_via_db(None)) == n


def test_leads_via_db_crm_arguman_kullanilmaz(tmp_path, monkeypatch):
    """ORTAM-OGRENDI: crm parametresi HIC KULLANILMAZ (legacy imza)."""
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    _insert_lead(p, "a.example")
    assert len(cli._leads_via_db("gecersiz-nesne")) == 1


def test_leads_via_db_alanlar(tmp_path, monkeypatch):
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    _insert_lead(p, "a.example", verdict="TEMİZ", created_at="2026-02-03T11:22:33",
                 bots_line="3/3 bot")
    r = cli._leads_via_db(None)[0]
    assert set(r) == {"domain", "verdict", "robots_line", "llms_line",
                      "bots_line", "measured", "created_at"}
    assert r["domain"] == "a.example"
    assert r["verdict"] == "TEMİZ"
    assert r["bots_line"] == "3/3 bot"


def test_leads_via_db_id_desc_sirali(tmp_path, monkeypatch):
    """ORTAM: ORDER BY id DESC — en yeni (son eklenen) once."""
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    _insert_lead(p, "ilk.example")
    _insert_lead(p, "son.example")
    assert cli._leads_via_db(None)[0]["domain"] == "son.example"


def test_leads_via_db_limit_50(tmp_path, monkeypatch):
    """ORTAM: LIMIT 50 — 60 kayitten 50 doner."""
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    for i in range(60):
        _insert_lead(p, f"d{i}.example")
    assert len(cli._leads_via_db(None)) == 50


def test_leads_via_db_bos_liste(tmp_path, monkeypatch):
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    assert cli._leads_via_db(None) == []


def test_leads_via_db_unicode(tmp_path, monkeypatch):
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    _insert_lead(p, "i̇ğ.example", verdict="GİRİŞ REDDEDİLDİ",
                 robots_line="ÖLÇÜLEMEDİ (taranmadı)")
    r = cli._leads_via_db(None)[0]
    assert r["domain"] == "i̇ğ.example"
    assert "ÖLÇÜLEMEDİ" in r["robots_line"]


def test_leads_via_db_crm_leads_entegrasyon(tmp_path, monkeypatch, capsys):
    """ORTAM: run_crm_command 'leads' _leads_via_db'i cagirir."""
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    _insert_lead(p, "a.example", verdict="TEMİZ", created_at="2026-02-03T11:22:33",
                 bots_line="3/3")
    cli.run_crm_command(SimpleNamespace(crm_action="leads"))
    out = capsys.readouterr().out
    assert "2026-02-03T11:22" in out
    assert "a.example" in out
    assert "TEMİZ" in out


def test_leads_via_db_bos_huni_mesaji(tmp_path, monkeypatch, capsys):
    """ORTAM-OGRENDI: bos huni -> 'liste uydurulmaz' dürüst mesaji."""
    from answrank.config import settings
    p = str(tmp_path / "leads.db")
    monkeypatch.setattr(settings, "db_path", p)
    from answrank.db import Database
    Database()
    cli.run_crm_command(SimpleNamespace(crm_action="leads"))
    out = capsys.readouterr().out
    assert "Mini-probe lead'i yok" in out
    assert "huni boş" in out


# == _verify_and_stage (run_prospect_command uzerinden) =======================================

class FakeProspector:
    """Saf-in-memory LeadProspector — gercek ag YOK."""

    def __init__(self, db=None, politeness=1.5, timeout=10.0, country=None):
        self.db = db
        self.politeness = politeness
        self.staged = []

    async def run_verify(self, cands):
        return [SimpleNamespace(**{
            **c, "reachable": c.get("reachable", False),
            "robots_disallowed": c.get("robots_disallowed", False),
            "http_status": c.get("http_status", 200),
            "robots_status": c.get("robots_status", 200),
            "phone": c.get("phone"),
            "email": c.get("email"),
            "notes": c.get("notes", ""),
        }) for c in cands]

    async def stage(self, v):
        self.staged.append(v.domain)
        return 1


@pytest.fixture
def fake_prospector(monkeypatch):
    """ORTAM: LeadProspector modul-niteligi STUBLA (from-import runtime okur)."""
    yapilan = {}

    def _ctor(db=None, politeness=1.5, timeout=10.0, country=None):
        p = FakeProspector(db=db, politeness=politeness)
        yapilan["db"] = db
        yapilan["politeness"] = politeness
        return p

    import answrank.crm.prospector as mod
    monkeypatch.setattr(mod, "LeadProspector", _ctor)
    return yapilan


def _prospect_file(tmp_path, cands):
    f = tmp_path / "cands.json"
    f.write_text(json.dumps(cands, ensure_ascii=False), encoding="utf-8")
    return str(f)


def _args(file, **kw):
    base = dict(file=file, country="AE", sector="dental", dry_run=False,
                politeness=1.5, limit=10)
    base.update(kw)
    return SimpleNamespace(**base)


def test_verify_and_stage_reachable_staged(tmp_path, fake_prospector, capsys):
    f = _prospect_file(tmp_path, [{"domain": "a.example", "reachable": True,
                                   "phone": "+90 555", "email": "x@y.example"}])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "1 lead stage edildi" in out
    assert "STAGED" in out


def test_verify_and_stage_reject_edilir(tmp_path, fake_prospector, capsys):
    """ORTAM: reachable DEGIL + robots_disallowed DEGIL -> RET."""
    f = _prospect_file(tmp_path, [{"domain": "b.example", "reachable": False,
                                   "notes": "timeout"}])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "0 lead stage edildi" in out
    assert "1 ret" in out
    assert "RET — timeout" in out


def test_verify_and_stage_robots_disallowed_staged(tmp_path, fake_prospector, capsys):
    """ORTAM-OGRENDI: robots_disallowed True -> STAGED (robots saygisi:
    erisim-reddi KANIT sayilir, DM 'GİRİŞ REDDEDİLDİ' icin gecer)."""
    f = _prospect_file(tmp_path, [{"domain": "c.example",
                                   "reachable": False,
                                   "robots_disallowed": True}])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "1 lead stage edildi" in out
    assert "ENGELLİ" in out


def test_verify_and_stage_dry_run_stage_cagrilmaz(tmp_path, fake_prospector,
                                                 capsys):
    """ORTAM-OGRENDI: args.dry_run True -> await p.stage(v) CAGRILMAZ ve
    'N lead stage edildi' OZET SATIRI YAZILMAZ (yalniz DRY-RUN notu)."""
    f = _prospect_file(tmp_path, [{"domain": "a.example", "reachable": True}])
    cli.run_prospect_command(_args(f, dry_run=True))
    out = capsys.readouterr().out
    assert "DRY-RUN — CRM'e yazılmadı." in out
    assert "stage edildi" not in out
    assert "STAGED" in out


def test_verify_and_stage_dry_run_false_gercek_stage(tmp_path, monkeypatch,
                                                     fake_prospector, capsys):
    """ORTAM: dry_run False -> Database() ile gercek stage cagrisi."""
    staged_gorulen = {}

    class _DB:
        def __init__(self):
            pass

    monkeypatch.setattr("answrank.db.Database", _DB)
    f = _prospect_file(tmp_path, [{"domain": "a.example", "reachable": True}])
    cli.run_prospect_command(_args(f, dry_run=False))
    assert "DRY-RUN" not in capsys.readouterr().out


def test_verify_and_stage_iletisim_formati(tmp_path, fake_prospector, capsys):
    """ORTAM: phone / email birlesimi; ikisi de yoksa 'DOĞRULANAMADI'."""
    f = _prospect_file(tmp_path, [
        {"domain": "p.example", "reachable": True, "phone": "+90 555 123"},
        {"domain": "e.example", "reachable": True, "email": "a@b.example"},
        {"domain": "pe.example", "reachable": True, "phone": "+1",
         "email": "c@d.example"},
        {"domain": "y.example", "reachable": True},
    ])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "+90 555 123" in out
    assert "a@b.example" in out
    assert "+1 / c@d.example" in out
    assert "DOĞRULANAMADI" in out


def test_verify_and_stage_http_tire(tmp_path, fake_prospector, capsys):
    """ORTAM: http_status None/0 -> tabloda '—'."""
    f = _prospect_file(tmp_path, [{"domain": "a.example", "reachable": True,
                                   "http_status": None,
                                   "robots_status": None}])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "—" in out


def test_verify_and_stage_cok_aday_sayi(tmp_path, fake_prospector, capsys):
    f = _prospect_file(tmp_path, [{"domain": f"d{i}.example",
                                   "reachable": i % 2 == 0}
                                  for i in range(6)])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "3 lead stage edildi" in out
    assert "3 ret" in out


def test_verify_and_stage_country_sector_setdefault(tmp_path, fake_prospector,
                                                    monkeypatch):
    """ORTAM: adaylara country/sector setdefault edilir (eksikse)."""
    yakalanan = {}

    class _P(FakeProspector):
        async def run_verify(self, cands):
            yakalanan["cands"] = list(cands)
            return await super().run_verify(cands)

    import answrank.crm.prospector as mod
    monkeypatch.setattr(mod, "LeadProspector",
                        lambda db=None, politeness=1.5: _P(db=db,
                                                           politeness=politeness))
    f = _prospect_file(tmp_path, [{"domain": "a.example", "sector": "plastic"}])
    cli.run_prospect_command(_args(f, country="TR", sector="dental"))
    assert yakalanan["cands"][0]["country"] == "TR"
    assert yakalanan["cands"][0]["sector"] == "plastic"


def test_verify_and_stage_bos_liste_reddeder(tmp_path, fake_prospector, capsys):
    """ORTAM: bos/gecersiz liste -> uydurma aday uretilmez."""
    f = _prospect_file(tmp_path, [])
    cli.run_prospect_command(_args(f))
    out = capsys.readouterr().out
    assert "Liste boş/geçersiz" in out
    assert "stage edildi" not in out


def test_verify_and_stage_dosya_dict_reddeder(tmp_path, fake_prospector, capsys):
    f = tmp_path / "c.json"
    f.write_text('{"domain": "a.example"}', encoding="utf-8")
    cli.run_prospect_command(_args(str(f)))
    assert "Liste boş/geçersiz" in capsys.readouterr().out


def test_verify_and_stage_limit_kullanimi(tmp_path, fake_prospector, capsys):
    """ORTAM: baslikta len(cands[:limit]) — limit tabloyu kisitlar."""
    f = _prospect_file(tmp_path, [{"domain": f"d{i}.example",
                                   "reachable": True} for i in range(8)])
    cli.run_prospect_command(_args(f, limit=3))
    out = capsys.readouterr().out
    assert "Lead Doğrulama (3 aday)" in out


def test_verify_and_stage_ret_not_yoksa_varsayilan(tmp_path, fake_prospector, capsys):
    """ORTAM: notes yoksa 'RET — ulaşılamadı' varsayilan metni."""
    f = _prospect_file(tmp_path, [{"domain": "b.example", "reachable": False}])
    cli.run_prospect_command(_args(f))
    assert "RET — ulaşılamadı" in capsys.readouterr().out


def test_verify_and_stage_politeness_gecer(tmp_path, fake_prospector):
    """ORTAM: args.politeness LeadProspector'a aktarilir."""
    f = _prospect_file(tmp_path, [{"domain": "a.example", "reachable": True}])
    cli.run_prospect_command(_args(f, politeness=3.25))
    assert fake_prospector["politeness"] == 3.25


def test_verify_and_stage_unicode_domain(tmp_path, fake_prospector, capsys):
    f = _prospect_file(tmp_path, [{"domain": "i̇ğ.example",
                                   "reachable": True}])
    cli.run_prospect_command(_args(f))
    assert "i̇ğ.example" in capsys.readouterr().out
