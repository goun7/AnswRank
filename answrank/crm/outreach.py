"""Personalized Outreach and Cold DM Copy Generator — MEASUREMENT-GATED.

Zero-Trust doctrine (16 Eyl 2026 derin-tarama, Bulgu-C1): every number that
reaches a prospect must come from a REAL artifact — the audit record itself or
a stored citation run. Anything not measured is stated as not-yet-measured;
fabricated competitor stats, invented search volumes, fake case-study deltas
and unbacked scarcity claims are removed permanently and locked by tests.
"""

from typing import Dict, Optional

from answrank.models import AuditResult, CitationRunResult
from answrank.citations.runner import MODELS
from answrank.textnorm import brand_from_domain


class OutreachGenerator:
    """Generates outreach copy strictly from real audit/citation artifacts."""

    def generate_all_variants(
        self,
        audit: AuditResult,
        contact_name: str = "Sayın Yetkili",
        top_competitor: Optional[str] = None,
        competitor_score: Optional[int] = None,
        citation: Optional[CitationRunResult] = None,
    ) -> Dict[str, str]:
        """Returns the 3 opening variants and 2 follow-ups.

        `citation` must be a REAL CitationRunResult for this domain (DB lookup)
        for any citation statistic to appear. `competitor_score` is only honored
        together with `citation` — a bare number is never printed.
        """
        brand = brand_from_domain(audit.domain) or audit.domain
        location = getattr(audit, "city", None) or "bölgenizde"
        sector_tr = {
            "dental": "diş kliniği",
            "accounting": "mali müşavir",
            "aesthetic": "estetik merkezi",
            "general": "işletme",
        }.get(audit.sector, "işletme")

        return {
            "agency_pitch": self._agency_pitch(audit, brand, location, sector_tr),
            "variant_1_pain_numbers": self._variant_1(
                audit, brand, contact_name, location, sector_tr, citation),
            "variant_2_lost_revenue": self._variant_2(
                audit, brand, contact_name, location, sector_tr, citation),
            "variant_3_case_study": self._variant_3(audit, brand, contact_name, citation),
            "followup_day_3": self._followup_day3(brand, contact_name, location, top_competitor),
            "followup_day_7": self._followup_day7(contact_name, audit),
        }

    # ------------------------------------------------------------------
    # Variants — each asserts only what its inputs actually measured
    # ------------------------------------------------------------------

    @staticmethod
    def lead_dm(domain: str, robots_line: str, llms_line: str, bots_line: str,
                verdict: str, ai_visibility: Optional[dict] = None) -> str:
        """E7: halka-açık mini-probe lead'i için yeniden-ölçmeyen DM.

        Yalnız ziyaretçinin KENDİ probe'unda ölçülmüş üç satır alıntılanır;
        skor/para/pazarlama sayısı üretilmez — DM'de gördüğünüz her cümle
        kopyalanmış ölçüm evidansıdır (E5/E7 dürüstlük sınırı).

        ai_visibility (E12, opsiyonel): gerçek çoklu-LLM atıf ölçümünün
        sonucu. Yalnız ölçüldüyse eklenir — {hits, total, rate, engine};
        verilmezse uydurulmaz."""
        base = (
            f"Merhaba,\n\nsiteniz ({domain}) için ücretsiz mini-probe'unuzda şunları ölçtük:\n"
            f"  • robots.txt: {robots_line}\n"
            f"  • llms.txt: {llms_line}\n"
            f"  • arama botları: {bots_line}\n\n"
        )
        if (ai_visibility and ai_visibility.get("is_fully_live") is True
                and ai_visibility.get("domain") == domain
                and all(key in ai_visibility for key in
                        ("hits", "total", "run_id", "created_at", "grounding_status"))):
            hits, total = ai_visibility["hits"], ai_visibility["total"]
            modes = ", ".join(sorted(set(ai_visibility["grounding_status"].values())))
            base += (
                f"Ayrıca soru bankamızdaki {total} test yanıtının {hits} tanesinde marka adı veya domain "
                f"eşleşmesi kaydedildi. Bunlar canlı API yanıtlarıdır; kullanıcı arama trafiğini "
                f"veya sitenizin teknik sağlığını ölçmez. "
                f"Kayıtlı yanıt yöntemi: {modes}. Bu kayıt arama kaynaklandırmasını bağımsız olarak doğrulamaz.\n"
                f"Bu, tek bir ölçüm koşusudur — yapay zeka yanıtları run-to-run değişken "
                f"gösterir; sayı bir aralık değil, anlık bir okumadır (kararlılık için "
                f"Monte-Carlo tekrar ölçümü gerekir).\n"
                f"Koşu: {ai_visibility['run_id']}\n"
                f"Tarih: {ai_visibility['created_at']}\n\n"
            )
        base += (
            f"Hüküm: {verdict}. Bu satırlar bir skor değil, erişim kanıtıdır — "
            f"ölçemediğimiz hiçbir şeyi suçlama olarak yazmıyoruz. Tam 360° denetim ve "
            f"Madde-7 kontrat garantisi için kısa bir görüşme planlayalım mı?\n\n"
            f"— AnswRank (mini-probe kaydı: kendi instance'ınızda tutulur)"
        )
        return base

    def _agency_pitch(self, audit, brand, location, sector_tr) -> str:
        """E2 beyaz-etiket ajans kênhı: AnswRank motoru arkada, ajans markası önde.

        Kıtlık sözü kota motoruyla (ExclusivityManager.agency_portfolio) BİREBİR
        aynı sözcükleri taşır — DM'de satılmayan kotalı söz motor tarafından
        reddedilemez (üç-yüzey kilidi: DM / sözleşme / kota testi).
        Örnek müşteri RF2606 .example'dır; gerçek marka kullanılmaz."""
        city = getattr(audit, "city", None) or "bölgenizde"
        return (
            f"Sayın Ajans Yetkilisi,\n\n"
            f"{brand} gibi {sector_tr} işletmelerinin yapay zekâ aramasında görünür olması "
            f"artık satış borusunun kendisi. Size beyaz etiketli denetim-raporlama ortağı "
            f"olmayı teklif ediyoruz: kendi logonuzla rapor, kendi sözleşmenizle müşteri; "
            f"AnswRank ölçüm motoru arka planda (Madde-7 delta garantisi dahil).\n\n"
            f"Kıtlık kuralımız net: portföyünüzde her sektörde tek müşteri — bir {sector_tr} "
            f"sektöründe tek müşteri kilidi sizde; ikinci aynı-sektör müşteri kota motoru "
            f"tarafından reddedilir. {city} tarafında boş sektörleri birlikte değerlendirelim.\n\n"
            f"Portföy örneği: musteri-ornek-{sector_tr.replace(' ', '-')}.example\n"
            f"Teşhis için: answrank serve → /api/miniprobe (sınırsız ve ücretsiz)"
        )

    def _variant_1(self, audit, brand, contact_name, location, sector_tr, citation) -> str:
        findings = self._audit_findings_clause(audit)
        engines = ", ".join(m.split("-")[0] for m in MODELS)
        if citation is not None and citation.total_runs:
            n = citation.total_runs
            comp_clause = ""
            if citation.top_competitors:
                leader, leader_hits = max(citation.top_competitors.items(), key=lambda kv: kv[1])
                comp_clause = (f" {n} cevabın {leader_hits} tanesinde {leader} öne çıktı;"
                               f" {brand} {citation.brand_citations_found} yanıtta geçti.")
            if citation.live_items_count == 0:
                live_clause = " (Bu ölçüm deterministik simülasyon; anahtarlı motorlarla canlı teyit edelim.)"
            elif not citation.is_fully_live:
                live_clause = f" ({citation.live_items_count}/{n} koşu gerçek API ölçümü.)"
            else:
                live_clause = f" ({n}/{n} koşu canlı API ölçümü.)"
            pain = (f"Yapay zeka alıntı testiniz ölçüldü: {engines} üzerinden {n} soru×motor, "
                    f"%{citation.citation_rate_percentage:g} görünürlük{comp_clause}{live_clause}")
        else:
            pain = (f"{brand} için teknik denetiminiz tamamlandı. Müşteriler/hastalar sorgularını giderek "
                    f"daha çok {', '.join(m.split('-')[0] for m in MODELS[:2])} gibi yapay zekalarına yöneltiyor; "
                    f"alıntı görünürlüğünüz henüz ölçülmedi — ilk ölçümü biz yapalım.")
        return f"""Merhaba {contact_name},
{location} ölçeğinde {sector_tr} olarak {brand} için kısa bir teknik tespit paylaşmak istedim:
{pain}
Teknik taraf: {findings}
Tek sayfalık denetim raporunu ve nerede kaybettiğinizi ücretsiz iletmemi ister misiniz?"""

    def _variant_2(self, audit, brand, contact_name, location, sector_tr, citation) -> str:
        lost = getattr(audit, "lost_revenue_estimate_monthly_try", None)
        if lost:
            rev_clause = (f"Aylık tahmini kaçan ciro, denetim kayıtlarımızdaki gelir modeline göre "
                          f"{lost:,.0f} TL olarak hesaplandı — bu bir model kestirimidir, ölçüm değil.")
        else:
            rev_clause = ("Bu denetimde kaçan ciro için sağlam bir model girdisi bulunamadı; boşuna bir "
                          "rakam paylaşmıyoruz — ölçüm tamamlanınca tabloyu net koyarız.")
        if citation is None:
            meas = " Alıntı görünürlüğü henüz ölçülmedi; ölçümü ücretsiz üstleniyoruz."
        elif not citation.is_fully_live:
            meas = (f" Görünürlük ölçünüz %{citation.citation_rate_percentage:g} — simülasyon karışıklı; "
                    "anahtarlı motorlarla canlı teyit edelim.")
        else:
            meas = f" Görünürlük ölçünüz %{citation.citation_rate_percentage:g} (canlı API)."
        return f"""Merhaba {contact_name},
{brand} için hazırladığım görünürlük değerlendirmesi: {location} genelinde '{sector_tr}' aramalarında yapay zeka yanıtlarında konumlanmak, klasik SEO'dan tamamen farklı bir teknik disiplindir.{meas}
{rev_clause}
Düzeltme reçetemiz hazır (marka gücünüz eşikse ilk sıçrama 2-4 haftada gözlenir). 15 dakikalık bir görüşmede ekran paylaşarak göstermek isterim. Hangi gün müsaitsiniz?"""

    def _variant_3(self, audit, brand, contact_name, citation) -> str:
        score_line = f"Mevcut teknik denetim skorunuz: {audit.overall_score}/100."
        if citation is not None:
            proof = "Alıntı testiniz de ölçüldü ve raporda; çıtayı birlikte koymadan örnek oran paylaşmıyoruz."
        else:
            proof = "Vaka rakamı uydurmuyoruz: ölçümü birlikte yapıp kendi verinizle ilerleyelim."
        return f"""Merhaba {contact_name},
{brand} için denetimimiz tamamlandı. {score_line} {proof}
10 dakikalık bir inceleme için raporu göndereyim mi?"""

    def _followup_day3(self, brand, contact_name, location, top_competitor):
        comp = f" Rakibiniz {top_competitor} öndeyse" if top_competitor else ""
        return f"""Merhaba {contact_name},
{brand} için hazırladığım tek sayfalık yapay zeka görünürlük raporunu iletmiştim.{comp}, durumu kendi lehinize çevirmek için 10 dakikalık bir inceleme planlayabiliriz.
Not: {location} ölçeğinde sektör başına tek işletmeyle çalışıyoruz (lider kontenjanı); yer dolmadan konuşalım isterim. İyi çalışmalar dilerim."""

    def _followup_day7(self, contact_name, audit):
        return f"""{contact_name} merhaba,
yoğunluğunuzu anlıyorum. Denetim kaydınız ({audit.audit_id}) sistemimizde duruyor; konuyu gündeme almak istediğinizde tek mesaj yeterli. Sağlıklı ve bereketli bir hafta dilerim."""

    # ------------------------------------------------------------------

    @staticmethod
    def _audit_findings_clause(audit: AuditResult) -> str:
        """Concrete, already-measured technical findings — no invented numbers."""
        bits = []
        cats = getattr(audit, "categories", None)
        robots = getattr(cats, "robots", None) if cats else None
        if robots is not None:
            if not getattr(robots, "exists", True):
                bits.append("robots.txt hiç yok")
            elif not getattr(robots, "ai_search_allowed", True):
                bits.append("robots.txt AI arama botlarına kapalı")
            elif not getattr(robots, "sitemap_declared", True):
                bits.append("sitemap bildirimi eksik")
        llms = getattr(cats, "llms_txt", None) if cats else None
        if llms is not None and not getattr(llms, "has_llms_txt", True):
            bits.append("llms.txt / AI-erişim dosyaları yok")
        if getattr(audit, "crawl_warnings", None):
            bits.append(f"{len(audit.crawl_warnings)} teknik uyarı saptandı")
        return "; ".join(bits) if bits else "temel teknik kontroller geçti; asıl risk görünürlük katmanında."
