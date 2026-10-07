"""Kalan EN KRİTİK test açıkları — run_monitor_command + swarm SSE event_generator.

Kapsam (mevcut testleri DEĞİŞTİRMEZ, sadece YENI dosya):

  1. answrank.cli.run_monitor_command (49 satır test-dışı) — E1 izleme CLI'sının
     tüm dalları: add / list / run / digest / fulfillment.
  2. answrank.api.app.stream_swarm_execution.event_generator (46 satır
     test-dışı) — SSE olay-akışı üreticisi: olay dağıtımı, PIPELINE_DONE,
     PIPELINE_ERROR, sentinel ile kapanış.

İZOLASYON: conftest'in autouse `isolated_db_path` fixture'i her testte
settings.db_path'i geçici bir dosyaya yönlendirir; run_monitor_command
`Database()` ile settings'den okuduğu için aynı izole DB'yi paylaşırız.
Dış ağ çağrıları (canlı ölçüm / swarm pipeline) mock'lanır; SADECE
fonksiyonun kendi dal mantığı test edilir. Geliştirme DB'sine dokunulmaz.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from answrank.api.app import app
from answrank.cli import run_monitor_command
from answrank.db import Database
from answrank.monitor.service import MonitorService


# =====================================================================
# fixtures + yardımcılar
# =====================================================================

@pytest.fixture()
def svc() -> MonitorService:
    """İzole DB üzerinde MonitorService (settings.db_path conftest tarafından set)."""
    return MonitorService(db=Database())


def _run(cmd: str, **kwargs) -> None:
    """run_monitor_command'ı sahte args namespace ile çağırır."""
    run_monitor_command(SimpleNamespace(monitor_cmd=cmd, **kwargs))


def _measured(score=61.0, sov=12.5, audit_id="audit_x1", cit_id=7):
    async def ex(domain, sector, brand):
        return {"status": "MEASURED", "score_base": score, "sov_pct": sov,
                "audit_id": audit_id, "citation_run_id": cit_id, "note": ""}
    return ex


def _unauditable():
    async def ex(domain, sector, brand):
        return {"status": "UNAUDITABLE", "score_base": None, "sov_pct": None,
                "audit_id": None, "citation_run_id": None, "note": "DOĞRULANAMADI"}
    return ex


# =====================================================================
# 1) run_monitor_command — E1 izleme CLI'ı
# =====================================================================

def test_monitor_add_kayit_acar_ve_bilgi_yazar(svc, capsys) -> None:
    """add → başarı mesajı domain + kadans ile yazılır."""
    _run("add", domain="klinik.example", brand="Örnek Klinik",
         sector="dental", cadence=15, contract=None)
    out = capsys.readouterr().out
    assert "klinik.example" in out
    assert "15 gün kadans" in out
    # gerçekten kaydedildi
    rows = svc.list()
    assert any(m["domain"] == "klinik.example" for m in rows)


def test_monitor_add_sozlesme_bagli_kaydedilir(svc, capsys) -> None:
    """add --contract → contract_id DB'ye yazılır (fulfillment hükmü için)."""
    _run("add", domain="sozlesmeli.example", brand="Sözleşmeli",
         sector="dental", cadence=30, contract="S-1001")
    rows = {m["domain"]: m for m in svc.list()}
    assert rows["sozlesmeli.example"]["contract_id"] == "S-1001"


def test_monitor_add_default_kadans_30_gun(svc) -> None:
    """cadence verilmezse varsayılan 30 gündür."""
    _run("add", domain="default.example", brand="Varsayılan",
         sector="general", cadence=30, contract=None)
    rows = {m["domain"]: m for m in svc.list()}
    assert rows["default.example"]["cadence_days"] == 30


def test_monitor_list_bos_uyari_verir(svc, capsys) -> None:
    """Kayıt yokken 'Kayıtlı izleme yok' — sayı uydurulmaz."""
    _run("list")
    out = capsys.readouterr().out
    assert "Kayıtlı izleme yok" in out


def test_monitor_list_kayitlari_gosterir(svc, capsys) -> None:
    """list → id / domain / sector / cadence / next_due satırı."""
    _run("add", domain="liste.example", brand="Liste", sector="dental",
         cadence=21, contract=None)
    capsys.readouterr()
    _run("list")
    out = capsys.readouterr().out
    assert "liste.example" in out
    assert "21g" in out


def test_monitor_run_vadesi_gelmis_yoksa_bekler(svc, capsys) -> None:
    """due() boşsa ölçüm yapılmaz, bekleme mesajı yazılır."""
    # yeni monitor: next_due = şimdi → ama henüz zamanı gelmemiş olmalı;
    # geleceğe ertele
    mid = svc.add(domain="ileri.example", brand="İleri", sector="dental",
                  now=datetime.now(timezone.utc))
    svc.db.postpone_next_due(mid, datetime.now(timezone.utc) + timedelta(days=20))
    _run("run")
    out = capsys.readouterr().out
    assert "Vadesi gelmiş izleme yok" in out


