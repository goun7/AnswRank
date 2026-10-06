"""3. grup EN KRITIK test-disi fonksiyonlar — dal-kesen unit testler.

Secilen 6 fonksiyon (guvenlik/finans/odeme oncelikli, AST ile 40+ satirlik
test-disi fonksiyonlar arasindan):

  FINANS:
    1. answrank/finance/tax_ledger.py  TaxLedger._write_unified_report_md   (52 satir)
       — mali mustavir-hazir vergi raporu markdown uretimi (KDV/GVK 89/13).
    6. answrank/cli.py                 run_swarm_command                    (45 satir)
       — 5-ajanli suru icrasi; fiscal fatura / bolge kilidi / kaçan ciro.

  GUVENLIK:
    2. answrank/cli.py                 run_adversarial_command              (40 satir)
       — dolayli prompt enjeksiyonu + gizli CSS taramasi cikti mantigi.
    3. answrank/cli.py                 run_prospect_command                 (43 satir)
       — E9 otonom lead dogrulama: HICBIR aday uydurulmaz, robots saygisi.
    4. answrank/cli.py                 run_deploy_command                   (42 satir)
       — dagitim hedefi icin kimlik bilgisi zorunlulugu (fail-closed guard).

  DURUSTLUK (AI gorunurluk olcumu):
    5. answrank/cli.py                 run_citations_command                (56 satir)
       — olcum modalitesi etiketi: TAM SIMULASYON / karisik / tamami canli.

Kurallar:
  - Mevcut test/kod dosyalarina DOKUNULMAZ; yalnizca bu YENI dosya eklendi.
  - Dis cagrilar (crawler, LLM runner, deployer HTTP, swarm pipeline, DB
    yazimi) mock'lanir; yalnizca fonksiyonun KENDI mantigi test edilir.
  - AT-192: x402 verify_payload |n|>2^53 ValueError yoluna DOKUNULMADI
    (kullanici karari bekliyor) — bu dosyada verify_payload testi YOK.
"""

import io
import json
from types import SimpleNamespace

import pytest
from rich.console import Console

import answrank.cli as cli_mod
from answrank.agents.swarm import SwarmCandidate, SwarmStage
from answrank.finance.tax_ledger import TaxLedger, UnifiedProductRow
from answrank.integrations.deployer import (CMSDeployer, DeploymentResult,
                                            DeployTarget)
from answrank.audit.adversarial import AdversarialAuditResult, AdversarialThreat


# ---------------------------------------------------------------------------
# Ortak yardimcilar
# ---------------------------------------------------------------------------

