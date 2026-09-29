"""E5 araştırma korpüsü (D-16.09-M kapanışı sonrası otonom tur): mini-probe
gözlemlerinin kalıcı arşivi + istatistik-kapısı. KURAL: yüzde yalnız O ALANI
ÖLÇEBİLDİĞİMİZ satırların paydasıyla üretilir; payda 0 ise satır yok — sayı yok."""
import asyncio
import pytest

from answrank.corpus import CorpusStore, render_report_md
from answrank.db import Database
from answrank.probe.miniprobe import MiniProbeResult


def _obs(domain, robots=200, llms=404, bots=200, measured=True, verdict="TEMİZ"):
    return MiniProbeResult(
        domain=domain,
        robots_line=("İZİNLİ (AI araması açık)" if robots == 200 else
                     "ENGELLİ (robots.txt AI aramasını kapatıyor)") if measured
                    else "ÖLÇÜLEMEDİ (robots.txt indirilemedi)",
        llms_line=("VAR" if llms == 200 else "YOK") if measured else "ÖLÇÜLEMEDİ", bots_line="3/3 örnek bot erişebiliyor" if measured else "HÜKÜM VERİLEMEDİ (probe koşulmadı)",
        blocked_bots=[] if measured else ["GPTBot", "PerplexityBot", "ClaudeBot"],
        probed=3 if measured else 0, verdict=verdict, measured=measured,
    )


@pytest.fixture
def store(tmp_path):
    return CorpusStore(db=Database(db_path=str(tmp_path / "c.db")))


def test_save_and_list_roundtrip(store):
    store.save_observation(_obs("a.example"), source="corpus-v1")
    rows = store.list_observations()
    assert len(rows) == 1 and rows[0]["domain"] == "a.example"
    assert rows[0]["source"] == "corpus-v1"


def test_collect_politeness_and_crash_rows(store, monkeypatch):
    calls = []

    async def fake_run(raw, timeout_sec=6.0):
        calls.append(raw)
        if "bozuk" in raw:
            raise RuntimeError("iç hata sızıntı yapmasın")
        return _obs(raw.split("//")[-1])
    import answrank.corpus as cp
    monkeypatch.setattr(cp.MiniProbe, "run", staticmethod(fake_run))
    sleeps = []
    real_sleep = asyncio.sleep
    async def spy_sleep(x): sleeps.append(x); await real_sleep(0)
    monkeypatch.setattr(cp.asyncio, "sleep", spy_sleep)
    n = asyncio.run(store.collect(["https://a.example", "https://bozuk.example", "https://b.example"],
                                  politeness_sec=0.5, source="t"))
    assert n == 3
    rows = {r["domain"]: r for r in store.list_observations()}
    assert rows["a.example"]["measured"] == 1
    assert rows["bozk.example" if False else "bozuk.example"]["measured"] == 0
    assert "iç hata" not in (rows["bozuk.example"]["note"] or "")  # hata detayı arşivlenmez
    assert sleeps == [0.5, 0.5]  # ilk probesiz nazik aralık


def test_stats_denominator_only_measured(store):
    for i in range(4):
        store.save_observation(_obs(f"k{i}.example", robots=200 if i < 2 else 403, llms=200 if i == 0 else 404,
                                    bots=200 if i < 2 else 403,
                                    measured=(i != 3), verdict="TEMİZ" if i < 3 else "ÖLÇÜLEMEDİ"),
                               source="s")
    st = store.stats()
    # robots: 3 ölçüldü (4. satır measured=False), 2 açık → %66.7 (3 payda)
    assert st["robots_open_pct"]["n"] == 3 and st["robots_llms_present"]["n"] == 3
    assert abs(st["robots_open_pct"]["pct"] - (2 / 3 * 100)) < 0.1
    assert st["unmeasured_rows"] == 1


def test_stats_zero_measurements_no_numbers(store):
    for i in range(3):
        store.save_observation(_obs(f"u{i}.example", measured=False, verdict="ÖLÇÜLEMEDİ"), source="s")
    st = store.stats()
    assert st["n"] == 3
    report = render_report_md(st, method="test")
    low = report.lower()
    assert "%" not in report.split("Bulgular")[1] if "Bulgular" in report else "%" not in report
    assert "ölçülemedi" in low or "uydur" in low


def test_report_has_method_and_honest_labels(store):
    store.save_observation(_obs("r.example"), source="v1")
    st = store.stats()
    md = render_report_md(st, method="kamuya açık domain örneklemi; yalnız robots/llms/bot-yüzeyi")
    assert "Yöntem" in md and "kamuya açık" in md
    assert "ÖLÇÜLEMEDİ" in md
    assert "n=1" in md


def test_cli_corpus_empty_does_not_fabricate(tmp_path, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    monkeypatch.setenv("ANSWRANK_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "cli.db"))
    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "stats"])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "korpus boş" in out.lower() or "uydur" in out.lower()


def test_cli_corpus_probe_stats_and_source_filter(tmp_path, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    from answrank.corpus import CorpusStore
    from answrank.db import Database
    dbp = str(tmp_path / "cli2.db")
    monkeypatch.setattr(settings, "db_path", dbp)
    store = CorpusStore(db=Database(db_path=dbp))
    store.save_observation(_obs("filtre.example"), source="cerceve-a")
    assert [r["domain"] for r in store.list_observations(source="cerceve-a")] == ["filtre.example"]
    assert store.list_observations(source="bos-etiket") == []

    lst = tmp_path / "domains.txt"
    lst.write_text("# yorum satırı\nhttps://canli.example\n\n", encoding="utf-8")
    import answrank.corpus as cp

    async def fake_run(raw, timeout_sec=6.0):
        return _obs(raw.split("//")[-1])
    monkeypatch.setattr(cp.MiniProbe, "run", staticmethod(fake_run))
    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "probe", "--file", str(lst),
                                      "--tag", "cerceve-b", "--politeness", "0"])
    from answrank.cli import main
    main()
    out = " ".join(capsys.readouterr().out.split())
    assert "1 gözlem arşivlendi" in out

    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "stats", "--tag", "cerceve-a",
                                      "--out", str(tmp_path / "rep.md")])
    main()
    assert "n=1" in (tmp_path / "rep.md").read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "list", "--tag", "cerceve-a"]
                        if False else ["answrank", "corpus", "list"])
    main()
    assert "filtre.example" in " ".join(capsys.readouterr().out.split())

    empty = tmp_path / "e.txt"
    empty.write_text("# yalnız yorum\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "probe", "--file", str(empty)])
    main()
    assert "ölçüm yapılmaz" in " ".join(capsys.readouterr().out.split())


def test_cli_corpus_stats_print_and_empty_list(tmp_path, monkeypatch, capsys):
    import sys
    from answrank.config import settings
    from answrank.corpus import CorpusStore
    from answrank.db import Database
    dbp = str(tmp_path / "p.db")
    monkeypatch.setattr(settings, "db_path", dbp)
    CorpusStore(db=Database(db_path=dbp)).save_observation(_obs("p.example"), source="t")
    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "stats"])
    from answrank.cli import main
    main()
    assert "GEO Korpüs İstatistiği" in capsys.readouterr().out
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "empty.db"))
    monkeypatch.setattr(sys, "argv", ["answrank", "corpus", "list"])
    main()
    assert "Kayıtlı gözlem yok" in " ".join(capsys.readouterr().out.split())
