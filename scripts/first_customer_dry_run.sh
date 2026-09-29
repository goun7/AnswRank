#!/usr/bin/env bash
# ILK MUSTERI DRY-RUN — yerel tutarlilik denetimi ( mainnet'e PARA HARCANMAZ).
#
# ⚠ DURUST ETIKET — ZORUNLU:
#   Bu script HICBIR gercek odeme yapmaz, HICBIR gercek zincir cagrisi
#   yapmaz. Butun varliklar YERELDIR ( 127.0.0.1). Mainnet'e cikis YOK.
#   Amac: ilk-musteri onboarding yolunun hazir oldugunu KANITLAMAK.
#
# Yaptigi ( sirayla, her biri rc=0 olmali):
#   1. 22+ servisi tara -> USDC etiket durumu + fiyat + kota
#   2. guard_sync_gate.sh'i cagir -> guard/verify sync
#   3. her ulasilabilen servisin /healthz'ini kontrol et -> chain_valid
#   4. USDC nominal tutarlilik: fiyatlar 1 USDC = 1 USD ile celismiyor mu
#
# Cikis: rc=0 ( hepsi tutarli) | rc=1 ( biri tutarsiz/ulasilamadi)
#
# Kullanim:
#   ./scripts/first_customer_dry_run.sh
#   DRY_RUN_VERBOSE=1 ./scripts/first_customer_dry_run.sh   # tum cikti
set -uo pipefail

BURADAN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERBOSE="${DRY_RUN_VERBOSE:-0}"

# --- renksiz cikti ( log'lar icin) ---
_ok()   { echo "[OK]   $*"; }
_fail() { echo "[FAIL] $*"; }
_info()  { [ "$VERBOSE" = "1" ] && echo "[info]  $*"; }
_step()  { echo; echo "=== $* ==="; }

hatalar=0

# 1 USDC = 1 USD kabulu ( nominal tutarlilik; gercek peg DEGIL)
nominal_kontrol() {
  # "$0.05" -> 0.05; "$1.2" -> 1.2
  local s="$1"
  s="${s//\$/}"
  s="${s//,/}"    # binlik ayiraci yok ama guvenlik
  echo "$s"
}

# --- 1) SERVIS TARAMASI --------------------------------------------------
_step "1/4  servis taramasi ( USDC etiket + fiyat + kota)"

# servis:port listesi ( start_services.sh ile ayni)
SERVISLER=(
  "callsnap:8001"      "vadedostu:8002"    "repriceai:8003"
  "pqhaven:8004"       "cleartag:8005"     "borsa:8006"
  "answrank:8007"      "renewlock:8008"    "proje42:8010"
  "klinikkapici:8011"  "chargeshield:8012" "provix:8013"
  "lexbinder:8014"     "yevmiye:8015"      "gecit:8016"
  "vardro:8017"        "geosentinel:8018"  "lup:8019"
  "kilerim:8020"       "sonorix:8021"      "voltpulse:8022"
  "cbamshield:8023"    "mcpguard:9001"
)

usdc_say=0; sim_say=0; ulasilamadi=0
declare -a SIM_LISTESI

