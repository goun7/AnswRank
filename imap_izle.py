#!/usr/bin/env python3
"""Gmail IMAP ile gelen kutusunu izler — AnswRank DM kampanyasi yanitlari.

GOREV: 15 e-posta gonderildi, yanitlar bekleniyor. Bu script gelen kutusunu
15 dakikada bir kontrol eder, yanitlari yanit_gelen/*.eml olarak kaydeder ve
SICAK olanlar icin DRAFT takip maili hazirlar.

DM HOLD KORUMASI (cok onemli):
  - Bu script HICBIR e-posta GONDERMEZ.
  - smtplib ASLA import edilmez — gonderim bu surecte imkansizdir.
  - Sadece IMAP ile OKUR (BODY.PEEK[] ile, mesajlari 'okundu' yapmaz).
  - Takip mailleri outbox'a DRAFT olarak yazilir (otomatik_takip.py).
  - Gonderim icin insan onayi + send_dm.py --send gerekir (yapILMAZ).

GIZLILIK / KISITLAR:
  - SERPER_API_KEY ekrana veya log'a YAZILMAZ (alt prosesler sadece
    anahtar uzunlugunu raporlar, asla anahtari).
  - Klinik e-posta adresleri log'a YAZILMAZ — loglarda sadece domain
    kullanilir. Adresler sadece outbox DRAFT'lari icinde olur.
  - Para harcanmaz: olculmus domain'ler tekrar olculmez (olcumler/ cache).

Kullanim:
  python3 imap_izle.py --test              # IMAP baglantisini dogrula
  python3 imap_izle.py --tek               # tek bir kontrol turu
  python3 imap_izle.py --dongu             # 15 dk'da bir sonsuz kontrol
  python3 imap_izle.py --dongu --aralik 900

Bir yanit geldiginde:
  1) yanit_gelen/<domain>_<zaman>.eml olarak kaydet
  2) yanit_isle.py ile siniflandir (SICAK/ILIK/SOGUK)
  3) SICAK ise:
       a) ai_gorunurluk.py ile olc (cache varsa 0 kredi)
       b) uret_rapor.py ile 1 sayfalik rapor uret
       c) otomatik_takip.py ile outbox'a DRAFT yaz (GONDERMEZ)
  4) ILIK/SOGUK ise not dus, birak
"""
import argparse
import datetime as _dt
import email
import email.utils
import imaplib
import json
import os
import re
import subprocess
import sys
import time

# NOT: smtplib bilerek import EDILMEZ (DM HOLD — gonderim imkansiz).
HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DOSYASI = os.path.join(HERE, ".env")
YANIT_DIZIN = os.path.join(HERE, "yanit_gelen")
OUTBOX = os.path.join(HERE, "outbox")
RAPOR_DIZIN = os.path.join(HERE, "raporlar")
OLCUM_DIZIN = os.path.join(HERE, "olcumler")
STATE_DOSYA = os.path.join(HERE, ".imap_durum.json")
LOG_DOSYA = os.path.join(HERE, "imap_izle_log.txt")
YANIT_JSON = os.path.join(HERE, "yanitlar_sonuclari.json")

IMAP_SUNUCU = "imap.gmail.com"
IMAP_PORT = 993
GONDEREN = "vegoko7@gmail.com"          # send_dm.py / otomatik_takip.py ile ayni
ARALIK_SANIYE = 15 * 60                 # 15 dakika

# Kampanya adresleri AYRI DOSYADAN okunur (gizlilik: repo'da gercek adres YOK).
# .kampanya_adresleri.txt .gitignore'da; repo'da bulunmaz.
ADRES_DOSYASI = ".kampanya_adresleri.txt"
def _adresleri_yukle():
    import pathlib
    yol = pathlib.Path(ADRES_DOSYASI)
    if yol.exists():
        return [s.strip() for s in yol.read_text("utf-8").splitlines()
                if s.strip() and not s.startswith("#")]
    return []
GONDERILEN_ADRESLER = _adresleri_yukle()