class _FakeProgress:
    """Rich Progress'in canli (thread'li) cikti yapan gerceginin yerine —
    CLI fonksiyonlarindaki `with Progress(...) as progress:` bloklarini
    sessizce gecirir; progress.add_task no-op."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add_task(self, **kw):
        return 0


@pytest.fixture
def cap_cli(monkeypatch):
    """cli.console'u bir StringIO'ya yonlendirir ve Progress'i susturur.

    Genislik 250 birakilir: Panel.fit/Table satir kirpmalarinin assert
    ettigimiz duz metinleri bolmesini engeller.
    """
    buf = io.StringIO()
    monkeypatch.setattr(cli_mod, "console", Console(file=buf, width=250))
    monkeypatch.setattr(cli_mod, "Progress", _FakeProgress)
    return buf


def _ns(**kw):
    """argparse.Namespace yerine SimpleNamespace (args.* erisimi)."""
    return SimpleNamespace(**kw)


def _verified(domain="aday.example", http_status=200, robots_status=200,
              robots_disallowed=False, reachable=True, phone="+44 20 1",
              email="info@aday.example", notes=""):
    return SimpleNamespace(
        domain=domain, http_status=http_status, robots_status=robots_status,
        robots_disallowed=robots_disallowed, reachable=reachable,
        phone=phone, email=email, notes=notes,
    )


# ===========================================================================
# 1. FINANS — TaxLedger._write_unified_report_md  (answrank/finance/tax_ledger.py:492)
# ===========================================================================

def _rows(*specs):
    """UnifiedProductRow listesi olusturur."""
    return [UnifiedProductRow(**s) for s in specs]


def _write(tmp_path, rows, ay=3, yil=2026, taxpayer="Unpump (sahis sirketi)",
           yurtici=1000.0, yurtdisi=5000.0, kdv=200.0, muaf=4000.0,
           matrah=1500.0):
    yol = str(tmp_path / "vergi_raporu.md")
    TaxLedger._write_unified_report_md(
        yol, rows, yil, ay, taxpayer,
        yurtici, yurtdisi, kdv, muaf, matrah)
    with open(yol, encoding="utf-8") as f:
        return f.read()


def test_finans_rapor_basligi_ve_urun_satirlari(tmp_path):
    """Ocak..Aralik indeksi ve urun bazinda gelir tablosu dogru yazilir."""
    rows = _rows(
        dict(product_name="AnswRank", invoices_count=3,
             yurtici_try=1000.0, yurt_disi_try=5000.0, kdv_try=200.0),
        dict(product_name="MCPGuard", invoices_count=1,
             yurtici_try=250.0, yurt_disi_try=0.0, kdv_try=50.0),
    )
    icerik = _write(tmp_path, rows, ay=3, yil=2026)
    assert "# VERGI RAPORU — Mart 2026" in icerik
    assert "## TEK MUKELLEF — COK URUN" in icerik
    assert "**Mukellep:** Unpump (sahis sirketi)" in icerik
    # urun satirlari: isim, fatura adedi, yurt ici / yurt disi / kdv
    assert "| AnswRank | 3 | 1,000.00 | 5,000.00 | 200.00 |" in icerik
    assert "| MCPGuard | 1 | 250.00 | 0.00 | 50.00 |" in icerik
    # TOPLAM: faturalar toplanir (3+1=4), para degerleri parametreden
    assert "| **TOPLAM** | **4** | **1,000.00** | **5,000.00** | **200.00** |" in icerik


def test_finans_ay_adi_aralik_disinda_dal_verir(tmp_path):
    """1<=ay<=12 → ay_adi listeden; disinda 'Ay-<n>' geri-dususu."""
    assert "Mart 2026" in _write(tmp_path, _rows(), ay=3, yil=2026)
    assert "Ocak 2026" in _write(tmp_path, _rows(), ay=1, yil=2026)
    assert "Aralik 2026" in _write(tmp_path, _rows(), ay=12, yil=2026)
    assert "Ay-0 2026" in _write(tmp_path, _rows(), ay=0, yil=2026)
    assert "Ay-13 2026" in _write(tmp_path, _rows(), ay=13, yil=2026)


def test_finans_bos_urun_listesi_sifir_toplam(tmp_path):
    """rows bos ise urun tablosu govdiyssiz ama TOPLAM 0.00 yazilir."""
    icerik = _write(tmp_path, _rows(), yurtici=0.0, yurtdisi=0.0, kdv=0.0,
                    muaf=0.0, matrah=0.0)
    assert "| **TOPLAM** | **0** | **0.00** | **0.00** | **0.00** |" in icerik


def test_finans_kdv_ve_gvk8913_tutarlari_metine_islenir(tmp_path):
    """KDV Kanunu 11/1-a (Kod 302) ve GVK 89/13 tutarlari parametreden gelir."""
    icerik = _write(tmp_path, _rows(), yurtici=12000.0, yurtdisi=77000.0,
                    kdv=2400.0, muaf=61600.0, matrah=21000.0)
    assert "**Yurt ici gelir:** 12,000.00 TRY" in icerik
    assert "**Yurt disi gelir:** 77,000.00 TRY" in icerik
    assert "**Toplam tahsil edilen KDV:** 2,400.00 TRY" in icerik
    assert "**GVK 89/13 indirimi ( muaf kisim):** 61,600.00 TRY" in icerik
    assert "**Vergiye tabi matrah:** 21,000.00 TRY" in icerik
    # istisna kodu etiketi mali mustavir icin korunmali
    assert "Istisna Kodu 302" in icerik


def test_finans_mukellep_adi_ve_uretici_atfi(tmp_path):
    """Mukellep adi parametreden; rapor kaynagi atfi sabit metinde."""
    icerik = _write(tmp_path, _rows(), ay=9, yil=2025,
                    taxpayer="Test Holding A.S.")
    assert "**Mukellep:** Test Holding A.S." in icerik
    assert "**Donem:** Eylul 2025" in icerik
    assert "generate_monthly_unified_report" in icerik


# ===========================================================================
# 2. GUVENLIK — run_adversarial_command  (answrank/cli.py:726)
# ===========================================================================

class _FakeCrawler:
    def __init__(self, domain="hedef.example", html="<html><body>x</body></html>"):
        self.domain = domain
        self.html = html
        self.fetched_url = None

    async def fetch(self, url):
        self.fetched_url = url
        return SimpleNamespace(domain=self.domain, html_content=self.html)


class _FakeAnalyzer:
    def __init__(self, result):
        self.result = result
        self.captured = None

    def analyze(self, soup, raw_html=None):
        self.captured = {"raw_html": raw_html, "soup_aldi": soup is not None}
        return self.result


def _adversarial_kur(monkeypatch, analyzer):
    """run_adversarial_command'in iki dis bagimliligini enjekte eder."""
    crawler = _FakeCrawler()
    monkeypatch.setattr("answrank.audit.crawler.WebCrawler", lambda: crawler)
    monkeypatch.setattr("answrank.audit.adversarial.AdversarialAnalyzer",
                        lambda: analyzer)
    return crawler


def test_adversarial_temiz_yayinda_kutlama_mesaji(monkeypatch, cap_cli):
    """is_clean=True → 'Tebrikler' mesaji basilir; tehdit tablosu cizilmez."""
    from answrank.audit.adversarial import AdversarialAuditResult
    analyzer = _FakeAnalyzer(AdversarialAuditResult(
        is_clean=True, risk_score=0, threat_level="CLEAN"))
    crawler = _adversarial_kur(monkeypatch, analyzer)

    cli_mod.run_adversarial_command(_ns(url="https://hedef.example"))

    out = cap_cli.getvalue()
    assert crawler.fetched_url == "https://hedef.example"
    assert analyzer.captured["soup_aldi"] is True
    assert analyzer.captured["raw_html"].startswith("<html>")
    assert "Tebrikler" in out
    assert "Tespit Edilen Güvenlik Tehditleri" not in out


