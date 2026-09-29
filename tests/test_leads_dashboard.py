"""E7 (D-16.09-M/4 — yalnız lead-gen): halka-açık mini-probe'un CRM huni bağlantısı.

Dürüstlük sınırının çizgisi: lead DM'i YENİDEN ÖLÇMEZ ve SKOR ÜRETMEZ — yalnızca
ziyaretçinin kendi probe'unda ölçülmüş üç satır alıntılanır. IP loglanmaz (tek
kiracılık + KVKK asgaricilik); GİRİŞ REDDEDİLDİ girişleri lead sayılmaz (geçerli
site değildir).
"""
import pytest

from answrank.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "lead.db"))


def _client(db, monkeypatch):
    from answrank.api import app as appmod
    monkeypatch.setattr(appmod, "db", db)
    from fastapi.testclient import TestClient
    from answrank.api.app import app
    return TestClient(app)


def test_probe_records_lead_only_when_real_site(db, monkeypatch):
    from answrank.probe import miniprobe as mp
    from answrank.probe.miniprobe import MiniProbeResult
    res = MiniProbeResult(domain="klinik-x.example", robots_line="İZİNLİ (AI araması açık)",
                          llms_line="YOK", bots_line="3/3 örnek bot erişebiliyor",
                          blocked_bots=[], probed=3, verdict="TEMİZ", measured=True,
                          robots_status=200, llms_status=404,
                          bot_statuses={"GPTBot": 200, "PerplexityBot": 200, "ClaudeBot": 200})
    monkeypatch.setattr(mp.MiniProbe, "run", classmethod(lambda cls, raw, timeout_sec=6.0: _ret(res)))
    client = _client(db, monkeypatch)
    r = client.post("/api/miniprobe", json={"domain": "klinik-x.example"})
    assert r.status_code == 200
    leads = client.get("/api/leads").json()["leads"]
    assert len(leads) == 1 and leads[0]["domain"] == "klinik-x.example"
    assert leads[0]["verdict"] == "TEMİZ" and "3/3" in leads[0]["bots_line"]
    assert "ip" not in leads[0] and "client_ip" not in leads[0]  # IP asla tutulmaz


async def _ret(res):
    return res


def test_rejected_inputs_are_not_leads(db, monkeypatch):
    client = _client(db, monkeypatch)
    r = client.post("/api/miniprobe", json={"domain": "127.0.0.1"})
    assert r.status_code == 200  # reddedilir ama 200 + GİRİŞ REDDEDİLDİ
    assert client.get("/api/leads").json()["leads"] == []


def test_lead_dm_uses_only_measured_lines_no_scores(db, monkeypatch, tmp_path, capsys):
    import sys
    from answrank.config import settings
    row = {"domain": "abc-klinik.example", "verdict": "BOT ERİŞİMİ ENGELLİ",
           "robots_line": "İZİNLİ (AI araması açık)", "llms_line": "YOK",
           "bots_line": "2/3 örnek bot ENGELLİ: GPTBot, ClaudeBot", "measured": 1}
    with db._get_connection() as c:
        c.execute("INSERT INTO miniprobe_leads (domain, verdict, robots_line, llms_line,"
                  " bots_line, measured, created_at) VALUES (?,?,?,?,?,?,?)",
                  (row["domain"], row["verdict"], row["robots_line"], row["llms_line"],
                   row["bots_line"], 1, "2026-09-16T00:00:00"))
        c.commit()
    monkeypatch.setattr(settings, "db_path", str(db.db_path))
    monkeypatch.setattr(sys, "argv", ["answrank", "crm", "draft", "--from-lead",
                                      "abc-klinik.example"])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "2/3 örnek bot ENGELLİ" in out and "GPTBot" in out
    for banned in ("puan", "₺", "%", "0-100", "skor:"):  # "skor DEĞİL" meşru cümlesi serbest
        assert banned not in out.lower()
    assert "abc-klinik.example" in out


def test_crm_leads_cli_lists(db, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    with db._get_connection() as c:
        c.execute("INSERT INTO miniprobe_leads (domain, verdict, robots_line, llms_line,"
                  " bots_line, measured, created_at) VALUES (?,?,?,?,?,?,?)",
                  ("y.example", "TEMİZ", "İZİNLİ", "VAR", "3/3", 1, "2026-09-16T00:00:00"))
        c.commit()
    monkeypatch.setattr(settings, "db_path", str(db.db_path))
    monkeypatch.setattr(sys, "argv", ["answrank", "crm", "leads"])
    from answrank.cli import main
    main()
    assert "y.example" in " ".join(capsys.readouterr().out.split())
    with db._get_connection() as c:
        c.execute("DELETE FROM miniprobe_leads")
        c.commit()
    main()
    assert "liste uydurulmaz" in " ".join(capsys.readouterr().out.split()).lower()


def test_dashboard_has_monitor_panel_hook():
    tpl = open("answrank/api/templates/dashboard.html", encoding="utf-8").read()
    assert "GEO İzleme" in tpl and "/api/monitors" in tpl
    assert "ÖLÇÜLEMEDİ" in tpl  # panelin boş durumu bile dürüst etiketli


def test_draft_from_lead_without_measurement_refuses(db, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    monkeypatch.setattr(settings, "db_path", str(db.db_path))
    monkeypatch.setattr(sys, "argv", ["answrank", "crm", "draft", "--from-lead", "yok.example"])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "ÖLÇÜMLÜ mini-probe lead'i yok" in out and "uydurulmaz" in out