# yanit_isle.py icindeki klinik domain listesi ile ayni.
# RFC 2606 ornek alanlari — gercek domain'ler yerel dosyada
KLINIK_DOMAINLERI = [
    "example.com", "example.net", "example.org", "test.example",
    "demo.example", "klinik-1.example", "klinik-2.example", "klinik-3.example",
    "klinik-4.example", "klinik-5.example", "klinik-6.example", "klinik-7.example",
    "klinik-8.example", "klinik-9.example", "klinik-10.example",
]

# Yanit olarak degil, bilgi olarak kaydedilen otomatik bildirimler.
BOUNCE_GONDERENLER = ("mailer-daemon", "postmaster", "mail-daemon",
                      "gmail-noreply", "no-reply", "noreply")
BOUNCE_KONULAR = ("delivery status notification", "undelivered mail returned",
                  "mail delivery failed", "delivery failure",
                  "returned mail", "address not found")

KAMANYA_TARIHI = "28-Sep-2026"   # outbox_gonderim_log.json: 2026-09-28 21:56
KLASORLER = ["INBOX", "[Gmail]/Spam"]

# Header seti — aday tespiti icin BU kadar veri yeterli (bedava, hizli).
HEADER_ALANLARI = ("FROM", "SUBJECT", "MESSAGE-ID", "IN-REPLY-TO",
                   "REFERENCES", "DATE")

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
def env_oku(yol=ENV_DOSYASI):
    env = {}
    if not os.path.exists(yol):
        return env
    with open(yol, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def log(mesaj, seviye="INFO"):
    """Hem ekrana hem dosyaya yazar. Adres/anahtar ICERMEZ (cagiran dikkat)."""
    zaman = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    satir = f"[{zaman}] [{seviye}] {mesaj}"
    print(satir, flush=True)
    try:
        with open(LOG_DOSYA, "a", encoding="utf-8") as f:
            f.write(satir + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# State (daha once islenmis mesajlari tekrar isleme)
# ---------------------------------------------------------------------------
def state_oku():
    if not os.path.exists(STATE_DOSYA):
        return {"uidler": [], "msg_idler": []}
    try:
        with open(STATE_DOSYA, encoding="utf-8") as f:
            s = json.load(f)
        return {"uidler": s.get("uidler", []),
                "msg_idler": s.get("msg_idler", [])}
    except (json.JSONDecodeError, OSError):
        return {"uidler": [], "msg_idler": []}


def state_yaz(state):
    try:
        with open(STATE_DOSYA, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# IMAP
# ---------------------------------------------------------------------------
def imap_baglan(kullanici, sifre):
    """imap.gmail.com:993 SSL ile baglanir ve girer yapar."""
    M = imaplib.IMAP4_SSL(IMAP_SUNUCU, IMAP_PORT)
    M.login(kullanici, sifre)
    return M


def adres_cikar(gonderen):
    """'Ad <a@b.com)' -> 'a@b.com'."""
    if not gonderen:
        return ""
    m = re.search(r"<([^>]+@[^>]+)>", gonderen)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", gonderen)
    return m.group(0).strip().lower() if m else ""


def domain_cikar(adres):
    """adres -> domain (www'suz)."""
    if not adres or "@" not in adres:
        return ""
    host = adres.split("@", 1)[1].lower().removeprefix("www.")
    for k in KLINIK_DOMAINLERI:
        if host == k or host.endswith("." + k) or k in host:
            return k
    return host


def bounce_mi(msg, adres):
    g = (adres or "")
    for b in BOUNCE_GONDERENLER:
        if b in g:
            return True
    konu = ((msg.get("Subject") or "") + " " + (msg.get("From") or "")).lower()
    for b in BOUNCE_KONULAR:
        if b in konu:
            return True
    return False


def kampanya_yaniti_mi(msg, adres, domain):
    """Bu mesaj bizim 15 mailimize bir yanit mi?"""
    if not adres or adres == GONDEREN:
        return False
    if adres in GONDERILEN_ADRESLER:
        return True
    if domain and domain in KLINIK_DOMAINLERI:
        return True
    # Konudan tanima (clinic farki adresten yazmissa)
    konu = (msg.get("Subject") or "").lower()
    if "ai visibility check" in konu or "unpump" in konu:
        return True
    # References/In-Reply-To bizim mesajimiza mi?
    for h in ("In-Reply-To", "References"):
        v = (msg.get(h) or "").lower()
        if v and "gmail" in v:
            return True
    return False


def klasor_postalari(M, klasor, state):
    """Iki asamali tarama (5193 mesajli inbox icin verimli):
      1) KAMANYA_TARIHI sonrasi ISLENMEMIS mesajlarin SADECE header'i
      2) Adaylarin (yanit/bounce) tam govdesi
    Donus: [(uid, msg, raw, domain)]
    """
    try:
        typ, _ = M.select(klasor, readonly=True)
        if typ != "OK":
            return []
    except imaplib.IMAP4.error:
        return []

    try:
        typ, data = M.uid("search", None, "SINCE", KAMANYA_TARIHI)
    except imaplib.IMAP4.error as e:
        log(f"IMAP search hatasi ({klasor}): {e}", "HATA")
        return []
    if typ != "OK" or not data or not data[0]:
        return []

    goruldu = set(state["uidler"])
    goruldu_mid = set(state["msg_idler"])
    uidler = [u for u in data[0].split() if u]
    uidler = [u for u in uidler if u.decode() not in goruldu]

    adaylar = []
    for uid in uidler:
        # 1) Sadece header cek (hizli, govde yok)
        istek = ("(BODY.PEEK[HEADER.FIELDS (%s)])"
                 % " ".join(HEADER_ALANLARI))
        try:
            typ, fd = M.uid("fetch", uid, istek)
        except imaplib.IMAP4.error as e:
            log(f"IMAP header hatasi (uid {uid.decode()}): {e}", "HATA")
            continue
        if typ != "OK" or not fd:
            continue
        hraw = None
        for parca in fd:
            if isinstance(parca, tuple) and len(parca) >= 2:
                hraw = parca[1]
                break
        if hraw is None:
            continue
        try:
            hmsg = email.message_from_bytes(hraw)
        except Exception:
            continue

        mid = (hmsg.get("Message-ID") or "").strip().lower()
        if mid and mid in goruldu_mid:
            state["uidler"].append(uid.decode())
            continue

        adres = adres_cikar(hmsg.get("From") or "")
        domain = domain_cikar(adres)
        if bounce_mi(hmsg, adres) or kampanya_yaniti_mi(hmsg, adres, domain):
            adaylar.append((uid, hmsg, domain))
        else:
            # Ilgisiz mail — tekrar bakmamak icin isaret
            state["uidler"].append(uid.decode())
            if mid:
                state["msg_idler"].append(mid)

    if not adaylar:
        return []

    sonuc = []
    for uid, hmsg, domain in adaylar:
        # 2) Adayin tam govdesi
        try:
            typ, fd = M.uid("fetch", uid, "(BODY.PEEK[])")
        except imaplib.IMAP4.error as e:
            log(f"IMAP fetch hatasi (uid {uid.decode()}): {e}", "HATA")
            continue
        if typ != "OK" or not fd:
            continue
        raw = None
        for parca in fd:
            if isinstance(parca, tuple) and len(parca) >= 2:
                raw = parca[1]
                break
        if raw is None:
            continue
        try:
            msg = email.message_from_bytes(raw)
        except Exception as e:
            log(f".eml parse hatasi (uid {uid.decode()}): {e}", "HATA")
            continue
        sonuc.append((uid, msg, raw, domain))
    return sonuc


def yanit_kaydet(msg, raw, domain, klasor):
    """yanit_gelen/<domain>_<zaman>.eml olarak kaydeder. Adres icermez."""
    os.makedirs(YANIT_DIZIN, exist_ok=True)
    etiket = domain or "bilinmeyen"
    etiket = re.sub(r"[^a-z0-9.-]", "_", etiket)
    zaman = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    yol = os.path.join(YANIT_DIZIN, f"{etiket}_{zaman}.eml")
    with open(yol, "wb") as f:
        f.write(raw)
    return yol


# ---------------------------------------------------------------------------
# Pipeline (alt prosesler — hicbiri e-posta GONDERMEZ)
# ---------------------------------------------------------------------------
def calistir(args, Turkce_aciklama):
    """Alt proses calistirir; ciktiyi dondurur. Hata olursa None."""
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           cwd=HERE, timeout=300)
    except subprocess.TimeoutExpired:
        log(f"{Turkce_aciklama}: zaman asimi", "HATA")
        return None
    if r.returncode != 0:
        log(f"{Turkce_aciklama}: rc={r.returncode} "
            f"{(r.stderr or '').strip()[:200]}", "HATA")
        return None
    return r


def yanit_siniflandir(eml_yolu):
    """yanit_isle.py calistirir, bu .eml icin sonucu dondurur."""
    calistir([sys.executable, os.path.join(HERE, "yanit_isle.py"),
              "--dizin", YANIT_DIZIN, "--cikti", YANIT_JSON],
             "yanit_isle")
    if not os.path.exists(YANIT_JSON):
        return None
    try:
        with open(YANIT_JSON, encoding="utf-8") as f:
            veri = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(f"yanit_isle ciktisi okunamadi: {e}", "HATA")
        return None
    for y in veri.get("yanitlar") or []:
        if y.get("dosya") == eml_yolu:
            return y
    return None


def domain_olc(domain):
    """ai_gorunurluk.py ile olcer. Cache varsa 0 kredi."""
    yol = os.path.join(OLCUM_DIZIN, f"{domain}.json")
    if os.path.exists(yol):
        log(f"  [olcum] {domain}: cache var (olcumler/), 0 kredi")
        return 0, "cache"
    r = calistir([sys.executable, os.path.join(HERE, "ai_gorunurluk.py"),
                  domain, "--json"], f"ai_gorunurluk {domain}")
    if r is None:
        return 0, "hata"
    try:
        sonuc = json.loads(r.stdout)
        kredi = sonuc.get("kredi_kullanildi", 0)
    except json.JSONDecodeError:
        kredi = 0
    log(f"  [olcum] {domain}: YENI domain, {kredi} kredi (2500 kota)")
    return kredi, "yeni"


def rapor_uret(domain):
    """uret_rapor.py ile 1 sayfalik rapor uretir, raporlar/ klasorune kaydeder."""
    r = calistir([sys.executable, os.path.join(HERE, "uret_rapor.py"), domain],
                 f"uret_rapor {domain}")
    if r is None:
        return None
    os.makedirs(RAPOR_DIZIN, exist_ok=True)
    yol = os.path.join(RAPOR_DIZIN, f"{domain}.txt")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(r.stdout)
    return yol


def draft_hazirla():
    """otomatik_takip.py calistirir — outbox'a DRAFT yazar (GONDERMEZ)."""
    r = calistir([sys.executable, os.path.join(HERE, "otomatik_takip.py"),
                  "--yanitlar", YANIT_JSON, "--outbox", OUTBOX],
                 "otomatik_takip")
    return r is not None


def draft_dogrula(domain):
    """outbox'da bu domain icin DRAFT var mi ve HOLD guvenli mi?"""
    yol = os.path.join(OUTBOX, f"DRAFT_takip_1_{domain}.eml")
    if not os.path.exists(yol):
        return False, "DRAFT bulunamadi"
    with open(yol, encoding="utf-8") as f:
        icerik = f.read()
    if "X-Status: DRAFT" not in icerik:
        return False, "X-Status: DRAFT yok"
    # DM HOLD korumasi: govde sent/delivered/gonderildi icermemeli
    kucuk = icerik.lower()
    tehlikeli = [k for k in ("sent", "delivered", "gonderildi") if k in kucuk]
    if tehlikeli:
        return False, f"DM HOLD riski: {tehlikeli}"
    return True, yol


def yanit_isle(uid, msg, raw, domain, klasor):
    """Tek bir yaniti kaydeder ve pipeline'dan gecirir."""
    eml_yolu = yanit_kaydet(msg, raw, domain, klasor)
    log(f"YANIT KAYDEDILDI: {domain or '?'} "
        f"({klasor}) -> {os.path.basename(eml_yolu)}")

    # 1) Siniflandir
    yanit = yanit_siniflandir(eml_yolu)
    if yanit is None:
        log(f"  {domain}: siniflandirma basarisiz", "HATA")
        return
    if yanit.get("hata"):
        log(f"  {domain}: hata — {yanit['hata']}")
        return

    sinif = yanit.get("sinif")
    guven = yanit.get("guven")
    isaretler = yanit.get("isaretler") or []
    log(f"  {domain}: sinif={sinif.upper()} guven=%{int((guven or 0) * 100)}"
        + (f" isaretler={isaretler}" if isaretler else ""))

    if sinif != "sicak":
        log(f"  {domain}: {sinif.upper()} — DRAFT YOK (kullanici onayi "
            f"beklenmiyor, not dustul)")
        return

    # 2) SICAK — olcum (para harcama, cache kullan)
    kredi, kaynak = domain_olc(domain)

    # 3) 1 sayfalik rapor
    rapor_yolu = rapor_uret(domain)
    if rapor_yolu:
        log(f"  [rapor] {rapor_yolu}")

    # 4) outbox'a DRAFT (GONDERMEZ)
    ok = draft_hazirla()
    if not ok:
        log(f"  {domain}: DRAFT hazirlanamadi", "HATA")
        return
    gecerli, bilgi = draft_dogrula(domain)
    if gecerli:
        log(f"  [DRAFT] {domain}: outbox'da hazir (GONDERILMEDI) — {bilgi}")
        log(f"  [DM HOLD] Gonderim YOK. Insan onayı: "
            f"send_dm.py --send (yapILMADI)")
    else:
        log(f"  [DRAFT] {domain}: DOGRULAMA BASARISIZ — {bilgi}", "HATA")


def bounce_isle(uid, msg, domain):
    """Bounce/otomatik bildirim — yanit degil, sadece not dusulur."""
    konu = (msg.get("Subject") or "")[:80]
    log(f"[BOUNCE/OTOMATIK] {domain or '?'}: {konu} (yanit olarak sayILMAZ)")


# ---------------------------------------------------------------------------
# Dongu
# ---------------------------------------------------------------------------
def dubai_saati():
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=4)))


