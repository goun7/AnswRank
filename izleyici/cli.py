"""CLI: python3 -m izleyici <add|list|remove|run|delta> ..."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

from . import delta, kosu, takip


def _cmd_add(args):
    sorgular = []
    if args.sorgular:
        # sorgu dosyası proje kökü içinde olmalı (path-traversal kapısı)
        try:
            tam = takip.kapsamda(args.sorgular, takip.HERE)
        except ValueError as exc:
            print("hata: %s" % exc, file=sys.stderr)
            return 1
        with open(tam, encoding="utf-8") as f:
            sorgular = [x.strip() for x in f if x.strip()]
    try:
        takip.ekle(args.domain, sorgular or None)
    except ValueError as exc:
        print("hata: %s" % exc, file=sys.stderr)
        return 1
    print("takip eklendi: %s (%d sorgu)" % (takip.normalle(args.domain),
                                            len(sorgular)))
    return 0


def _cmd_list(_args):
    t = takip.yukle()
    if not t:
        print("takip listesi boş — `python3 -m izleyici add <domain>`")
        return 0
    for d, k in sorted(t.items()):
        print("%s  sorgu=%d  eklenme=%s" % (d, len(k.get("sorgular", [])),
                                            k.get("eklenme", "?")))
    return 0


def _cmd_remove(args):
    ok = takip.cikar(args.domain)
    print("çıkarıldı" if ok else "takip listesinde değil")
    return 0 if ok else 1


def _cmd_run(args):
    import ai_gorunurluk as motor

    anahtar = (motor.env_oku().get("SERPER_API_KEY") or "")
    if not anahtar:
        print("hata: SERPER_API_KEY bulunamadı (%s)" % motor.ENV_DOSYASI,
              file=sys.stderr)
        return 1
    hedefler = [args.domain] if args.domain else None
    sonuc = kosu.kos(domainler=hedefler, api_key=anahtar)
    for s in sonuc:
        print("%s  puan=%s  snapshot=%s" % (s["domain"], s["puan"],
                                            s["snapshot"]))
    return 0


def _cmd_delta(args):
    eski, yeni = kosu.son_iki_snapshot(args.domain)
    if yeni is None:
        print("hata: delta için ≥2 snapshot gerekli — önce `run`",
              file=sys.stderr)
        return 1
    md = delta.rapor_md(eski, yeni)
    if args.dosya:
        kok = os.path.join(takip.IZLE_KOK, "raporlar")
        os.makedirs(kok, exist_ok=True)
        yol = os.path.join(
            kok, "%s-%s-delta.md" % (takip.normalle(args.domain),
                                     yeni.get("tarih", "son")))
        with open(yol, "w", encoding="utf-8") as f:
            f.write(md)
        print(yol)
    else:
        sys.stdout.write(md)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="izleyici",
        description="AEO görünürlük izleyici — AnswRank motoru üstünde")
    sub = ap.add_subparsers(dest="komut", required=True)

    p = sub.add_parser("add", help="alan adı ekle")
    p.add_argument("domain")
    p.add_argument("--sorgular", help="sorgu listesi dosyası (satır başına 1)")
    p.set_defaults(fn=_cmd_add)

    p = sub.add_parser("list", help="takip listesi")
    p.set_defaults(fn=_cmd_list)

    p = sub.add_parser("remove", help="alan adı çıkar")
    p.add_argument("domain")
    p.set_defaults(fn=_cmd_remove)

    p = sub.add_parser("run", help="ölç ve snapshot al")
    p.add_argument("domain", nargs="?", help="yoksa takipli hepsi")
    p.set_defaults(fn=_cmd_run)

    p = sub.add_parser("delta", help="son iki snapshot farkı")
    p.add_argument("domain")
    p.add_argument("--dosya", action="store_true",
                   help="stdout yerine raporlar/ altına yaz")
    p.set_defaults(fn=_cmd_delta)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