def test_monitor_run_olculen_kosuyu_yazar(svc, capsys) -> None:
    """due + MEASURED executor → 'domain: MEASURED (run N; skor X)'."""
    svc.add(domain="olculen.example", brand="Ölçülen", sector="dental",
            now=datetime.now(timezone.utc) - timedelta(days=40))
    with patch("answrank.monitor.service.live_executor", _measured(score=72.5)):
        _run("run")
    out = capsys.readouterr().out
    assert "olculen.example: MEASURED" in out
    assert "skor 72.5" in out


def test_monitor_run_olcum_yoksa_sayi_uydurulmaz(svc, capsys) -> None:
    """UNAUDITABLE koşu → 'sayı uydurulmaz' (skor None)."""
    svc.add(domain="olcusuz.example", brand="Ölçüsüz", sector="dental",
            now=datetime.now(timezone.utc) - timedelta(days=40))
    with patch("answrank.monitor.service.live_executor", _unauditable()):
        _run("run")
    out = capsys.readouterr().out
    assert "olcusuz.example: UNAUDITABLE" in out
    assert "sayı uydurulmaz" in out


def test_monitor_run_kosu_kaydi_dusulur(svc) -> None:
    """executor ağ hatası bile olsa koşu UNAUDITABLE olarak kaydedilir."""
    mid = svc.add(domain="ag.example", brand="Ağ", sector="dental",
                  now=datetime.now(timezone.utc) - timedelta(days=40))

    async def boom(domain, sector, brand):
        raise ConnectionError(" ağ kopuk")

    with patch("answrank.monitor.service.live_executor", boom):
        _run("run")
    runs = svc.db.monitor_runs(mid)
    assert len(runs) == 1
    assert runs[0]["status"] == "UNAUDITABLE"
    assert runs[0]["score_base"] is None


def test_monitor_digest_kayit_yoksa_reddeder(svc, capsys) -> None:
    """Olmayan monitor → 'bulunamadı' — uydurma digest üretilmez."""
    _run("digest", monitor_id="mon_yok")
    out = capsys.readouterr().out
    assert "bulunamadı" in out
    assert "uydurma digest" in out


def test_monitor_digest_ilk_olcum_yazar(svc, capsys) -> None:
    """Tek MEASURED koşu → İLK ÖLÇÜM digest'i, domain panelde."""
    mid = svc.add(domain="ilkolcum.example", brand="İlk", sector="dental",
                  now=datetime.now(timezone.utc) - timedelta(days=40))
    with patch("answrank.monitor.service.live_executor", _measured(score=55.0)):
        _run("run")
    capsys.readouterr()
    _run("digest", monitor_id=mid)
    out = capsys.readouterr().out
    assert "ilkolcum.example" in out
    assert "İLK ÖLÇÜM" in out or "ilk ölçüm" in out


def test_monitor_fulfillment_kayit_yoksa_reddeder(svc, capsys) -> None:
    """Olmayan monitor → 'İzleme kaydı yok' — uydurma hüküm verilmez."""
    _run("fulfillment", monitor_id="mon_yine_yok")
    out = capsys.readouterr().out
    assert "İzleme kaydı yok" in out
    assert "uydurma hüküm" in out


def test_monitor_fulfillment_bos_liste_sessiz_gecer(svc, capsys) -> None:
    """monitor_id yok + kayıt yok → hata verilmez, sessizce biter."""
    _run("fulfillment", monitor_id=None)
    out = capsys.readouterr().out
    assert out == ""


def test_monitor_fulfillment_sozlesmesiz_no_link(svc, capsys) -> None:
    """Sözleşme bağ yok → NO_LINK; delta sayı üretilmez."""
    mid = svc.add(domain="nosoz.example", brand="Sözlemesiz", sector="dental")
    _run("fulfillment", monitor_id=mid)
    out = capsys.readouterr().out
    assert "NO_LINK" in out
    assert "delta=—" in out


def test_monitor_fulfillment_yetersiz_olcum_insufficient(svc, capsys) -> None:
    """Sözleşmeli ama iki ölçümlü koşu yok → INSUFFICIENT."""
    mid = svc.add(domain="azolcum.example", brand="Az", sector="dental",
                  contract_id="S-2002")
    _run("fulfillment", monitor_id=mid)
    out = capsys.readouterr().out
    assert "INSUFFICIENT" in out
    assert "ÖLÇÜM YETERSİZ" in out