def tek_tur(kullanici, sifre, state, kaydet=True):
    """Tek bir IMAP kontrol turu. Yeni yanit sayisini dondurur."""
    M = None
    try:
        M = imap_baglan(kullanici, sifre)
    except imaplib.IMAP4.error as e:
        log(f"IMAP giris hatasi: {e}", "HATA")
        log("Gmail ayarlarinda IMAP acik mi? (Forwarding and POP/IMAP)",
            "HATA")
        return -1
    except Exception as e:
        log(f"IMAP baglanti hatasi: {type(e).__name__}: {e}", "HATA")
        return -1

    yeni_yanit = 0
    try:
        for klasor in KLASORLER:
            for uid, msg, raw, domain in klasor_postalari(M, klasor, state):
                gonderen = msg.get("From") or ""
                adres = adres_cikar(gonderen)
                if not domain:
                    domain = domain_cikar(adres)

                if bounce_mi(msg, adres):
                    bounce_isle(uid, msg, domain)
                elif kampanya_yaniti_mi(msg, adres, domain):
                    yanit_isle(uid, msg, raw, domain, klasor)
                    yeni_yanit += 1
                # baska turlu: bizimle ilgisiz mail — gormezden gel

                state["uidler"].append(uid.decode())
                mid = (msg.get("Message-ID") or "").strip().lower()
                if mid:
                    state["msg_idler"].append(mid)
        if kaydet:
            state_yaz(state)
    finally:
        try:
            M.close()
            M.logout()
        except Exception:
            pass
    return yeni_yanit


