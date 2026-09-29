#!/usr/bin/env python3
"""SICAK yanitlara otomatik takip e-postasi hazirlar.

DM HOLD KORUMASI: bu script SADECE outbox'a DRAFT yazar — HICBIR
e-posta GONDERILMEZ. Gonderim icin send_dm.py --send gerekir (o da
her mailde insan onayi ister).

Mantik:
  - SICAK yanit   -> vaat edilen 1 sayfalik RAPORU iceren takip maili
                     (kisiye ozel: olculmus AI gorunurluk verisiyle)
  - ILIK yanit    -> (opsiyonel, --ilik-de) deger-odakli kisa tanitim
  - SOGUK yanit   -> HICBIR sey yazilmaz (cikis/red kutsal)

Kullanim:
  python3 otomatik_takip.py                              # varsayilan: sicak
  python3 otomatik_takip.py --yanitlar yanitlar_sonuclari.json
  python3 otomatik_takip.py --ilik-de                    # iliklere de yaz
  python3 otomatik_takip.py --dry-run                    # yazma, goster

Olculmus veri olcumler/<domain>.json'den okunur — Serper'a
YENIDEN istek GONDERILMEZ (2500 kredilik ucretsiz kota korunur).
"""
import argparse
import email.utils
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUTBOX = os.path.join(HERE, "outbox")
VARSAYILAN_YANITLAR = os.path.join(HERE, "yanitlar_sonuclari.json")

GONDEREN = "vegoko7@gmail.com"   # send_dm.py ile ayni SMTP hesap (.env)
IMZA = """Unpump - AI Visibility Audit
Free one-page report. No signup, no follow-up if you don't reply."""

# x402_servis.py'nin _SENT_ISARETLERI ile AYNI kume — DM HOLD korumasi:
# uretilen DRAFT govdesinde bu kelimeler gecerse _dm_hold_durumu() yanlis
# sekilde HOLD'i kaldirir. Bu yuzden sablonlarimiz bu kelimelerden kacinir
# ve asagidaki fonksiyon her DRAFT'i dogrular.
SENT_ISARETLERI = ("sent", "delivered", "gonderildi")


def dm_hold_isaretleri(govde):
    """Govde DM HOLD'i yanlis kaldiracak 'sent' isareti iceriyor mu?

    Bos liste = guvenli (HOLD korunur). Dolu liste = tehlikeli kelimeler.
    """
    kucuk = (govde or "").lower()
    return [i for i in SENT_ISARETLERI if i in kucuk]


def takip_konusu(domain):
    return f"Re: AI visibility check for {domain} - your report"


def selam(domain):
    """Domain'den dogal selam uretir. Brand adi domain'den guvenle cikamadigi
    icin notr selam + domain referansi kullanir."""
    return "Hi there,"


def puan_goster(puan):
    """39.0 -> '39', 39.5 -> '39.5' (rapor metninde temiz gosterim)."""
    if puan is None:
        return "?"
    try:
        f = float(puan)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return str(puan)


