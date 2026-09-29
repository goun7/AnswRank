#!/usr/bin/env python3
"""Güvenli canlı-atıf probu — API anahtarı ASLA ekrana/günlüğe sızmasın.

Kullanım:
  1) Anahtarlarınızı bir dosyaya yazın (repo DIŞINDA önerilir):
       /home/gokun/.answrank/keys.env
     İçeriği (OPENAI-uyumlu provider örneği):
       ANSWRANK_OPENAI_BASE_URL=https://sizin-provideriniz.com
       OPENAI_API_KEY=sk-...
       ANSWRANK_OPENAI_MODEL=sizin-modeliniz
  2) Çalıştırın:
       python3 scripts/live_citation_probe.py --domain sizinsiteniz.com --engine openai
  3) İsterseniz yolu belirtin:
       python3 scripts/live_citation_probe.py --env-file /yol/keys.env ...

Bu betik:
  - anahtar dosyasını okur ama İÇERİĞİNİ asla yazdırmaz,
  - her çıktıyı anahtar değerine karşı tarar ve varsa '***' ile maskeler,
  - traceback/headers dahil hiçbir yere anahtarı yazmaz (sys.excepthook maskeli).
"""
from __future__ import annotations

import os
import sys


def _redact_secrets(values: list[str]) -> None:
    """Çıktı kanallarını anahtar değerlerine karşı maskeliyen filtre takar."""
    secrets = [v for v in values if v and len(v) >= 8]
    if not secrets:
        return

    def _scrub(text: str) -> str:
        for s in secrets:
            if s and s in text:
                text = text.replace(s, "***")
        return text

    class _Masked:
        def __init__(self, stream):
            self._stream = stream

        def write(self, data):
            if isinstance(data, str) and data:
                return self._stream.write(_scrub(data))
            return self._stream.write(data)

        def __getattr__(self, name):
            return getattr(self._stream, name)

    sys.stdout = _Masked(sys.stdout)
    sys.stderr = _Masked(sys.stderr)

    def _excepthook(exc_type, exc, tb):
        import traceback
        sys.stderr.write("*** maskeleme: anahtar sızmasın diye detay azaltıldı ***\n")
        sys.stderr.write(f"{exc_type.__name__}: {_scrub(str(exc))}\n")

    sys.excepthook = _excepthook


def load_env_file(path: str) -> dict[str, str]:
    """KEY=VALUE dosyasını okur; yorum/boş satır atlar. İçeriği döndürMEZ
    (sadece os.environ'e koyar); hata mesajında değer yok."""
    if not os.path.isfile(path):
        raise SystemExit(f"✗ Anahtar dosyası yok: {path}\n"
                         "Önce dosyayı oluşturun (içeriği buraya yazdırmayın).")
    loaded: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise SystemExit(f"✗ Geçersiz satır (KEY=VALUE beklenir): satır {line[:20]}…")
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key:
                os.environ[key] = val
                loaded[key] = val
    if not loaded:
        raise SystemExit(f"✗ {path} içinde geçerli KEY=VALUE satırı yok.")
    return loaded


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=os.environ.get(
        "ANSWRANK_ENV_FILE", "/home/gokun/.answrank/keys.env"),
        help="anahtar dosyası (varsayılan: ~/.answrank/keys.env)")
    ap.add_argument("--domain", required=True, help="Ölçülecek domain (kendi siteniz)")
    ap.add_argument("--brand", default=None, help="Marka adı (domain'den türetilir)")
    ap.add_argument("--engine", default="openai",
                    choices=["openai", "gemini", "claude", "perplexity", "mistral"],
                    help="Hangi motor ölçülsün")
    ap.add_argument("--query", default=None, help="Soru (verilmezse sektör varsayılanı)")
    ap.add_argument("--full-citations", action="store_true",
                    help="20 soru × motor tam koşu yerine tek soru dumanı")
    args = ap.parse_args()

    loaded = load_env_file(args.env_file)
    # maskelemeyi SADECE değerleri okuduktan sonra kur — böylece hata mesajlarında
    # bile anahtar görünmez
    _redact_secrets(list(loaded.values()))

    from answrank.citations.runner import MultiLLMCitationRunner
    runner = MultiLLMCitationRunner()

    brand = args.brand or args.domain.split("//")[-1].split("/")[0]
    query = args.query or f"{brand} hakkında en iyi diş kliniği önerisi"

    print(f"Motor: {args.engine} · Domain: {args.domain}")
    print("Modalite etiketi ilk başarılı sorguda yazılır (uydurulmaz).\n")

    import asyncio
    method = {"openai": "query_openai_live", "gemini": "query_gemini_live",
              "claude": "query_claude_live", "perplexity": "query_perplexity_live",
              "mistral": "query_mistral_live"}[args.engine]
    answer = asyncio.run(getattr(runner, method)(query))

    label_map = {"openai": "ChatGPT-4o", "gemini": "Gemini-Pro",
                 "claude": "Claude-3.5", "perplexity": "Perplexity-Sonar",
                 "mistral": "Mistral-Large"}
    label = label_map[args.engine]
    modality = runner.grounding_status.get(label, "ölçülmedi")
    print(f"Modalite: {modality}")
    if modality == "search-grounded":
        print("  → GERÇEK canlı aramadan kaynaklı atıf (E10)")
    elif modality == "model-recall":
        print("  → model hatıraması (canlı arama YOK) — 'canlı atıf' olarak sunulamaz")
    elif modality == "ölçülemedi":
        print("  → anahtar var ama API reddetti/yanıt boş — ölçüm OLMADI")
    elif modality == "anahtar yok":
        print("  → anahtar yok — bu motor ölçülmedi")
    print(f"\nYanıt ({label}):")
    print(answer if answer else "— yanıt alınamadı (None; uydurulmadı)")


if __name__ == "__main__":
    main()