def test_baglanti(kullanici, sifre):
    """IMAP baglantisini dogrular (kredi/adres leak etmez)."""
    print("IMAP baglanti testi...")
    try:
        M = imap_baglan(kullanici, sifre)
    except imaplib.IMAP4.error as e:
        print(f"  BASARISIZ (IMAP4.error): {e}")
        print("  Olasi nedenler:")
        print("  1) Gmail ayarlarinda IMAP KAPALI")
        print("     -> Forwarding and POP/IMAP -> IMAP: Enable")
        print("  2) App Password hatali (16 haneli olmali)")
        print("  3) Hesapta 2FA olmali (app password icin sart)")
        return 1
    except Exception as e:
        print(f"  BASARISIZ ({type(e).__name__}): {e}")
        return 1
    try:
        typ, data = M.select("INBOX", readonly=True)
        print(f"  INBOX: {typ} {data}")
        typ, data = M.uid("search", None, "ALL")
        n = len(data[0].split()) if (typ == "OK" and data and data[0]) else 0
        print(f"  INBOX'taki toplam mesaj: {n}")
        print("  IMAP CALISIYOR")
        return 0
    finally:
        try:
            M.close()
            M.logout()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(
        description="Gmail IMAP inbox izleyici — AnswRank yanit kampanyasi "
                    "(GONDERIM YAPMAZ, DM HOLD)")
    mod = ap.add_mutually_exclusive_group()
    mod.add_argument("--test", action="store_true",
                     help="IMAP baglantisini dogrula ve cik")
    mod.add_argument("--tek", action="store_true",
                     help="tek kontrol turu yap ve cik")
    mod.add_argument("--dongu", action="store_true",
                     help="15 dk'da bir sonsuz kontrol (varsayilan davranis)")
    ap.add_argument("--aralik", type=int, default=ARALIK_SANIYE,
                    help=f"kontrol araligi saniye (varsayilan {ARALIK_SANIYE})")
    a = ap.parse_args()

    env = env_oku()
    kullanici = env.get("SMTP_USER", "")
    sifre = env.get("SMTP_PASS", "")
    if not (kullanici and sifre):
        print("HATA: SMTP_USER / SMTP_PASS .env'de yok (IMAP icin ayni "
              "app password kullanilir).")
        return 1

    if a.test:
        return test_baglanti(kullanici, sifre)

    if not a.dongu and not a.tek:
        print("mod secilmedi: --dongu varsayildi (15 dk). "
              "Tek tur icin --tek, test icin --test")
        a.dongu = True

    os.makedirs(YANIT_DIZIN, exist_ok=True)
    log("=== IMAP izleyici basladi (DM HOLD: GONDERIM YOK) ===")
    log(f"hizmet: {kullanici.split('@')[0]}@... | aralik: {a.aralik}s | "
        f"klasorler: {', '.join(KLASORLER)}")

    state = state_oku()
    tur = 0
    while True:
        tur += 1
        dz = dubai_saati()
        is_saati = 8 <= dz.hour < 20
        log(f"--- tur {tur} | Dubai {dz.strftime('%H:%M')} "
            f"({'is saati' if is_saati else 'gece — yanit beklenmez'}) ---")

        try:
            n = tek_tur(kullanici, sifre, state)
            if n < 0:
                log("IMAP baglanamadi — sonraki tur tekrar denenecek", "HATA")
            elif n == 0:
                log("yeni yanit YOK")
            else:
                log(f"{n} YENI yanit islendi")
        except KeyboardInterrupt:
            log("durduruldu (Ctrl-C)")
            break
        except Exception as e:
            log(f"beklenmeyen hata: {type(e).__name__}: {e}", "HATA")

        if a.tek:
            break
        time.sleep(a.aralik)

    log("=== IMAP izleyici durdu ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
