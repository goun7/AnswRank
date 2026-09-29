"""Objection Handling & Automated Rebuttal Generator for AnswRank CRM.

Implements the 5 primary objection categories and response scripts
specified in Bölüm 6.3 of ANSWRANK_MASTER_100.md.
"""

import re
from enum import Enum
from typing import Dict, List
from pydantic import BaseModel
from answrank.config import settings


class ObjectionCode(str, Enum):
    SEO_ALREADY = "SEO_ALREADY"
    AUDIENCE_OLD = "AUDIENCE_OLD"
    PRICE_OR_GUARANTEE = "PRICE_OR_GUARANTEE"
    IN_HOUSE_OR_AGENCY = "IN_HOUSE_OR_AGENCY"
    NEED_TIME = "NEED_TIME"
    UNKNOWN = "UNKNOWN"


class ObjectionScript(BaseModel):
    code: ObjectionCode
    title: str
    sample_phrases: List[str]
    rebuttal_template: str
    talking_points: List[str]


class RebuttalResponse(BaseModel):
    matched_code: ObjectionCode
    confidence: float
    rebuttal_text: str
    recommended_talking_points: List[str]


class ObjectionLibrary:
    """Library containing the 5 core objection scripts from ANSWRANK_MASTER_100.md."""

    SCRIPTS: Dict[ObjectionCode, ObjectionScript] = {
        ObjectionCode.SEO_ALREADY: ObjectionScript(
            code=ObjectionCode.SEO_ALREADY,
            title="Biz Zaten Google'da İlk Sıradayız / SEO Yapıyoruz",
            sample_phrases=[
                "google'da ilk sıradayız",
                "bizim seo ajansımız var",
                "organik aramada zaten çıkıyoruz",
                "seo çalışması yapıyoruz",
                "google'da birinciyiz",
            ],
            rebuttal_template=(
                "Google'da ilk sırada olmanız harika bir başarı; ancak AEO (Answer Engine Optimization) ile "
                "klasik SEO tamamen farklı mekanizmalara dayanır. Ahrefs'in 2026 araştırmasına göre, ChatGPT'nin "
                "kaynak gösterdiği URL'lerin yalnızca %12'si aynı sorguda Google ilk 10'da yer alıyor — %88'i klasik SEO hedefiyle örtüşmüyor (Ahrefs, Ağustos 2025, 15.000 prompt analizi). "
                "Kullanıcılar artık Google'da 10 mavi link arasında gezinmek yerine, ChatGPT veya Perplexity'ye "
                "'en iyi {sector} hangisi?' diye sorup tek bir tavsiye alıyor. {company} olarak siteniz kritik AI arama botlarına (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Google-Extended gibi) kapalıysa "
                "veya llms.txt standardına sahip değilse, Google 1. sıranız AI cevaplarında hiçbir şey ifade etmez."
            ),
            talking_points=[
                "SEO ≠ AEO: Klasik pagerank mantığı LLM RAG mimarisinde doğrudan kaynak garantisi vermez.",
                "Ahrefs verisi (Ağustos 2025): AI atıflarının yalnızca %12'si Google ilk 10'da — %88 yeni fırsat alanı.",
                "Tek Yanıt Monopolü: AI 10 link değil, 1 sentezlenmiş yanıt ve 3 referans verir.",
            ],
        ),
        ObjectionCode.AUDIENCE_OLD: ObjectionScript(
            code=ObjectionCode.AUDIENCE_OLD,
            title="Bize Yapay Zekadan Müşteri Gelmez / Kitlemiz Klasik",
            sample_phrases=[
                "bizim kitle yapay zeka kullanmaz",
                "müşterilerimiz yaşlı",
                "bize oradan hasta gelmez",
                "bizim sektör için erken",
                "geleneksel yöntemler yeterli",
            ],
            rebuttal_template=(
                "Hizmet alan kitlenizin profili geleneksel olsa dahi, onların yerine karar veren veya araştırma yapan "
                "çocukları, yakınları ve profesyonellerin %32'si doğrudan ChatGPT ve Gemini'de tavsiye aramaktadır. "
                "ChatGPT haftalık 900+ milyon aktif kullanıcıya ulaşmıştır. Yapay zeka aramalarında {company} yerine "
                "{competitor} referans gösterildiğinde, yüksek bütçeli bilinçli müşteri doğrudan rakibe gitmektedir."
            ),
            talking_points=[
                "Karar verici dinamiği: Hizmet alan kişi değil, satın alma kararını yönlendiren aile üyesi AI kullanıyor.",
                "Haftalık 900M+ aktif ChatGPT kullanıcısı.",
                "Kayıp maliyeti: Rakip gösterildiğinde giden her hasta yüksek bilet kaybıdır.",
            ],
        ),
        ObjectionCode.PRICE_OR_GUARANTEE: ObjectionScript(
            code=ObjectionCode.PRICE_OR_GUARANTEE,
            title="Fiyat Yüksek / Garantisi Var mı?",
            sample_phrases=[
                "fiyat çok yüksek",
                "bütçemize uygun değil",
                "garanti veriyor musunuz",
                "kesin sonuç garantisi var mı",
                "pahalı geldi",
            ],
            rebuttal_template=(
                "AnswRank'te spekülatif vaatlerde bulunmuyoruz; sözleşmemizin Madde 7'sinde yer alan 'Ölçülebilir Delta Garantisi' "
                "ile tüm riski üzerimize alıyoruz. 14 gün sonunda sektörünüzün 20 kritik sorusunda yapay zeka atıflarınızda "
                "ve denetim skorunuzda net delta (artış) sağlanamazsa, takip eden ayı hiçbir ek ücret ödemeksizin "
                "ücretsiz optimizasyonla sürdürüyoruz. Yatırımınız tek bir yüksek bütçeli hastayla/müşteriyle kendini amorti eder."
            ),
            talking_points=[
                "Sözleşmeli Madde 7 Performans Güvencesi: Hedef delta tutmazsa sonraki ay ücretsiz hizmet.",
                "Birim ekonomi: Tek bir implant/danışmanlık işlemi hizmet bedelini karşılar.",
                "Sıfır risk: Hukuki regülasyonlara tam uyumlu delta garantisi.",
            ],
        ),
        ObjectionCode.IN_HOUSE_OR_AGENCY: ObjectionScript(
            code=ObjectionCode.IN_HOUSE_OR_AGENCY,
            title="Bunu Kendi Ajansımız / Ekibimiz Yapamaz mı?",
            sample_phrases=[
                "kendi ajansımıza söyleriz",
                "içerideki yazılımcımız halleder",
                "mevcut ekibimiz baksın",
                "ajansımız bunu yapar",
            ],
            rebuttal_template=(
                "Geleneksel web ajansları veya içerik ekipleri klasik web sayfaları için uzmandır; ancak AnswRank, "
                f"{settings.ai_bots_total} bağımsız AI botunun (GPTBot, ClaudeBot, PerplexityBot, xAI-SearchBot vb.) robots.txt mimarisini, llms.txt ve llms-full.txt "
                "standartlarını, JSON-LD semantik bilgi grafiği entegrasyonunu ve RAG chunking optimizasyonunu sağlar. "
                "Bu derin teknik denetimi ajansınıza hazır bir aksiyon listesi (Ready-to-Deploy Fixes) olarak sunuyoruz; "
                "dolayısıyla mevcut ekibinizin işini zorlaştırmaz, onlara kılavuzluk eder."
            ),
            talking_points=[
                "Ajansla çatışma değil sinerji: Hazır JSON-LD, robots ve llms.txt kod blokları sunulur.",
                f"{settings.ai_bots_total} AI botu (3 katman: {len(settings.ai_bots_search)} arama + {len(settings.ai_bots_training)} eğitim + {len(settings.ai_bots_user_agents)} kullanıcı-ajanı) ve RAG chunking klasik ajansların uzmanlık alanı dışındadır.",
                "Zamandan tasarruf: Ekibinizin haftalarca araştıracağı protokolleri tek günde teslim ederiz.",
            ],
        ),
        ObjectionCode.NEED_TIME: ObjectionScript(
            code=ObjectionCode.NEED_TIME,
            title="Düşünmem Lazım / Hemen Karar Veremem",
            sample_phrases=[
                "biraz düşünelim",
                "sonra konuşalım",
                "önümüzdeki ay bakalım",
                "ortaklarıma danışmam lazım",
                "hemen karar veremem",
            ],
            rebuttal_template=(
                "Elbette değerlendirebilirsiniz; ancak üretici yapay zeka modelleri bilgi grafiklerini ilk taramada "
                "belleklerine alarak 'Erken Giren Marka Avantajı' (First-Mover Advantage) oluşturur. "
                "Şu an bölgenizde {competitor} atıf alırken {company} görünmüyorsa, ertelenen her hafta AI modellerinin "
                "rakibinizi birincil otorite olarak pekiştirmesi anlamına gelir. 14 günlük pencereyi kaçırmamak adına "
                "risksiz pilot denetimimizle bu hafta başlayabiliriz."
            ),
            talking_points=[
                "İlk giren marka avantajı (First-Mover Advantage) AI modellerinde kalıcı otorite oluşturur.",
                "Beklenen her gün rakip markanın pekişmesi ve organik hasta/danışan kaybı demektir.",
                "Hemen başlatılabilir, risksiz delta garantili süreç.",
            ],
        ),
    }


