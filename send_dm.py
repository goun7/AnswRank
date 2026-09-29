#!/usr/bin/env python3
"""15 DRAFT e-postayı SMTP ile gönderir.

KISITLAR (sert):
  - PRIVATE_KEY YASAK
  - SMTP_USER / SMTP_PASS .env'den okunur
  - --dry-run varsayılan: gerçek gönderim için --send gerekir
  - her e-postadan önce onay ister (HITL)

Kullanım:
  python3 send_dm.py --dry-run     # ne göndereceğini göster, gönderme
  python3 send_dm.py --send        # GERÇEK gönderim (onay ister)
"""
import email
import email.utils
import glob
import os
import smtplib
import ssl
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUTBOX = os.path.join(HERE, "outbox")

# .env oku (basit)
ENV = {}
envp = os.path.join(HERE, ".env")
if os.path.exists(envp):
    with open(envp) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            ENV[k.strip()] = v.strip().strip('"').strip("'")


def load_emls():
    out = []
    for f in sorted(glob.glob(os.path.join(OUTBOX, "*.eml"))):
        with open(f) as fh:
            msg = email.message_from_file(fh)
        out.append((f, msg))
    return out


def main():
    real_send = "--send" in sys.argv
    dry = not real_send

    emls = load_emls()
    if not emls:
        print("outbox boş — gönderilecek e-posta yok")
        return 0

    user = ENV.get("SMTP_USER", "")
    pw = ENV.get("SMTP_PASS", "")
    if real_send and not (user and pw):
        print("HATA: SMTP_USER / SMTP_PASS .env'de yok. Gönderilemez.")
        print("  .env'e şunları ekleyin:")
        print("  SMTP_USER=sizin@gmail.com")
        print("  SMTP_PASS=<16 haneli uygulama şifresi>")
        return 1

    print(f"{'DRY-RUN (gönderim YOK)' if dry else 'GERÇEK GÖNDERİM'}")
    print(f"e-posta sayısı: {len(emls)}")
    print("=" * 50)

    for i, (f, msg) in enumerate(emls, 1):
        kime = msg["To"]
        konu = str(msg["Subject"])[:50]
        print(f"[{i:2}/{len(emls)}] {kime}")
        print(f"         konu: {konu}")

        if dry:
            continue

        # HITL: her e-postada onay
        try:
            cevap = input("   gönder? [e/H] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n   iptal edildi")
            return 0
        if cevap not in ("e", "evet", "y", "yes"):
            print("   atlandı")
            continue

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
                s.login(user, pw)
                s.send_message(msg)
            print("   ✓ GÖNDERİLDİ")
        except Exception as e:
            print(f"   ✗ HATA: {e}")
            return 1

    if dry:
        print()
        print("Bu bir dry-run'du. Gerçek gönderim için:")
        print("  python3 send_dm.py --send")
    return 0


if __name__ == "__main__":
    sys.exit(main())