def test_adversarial_kritik_tehdit_kirmizi_badge_ve_tablo(monkeypatch, cap_cli):
    """is_clean=False + CRITICAL → kirmizi badge; tehdit tablosu cizilir."""
    from answrank.audit.adversarial import AdversarialAuditResult
    analyzer = _FakeAnalyzer(AdversarialAuditResult(
        is_clean=False, risk_score=95, threat_level="CRITICAL",
        cloaked_elements_count=2, invisible_unicode_count=7,
        threats=[AdversarialThreat(
            threat_type="CSS Cloaking", severity="CRITICAL",
            snippet="gizli_css_kod_parca", description="Gizlenmis metin")]))
    _adversarial_kur(monkeypatch, analyzer)

    cli_mod.run_adversarial_command(_ns(url="https://hedef.example"))

    out = cap_cli.getvalue()
    assert "Risk Skoru: 95/100" in out
    assert "Tehdit Seviyesi: CRITICAL" in out
    assert "Gizli Öğeler: 2" in out
    assert "Görünmez Karakterler: 7" in out
    assert "Tespit Edilen Güvenlik Tehlikleri" in out or \
           "Tespit Edilen Güvenlik Tehditleri" in out
    assert "CSS Cloaking" in out
    assert "Gizlenmis metin" in out


def test_adversarial_dusuk_ve_orta_seviye_sari_badge_dali(monkeypatch, cap_cli):
    """threat_level LOW ve MEDIUM ayni sari badge dalina girer (CRITICAL disi);
    tehdit listesi dolu oldugu surece 'Tebrikler' kutlamasi basilamaz."""
    for seviye in ("LOW", "MEDIUM"):
        cap_cli.seek(0)
        cap_cli.truncate(0)
        analyzer = _FakeAnalyzer(AdversarialAuditResult(
            is_clean=False, risk_score=20, threat_level=seviye,
            threats=[AdversarialThreat(
                threat_type="Hidden Prompt", severity=seviye,
                snippet="gizli", description="az tehlikeli manipulasyon")]))
        _adversarial_kur(monkeypatch, analyzer)
        cli_mod.run_adversarial_command(_ns(url="https://hedef.example"))
        out = cap_cli.getvalue()
        assert f"Tehdit Seviyesi: {seviye}" in out
        assert "az tehlikeli manipulasyon" in out
        assert "Tebrikler" not in out  # tehdit var → kutlama yok


def test_adversarial_tehdit_listesi_bossa_kutlama_yazilir(monkeypatch, cap_cli):
    """DAL KEŞİF: 'Tebrikler' mesaji is_clean'e degil res.threats listesine
    baglidir. is_clean=False olsa bile threats bossa else dali calisir ve
    kutlama mesaji basilir (badge rengi ise is_clean'e gore sari/kirmizi)."""
    analyzer = _FakeAnalyzer(AdversarialAuditResult(
        is_clean=False, risk_score=45, threat_level="MEDIUM", threats=[]))
    _adversarial_kur(monkeypatch, analyzer)

    cli_mod.run_adversarial_command(_ns(url="https://hedef.example"))

    out = cap_cli.getvalue()
    assert "Tebrikler" in out  # else dali: tehdit listesi bos
    assert "Risk Skoru: 45/100" in out
    assert "Tehdit Seviyesi: MEDIUM" in out


def test_adversarial_snippet_altmis_karaktere_kesilir(monkeypatch, cap_cli):
    """Tehdit kod kesidi 60 karakterle kirpilir (cikti genisligi koruması)."""
    from answrank.audit.adversarial import AdversarialAuditResult
    uzun = "A" * 200
    analyzer = _FakeAnalyzer(AdversarialAuditResult(
        is_clean=False, risk_score=80, threat_level="CRITICAL",
        threats=[AdversarialThreat(threat_type="Prompt Inject",
                                   severity="HIGH", snippet=uzun,
                                   description="kisa")]))
    _adversarial_kur(monkeypatch, analyzer)

    cli_mod.run_adversarial_command(_ns(url="https://hedef.example"))

    out = cap_cli.getvalue()
    assert uzun not in out              # 200 karakterlik hali gorememeli
    assert uzun[:60] in out             # yalnizca ilk 60 karakter


# ===========================================================================
# 3. GUVENLIK — run_prospect_command  (answrank/cli.py:989)
# ===========================================================================

class _FakeProspector:
    """LeadProspector'in dis cagrilarini kaydeder; run_verify istenirse
    hata firlatir veya hazir verified lead listesi doner."""

    def __init__(self, db=None, politeness=1.0):
        self.db = db
        self.politeness = politeness
        self.verify_cagrildi = False
        self.staged = []
        self.verified_don = None

    async def run_verify(self, candidates):
        self.verify_cagrildi = True
        if self.verified_don is not None:
            return self.verified_don
        raise AssertionError("run_verify beklenmedik sekilde cagrildi")

    async def stage(self, v):
        self.staged.append(v)
        return "staged-id"