class ObjectionHandler:
    """Matches candidate objections and formats customized rebuttals."""

    @classmethod
    def detect_objection(cls, text: str) -> ObjectionCode:
        """Detect objection code using keyword, phrase and stem heuristics."""
        clean_text = text.lower()

        for code, script in ObjectionLibrary.SCRIPTS.items():
            for phrase in script.sample_phrases:
                if phrase in clean_text:
                    return code

        # Agglutinative Turkish stem checks
        if re.search(r"(fiyat|pahalı|bütçe|maliyet|garanti)", clean_text):
            return ObjectionCode.PRICE_OR_GUARANTEE
        if re.search(r"(ajans|yazılımcı|ekip|kendimiz|içeri|içimiz)", clean_text):
            return ObjectionCode.IN_HOUSE_OR_AGENCY
        if re.search(r"(seo|google|sıra|arama|organik)", clean_text):
            return ObjectionCode.SEO_ALREADY
        if re.search(r"(yaşlı|kitle|gelmez|geleneksel|kullanmaz)", clean_text):
            return ObjectionCode.AUDIENCE_OLD
        if re.search(r"(düşün|sonra|bekle|zaman|ortak)", clean_text):
            return ObjectionCode.NEED_TIME

        return ObjectionCode.UNKNOWN


    @classmethod
    def generate_rebuttal(
        cls,
        text: str,
        company_name: str = "İşletmeniz",
        sector: str = "sağlık/hizmet",
        competitor_name: str = "en yakın rakibiniz",
    ) -> RebuttalResponse:
        """Generate tailored rebuttal response based on detected objection."""
        code = cls.detect_objection(text)

        if code == ObjectionCode.UNKNOWN:
            return RebuttalResponse(
                matched_code=ObjectionCode.UNKNOWN,
                confidence=0.0,
                rebuttal_text=(
                    f"Anlıyorum. Günümüz yapay zeka arama motorlarında {company_name} olarak görünürlük kazanmanız "
                    f"ve doğrudan referans gösterilmeniz kritik bir rekabet avantajıdır. 14 günlük Delta Garantimizle "
                    f"nasıl ilerleyebileceğimizi 15 dakikalık kısa bir görüşmede aktarabiliriz."
                ),
                recommended_talking_points=[
                    "Ölçülebilir Delta Garantisi ve risksiz başlangıç.",
                    "Sektördeki ilk 3 AI kaynağı arasında yer alma hedefi.",
                ],
            )

        script = ObjectionLibrary.SCRIPTS[code]
        formatted_rebuttal = script.rebuttal_template.format(
            company=company_name,
            sector=sector,
            competitor=competitor_name,
        )

        return RebuttalResponse(
            matched_code=code,
            confidence=0.95,
            rebuttal_text=formatted_rebuttal,
            recommended_talking_points=script.talking_points,
        )
