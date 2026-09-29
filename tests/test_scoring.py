"""Mathematical scoring and AuditEngine tests."""

from answrank.audit.engine import AuditEngine
from answrank.audit.crawler import CrawlData

def test_category_caps_total_hundred_behaviorally():
    """Caps live ONLY in the analyzers (settings.weights was a dead duplicate and
    was removed 16 Eyl). Behavioral proof: a perfect-signal site reaches exactly
    100 — i.e. the eight analyzer caps sum to 100 (see test_audit_engine_perfect_site)."""
    from answrank.config import settings as _st
    assert not hasattr(_st, "weights"), "dead duplicate config must not come back"

def test_audit_engine_perfect_site():
    """Audit a site with perfect AEO/GEO signals -> score should be 100, band 'Excellent'."""
    engine = AuditEngine()

    robots_content = """
    User-agent: *
    Allow: /
    User-agent: OAI-SearchBot
    Allow: /
    User-agent: PerplexityBot
    Allow: /
    User-agent: Claude-SearchBot
    Allow: /
    User-agent: Google-Extended
    Allow: /
    Sitemap: https://yilmazdental.com/sitemap.xml
    # https://yilmazdental.com/llms.txt
    """

    llms_content = """
    # Yılmaz Dental Clinic
    > Kadıköy Bağdat Caddesi implant ve estetik diş kliniği.
    ## Tedaviler
    - Zirkonyum
    - İmplant
    ## İletişim
    [llms-full.txt](https://yilmazdental.com/llms-full.txt)
    """

    html_content = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <title>Yılmaz Dental Clinic — Kadıköy En İyi Diş Kliniği</title>
      <meta name="description" content="Kadıköy Bağdat Caddesi'nde garantili implant ve estetik diş hekimliği hizmeti sunuyoruz.">
      <link rel="canonical" href="https://yilmazdental.com/">
      <meta property="og:title" content="Yılmaz Dental">
      <meta property="article:modified_time" content="2026-09-01">
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@graph": [
          {
            "@type": "Dentist",
            "name": "Yılmaz Dental Clinic",
            "telephone": "+902161234567",
            "address": "Kadıköy İstanbul",
            "geo": {"@type": "GeoCoordinates", "latitude": 41.0, "longitude": 29.0},
            "priceRange": "$$",
            "sameAs": ["https://maps.google.com/test", "https://instagram.com/yilmaz", "https://linkedin.com/yilmaz"]
          },
          {
            "@type": "FAQPage",
            "mainEntity": [
              {"@type": "Question", "name": "İmplant acıtır mı?", "acceptedAnswer": {"@type": "Answer", "text": "Hayır acıtmaz."}}
            ]
          }
        ]
      }
      </script>
    </head>
    <body>
      <h1>Kadıköy Estetik Diş Kliniği</h1>
      <h2>Uzman Kadro</h2>
      <h3>İmplantoloji</h3>
      <p>Kadıköy implant tedavisi için uzman kadromuzla 10 yıl garantili çözümler sunuyoruz.</p>
      <p>Dr. Yılmaz belirtmektedir: "Kliniğimizde %98.4 başarı oranıyla 3.500 vaka tamamlandı."</p>
      <p>İletişim: 0216 123 45 67, Bağdat Caddesi No: 42 Kadıköy İstanbul.</p>
      <ul><li>Dijital Tarama</li><li>Ağrısız Cerrahi</li></ul>
      <table><tr><td>Hizmet</td><td>Fiyat</td></tr></table>
      <a href="https://maps.google.com/test">Google Maps</a>
      <a href="https://instagram.com/yilmaz">Instagram</a>
      <a href="https://linkedin.com/yilmaz">LinkedIn</a>
      <a href="/kvkk">KVKK Metni</a>
      <p>Kliniğimizde estetik gülüş tasarımı, porselen lamina ve zirkonyum kaplama işlemleri steril ameliyathane ortamında gerçekleştirilir. Yurt içi ve yurt dışından gelen tüm hastalarımıza kişiselleştirilmiş tedavi planı sunulmaktadır. Dijital panoramik röntgen ve 3D tomografi cihazlarımızla teşhis sürecini dakikalar içinde tamamlıyoruz. Ağrısız sedasyon ünitemiz sayesinde diş hekimi korkusu olan yetişkin ve çocuk hastalarımıza konforlu ve güvenli bir tedavi deneyimi sağlıyoruz. Tüm cerrahi operasyonlarımız Sağlık Bakanlığı onaylı hekimlerimiz tarafından yürütülmektedir. Randevu öncesinde hastalarımıza detaylı maliyet şeffaflığı ve tedavi aşamaları yazılı olarak sunulur. Kliniğimiz Kadıköy vapur iskelesine ve toplu taşıma merkezlerine beş dakikalık yürüme mesafesindedir.</p>
    </body>
    </html>
    """

    crawl = CrawlData(
        url="https://yilmazdental.com/",
        domain="yilmazdental.com",
        html_content=html_content,
        status_code=200,
        headers={"content-type": "text/html"},
        robots_txt=robots_content,
        llms_txt=llms_content,
        llms_full_txt="Full documentation",
        is_https=True,
    )

    res = engine.audit_crawl_data(crawl, sector="dental")
    assert res.overall_score >= 90
    assert res.score_band == "Excellent"
    assert res.categories.robots.score == 18
    assert res.categories.llms_txt.score == 18
    assert res.categories.schema_jsonld.score == 16
    assert res.categories.meta_architecture.score == 14
    assert res.categories.citability_rag.score == 12
    assert res.categories.entity_coherence.score == 10
    assert res.categories.trust_stack.score == 6
    assert res.categories.negative_signals.score == 6
    assert res.overall_score == 100

def test_audit_engine_critical_site():
    """Audit an empty/unoptimized site -> score should be in 'Critical' band."""
    engine = AuditEngine()
    crawl = CrawlData(
        url="https://poor-site.com/",
        domain="poor-site.com",
        html_content="<html><body><p>Yetersiz içerik.</p></body></html>",
        status_code=200,
        headers={"content-type": "text/html"},
        robots_txt=None,
        llms_txt=None,
        is_https=False,
    )
    res = engine.audit_crawl_data(crawl, sector="dental")
    assert res.overall_score < 35
    assert res.score_band == "Critical"
    assert len(res.recommendations) >= 3
    assert res.lost_revenue_estimate_monthly_try > 0
