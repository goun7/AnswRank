"""W2: landing + ücretsiz tek-rapor servisi (FastAPI).

Güvenlik sözleşmesi:
  - `domain` web formundan GÜVENİLMEDEN gelen girdidir: takip.normalle
    (hostname regex) + IP-çözümleme guard'ı (private/loopback/link-local/
    reserved/multicast reddi) iki katman. Motor bu domain'e HTTP atacağı
    için a11y-ad'deki SSRF disiplini burada da uygulanır.
  - Hız limiti: istemci başına günlük N ücretsiz ölçüm (Serper kredisi
    koruması). In-memory; çoklu-instance dağıtımda Redis'e taşınır (TODO).
  - E-posta GÖNDERİLMEZ: lead kaydedilir, gönderim E13'ün insan-onaylı
    hattından yapılır (AnswRank DM HOLD disiplini).
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import json
import os
import re
import socket

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import delta, takip
from .kosu import snapshot_yaz, snapshot_yolu

LEADS_DOSYASI = os.path.join(takip.IZLE_KOK, "leads.json")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

LANDING = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AEO Görünürlük Raporu — AI aramasında görünüyor musunuz?</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;color:#1a1a2e}
 h1{font-size:1.4rem} input{width:100%;padding:.6rem;margin:.3rem 0;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}
 button{background:#1a1a2e;color:#fff;border:0;padding:.7rem 1.4rem;border-radius:6px;cursor:pointer}
 pre{white-space:pre-wrap;background:#f4f4f8;padding:1rem;border-radius:8px;overflow-x:auto;font-size:.85rem}
 .kucuk{color:#666;font-size:.85rem}
</style>
</head>
<body>
<h1>Markanız AI aramalarında görünüyor mu?</h1>
<p>ChatGPT ve AI Overviews çağında müşteriler artık Google'da değil,
<b>AI yanıtlarında</b> karar veriyor. Alan adınızı girin: sorgularınızda
kaçıncı sırada göründüğünüzü ve AI'ın sizi alıntılama olasılığınızı
ölçüyoruz. İlk rapor ücretsiz.</p>
<form onsubmit="raporAl(event)">
 <input id="domain" placeholder="ornek.com" required>
 <input id="email" type="email" placeholder="e-posta (raporu saklamak için)" required>
 <button>Ücretsiz rapor al</button>
</form>
<div id="sonuc"></div>
<p class="kucuk">Ölçüm: gerçek arama sonuçları üzerinde (search-grounded),
8 hakemli arXiv çalışmasına dayalı ağırlıklar. Günlük limit:
<span class="kucuk">istek başına {{LIMIT}}</span> ücretsiz ölçüm.</p>
<script>
async function raporAl(e){e.preventDefault();
 const r=await fetch('/rapor',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({domain:document.getElementById('domain').value,
                       email:document.getElementById('email').value})});
 const d=await r.json();
 document.getElementById('sonuc').innerHTML = r.ok
   ? '<pre>'+d.rapor.replace(/</g,'&lt;')+'</pre>'
   : '<p style="color:#b00">'+(d.detay||'hata')+'</p>';}
</script>
</body></html>"""


def _guvenli_domain(domain: str) -> str:
    """Form girdisi -> ölçülebilir, güvenli hostname. Değilse ValueError."""
    d = takip.normalle(domain)  # hostname regex: "..", "/", boşluk imkânsız
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", d):
        raise ValueError("IP adresi değil, alan adı girin")
    for info in socket.getaddrinfo(d, None):
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError("bu alan adı iç ağa çözümleniyor")
    return d


def _lead_yaz(domain: str, email: str, ip_hash: str) -> None:
    kayit = {"tarih": datetime.datetime.now().isoformat(timespec="seconds"),
             "domain": domain, "email": email, "ip_hash": ip_hash}
    kayitlar = []
    if os.path.exists(LEADS_DOSYASI):
        try:
            with open(LEADS_DOSYASI, encoding="utf-8") as f:
                kayitlar = json.load(f)
        except (json.JSONDecodeError, OSError):
            kayitlar = []
    kayitlar.append(kayit)
    takip.kapsamda(LEADS_DOSYASI, takip.IZLE_KOK)
    os.makedirs(os.path.dirname(LEADS_DOSYASI), exist_ok=True)
    with open(LEADS_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(kayitlar, f, ensure_ascii=False, indent=2)


class Istek(BaseModel):
    domain: str
    email: str


def create_app(olc_fn=None, gunluk_limit: int = 3) -> FastAPI:
    """Testlerde `olc_fn` sahte ölçümle enjekte edilir (ağ yok)."""
    app = FastAPI(title="AEO İzleyici — ücretsiz rapor")
    sayac: dict[str, tuple[str, int]] = {}

    @app.get("/", response_class=HTMLResponse)
    def landing():
        return HTMLResponse(LANDING.replace("{{LIMIT}}", str(gunluk_limit)))

    @app.post("/rapor")
    def rapor(istek: Istek, request: Request):
        bugun = datetime.date.today().isoformat()
        ip_hash = hashlib.sha256(
            (request.client.host or "?").encode()).hexdigest()[:16]
        if sayac.get(ip_hash, ("", 0))[0] != bugun:
            sayac[ip_hash] = (bugun, 0)
        gun, adet = sayac[ip_hash]
        if adet >= gunluk_limit:
            raise HTTPException(429, "günlük ücretsiz ölçüm limiti doldu")
        if not EMAIL_RE.match(istek.email or ""):
            raise HTTPException(400, "geçerli bir e-posta girin")
        try:
            d = _guvenli_domain(istek.domain)
        except (ValueError, socket.gaierror) as exc:
            raise HTTPException(400, str(exc))
        if olc_fn is None:
            import ai_gorunurluk as motor
            anahtar = motor.env_oku().get("SERPER_API_KEY") or ""
            if not anahtar:
                raise HTTPException(503, "ölçüm anahtarı yapılandırılmadı")
            sonuc = motor.olc(d, motor.sorgu_kumesi_sec(5), anahtar)
        else:
            from izleyici.takip import sorgular_icin  # noqa: F401 (testler)
            sonuc = olc_fn(d)
        snapshot_yaz(sonuc, snapshot_yolu(d))
        _lead_yaz(d, istek.email, ip_hash)
        sayac[ip_hash] = (bugun, adet + 1)
        return JSONResponse({"rapor": delta.rapor_md(None, sonuc),
                             "puan": sonuc.get("ai_alinti_puani")})

    return app


app = create_app()