def _prospect_dosya(tmp_path, veri):
    yol = tmp_path / "adaylar.json"
    yol.write_text(json.dumps(veri), encoding="utf-8")
    return str(yol)


def test_prospect_bos_liste_uydurma_aday_uretilmez(monkeypatch, cap_cli, tmp_path):
    """Bos liste → 'Liste boş/geçersiz' ve run_verify HIC cagrilmaz."""
    fake = _FakeProspector()
    monkeypatch.setattr("answrank.crm.prospector.LeadProspector",
                        lambda *a, **kw: fake)

    cli_mod.run_prospect_command(_ns(
        file=_prospect_dosya(tmp_path, []), country="UK", sector="dental",
        politeness=1.0, dry_run=False, limit=50))

    out = cap_cli.getvalue()
    assert "Liste boş/geçersiz" in out
    assert "uydurma aday üretilmez" in out
    assert fake.verify_cagrildi is False


def test_prospect_gecersiz_tip_uydurma_aday_uretilmez(monkeypatch, cap_cli, tmp_path):
    """JSON bir list DEGILSE (dict) erken donus; dogrulama yapilmaz."""
    fake = _FakeProspector()
    monkeypatch.setattr("answrank.crm.prospector.LeadProspector",
                        lambda *a, **kw: fake)

    cli_mod.run_prospect_command(_ns(
        file=_prospect_dosya(tmp_path, {"domain": "a.example"}), country="UK",
        sector="dental", politeness=1.0, dry_run=False, limit=50))

    assert "Liste boş/geçersiz" in cap_cli.getvalue()
    assert fake.verify_cagrildi is False


def test_prospect_dogrulanan_lead_stage_edilir(monkeypatch, cap_cli, tmp_path):
    """dry_run=False + reachable=True → stage gercek kanitla cagrilir,
    'stage edildi' ozeti basilir."""
    fake = _FakeProspector()
    fake.verified_don = [_verified()]
    monkeypatch.setattr("answrank.crm.prospector.LeadProspector",
                        lambda *a, **kw: fake)

    cli_mod.run_prospect_command(_ns(
        file=_prospect_dosya(tmp_path, [{"domain": "aday.example"}]),
        country="UK", sector="dental", politeness=2.0, dry_run=False, limit=10))

    out = cap_cli.getvalue()
    assert fake.verify_cagrildi is True
    assert len(fake.staged) == 1
    assert fake.staged[0].domain == "aday.example"
    assert "STAGED" in out
    assert "1 lead stage edildi" in out


def test_prospect_dry_run_stagelenmez(monkeypatch, cap_cli, tmp_path):
    """dry_run=True → p.stage HIC cagrilmaz; 'DRY-RUN' notu basilir."""
    fake = _FakeProspector()
    fake.verified_don = [_verified()]
    monkeypatch.setattr("answrank.crm.prospector.LeadProspector",
                        lambda *a, **kw: fake)

    cli_mod.run_prospect_command(_ns(
        file=_prospect_dosya(tmp_path, [{"domain": "a.example"}]),
        country="UK", sector="dental", politeness=1.0, dry_run=True, limit=10))

    out = cap_cli.getvalue()
    assert "DRY-RUN" in out
    assert "CRM'e yazılmadı" in out
    assert fake.staged == []


def test_prospect_dogrulanamayan_aday_reddedilir(monkeypatch, cap_cli, tmp_path):
    """reachable=False ve robots_disallowed=False → RET; stage edilmez."""
    fake = _FakeProspector()
    fake.verified_don = [_verified(
        reachable=False, http_status=0, robots_status=None,
        phone=None, email=None, notes="ana sayfa indirilemedi (ağ)")]
    monkeypatch.setattr("answrank.crm.prospector.LeadProspector",
                        lambda *a, **kw: fake)

    cli_mod.run_prospect_command(_ns(
        file=_prospect_dosya(tmp_path, [{"domain": "kapali.example"}]),
        country="UK", sector="dental", politeness=1.0, dry_run=False, limit=10))

    out = cap_cli.getvalue()
    assert "RET" in out
    assert "ana sayfa indirilemedi" in out
    assert "0 lead stage edildi" in out
    assert fake.staged == []


def test_prospect_robots_disallow_olsa_aday_kabul_edilir(monkeypatch, cap_cli, tmp_path):
    """robots_disallowed=True → reachable False olsa da 'ok' (saygi sabiti)."""
    fake = _FakeProspector()
    fake.verified_don = [_verified(
        reachable=False, robots_disallowed=True, http_status=0,
        notes="robots.txt kapsamı: ana sayfa çekilmedi")]
    monkeypatch.setattr("answrank.crm.prospector.LeadProspector",
                        lambda *a, **kw: fake)

    cli_mod.run_prospect_command(_ns(
        file=_prospect_dosya(tmp_path, [{"domain": "engelli.example"}]),
        country="UK", sector="dental", politeness=1.0, dry_run=False, limit=10))

    out = cap_cli.getvalue()
    assert "STAGED" in out
    assert "ENGELLİ" in out
    assert len(fake.staged) == 1