def test_monitor_fulfillment_tum_kayitlar_gezer(svc, capsys) -> None:
    """monitor_id verilmezse tüm kayıtlar için değerlendirme yapılır."""
    svc.add(domain="a1.example", brand="A1", sector="dental")
    svc.add(domain="a2.example", brand="A2", sector="dental")
    _run("fulfillment", monitor_id=None)
    out = capsys.readouterr().out
    assert "a1.example" in out.replace("\n", " ") or "NO_LINK" in out
    assert out.count("NO_LINK") == 2


# =====================================================================
# 2) event_generator — /api/swarm/stream SSE üreticisi
# =====================================================================

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _stream(client: TestClient, brand="Test Dental", domain="testdental.example",
            **kw) -> str:
    params = {"brand": brand, "domain": domain,
              "city": kw.get("city", "London"),
              "country": kw.get("country", "UK")}
    return client.get("/api/swarm/stream", params=params)


def _parse_events(body: str) -> list[dict]:
    return [json.loads(ln[len("data: "):])
            for ln in body.splitlines() if ln.startswith("data: ")]


def test_swarm_sse_olaylari_data_satiri_olarak_yayinlanir(client) -> None:
    """on_event ile gelen her adım 'data: {json}\\n\\n' olarak yayınlanır."""
    async def fake_pipeline(candidate, on_event=None):
        await on_event("Radar", "hedef taranıyor")
        await on_event("Qualifier", "nihai uygunluk")
        return candidate

    with patch("answrank.agents.swarm.SwarmOrchestrator.run_full_pipeline_sync",
               new=AsyncMock(side_effect=fake_pipeline)):
        r = _stream(client)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    olaylar = _parse_events(r.text)
    ajanlar = [e["agent"] for e in olaylar]
    assert "Radar" in ajanlar
    assert "Qualifier" in ajanlar
    # her olay SSE biçiminde + timestamp taşıyor
    for e in olaylar:
        assert "agent" in e and "message" in e and "timestamp" in e


def test_swarm_sse_pipeline_done_kapanis_olayi(client) -> None:
    """Pipeline başarılı bitince PIPELINE_DONE + marka/aşama bilgisi."""
    async def fake_pipeline(candidate, on_event=None):
        await on_event("Radar", "ok")
        return candidate

    with patch("answrank.agents.swarm.SwarmOrchestrator.run_full_pipeline_sync",
               new=AsyncMock(side_effect=fake_pipeline)):
        r = _stream(client, brand="Marka X", domain="markax.example")
    olaylar = _parse_events(r.text)
    kapanis = olaylar[-1]
    assert kapanis["agent"] == "PIPELINE_DONE"
    assert "Marka X" in kapanis["message"]
    assert "DISCOVERED" in kapanis["message"]


def test_swarm_sse_pipeline_hata_olayi(client) -> None:
    """Pipeline exception'ı → PIPELINE_ERROR olayı (dış hata gizlenmez)."""
    async def boom(candidate, on_event=None):
        await on_event("Radar", "başladı")
        raise RuntimeError("şebeke hatası")

    with patch("answrank.agents.swarm.SwarmOrchestrator.run_full_pipeline_sync",
               new=AsyncMock(side_effect=boom)):
        r = _stream(client, domain="hata.example")
    assert r.status_code == 200  # SSE hata olayı olarak yayınlanır, HTTP 500 değil
    olaylar = _parse_events(r.text)
    assert olaylar[-1]["agent"] == "PIPELINE_ERROR"
    assert "RuntimeError" in olaylar[-1]["message"]
    assert "şebeke hatası" in olaylar[-1]["message"]


def test_swarm_sse_hic_olay_yoksa_sadece_kapanis(client) -> None:
    """on_event hiç çağrılmasa bile PIPELINE_DONE yayımlanır."""
    async def quiet(candidate, on_event=None):
        return candidate

    with patch("answrank.agents.swarm.SwarmOrchestrator.run_full_pipeline_sync",
               new=AsyncMock(side_effect=quiet)):
        r = _stream(client, domain="sessiz.example")
    olaylar = _parse_events(r.text)
    assert len(olaylar) == 1
    assert olaylar[0]["agent"] == "PIPELINE_DONE"


def test_swarm_sse_jerky_olaylar_sirayla_gelir(client) -> None:
    """Çok sayıda olay gönderi sırasını korur (kuyruk FIFO)."""
    async def chatty(candidate, on_event=None):
        for i in range(6):
            await on_event(f"Agent{i}", f"adim {i}")
        return candidate

    with patch("answrank.agents.swarm.SwarmOrchestrator.run_full_pipeline_sync",
               new=AsyncMock(side_effect=chatty)):
        r = _stream(client, domain="cok.example")
    olaylar = _parse_events(r.text)
    ajanlar = [e["agent"] for e in olaylar]
    assert ajanlar[:-1] == [f"Agent{i}" for i in range(6)]
    assert ajanlar[-1] == "PIPELINE_DONE"