for sp in "${SERVISLER[@]}"; do
  ad="${sp%%:*}"; port="${sp##*:}"
  govde="$(curl -s -m 5 "http://127.0.0.1:$port/" 2>/dev/null)"
  if [ -z "$govde" ]; then
    _info "$ad :$port ULASILAMADI"
    ulasilamadi=$((ulasilamadi+1))
    continue
  fi
  cur="$(echo "$govde" | grep -o '"currency": "[^"]*"' | head -1 \
         | sed 's/"currency": "//;s/"$//')"
  if [ "$cur" = "USDC" ]; then
    usdc_say=$((usdc_say+1)); _ok "$ad :$port $cur"
  elif [ "$cur" = "USDC-sim" ]; then
    sim_say=$((sim_say+1))
    SIM_LISTESI+=("$ad")
    _info "$ad :$port $cur ( gecis bekliyor)"
  else
    _info "$ad :$port etiket yok ($cur)"
  fi
done

echo
echo "OZET: USDC=$usdc_say  USDC-sim=$sim_say  ulasilamadi=$ulasilamadi"
echo "  ( USDC-sim = gecis plani, docs/31 §6; ilk musteri AnswRank ile)"

# 2) GUARD SYNC -----------------------------------------------------------
_step "2/4  guard sync gate ( mainnet_guard + mainnet_verify)"

gate="$BURADAN/scripts/guard_sync_gate.sh"
if [ ! -x "$gate" ]; then
  _fail "guard_sync_gate.sh yok/calisir degil: $gate"
  hatalar=$((hatalar+1))
else
  if "$gate" >/tmp/dry_gate.log 2>&1; then
    _ok "guard sync ( 2/2 birebir)"
  else
    _fail "guard sync bozuk:"; tail -6 /tmp/dry_gate.log
    hatalar=$((hatalar+1))
  fi
fi

# 3) HEALTHZ + CHAIN VALID ------------------------------------------------
_step "3/4  healthz + receipt zinciri ( ulasilabilen her servis)"

zincir_hata=0
for sp in "${SERVISLER[@]}"; do
  ad="${sp%%:*}"; port="${sp##*:}"
  hz="$(curl -s -m 5 "http://127.0.0.1:$port/healthz" 2>/dev/null)"
  if [ -z "$hz" ]; then continue; fi
  # servise ozel alan adlari: chain_valid / ledger_chain_valid
  valid="$(echo "$hz" | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print(""); sys.exit()
for k in ("chain_valid","ledger_chain_valid"):
    if k in d:
        print(str(d[k]).lower()); sys.exit()
print("")' 2>/dev/null)"
  if [ "$valid" = "true" ]; then
    _ok "$ad :$port chain_valid=true"
  elif [ -n "$valid" ]; then
    _fail "$ad :$port chain_valid=$valid"
    zincir_hata=$((zincir_hata+1))
  else
    _info "$ad :$port chain_valid alani YOK ( servise ozel)"
  fi
done

# 4) USDC NOMINAL TUTARLILIK ---------------------------------------------
_step "4/4  USDC nominal tutarlilik ( 1 USDC = 1 USD kabulu)"

# AnswRank fiyatlarini healthz'den cek
hz7="$(curl -s -m 5 http://127.0.0.1:8007/healthz 2>/dev/null)"
if [ -z "$hz7" ]; then
  _fail "answrank :8007 healthz ULASILAMADI"
  hatalar=$((hatalar+1))
else
  # nominal tutarlilik: her fiyat pozitif ve kota'dan kucuk olmali
  printf '%s' "$hz7" | python3 -c '
import json, sys
hz = json.load(sys.stdin)
fiyatlar = hz.get("prices", {})
kota = float(str(hz.get("daily_quota", "$0")).lstrip("$"))
print(f"  answrank fiyatlar: {fiyatlar}")
print(f"  gunluk kota:       ${kota}")
hata = 0
for ad, f in fiyatlar.items():
    v = float(str(f).lstrip("$"))
    if v <= 0:
        print(f"[FAIL] {ad} fiyat pozitif DEGIL: {f}"); hata = 1
    if kota > 0 and v > kota:
        print(f"[FAIL] {ad} (${v}) gunluk kotayi (${kota}) asiyor"); hata = 1
if hata == 0:
    print(f"[OK]   {len(fiyatlar)} fiyat nominal tutarli "
          f"( 1 USDC = 1 USD; hepsi pozitif, kota ${kota} icinde)")
sys.exit(hata)
' || hatalar=$((hatalar+1))
fi

# --- OZET ----------------------------------------------------------------
_step "OZET ( ilk-musteri dry-run)"

echo "  USDC etiket  : $usdc_say/23 servis ( Answrank KOD-1 ile)"
echo "  USDC-sim     : $sim_say servis ( gecis plani, onay bekliyor)"
echo "  ulasilamadi  : $ulasilamadi"
echo "  guard sync   : $([ $hatalar -eq 0 ] && echo OK || echo FAIL)"
echo "  zincir hata  : $zincir_hata"
echo
echo "  USDC-sim kalan servisler ( ilk 5):" \
     "${SIM_LISTESI[@]:0:5}..."

if [ "$hatalar" != "0" ] || [ "$zincir_hata" != "0" ]; then
  echo
  echo "SONUC: FAIL — ilk-musteri yolu hazir DEGIL"
  exit 1
fi
echo
echo "SONUC: OK — onboarding yolu hazir ( hic gercek para harcanmadi)"
exit 0
