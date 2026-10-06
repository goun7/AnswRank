"""IKINCI GRUP: EN KRITIK test-disi fonksiyonlar icin dal-kesen unit testler (2026-10-06).

Hedefler (AST ile tespit edildi; tests/ icinde kendi adlariyla cagrilmayanlar,
guvenlik/finans oncelikli secildi):
  1. imap_izle.py:216                        klasor_postalari        (92L; guvenilmeyen e-posta isleme — EN BUYUK test-disi fonksiyon)
  2. answrank/api/app.py:760                 stream_swarm_execution  (69L; SSE akisi — her olay gercek yurutulen adima karsilik)
  3. x402_servis.py:315                      olcum_rapor             (48L; odeme servisi A/B raporu — durustluk/uydurma-yok kurali)
  4. answrank/finance/tax_ledger.py:368      generate_fiscal_summary (47L; mali mustavir-hazir vergi ozeti — KVK 10/ğ & GVK 89/13)
  5. answrank/api/app.py:839                 check_territory_lock_api(36L; bolge munhasirlik kilidi — bos domain ile sorgu reddi)

Yontem: her fonksiyonun GERCEK kodu okunup dallarina incelendi; dis cagrilar
(IMAP sunucusu, SwarmOrchestrator agi, Sester ledger/outbox durumu) mock'lanir
— yalnizca fonksiyonun KENDI mantigi (dal secimi, hata yuzeyi, durum gecisleri,
durustluk etiketleri) olculur. Sahte basarili olcum/odeme uretilmez.
"""
import asyncio
import email
import imaplib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

# ── x402_servis import-aninda fail-closed SystemExit atar (treasury+secret
#    ZORUNLU). Test ortaminda env mock'lanir — gercek servis BASLATILMAZ,
#    yalnizca fonksiyonlar cagrilir (0 gercek musteri, gercek odeme YOK).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(_ROOT))

