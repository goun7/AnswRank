"""/healthz call-count canlilik sayaci testleri.

Gerekce: dis izleyici ( systemd/watchdog) her 10 dk'da /healthz'e vurur.
Statik "status: ok" yaniti, servisin gercekten calistigini KANITLAMAZ
( ölü bir process de ayni sabiti dönebilir). Artan healthz_call_count ise
zamansal bir canlilik kantidir: her basarili sorguda kesinlikle artar.

Bu test x402_servis.py'yi UCGULAMA ortaminda import eder:
  - SELLER_SECRET zorunlu ( bos -> SystemExit, AT-193)
  - resolve_treasury zorunlu ( tek-kasa, fail-closed)
Sonra FastAPI TestClient ile /healthz'ye vurur ve sayacin arttirdir.
"""

import os
import sys

import pytest

# repo root'u sys.path'e ekle — x402_servis.py, mainnet_guard.py paket degil.
# realpath: tests/ dizini baska repolara SYMLINK olabilir ( Unpump `tests` ->
# 85-AnswRank/tests). Cozulmemis symlink yolu REPO_ROOT'u yanlis repo verir
# -> mainnet_guard bulunamaz -> yarim import -> AttributeError.
# realpath ile gercek fiziksel yolu cozup dogru repo root'unu aliriz.
_HERE = os.path.dirname(os.path.realpath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# x402_servis.py KESIN yolu. tests/ dizini baska repolara SYMLINK
# olabilir ( Unpump `tests` -> 85-AnswRank/tests) ve bazi testler
# sys.path'e DIGGERI x402_servis.py'lerin oldugu dizinler ekler
# ( orn. 24-Lup). Sadece `import x402_servis` dersen yanlis repodan
# ( Lup'tan) yuklenir -> _healthz_call_count yok -> AttributeError.
# Bu yuzden spec ile KESIN dosyadan yukluyoruz.
_X402_MODUL = os.path.join(_REPO_ROOT, "x402_servis.py")

_TREASURY_EOA = "0xF3F0cC9DE0Df5A17a09bfcc62d21BFC9Ba4f82c5"

# x402_servis, sester metering katmanini icerir. sester yalnizca
# .venv'de yukludur; sistem python3'unda import basarisiz olur. Test
# bu durumda atlanir — boylece `python3 -m pytest tests/ -q` RC=0'ý
# ( 980 passed) korur, .venv'te ise bu testler de calisir.
pytest.importorskip("sester")


@pytest.fixture(scope="module")
def x402_app():
    """x402_servis modulunu gecerli env ile import et.

    Import sirasinda okunan cevre degiskenlerini ONCE ayarla, sonra
    modulu taze import et ( module-level resolve_treasury ve
    SystemExit kontrolu calissin diye).
    """
    # Import sirasinda okunan cevre degiskenlerini ONCE ayarla.
    os.environ["ANSWRANK_SELLER_SECRET"] = "test-secret-healthz-kanit"
    os.environ["UNPUMP_TREASURY_EOA"] = _TREASURY_EOA
    # Test DB'si: hedef dizin kesin olsun
    os.environ.setdefault(
        "ANSWRANK_DB", "/tmp/answrank-healthz-test/receipts.sqlite")

    if "x402_servis" in sys.modules:
        del sys.modules["x402_servis"]
    import importlib.util
    # KESIN dosyadan yukle ( sys.path kirliligine bagli yanlis-repo riski yok)
    spec = importlib.util.spec_from_file_location("x402_servis", _X402_MODUL)
    x402_servis = importlib.util.module_from_spec(spec)
    sys.modules["x402_servis"] = x402_servis
    spec.loader.exec_module(x402_servis)
    # Taze import: sayac henuz 0 olmali ( stale state yok)
    assert x402_servis._healthz_call_count == 0, (
        f"taze import'ta sayac 0 degil ( dosya={x402_servis.__file__})")
    yield x402_servis
    # temizlik: tekrar import eden baska testler temiz modul alsin
    if "x402_servis" in sys.modules:
        del sys.modules["x402_servis"]


def _client(mod):
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


def test_healthz_call_count_artar(x402_app):
    """Her /healthz sorgusunda call_count kesinlikle artar.

    Bu, canliligin ZAMANSAL kanitidir: ayni degeri dondurmek servisin
    "yanit vermedigini" gosterirdi.
    """
    client = _client(x402_app)
    r1 = client.get("/healthz")
    assert r1.status_code == 200
    body1 = r1.json()
    assert "healthz_call_count" in body1, "call_count alani eksik"
    assert isinstance(body1["healthz_call_count"], int)
    c1 = body1["healthz_call_count"]

    r2 = client.get("/healthz")
    assert r2.status_code == 200
    c2 = r2.json()["healthz_call_count"]

    assert c2 == c1 + 1, f"sayac artmadi: {c1} -> {c2}"


def test_healthz_ucretsiz_ve_exempt(x402_app):
    """/healthz exempt_prefixes icinde — 402 degil 200 doner.

    Canlilik probunun ODEME yapmadan calismasi gerekir; yoksa izleyici
    her 10 dk'da ödeme harcardi.
    """
    client = _client(x402_app)
    # Hicbir X-Payment header'i yok
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_healthz_yaniti_zengin(x402_app):
    """/healthz izleme icin gerekli tum alanlari doner."""
    client = _client(x402_app)
    body = client.get("/healthz").json()
    for key in ("status", "sester", "ledger_chain_valid",
                "healthz_call_count", "prices", "daily_quota"):
        assert key in body, f"eksik alan: {key}"
    # ledger zinciri bu process'te yeni kuruldu -> gecerli olmali
    assert body["ledger_chain_valid"] is True


def test_healthz_call_count_ardisik_artar(x402_app):
    """Sayac N sorguda tam N artar ( atlama/çift-artma yok).

    Thread-safe artisin dogrulugu: 5 sorgu sonrasi delta tam 5 olmali.
    """
    client = _client(x402_app)
    before = x402_app._healthz_call_count
    n = 5
    for _ in range(n):
        r = client.get("/healthz")
        assert r.status_code == 200
    after = x402_app._healthz_call_count
    assert after - before == n, f"beklenen delta {n}, gercek {after - before}"


def test_bos_secret_fail_closed(monkeypatch):
    """ANSWRANK_SELLER_SECRET bos -> SystemExit ( AT-193; zayif-default yok).

    Bu test ayni zamanda modul-un fail-closed korunmasini dogrular:
    hatali yapilandirma ile servis BASLAYAMAZ.
    """
    monkeypatch.setenv("ANSWRANK_SELLER_SECRET", "")
    monkeypatch.setenv("UNPUMP_TREASURY_EOA", _TREASURY_EOA)
    # KESIN dosyadan yukle ( sys.path kirliligi: baska testler 24-Lup gibi
    # dizinleri sys.path'e ekler, orada da x402_servis.py var).
    import importlib.util
    sys.modules.pop("x402_servis", None)
    spec = importlib.util.spec_from_file_location("x402_servis", _X402_MODUL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["x402_servis"] = mod
    with pytest.raises(SystemExit) as exc:
        spec.loader.exec_module(mod)   # module-level SystemExit
    assert "secret-required" in str(exc.value)