# ===========================================================================
# 4. GUVENLIK — run_deploy_command  (answrank/cli.py:835)
# ===========================================================================

class _FakeDeployer:
    """CMSDeployer'in dis cagrilarini kaydeder; hicbir yere HTTP yapmaz."""

    def __init__(self):
        self.calls = []

    def export_local_bundle(self, output_dir, fixes):
        self.calls.append(("local", output_dir, dict(fixes)))
        return DeploymentResult(success=True, target=DeployTarget.LOCAL_EXPORT,
                                status_code=200,
                                message="Exported 3 files locally to " + output_dir)

    async def deploy_webhook(self, url, secret, payload):
        self.calls.append(("webhook", url, secret, payload))
        return DeploymentResult(success=True, target=DeployTarget.WEBHOOK_HMAC,
                                status_code=200,
                                message="Webhook successfully dispatched")

    async def deploy_wordpress(self, wp_url, wp_user, wp_pass, fixes):
        self.calls.append(("wordpress", wp_url, wp_user, dict(fixes)))
        return DeploymentResult(success=True, target=DeployTarget.WORDPRESS_REST,
                                status_code=200, message="WP ok")

    async def deploy_github(self, repo_owner, repo_name, branch, github_token, fixes):
        self.calls.append(("github", repo_owner, repo_name, branch,
                           github_token, dict(fixes)))
        return DeploymentResult(success=True, target=DeployTarget.GITHUB_COMMIT,
                                status_code=200,
                                message=f"Pushed to {repo_owner}/{repo_name}")


def _deploy_kur(monkeypatch, fake):
    """Gerçek CMSDeployer sinifinin methodlarini fake ile degistirir
    (class attribute patch — classmethod/async method cagrilarini yakalar)."""
    monkeypatch.setattr(CMSDeployer, "export_local_bundle",
                        fake.export_local_bundle)
    monkeypatch.setattr(CMSDeployer, "deploy_webhook", fake.deploy_webhook)
    monkeypatch.setattr(CMSDeployer, "deploy_wordpress", fake.deploy_wordpress)
    monkeypatch.setattr(CMSDeployer, "deploy_github", fake.deploy_github)


def _deploy_args(**ust):
    taban = dict(target="local", out=None, webhook_url=None, secret=None,
                 wp_url=None, wp_user=None, wp_pass=None,
                 gh_repo=None, gh_token=None, gh_branch=None,
                 brand="Test Brand", domain="test.example",
                 sector="dental", city="London")
    taban.update(ust)
    return _ns(**taban)


def test_deploy_local_bundle_disa_aktarir(monkeypatch, cap_cli, tmp_path):
    """target=local → export_local_bundle(out_dir, fixes) cagrilir; fixes
    uc uretimi (robots/llms/schema) icerir."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)
    out_dir = str(tmp_path / "dist")

    cli_mod.run_deploy_command(_deploy_args(target="local", out=out_dir))

    assert len(fake.calls) == 1
    tip, hedef, fixes = fake.calls[0]
    assert tip == "local"
    assert hedef == out_dir
    assert set(fixes) == {"robots.txt", "llms.txt", "schema.jsonld"}
    assert "test.example" in fixes["robots.txt"]
    assert "Exported 3 files locally" in cap_cli.getvalue()


def test_deploy_webhook_kimlik_yoksa_fail_closed(monkeypatch, cap_cli):
    """Webhook icin --webhook-url VE --secret zorunlu; eksikse erken donus
    ve deploy_webhook HIC cagrilmaz (fail-closed guard)."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(
        _deploy_args(target="webhook", webhook_url=None, secret="s3cr3t"))

    out = cap_cli.getvalue()
    assert "--webhook-url ve --secret zorunludur" in out
    assert fake.calls == []

    cap_cli.seek(0)
    cap_cli.truncate(0)
    cli_mod.run_deploy_command(
        _deploy_args(target="webhook", webhook_url="https://hook.example",
                     secret=None))
    assert "--webhook-url ve --secret zorunludur" in cap_cli.getvalue()
    assert fake.calls == []


def test_deploy_webhook_kimlik_varsa_gonderir(monkeypatch, cap_cli):
    """url+secret verilirse deploy_webhook(url, secret, payload) cagrilir."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(_deploy_args(
        target="webhook", webhook_url="https://hook.example",
        secret="s3cr3t"))

    assert fake.calls == [("webhook", "https://hook.example", "s3cr3t",
                           {"brand": "Test Brand",
                            "fixes": fake.calls[0][3]["fixes"]})]
    assert "Webhook successfully dispatched" in cap_cli.getvalue()


def test_deploy_wordpress_kimlik_yoksa_fail_closed(monkeypatch, cap_cli):
    """WordPress icin uc kimlik de zorunlu; eksikse erken donus."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(
        _deploy_args(target="wordpress", wp_url="https://wp.example",
                     wp_user=None, wp_pass="p"))

    assert "--wp-url, --wp-user ve --wp-pass zorunludur" in cap_cli.getvalue()
    assert fake.calls == []