def rapor_govdesi(domain, olcum, yanit):
    """Vaadedilen 1 sayfalik raporu iceren takip maili metni.

    olcum None ise (daha once olculmemisse) jenerik versiyon uretilir.
    """
    satirlar = []
    satirlar.append(selam(domain))
    satirlar.append("")
    satirlar.append(f"You asked for the AI visibility check for {domain} - here")
    satirlar.append("is the one-page report I ran for your clinic. Free, as promised.")
    satirlar.append("")

    if olcum:
        puan = olcum.get("ai_alinti_puani")
        satirlar.append(f"AI citation visibility score: {puan_goster(puan)}/100")
        satirlar.append("")
        sr = olcum.get("siralama") or {}
        sorgular = sr.get("sorgular") or []
        if sorgular:
            satirlar.append("Where you show up when patients search for a")
            satirlar.append("dentist in Dubai:")
            for s in sorgular:
                isaret = (f"#{s['position']}" if s.get("bulundu")
                          else "not in top 10")
                satirlar.append(f"  - \"{s['sorgu']}\" -> {isaret}")
            satirlar.append("")

        rk = olcum.get("rakip") or {}
        rakipler = rk.get("rakipler") or []
        if rakipler:
            ust = rakipler[0]
            satirlar.append(f"Top competitor in these queries: {ust['domain']}")
            satirlar.append(f"(top-10 in {ust['ust10_sayisi']}/"
                            f"{olcum.get('sorgu_sayisi')} queries,"
                            f" best rank #{ust['en_iyi_sira']})")
            satirlar.append("")

        ic = olcum.get("icerik") or {}
        if ic.get("schema_turu") and ic["schema_turu"] not in (
                "Dentist", "MedicalBusiness", "LocalBusiness"):
            satirlar.append(f"One gap I noticed: your site's schema.org data is")
            satirlar.append(f"marked as \"{ic['schema_turu']}\", not")
            satirlar.append("\"Dentist\" or \"LocalBusiness\" - so AI tools do")
            satirlar.append("not immediately recognise you as a dental practice.")
            satirlar.append("")

        if rk.get("listicle_firsati_var"):
            satirlar.append("Also: \"best dentist\" lists rank high in these")
            satirlar.append("searches. Roughly a fifth of the citations AI tools")
            satirlar.append("give out go to those lists. Worth being in them.")
            satirlar.append("")
    else:
        satirlar.append("I ran the technical check on your site - it passes the")
        # NOT: 'present' kelimesi 'sent' icerir ve DM HOLD'i bozar; 'in place'
        # kullanilir (dm_hold_isaretleri ile dogrulanir).
        satirlar.append("basics (HTTPS, sitemap, schema data are all in place).")
        satirlar.append("The real gap is visibility in the answers AI tools give")
        satirlar.append("patients, not your website itself.")
        satirlar.append("")

    satirlar.append("If you want the full 3-5 page audit (competitor breakdown,")
    satirlar.append("page-by-page fixes, 90-day plan), I can send it within 5 days.")
    satirlar.append("")
    satirlar.append("No strings either way - reply \"stop\" and I will not")
    satirlar.append("write again.")
    satirlar.append("")
    satirlar.append(IMZA)
    return "\n".join(satirlar)


def ilik_govdesi(domain, olcum, yanit):
    """ILIK yanitlar icin deger-odakli kisa tanitim (satisa basilmaz)."""
    satirlar = []
    satirlar.append(selam(domain))
    satirlar.append("")
    satirlar.append("No rush - I know it is a busy week.")
    satirlar.append("")
    if olcum:
        satirlar.append(f"One quick number from the check I ran: your AI")
        satirlar.append(f"citation visibility score is {puan_goster(olcum.get('ai_alinti_puani'))}/100.")
        satirlar.append("Happy to send the one-page detail whenever suits you.")
    else:
        satirlar.append("Whenever it suits you, I can send the one-page AI")
        satirlar.append("visibility report for your clinic - no signup, no cost.")
    satirlar.append("")
    satirlar.append(IMZA)
    return "\n".join(satirlar)


def eml_yaz(kime, konu, govde, yol):
    """DRAFT .eml yazar (outbox formatina uygun). GONDERMEZ."""
    msg = []
    msg.append(f"To: {kime}")
    msg.append(f"From: {GONDEREN}")
    msg.append(f"Subject: {konu}")
    msg.append("Content-Type: text/plain; charset=\"utf-8\"")
    msg.append("Content-Transfer-Encoding: 7bit")
    msg.append("MIME-Version: 1.0")
    msg.append("X-Status: DRAFT")      # DM HOLD isareti
    msg.append("X-Unpump-Seq: 1")
    msg.append("")
    msg.append(govde)
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(msg) + "\n")
    return yol


def alici_bul(yanit):
    """Yanitin gonderen adresini bulur (Reply-To > From)."""
    g = yanit.get("gonderen") or ""
    # "Ad <adres>" -> adres
    import re
    m = re.search(r"<([^>]+@[^>]+)>", g)
    if m:
        return m.group(1)
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", g)
    return m.group(0) if m else ""