os.environ.setdefault("UNPUMP_TREASURY_EOA", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
os.environ.setdefault("ANSWRANK_MAINNET_PAY_TO", "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5")
os.environ.setdefault("ANSWRANK_SELLER_SECRET", "test-only-secret-kritik2-grup")
# Ledger DB'si home dizinine DEGIL, gecici bir dizine yazilsin.
os.environ.setdefault(
    "ANSWRANK_DB",
    str(Path(tempfile.mkdtemp(prefix="kritik2-x402-")) / "receipts.sqlite"),
)

pytest.importorskip("sester")  # sibling Sester reposu (x402 dogfood)

import imap_izle  # noqa: E402
import x402_servis as xs  # noqa: E402

from answrank.api.app import (  # noqa: E402
    TerritoryCheckRequest,
    check_territory_lock_api,
    stream_swarm_execution,
)
from answrank.agents.swarm import SwarmCandidate, SwarmStage  # noqa: E402
from answrank.crm.exclusivity import (  # noqa: E402
    ConflictCheckResult,
    TerritoryLock,
)
from answrank.finance.tax_ledger import (  # noqa: E402
    FiscalInvoiceRecord,
    TaxLedger,
    TaxRegime,
)


# ════════════════════════════════════════════════════════════════════════════
# 1. imap_izle.klasor_postalari — guvenilmeyen e-posta isleme (92 satir)
# ════════════════════════════════════════════════════════════════════════════

def _eml(from_hdr, subject, mid=None, extra_lines=()):
    """RFC-8422 uyumlu minimal e-posta baytlari (gercek email parser ile cozulur)."""
    lines = ["From: " + from_hdr, "Subject: " + subject]
    if mid is not None:
        lines.append("Message-ID: <" + mid + ">")
    lines.extend(extra_lines)
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


class _FakeIMAP:
    """imaplib.IMAP4 taklidi — select/uid cagrilarini betimlenmis yanitlarla cevaplar.

    Hicbir yerde gercek IMAP sunucusuna baglanmaz (ag YOK).
    """

    def __init__(self, *, select_result=("OK", b""), select_error=False,
                 search_result=("OK", [b""]), search_error=False,
                 headers=None, bodies=None, fetch_errors=(), body_errors=(),
                 header_typ="OK", body_typ="OK", header_fd=None):
        self.select_result = select_result
        self.select_error = select_error
        self.search_result = search_result
        self.search_error = search_error
        self.headers = dict(headers or {})
        self.bodies = dict(bodies or {})
        self.fetch_errors = set(fetch_errors)
        self.body_errors = set(body_errors)
        self.header_typ = header_typ
        self.body_typ = body_typ
        self.header_fd = header_fd
        self.fetch_calls = []
        self.select_calls = []

    def select(self, folder, readonly=True):
        self.select_calls.append(folder)
        if self.select_error:
            raise imaplib.IMAP4.error("select: sanal hata")
        return self.select_result

    def uid(self, cmd, *args):
        if cmd == "search":
            if self.search_error:
                raise imaplib.IMAP4.error("search: sanal hata")
            return self.search_result
        if cmd == "fetch":
            uid, istek = args[0], args[1]
            uid_s = uid.decode()
            self.fetch_calls.append((uid_s, istek))
            if uid_s in self.fetch_errors:
                raise imaplib.IMAP4.error(f"fetch: sanal hata ({uid_s})")
            if "HEADER" in istek:
                if self.header_typ != "OK":
                    return (self.header_typ, [])
                hraw = self.headers.get(uid_s)
                fd = [(b"hdr", hraw)] if self.header_fd is None else self.header_fd
                return ("OK", fd)
            if uid_s in self.body_errors:
                raise imaplib.IMAP4.error(f"body fetch: sanal hata ({uid_s})")
            if self.body_typ != "OK":
                return (self.body_typ, [])
            return ("OK", [(b"body", self.bodies.get(uid_s))])
        return ("OK", [])


def _state(**kw):
    base = {"uidler": [], "msg_idler": []}
    base.update(kw)
    return base


# --- hata yuzeyi: her dis-baglanti hatasi bos liste döndürür (kras yok) ---

def test_klasor_select_basarisiz_bos_donuyor():
    """select 'OK' donmezse fonksiyon sessizce [] döndürür."""
    M = _FakeIMAP(select_result=("NO", b"klasor yok"))
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_select_hatasi_bos_donuyor():
    """select imaplib.IMAP4.error firlatirsa yakalanir ve [] döndürülür."""
    M = _FakeIMAP(select_error=True)
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_search_hatasi_bos_donuyor():
    """search IMAP hatasi firlatirsa yakalanir, loglanir ve [] döndürülür."""
    M = _FakeIMAP(select_result=("OK", b""), search_error=True)
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_search_bos_veri_bos_donuyor():
    """search basarili ama veri bos ise (klasor bos) [] döndürülür."""
    M = _FakeIMAP(search_result=("OK", [b""]))
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_search_basarisiz_bos_donuyor():
    """search 'OK' disinda bir typ dönerse [] döndürülür."""
    M = _FakeIMAP(search_result=("ERR", [b"1"]))
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


# --- state: islenmis mesajlar tekrar islenmez ---

def test_klasor_hepsi_islenmis_fetche_girilmez():
    """Tüm uid'ler state'te kayitli ise tek bir fetch bile yapilmaz."""
    M = _FakeIMAP(search_result=("OK", [b"100 101"]),
                  headers={"100": _eml("a@b.com", "x"), "101": _eml("c@d.com", "y")})
    state = _state(uidler=["100", "101"])
    assert imap_izle.klasor_postalari(M, "INBOX", state) == []
    assert M.fetch_calls == [], "islenmis uid'ler icin fetch yapilmamali"


def test_klasor_tekrar_message_id_atlanir():
    """Message-ID daha once gorulmussa aday yapilmaz; uid islenmis olarak isaretlenir."""
    mid = "once-goruldu@example.net"
    M = _FakeIMAP(search_result=("OK", [b"200"]),
                  headers={"200": _eml("klinik@klinik-1.example", "Merhaba", mid=mid)},
                  bodies={"200": _eml("klinik@klinik-1.example", "Merhaba", mid=mid)})
    state = _state(msg_idler=["<" + mid + ">"])
    sonuc = imap_izle.klasor_postalari(M, "INBOX", state)
    assert sonuc == []
    assert state["uidler"] == ["200"], "uid tekrar bakmamak uzere isaretlenmeli"
    # govde fetch'i yapilmamali (aday bile degil)
    assert all("BODY.PEEK[]" not in i for (_, i) in M.fetch_calls)


def test_klasor_ilgisiz_posta_isaretlenir_aday_degil():
    """Kampanya/bounce olmayan posta aday degildir; state'e kaydedilir."""
    ham = _eml("nobody@tamamen-ilgisiz.net", "Buy cheap watches now",
               mid="spam1@ilgisiz.net")
    M = _FakeIMAP(search_result=("OK", [b"300"]), headers={"300": ham},
                  bodies={"300": ham})
    state = _state()
    sonuc = imap_izle.klasor_postalari(M, "INBOX", state)
    assert sonuc == []
    assert state["uidler"] == ["300"]
    assert "<spam1@ilgisiz.net>" in state["msg_idler"]


# --- aday siniflandirma: bounce ve kampanya yaniti ---

def test_klasor_bounce_aday_donuyor():
    """mailer-daemon postasi bounce olarak aday kabul edilir ve govdesi cekilir."""
    ham = _eml("MAILER-DAEMON@example.net",
               "Delivery Status Notification (Failure)", mid="bounce1@x.net")
    M = _FakeIMAP(search_result=("OK", [b"400"]), headers={"400": ham},
                  bodies={"400": ham})
    sonuc = imap_izle.klasor_postalari(M, "INBOX", _state())
    assert len(sonuc) == 1
    uid, msg, raw, domain = sonuc[0]
    assert uid == b"400"
    assert msg.get("Subject") == "Delivery Status Notification (Failure)"
    assert raw == ham
    assert domain == "example.net", "domain_cikar bounce adresinden cikarilmali"


def test_klasor_kampanya_yaniti_aday_donuyor():
    """Klinik domain'inden gelen yanit kampanya yanidi olarak aday olur."""
    ham = _eml("Dr. Ayse <ayse@klinik-2.example>", "Re: AI visibility check",
               mid="yanit1@klinik-2.example")
    M = _FakeIMAP(search_result=("OK", [b"500"]), headers={"500": ham},
                  bodies={"500": ham})
    sonuc = imap_izle.klasor_postalari(M, "INBOX", _state())
    assert len(sonuc) == 1
    _, msg, _, domain = sonuc[0]
    assert domain == "klinik-2.example"
    assert msg.get("From") == "Dr. Ayse <ayse@klinik-2.example>"


def test_klasor_gonderen_kendiyse_aday_degil():
    """Kendi gonderen adresimizden (GONDEREN) gelen posta aday degildir."""
    ham = _eml("vegoko7@gmail.com", "AI visibility check", mid="oz1@gmail.com")
    M = _FakeIMAP(search_result=("OK", [b"600"]), headers={"600": ham},
                  bodies={"600": ham})
    state = _state()
    assert imap_izle.klasor_postalari(M, "INBOX", state) == []
    assert state["uidler"] == ["600"], "kendi postamiz islenmis olarak isaretlenir"


def test_klasor_references_gmail_ile_aday():
    """In-Reply-To bizim gmail mesajimiza referans veriyorsa kampanya yanidi sayilir."""
    ham = _eml("farkli@baska-bir.net", "Tamam, konusalim",
               mid="farkli1@baska.net",
               extra_lines=["In-Reply-To: <abcvegoko7@gmail.com>"])
    M = _FakeIMAP(search_result=("OK", [b"700"]), headers={"700": ham},
                  bodies={"700": ham})
    sonuc = imap_izle.klasor_postalari(M, "INBOX", _state())
    assert len(sonuc) == 1
    assert sonuc[0][3] == "baska-bir.net"


# --- fetch hata dallari ---

def test_klasor_header_fetch_hatasi_atlanir():
    """Bir uid'nin header fetch'i IMAP hatasi verirse o uid atlanir (kras yok)."""
    M = _FakeIMAP(search_result=("OK", [b"800"]),
                  headers={"800": _eml("x@y.net", "z")},
                  fetch_errors=("800",))
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_header_fd_tuple_yoksa_atlanir():
    """fetch yanitinda tuple yoksa (hraw None) uid atlanir."""
    M = _FakeIMAP(search_result=("OK", [b"801"]),
                  headers={"801": _eml("a@b.net", "c")},
                  header_fd=[b"tuple-degil"])
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_govde_fetch_hatasi_dusulur():
    """Aday header'da bulunmus ama govde fetch'i hata verirse sonucta yer almaz."""
    ham = _eml("klinik@klinik-3.example", "Re: AI visibility check", mid="g1@k3.example")
    M = _FakeIMAP(search_result=("OK", [b"900"]), headers={"900": ham},
                  bodies={"900": ham}, body_errors=("900",))
    # header fetch basarili → aday; govde fetch hata verir → sonuctan dusulur
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []
    assert any("BODY.PEEK[]" in i for (_, i) in M.fetch_calls), "govde fetch denendi"


def test_klasor_govde_fetch_typ_ok_degilse_dusulur():
    """Adayin govde fetch'i 'OK' disinda typ dönerse sonucta yer almaz."""
    header = _eml("klinik@klinik-4.example", "Re: AI visibility check", mid="g2@k4.example")
    M = _FakeIMAP(search_result=("OK", [b"901"]), headers={"901": header},
                  bodies={"901": header}, body_typ="NO")
    assert imap_izle.klasor_postalari(M, "INBOX", _state()) == []


def test_klasor_coklu_aday_sirayla_donuyor():
    """3 aday (bounce + 2 klinik yanidi) sirayla islenir ve sirali doner."""
    h1 = _eml("mailer-daemon@x.net", "Undelivered mail returned", mid="b@a.net")
    h2 = _eml("d1@klinik-5.example", "Re: AI visibility check", mid="c@k5.example")
    h3 = _eml("d2@klinik-6.example", "Unpump hakkinda", mid="d@k6.example")
    M = _FakeIMAP(search_result=("OK", [b"1 2 3"]),
                  headers={"1": h1, "2": h2, "3": h3},
                  bodies={"1": h1, "2": h2, "3": h3})
    sonuc = imap_izle.klasor_postalari(M, "INBOX", _state())
    assert [u for (u, _, _, _) in sonuc] == [b"1", b"2", b"3"]
    assert [d for (_, _, _, d) in sonuc] == ["x.net", "klinik-5.example", "klinik-6.example"]


# ════════════════════════════════════════════════════════════════════════════
# 2. answrank.api.app.stream_swarm_execution — SSE akisi (uydurma olay YOK)
# ════════════════════════════════════════════════════════════════════════════

class _FakeOrchestrator:
    """SwarmOrchestrator taklidi — gercek ag/gezici cagrilar YOK.

    run_full_pipeline_sync yalnizca betimlenmis GERCEK adimlari on_event ile
    yayar; hicbir uydurma/konserve mesaj uretmez.
    """

    def __init__(self, events, final_stage=SwarmStage.AUDITED, raise_exc=None):
        self._events = list(events)
        self._final_stage = final_stage
        self._raise_exc = raise_exc
        self.seed_kwargs = None
        self.candidate = None

    def seed_target(self, brand_name, domain, city, country, **kw):
        self.seed_kwargs = dict(brand_name=brand_name, domain=domain,
                                city=city, country=country)
        self.candidate = SwarmCandidate(
            brand_name=brand_name, domain=domain, city=city, country=country,
            stage=SwarmStage.DISCOVERED,
        )
        return self.candidate

    async def run_full_pipeline_sync(self, candidate, on_event=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        for agent, message in self._events:
            if on_event is not None:
                await on_event(agent, message)
        candidate.stage = self._final_stage
        return candidate


def _patch_orch(monkeypatch, orch):
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator",
                        lambda: orch)


def _drain(coro_thunk):
    """Async route'u cagirip StreamingResponse govde iteratorunu tuketur.

    stream_swarm_execution 'async def' oldugu icin dogrudan cagri coroutine
    verir; burada await ederek gercek StreamingResponse'i alir.
    """
    chunks = []

    async def _run():
        resp = await coro_thunk()
        async for chunk in resp.body_iterator:
            chunks.append(chunk)

    asyncio.run(_run())
    return chunks


def _parse_sse(chunks):
    """Her SSE parcasini sozluge cevirir (data: {json}\\n\\n bicimi)."""
    olaylar = []
    for chunk in chunks:
        metin = chunk.decode("utf-8") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        metin = metin.strip()
        assert metin.startswith("data: "), "SSE parcasi 'data: ' ile baslamali"
        payload = metin[len("data: "):]
        olaylar.append(json.loads(payload))
    return olaylar


def test_stream_olay_formati_gecerli_sse(monkeypatch):
    """Her parca gecerli bir SSE olayidir: agent/message/timestamp anahtarlariyla."""
    orch = _FakeOrchestrator([("AGENT_01_SCOUT", "aday nitelendi")])
    _patch_orch(monkeypatch, orch)
    resp = _drain(lambda: stream_swarm_execution("Marka", "marka.example"))
    olaylar = _parse_sse(resp)
    for o in olaylar:
        assert set(o) >= {"agent", "message", "timestamp"}
        assert isinstance(o["message"], str) and o["message"]


def test_stream_sadece_gercek_adimlar_yayilir(monkeypatch):
    """Yayilan olaylar pipeline'in gercek yuruttugu adimlardan baskasi DEGILDIR."""
    gercek = [
        ("AGENT_01_SCOUT", "Candidate 'Marka' (London, UK) qualified"),
        ("AGENT_02_AUDITOR", "Denetim tamamlandi: 72/100"),
        ("AGENT_03_HUNTER", "Pitch uretildi"),
    ]
    orch = _FakeOrchestrator(gercek, final_stage=SwarmStage.OUTREACH_SENT)
    _patch_orch(monkeypatch, orch)
    resp = _drain(lambda: stream_swarm_execution("Marka", "marka.example"))
    olaylar = _parse_sse(resp)
    # son olay PIPELINE_DONE; oncesindekiler birebir gercek adimlardir
    assert [o["agent"] for o in olaylar[:-1]] == [a for a, _ in gercek]
    assert [o["message"] for o in olaylar[:-1]] == [m for _, m in gercek]
    assert olaylar[-1]["agent"] == "PIPELINE_DONE"


def test_stream_pipeline_done_final_sahne(monkeypatch):
    """PIPELINE_DONE olayi adayin SON sahnesini icerir (uydurma sahne yok)."""
    orch = _FakeOrchestrator([], final_stage=SwarmStage.AUDITED)
    _patch_orch(monkeypatch, orch)
    resp = _drain(lambda: stream_swarm_execution("Marka", "marka.example"))
    done = _parse_sse(resp)[-1]
    assert done["agent"] == "PIPELINE_DONE"
    assert done["message"] == "Pipeline finished: Marka -> AUDITED"


def test_stream_pipeline_hatasi_hata_olayi(monkeypatch):
    """Pipeline firlatirma yaparsa PIPELINE_ERROR olayi yayilir ve akis kapanir."""
    orch = _FakeOrchestrator([], raise_exc=RuntimeError("boom"))
    _patch_orch(monkeypatch, orch)
    resp = _drain(lambda: stream_swarm_execution("Marka", "marka.example"))
    olaylar = _parse_sse(resp)
    assert len(olaylar) == 1
    assert olaylar[0]["agent"] == "PIPELINE_ERROR"
    assert olaylar[0]["message"] == "Pipeline failed: RuntimeError: boom"


def test_stream_seed_target_argumanlari_aktarilir(monkeypatch):
    """brand/domain/city/country seed_target'a dogru aktarilir."""
    orch = _FakeOrchestrator([])
    _patch_orch(monkeypatch, orch)
    async def _run():
        await stream_swarm_execution("Marka", "marka.example", city="Dubai", country="UAE")

    asyncio.run(_run())
    assert orch.seed_kwargs == {
        "brand_name": "Marka", "domain": "marka.example",
        "city": "Dubai", "country": "UAE",
    }


# ════════════════════════════════════════════════════════════════════════════
# 3. x402_servis.olcum_rapor — odeme servisi A/B raporu (durustluk kurali)
# ════════════════════════════════════════════════════════════════════════════

def _req_ip(ip):
    """Rate-limit'in okudugu minimal Request taklidi."""
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.fixture(autouse=True)
def _temiz_olcum_state(monkeypatch):
    """Her olcum testi: bos sayaclar + rate-limit tablosu + guvenli outbox."""
    monkeypatch.setattr(xs, "_OLCUM_IP", {})
    monkeypatch.setattr(xs, "ref_ozet", lambda: {})
    monkeypatch.setattr(xs, "_dm_hold_durumu", lambda: False)


def test_olcum_rate_limit_ayni_ip_429():
    """Ayni IP'den 1 sn icinde ikinci istek 429 ile reddedilir (abuse korumasi)."""
    xs.olcum_rapor(_req_ip("1.1.1.1"))
    with pytest.raises(Exception) as exc_info:
        xs.olcum_rapor(_req_ip("1.1.1.1"))
    assert getattr(exc_info.value, "status_code", None) == 429


def test_olcum_rate_limit_farkli_ip_gecer():
    """Farkli IP'ler birbirini engellemez (paylasimsiz sayac)."""
    xs.olcum_rapor(_req_ip("2.2.2.2"))
    xs.olcum_rapor(_req_ip("3.3.3.3"))  # hata firlatmamali


def test_olcum_sifir_gonderim_hold_true_mesaji():
    """0 gonderim + HOLD aktif → 'Henüz gönderim yok' + 'DM HOLD aktif'."""
    xs.ref_ozet = lambda: {"unpump-p1a-tr-01": {"deneme": 0, "odeme": 0}}
    xs._dm_hold_durumu = lambda: True
    rapor = xs.olcum_rapor(_req_ip("4.4.4.4"))
    assert rapor["status"] == "ok"
    assert "Henüz gönderim yok" in rapor["rapor"]
    assert "DM HOLD aktif" in rapor["rapor"]
    assert rapor["dm_hold"] is True
    assert rapor["varyantlar"] == {}


def test_olcum_sifir_gonderim_hold_false_mesaji():
    """0 gonderim + HOLD kalkti → 'DM HOLD kalkti ama veri yok' notu."""
    xs.ref_ozet = lambda: {"unpump-p1a-tr-01": {"deneme": 0, "odeme": 0}}
    xs._dm_hold_durumu = lambda: False
    rapor = xs.olcum_rapor(_req_ip("5.5.5.5"))
    assert "DM HOLD kalkti ama veri yok" in rapor["rapor"]
    assert rapor["dm_hold"] is False


def test_olcum_hold_aktif_test_verisi_notu():
    """HOLD aktifken olusan veri TEST verisidir — rapor acikca etiketler."""
    xs.ref_ozet = lambda: {"unpump-p1a-tr-01": {"deneme": 4, "odeme": 1}}
    xs._dm_hold_durumu = lambda: True
    rapor = xs.olcum_rapor(_req_ip("6.6.6.6"))
    assert "TEST verisidir" in rapor["rapor"]
    assert "GERÇEK" in rapor["rapor"]
    assert rapor["dm_hold"] is True


def test_olcum_hold_kalkti_test_notu_yok():
    """HOLD kalktiysa A/B raporu temizdir — TEST notu ICERMEZ."""
    xs.ref_ozet = lambda: {"unpump-p1a-tr-01": {"deneme": 4, "odeme": 1}}
    xs._dm_hold_durumu = lambda: False
    rapor = xs.olcum_rapor(_req_ip("7.7.7.7"))
    assert "TEST verisidir" not in rapor["rapor"]
    assert "A/B karsilastirma" in rapor["rapor"]


def test_olcum_ab_varyant_kumulasyonu():
    """Aynı profilin a/b varyantlari A ve B sepetinde toplanir."""
    xs.ref_ozet = lambda: {
        "unpump-p1a-tr-01": {"deneme": 10, "odeme": 2},
        "unpump-p1b-tr-02": {"deneme": 8, "odeme": 1},
        "unpump-p2a-en-03": {"deneme": 5, "odeme": 0},
    }
    xs._dm_hold_durumu = lambda: False
    rapor = xs.olcum_rapor(_req_ip("8.8.8.8"))
    v = rapor["varyantlar"]
    assert v["AI-oncul SaaS"]["A"] == {"deneme": 10, "odeme": 2}
    assert v["AI-oncul SaaS"]["B"] == {"deneme": 8, "odeme": 1}
    assert v["Dubai dis klinigi"]["A"] == {"deneme": 5, "odeme": 0}
    assert v["Dubai dis klinigi"]["B"] == {"deneme": 0, "odeme": 0}


def test_olcum_profil_adi_haritasi():
    """p1/p2/p3 kodlari insan-okur profil adlarina haritalanir."""
    xs.ref_ozet = lambda: {
        "unpump-p3b-tr-01": {"deneme": 1, "odeme": 0},
    }
    xs._dm_hold_durumu = lambda: False
    v = xs.olcum_rapor(_req_ip("9.9.9.9"))["varyantlar"]
    assert "Bireysel gelistirici" in v
    assert v["Bireysel gelistirici"]["B"] == {"deneme": 1, "odeme": 0}


def test_olcum_gecersiz_ref_atlanir():
    """Pattern'e uymayan ref sayaclari aktif olsa bile varyantlara giremez."""
    xs.ref_ozet = lambda: {"ozel-kampanya-ref": {"deneme": 7, "odeme": 3}}
    xs._dm_hold_durumu = lambda: False
    rapor = xs.olcum_rapor(_req_ip("10.10.10.10"))
    assert rapor["varyantlar"] == {}
    assert "A/B karsilastirma" in rapor["rapor"]


# ════════════════════════════════════════════════════════════════════════════
# 4. answrank.finance.tax_ledger.generate_fiscal_summary — vergi ozeti (FINANS)
# ════════════════════════════════════════════════════════════════════════════

def _kayit(*, regime, amount, vat, exempt, taxable, product, currency="GBP",
           country="UK"):
    """Gecerli bir FiscalInvoiceRecord (tutarli vergi aritmetigi)."""
    return FiscalInvoiceRecord(
        invoice_id=f"INV-{product}-{country}-{amount}",
        client_brand="Musteri",
        client_country=country,
        regime=regime,
        currency=currency,
        amount_foreign=amount / 46.50 if currency != "TRY" else amount,
        exchange_rate_tcmb=46.50 if currency != "TRY" else 1.0,
        fx_source="static_default",
        amount_try=amount,
        product_name=product,
        vat_rate_pct=0.0 if regime == TaxRegime.EXPORT_SERVICE else 20.0,
        vat_amount_try=vat,
        gross_total_try=amount + vat,
        exempt_income_try=exempt,
        taxable_base_try=taxable,
        statutory_legal_note="not",
    )


@pytest.fixture
def ledger():
    return TaxLedger(load_persisted=False)


def test_fiscal_bos_ledger_sifir(ledger):
    """Kayit yok: tum toplamlar sifir, kalkan %0, kirilim bos."""
    r = ledger.generate_fiscal_summary()
    assert r.total_invoices_count == 0
    assert r.export_invoices_count == 0
    assert r.domestic_invoices_count == 0
    assert r.total_gross_revenue_try == 0.0
    assert r.total_vat_collected_try == 0.0
    assert r.total_exempt_income_kvk10g_try == 0.0
    assert r.effective_tax_shield_pct == 0.0
    assert r.product_breakdown == []


def test_fiscal_ihracat_yurtici_ayrimi(ledger):
    """Ihracat ve yurt ici gelir ayrı ayrı toplanir; KDV yalniz yurt icinden."""
    ledger.records.append(_kayit(regime=TaxRegime.EXPORT_SERVICE, amount=2000.0,
                                 vat=0.0, exempt=2000.0, taxable=0.0,
                                 product="AnswRank"))
    ledger.records.append(_kayit(regime=TaxRegime.DOMESTIC_SERVICE, amount=1000.0,
                                 vat=200.0, exempt=0.0, taxable=1000.0,
                                 product="ClearTag", currency="TRY", country="TR"))
    r = ledger.generate_fiscal_summary()
    assert r.export_invoices_count == 1
    assert r.domestic_invoices_count == 1
    assert r.total_invoices_count == 2
    assert r.total_foreign_revenue_try == 2000.0
    assert r.total_domestic_revenue_try == 1000.0
    assert r.total_gross_revenue_try == 3000.0
    assert r.total_vat_collected_try == 200.0
    assert r.total_exempt_income_kvk10g_try == 2000.0
    assert r.total_taxable_base_try == 1000.0


def test_fiscal_vergi_kalkani_yuzdesi(ledger):
    """Effective shield = istisna gelir / brutel gelir * 100 (yuvarlanmis)."""
    ledger.records.append(_kayit(regime=TaxRegime.EXPORT_SERVICE, amount=2000.0,
                                 vat=0.0, exempt=2000.0, taxable=0.0,
                                 product="AnswRank"))
    ledger.records.append(_kayit(regime=TaxRegime.DOMESTIC_SERVICE, amount=1000.0,
                                 vat=200.0, exempt=0.0, taxable=1000.0,
                                 product="ClearTag", currency="TRY", country="TR"))
    # 2000/3000*100 = 66.66... → 66.7
    assert ledger.generate_fiscal_summary().effective_tax_shield_pct == 66.7


def test_fiscal_urun_kirilimi_sirali_ve_dogru(ledger):
    """Urun kirilimi isme gore sirali; sayac/kazanc/KVK/ihracat payi dogru."""
    ledger.records.append(_kayit(regime=TaxRegime.EXPORT_SERVICE, amount=2000.0,
                                 vat=0.0, exempt=2000.0, taxable=0.0,
                                 product="AnswRank"))
    ledger.records.append(_kayit(regime=TaxRegime.EXPORT_SERVICE, amount=500.0,
                                 vat=0.0, exempt=500.0, taxable=0.0,
                                 product="PQHaven"))
    ledger.records.append(_kayit(regime=TaxRegime.DOMESTIC_SERVICE, amount=500.0,
                                 vat=100.0, exempt=0.0, taxable=500.0,
                                 product="PQHaven", currency="TRY", country="TR"))
    kirilim = ledger.generate_fiscal_summary().product_breakdown
    assert [k.product_name for k in kirilim] == ["AnswRank", "PQHaven"]
    answ = kirilim[0]
    assert answ.invoices_count == 1
    assert answ.revenue_try == 2000.0
    assert answ.vat_try == 0.0
    assert answ.export_share_pct == 100.0
    pq = kirilim[1]
    assert pq.invoices_count == 2
    assert pq.revenue_try == 1000.0
    assert pq.vat_try == 100.0
    assert pq.export_share_pct == 50.0  # 1 ihracat / 2 toplam


def test_fiscal_kdv_ihracatta_sifir(ledger):
    """Ihracat rejiminde KDV istisna: toplam KDV yalniz yurt ici kayitlardan."""
    ledger.records.append(_kayit(regime=TaxRegime.EXPORT_SERVICE, amount=5000.0,
                                 vat=0.0, exempt=5000.0, taxable=0.0,
                                 product="AnswRank"))
    r = ledger.generate_fiscal_summary()
    assert r.total_vat_collected_try == 0.0
    assert r.total_exempt_income_kvk10g_try == 5000.0
    assert r.total_taxable_base_try == 0.0


def test_fiscal_saf_fonksiyon_degismez(ledger):
    """Ayni kayitlarla iki cagri ayni ozeti verir (dis durumdan etkilenmez)."""
    ledger.records.append(_kayit(regime=TaxRegime.EXPORT_SERVICE, amount=800.0,
                                 vat=0.0, exempt=800.0, taxable=0.0,
                                 product="AnswRank"))
    a = ledger.generate_fiscal_summary()
    b = ledger.generate_fiscal_summary()
    assert a.model_dump() == b.model_dump()


# ════════════════════════════════════════════════════════════════════════════
# 5. answrank.api.app.check_territory_lock_api — bolge kilidi (GUVENLIK)
# ════════════════════════════════════════════════════════════════════════════

class _FakeOrchLock:
    """SwarmOrchestrator taklidi — yalnizca exclusivity.check_conflict'i cevaplar."""

    def __init__(self, result):
        self._result = result
        self.captured = {}

    def seed_target(self, **kw):  # StreamOrchestrator arayuz uyumu
        raise AssertionError("check endpoint'i seed_target cagirmamali")

    @property
    def exclusivity(self):
        outer = self

        class _Excl:
            def check_conflict(self, **kw):
                outer.captured.update(kw)
                return outer._result

        return _Excl()


def test_territory_bos_domain_reddedilir(monkeypatch):
    """Bos domain ile bolge sorgusu 422 — 'example.com' adina sorgu yapilmaz."""
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator",
                        lambda: _FakeOrchLock(None))
    with pytest.raises(Exception) as exc_info:
        check_territory_lock_api(TerritoryCheckRequest(city="London", domain=""))
    assert getattr(exc_info.value, "status_code", None) == 422
    assert "Aday domain belirtilmelidir" in str(exc_info.value.detail)