def test_deploy_github_token_yoksa_fail_closed(monkeypatch, cap_cli):
    """GitHub icin --gh-repo VE --gh-token zorunlu; eksikse erken donus."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(
        _deploy_args(target="github", gh_repo="owner/repo", gh_token=None))

    assert "--gh-repo (owner/name) ve --gh-token zorunludur" in cap_cli.getvalue()
    assert fake.calls == []


def test_deploy_github_gecersiz_repo_formati_reddedilir(monkeypatch, cap_cli):
    """--gh-repo 'owner/name' degilse (partition ile name bos) reddedilir;
    deploy_github cagrilmaz — bozuk input hedefe ulasamaz."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(
        _deploy_args(target="github", gh_repo="yanlizca-owner",
                     gh_token="tok"))

    out = cap_cli.getvalue()
    assert "'owner/repository' biçiminde olmalıdır" in out
    assert fake.calls == []


def test_deploy_github_dal_ve_sahip_dogru_aktarilir(monkeypatch, cap_cli):
    """Gecerli 'owner/repo' + --gh-branch → deploy_github owner/name/branch
    ve token dogru argumanlarla cagrilir."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(_deploy_args(
        target="github", gh_repo="acme/aeo-site", gh_token="tok-42",
        gh_branch="prod"))

    assert len(fake.calls) == 1
    _tip, owner, name, branch, token, fixes = fake.calls[0]
    assert owner == "acme" and name == "aeo-site"
    assert branch == "prod"
    assert token == "tok-42"
    assert set(fixes) == {"robots.txt", "llms.txt", "schema.jsonld"}
    assert "Pushed to acme/aeo-site" in cap_cli.getvalue()


def test_deploy_github_dal_verilmezse_main_kullanilir(monkeypatch, cap_cli):
    """gh_branch None → varsayilan 'main' dalina dağıtılır."""
    fake = _FakeDeployer()
    _deploy_kur(monkeypatch, fake)

    cli_mod.run_deploy_command(_deploy_args(
        target="github", gh_repo="acme/aeo-site", gh_token="tok-42",
        gh_branch=None))

    assert fake.calls[0][3] == "main"


# ===========================================================================
# 5. DURUSTLUK — run_citations_command  (answrank/cli.py:157)
# ===========================================================================

class _FakeRunner:
    """MultiLLMCitationRunner'in yerini; run_citations kw'larini kaydeder."""

    def __init__(self):
        self.calls = []
        self.result = None

    async def run_citations(self, **kw):
        self.calls.append(kw)
        return self.result


async def _noop_save(self, citation_res):
    """db.save_citations'i testte erisilebilir kilar."""
    return None


def _citations_args(**ust):
    taban = dict(brand="Test Brand", domain="test.example", sector="dental",
                 city="London", lang="tr", live=False, competitors=None)
    taban.update(ust)
    return _ns(**taban)


def _citation_kur(monkeypatch, sonuc):
    runner = _FakeRunner()
    runner.result = sonuc
    monkeypatch.setattr(cli_mod, "MultiLLMCitationRunner", lambda: runner)
    monkeypatch.setattr("answrank.db.Database.save_citations", _noop_save)
    return runner


def test_citations_tam_simulasyon_uyarisi(monkeypatch, cap_cli):
    """live_items_count == 0 → 'TAM SİMÜLASYON' dürüstlük etiketi basilir
    (API anhtari yoksa oran model ciktisidir, gercek olcum degildir)."""
    runner = _citation_kur(monkeypatch, SimpleNamespace(
        live_items_count=0, grounding_status={}, total_runs=10,
        citation_rate_percentage=0.0, brand_citations_found=0,
        top_competitors={}))

    cli_mod.run_citations_command(_citations_args(live=False))

    out = cap_cli.getvalue()
    assert runner.calls and runner.calls[0]["live"] is False
    assert "TAM SİMÜLASYON" in out
    assert "gerçek ölçüm değildir" in out
    assert "0/10" in out


def test_citations_karisik_canlilik_etiketi(monkeypatch, cap_cli):
    """live>0 ama sim>0 → 'Canlılık: 3/10' karisik etiketi."""
    _citation_kur(monkeypatch, SimpleNamespace(
        live_items_count=3, grounding_status={}, total_runs=10,
        citation_rate_percentage=30.0, brand_citations_found=3,
        top_competitors={}))

    cli_mod.run_citations_command(_citations_args())

    out = cap_cli.getvalue()
    assert "Canlılık: 3/10 canlı API" in out
    assert "TAM SİMÜLASYON" not in out
    assert "Tamamı canlı" not in out


def test_citations_tamami_canli_etiketi(monkeypatch, cap_cli):
    """live == total_runs → 'Tamamı canlı API ölçümü: 10/10'."""
    _citation_kur(monkeypatch, SimpleNamespace(
        live_items_count=10, grounding_status={}, total_runs=10,
        citation_rate_percentage=100.0, brand_citations_found=7,
        top_competitors={}))

    cli_mod.run_citations_command(_citations_args(live=True))

    assert "Tamamı canlı API ölçümü: 10/10" in cap_cli.getvalue()