def takip_hazirla(yanitlar, olcum_dizini, ilik_de=False, outbox=OUTBOX,
                  yaz=True, log=print):
    """SICAK (ve opsiyonel ILIK) yanitlar icin DRAFT takip mailleri uretir.

    Donus: {"yazilan": [...], "atlanan": [...], "hata": [...]}
    """
    import ai_gorunurluk as ag

    yazilan, atlanan, hatalar = [], [], []
    for y in yanitlar:
        if y.get("hata"):
            hatalar.append(y)
            continue
        sinif = y.get("sinif")
        domain = y.get("domain") or ""
        kime = alici_bul(y)

        if sinif == "soguk":
            atlanan.append((y, "SOGUK - takip yok (cikis/red)"))
            continue
        if sinif == "ilik" and not ilik_de:
            atlanan.append((y, "ILIK - --ilik-de ile acilmadi"))
            continue
        if not kime:
            hatalar.append((y, "gonderen adres bulunamadi"))
            continue

        # Onceden olculmus veri varsa kullan (Serper kota korumasi)
        dizin = olcum_dizini or ag.OLCUM_DIZINI
        olcum = ag.olcum_oku(domain, dizin=dizin) if domain else None

        if sinif == "sicak":
            govde = rapor_govdesi(domain, olcum, y)
            konu = takip_konusu(domain or "your clinic")
        else:
            govde = ilik_govdesi(domain, olcum, y)
            konu = f"Re: AI visibility check - whenever suits you"

        isim = f"DRAFT_takip_1_{domain or kime.split('@')[0]}.eml"
        # Ayni isimde DRAFT varsa ustune yazma (coklu calistirmada)
        yol = os.path.join(outbox, isim)

        # DM HOLD korumasi: govde 'sent/delivered/gonderildi' icermemeli
        # (yoksa x402_servis._dm_hold_durumu yanlis HOLD'i kaldirir)
        tehlikeli = dm_hold_isaretleri(govde)
        if tehlikeli:
            hatalar.append((y, f"DM HOLD riski - govde {tehlikeli} iceriyor"))
            continue

        if yaz:
            try:
                os.makedirs(outbox, exist_ok=True)
                eml_yaz(kime, konu, govde, yol)
            except OSError as e:
                hatalar.append((y, f"yazilamadi: {e}"))
                continue

        yazilan.append({
            "dosya": yol, "kime": kime, "domain": domain, "sinif": sinif,
            "konu": konu, "olculdu_mu": olcum is not None,
            "govde_onizleme": govde[:200].replace("\n", " "),
        })
        log(f"  [DRAFT] {sinif:5} -> {kime} ({domain or '?'})"
            f"{' [olculmus veriyle]' if olcum else ' [jenerik]'}")

    return {"yazilan": yazilan, "atlanan": atlanan, "hata": hatalar}


def main():
    ap = argparse.ArgumentParser(
        description="SICAK yanitlara DRAFT takip maili hazirla (GONDERMEZ)")
    ap.add_argument("--yanitlar", default=VARSAYILAN_YANITLAR,
                    help="yanit_isle.py ciktisi JSON")
    ap.add_argument("--ilik-de", action="store_true",
                    help="ILIK yanitlara da DRAFT yaz (varsayilan: sadece SICAK)")
    ap.add_argument("--outbox", default=OUTBOX)
    ap.add_argument("--dry-run", action="store_true",
                    help="hicbir dosya yazma, sadece ne yapilacagini goster")
    a = ap.parse_args()

    if not os.path.exists(a.yanitlar):
        print(f"HATA: {a.yanitlar} yok.", file=sys.stderr)
        print("  once: python3 yanit_isle.py --dizin ./yanit_gelen", file=sys.stderr)
        return 1

    with open(a.yanitlar, encoding="utf-8") as f:
        veri = json.load(f)

    yanitlar = veri.get("yanitlar") or []
    if not yanitlar:
        print("yanit yok - takip hazirlanamadi.", file=sys.stderr)
        return 0

    print(f"DM HOLD: DRAFT yaziliyor, GONDERIM YOK "
          f"({len(yanitlar)} yanit isleniyor)")
    print(f"mod: {'dry-run' if a.dry_run else 'DRAFT YAZ'} | "
          f"sicak + {'ilik' if a.ilik_de else 'sadece sicak'}")
    print("-" * 50)

    sonuc = takip_hazirla(yanitlar, None, ilik_de=a.ilik_de,
                          outbox=a.outbox, yaz=not a.dry_run)

    print()
    print(f"yazilan DRAFT : {len(sonuc['yazilan'])}")
    print(f"atlanan       : {len(sonuc['atlanan'])}")
    print(f"hata          : {len(sonuc['hata'])}")
    for _, neden in sonuc["atlanan"]:
        print(f"  atla: {neden}")
    for _, neden in sonuc["hata"]:
        print(f"  hata: {neden}")
    print()
    print("Gonderim icin (insan onayli): python3 send_dm.py --send")
    return 0


if __name__ == "__main__":
    sys.exit(main())