def test_territory_bosluk_dolu_domain_reddedilir(monkeypatch):
    """Yalnizca bosluklardan olusan domain strip sonrasi bos sayilir → 422."""
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator",
                        lambda: _FakeOrchLock(None))
    with pytest.raises(Exception) as exc_info:
        check_territory_lock_api(TerritoryCheckRequest(city="London", domain="   "))
    assert getattr(exc_info.value, "status_code", None) == 422


def test_territory_cakisma_kilitli_donuyor(monkeypatch):
    """Cakisma varsa locked=True + mevcut kilidin marka/domain/reason'i doner."""
    kilidin = TerritoryLock(
        lock_id="L-1", country="UK", city="London", niche="dental",
        client_domain="rakip.example", brand_name="Rakip Klinik",
    )
    sonuc = ConflictCheckResult(
        has_conflict=True, existing_lock=kilidin,
        action_recommended="REJECT_CONFLICT",
        conflict_reason="Territory 'London, UK' exclusively locked by 'Rakip Klinik'.",
    )
    fake = _FakeOrchLock(sonuc)
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator", lambda: fake)
    yanit = check_territory_lock_api(
        TerritoryCheckRequest(city="London", domain="aday.example"))
    assert yanit["locked"] is True
    assert yanit["brand_name"] == "Rakip Klinik"
    assert yanit["client_domain"] == "rakip.example"
    assert yanit["message"] == sonuc.conflict_reason
    assert yanit["city"] == "London" and yanit["niche"] == "dental"
    assert yanit["country"] == "UK"


def test_territory_cakisma_yoksa_acik_donuyor(monkeypatch):
    """Cakisma yoksa locked=False ve 'acik' mesaji doner."""
    sonuc = ConflictCheckResult(has_conflict=False, existing_lock=None,
                                action_recommended="PROCEED")
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator",
                        lambda: _FakeOrchLock(sonuc))
    yanit = check_territory_lock_api(
        TerritoryCheckRequest(city="Manchester", domain="aday.example"))
    assert yanit["locked"] is False
    assert "currently open" in yanit["message"]
    assert yanit["city"] == "Manchester"


def test_territory_domain_strip_ediliyor(monkeypatch):
    """Domain bas/son bosluklarla gelse check_conflict'e strip edilmis gecer."""
    sonuc = ConflictCheckResult(has_conflict=False, existing_lock=None,
                                action_recommended="PROCEED")
    fake = _FakeOrchLock(sonuc)
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator", lambda: fake)
    check_territory_lock_api(
        TerritoryCheckRequest(city="London", domain="  aday.example  "))
    assert fake.captured["candidate_domain"] == "aday.example"
    assert fake.captured["country"] == "UK"
    assert fake.captured["city"] == "London"
    assert fake.captured["niche"] == "dental"