def test_citations_grounding_status_bosken_tablo_basilmaz(monkeypatch, cap_cli):
    """grounding_status {} veya None → 'Ölçüm Modalitesi' tablosu cizilmez."""
    for gs in ({}, None):
        cap_cli.seek(0)
        cap_cli.truncate(0)
        _citation_kur(monkeypatch, SimpleNamespace(
            live_items_count=10, grounding_status=gs, total_runs=10,
            citation_rate_percentage=100.0, brand_citations_found=1,
            top_competitors={}))
        cli_mod.run_citations_command(_citations_args())
        out = cap_cli.getvalue()
        assert "Ölçüm Modalitesi" not in out


def test_citations_grounding_status_dolu_tablo_basılır(monkeypatch, cap_cli):
    """grounding_status dolu → motor/modalite/aciklama tablosu basilir ve
    bilinen status aciklamalari kullanilir."""
    _citation_kur(monkeypatch, SimpleNamespace(
        live_items_count=4, grounding_status={
            "Perplexity-Sonar": "search-grounded",
            "GPT-Search": "model-recall",
            "Claude": "anahtar yok",
            "Bilinmeyen": "ozel-durum",
        }, total_runs=10, citation_rate_percentage=40.0,
        brand_citations_found=4, top_competitors={}))

    cli_mod.run_citations_command(_citations_args())

    out = cap_cli.getvalue()
    assert "Ölçüm Modalitesi (E10 — dürüst motor etiketi)" in out
    assert "Gerçek canlı aramadan kaynaklanan atıflar" in out
    assert "CANLI ATIF ölçümü değildir" in out
    assert "API anahtarı yok — bu motor ölçülmedi" in out
    # bilinmeyen status kendisi doner (fallback)
    assert "ozel-durum" in out


def test_citations_rakipler_ve_oran_gosterimi(monkeypatch, cap_cli):
    """En cok cikan rakipler ilk 3 ile gosterilir; oran yüzde olarak basilir."""
    _citation_kur(monkeypatch, SimpleNamespace(
        live_items_count=10, grounding_status={}, total_runs=10,
        citation_rate_percentage=42.5, brand_citations_found=5,
        top_competitors={"Rakip A": 9, "Rakip B": 6, "Rakip C": 3,
                         "Rakip D": 1}))

    cli_mod.run_citations_command(_citations_args())

    out = cap_cli.getvalue()
    assert "Rakip A" in out and "Rakip B" in out and "Rakip C" in out
    assert "Rakip D" not in out  # yalnizca ilk 3
    assert "%42.5" in out
    assert "5/10 soru×motor" in out


def test_citations_live_flag_runner_a_aktarilir(monkeypatch, cap_cli):
    """--live bayragi runner.run_citations(live=...) olarak iletilir."""
    runner = _citation_kur(monkeypatch, SimpleNamespace(
        live_items_count=10, grounding_status={}, total_runs=10,
        citation_rate_percentage=100.0, brand_citations_found=1,
        top_competitors={}))

    cli_mod.run_citations_command(_citations_args(live=True))

    assert runner.calls[0]["live"] is True
    assert runner.calls[0]["brand_name"] == "Test Brand"
    assert runner.calls[0]["domain"] == "test.example"
    assert runner.calls[0]["sector"] == "dental"
    assert runner.calls[0]["city"] == "London"


# ===========================================================================
# 6. FINANS — run_swarm_command  (answrank/cli.py:768)
# ===========================================================================

class _FakeSwarmOrch:
    """SwarmOrchestrator'in dis pipeline cagrilarini kaydeder."""

    def __init__(self):
        self.seed_kw = None
        self.cand = None
        self.result = None

    def seed_target(self, **kw):
        self.seed_kw = kw
        return SwarmCandidate(
            brand_name=kw["brand_name"], domain=kw["domain"],
            sector=kw.get("sector", "dental"), city=kw.get("city", "İstanbul"),
            country=kw.get("country", "TR"),
            currency=kw.get("currency", "TRY"))

    async def run_full_pipeline_sync(self, cand, on_event=None):
        self.cand = cand
        return self.result


def _swarm_sonuc(**ust):
    taban = dict(brand_name="Klinik A", city="London", country="UK",
                 stage=SwarmStage.AUDITED, deep_score=None,
                 lost_revenue_monthly=None, currency="GBP",
                 last_action="Audited", outreach_pitch=None,
                 fixes_generated=None, territory_locked=False,
                 fiscal_invoice_id=None, fiscal_tax_exempt_try=None)
    taban.update(ust)
    return SimpleNamespace(**taban)


def _swarm_kur(monkeypatch, sonuc):
    orch = _FakeSwarmOrch()
    orch.result = sonuc
    monkeypatch.setattr("answrank.agents.swarm.SwarmOrchestrator", lambda: orch)
    return orch


def _swarm_args(**ust):
    taban = dict(brand="Klinik A", domain="klinik-a.example", sector="dental",
                 city="London", country="UK", currency="GBP",
                 ticket=15000.0, agency=None)
    taban.update(ust)
    return _ns(**taban)


def test_swarm_kacan_ciro_hesaplanmadi_dali(monkeypatch, cap_cli):
    """lost_revenue_monthly None → 'Hesaplanmadı' (sayı uydurulmaz)."""
    orch = _swarm_kur(monkeypatch, _swarm_sonuc(lost_revenue_monthly=None))

    cli_mod.run_swarm_command(_swarm_args())

    out = cap_cli.getvalue()
    assert "Hesaplanmadı" in out
    assert orch.cand is not None
    assert orch.cand.brand_name == "Klinik A"


def test_swarm_kacan_ciro_formatlanmis_dali(monkeypatch, cap_cli):
    """lost_revenue_monthly var → 'GBP 12,346/ay' formatinda gosterilir."""
    _swarm_kur(monkeypatch, _swarm_sonuc(
        lost_revenue_monthly=12345.6, currency="GBP"))

    cli_mod.run_swarm_command(_swarm_args())

    assert "GBP 12,346/ay" in cap_cli.getvalue()


def test_swarm_seed_target_argumanlari_aktarilir(monkeypatch, cap_cli):
    """CLI argumanlari seed_target'a dogru aktarilir."""
    orch = _swarm_kur(monkeypatch, _swarm_sonuc())

    cli_mod.run_swarm_command(_swarm_args(
        brand="Klinik A", domain="klinik-a.example", sector="dental",
        city="Manchester", country="UK", currency="USD", ticket=25000.0,
        agency="ajans.example"))

    kw = orch.seed_kw
    assert kw["brand_name"] == "Klinik A"
    assert kw["domain"] == "klinik-a.example"
    assert kw["city"] == "Manchester"
    assert kw["country"] == "UK"
    assert kw["currency"] == "USD"
    assert kw["ticket_size"] == 25000.0
    assert kw["agency_domain"] == "ajans.example"


def test_swarm_uretim_paketi_sayisi(monkeypatch, cap_cli):
    """fixes_generated dolu → 'N adet üretim hazırlandı' mesaji."""
    _swarm_kur(monkeypatch, _swarm_sonuc(
        fixes_generated={"robots.txt": "a", "llms.txt": "b",
                        "llms-full.txt": "c", "schema.jsonld": "d"}))

    cli_mod.run_swarm_command(_swarm_args())

    out = cap_cli.getvalue()
    assert "4 adet üretim hazırlandı" in out
    assert "robots.txt, llms.txt, llms-full.txt, schema.jsonld" in out


def test_swarm_bolge_kilidi_mesaji(monkeypatch, cap_cli):
    """territory_locked=True → 'Bölge Münhasırlığı ... kilitlendi. Yamyamlaşma engellendi.'"""
    _swarm_kur(monkeypatch, _swarm_sonuc(
        territory_locked=True, city="London", country="UK", sector="dental"))

    cli_mod.run_swarm_command(_swarm_args())

    out = cap_cli.getvalue()
    assert "Bölge Münhasırlığı" in out
    assert "kilitlendi" in out
    assert "Yamyamlaşma engellendi" in out


def test_swarm_mali_fatura_mesaji(monkeypatch, cap_cli):
    """fiscal_invoice_id + fiscal_tax_exempt_try → mali defter fatura mesaji."""
    _swarm_kur(monkeypatch, _swarm_sonuc(
        fiscal_invoice_id="INV-2026-042", fiscal_tax_exempt_try=5000.0))

    cli_mod.run_swarm_command(_swarm_args())

    out = cap_cli.getvalue()
    assert "Fatura INV-2026-042 işlendi" in out
    assert "5,000" in out


def test_swarm_sahne_ve_skor_gosterimi(monkeypatch, cap_cli):
    """stage.value ve deep_score panelde gosterilir; deep_score None → 0."""
    _swarm_kur(monkeypatch, _swarm_sonuc(
        stage=SwarmStage.FULFILLED, deep_score=None,
        last_action="Full AEO/GEO bundle generated and dispatched"))

    cli_mod.run_swarm_command(_swarm_args())

    out = cap_cli.getvalue()
    assert "Durum: FULFILLED" in out
    assert "360° Skor: 0/100" in out
    assert "Full AEO/GEO bundle generated and dispatched" in out


def test_swarm_iletisim_metni_paneli(monkeypatch, cap_cli):
    """outreach_pitch var → ayri panel olarak basilir."""
    _swarm_kur(monkeypatch, _swarm_sonuc(
        outreach_pitch="Merhaba, kaçan ciwonuz var.",
        stage=SwarmStage.OUTREACH_SENT, deep_score=72.0))

    cli_mod.run_swarm_command(_swarm_args())

    out = cap_cli.getvalue()
    assert "Merhaba, kaçan ciwonuz var." in out
    # deep_score float oldugu icin '72.0/100' formatinda basilir
    assert "360° Skor: 72.0/100" in out
