#!/usr/bin/env bash
# GUARD SYNC GATE — mainnet_guard.py + mainnet_verify.py birebir kalir.
#
# Iki repo ayni dosyalari ayri ayir tutuyor ( 25-pqhaven-x402 = SAHIP).
# Bu gate fark olursa CI'yi FAIL yapar ( hard gate) — sessiz
# sync-bozulmasini engeller. Karar notu: docs/29_GUARD_ENTEGRASYON_RAPORU.md
#
# Kullanim ( CI veya lokal):
#   ./scripts/guard_sync_gate.sh
#   RC 0 = sync ( birebir ayni), RC 1 = fark var ( CI kirmizi)
#
# Test: kasitli fark yaratmak icin
#   GUARD_SYNC_TEST=1 ./scripts/guard_sync_gate.sh   -> RC 1 beklenir
set -uo pipefail

# Sahip repo ( dokunma — read-only karsilastirma)
PQHAVEN="/home/gokun/projects/01_unicorn/25-pqhaven-x402"
BURADAN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DOSYALAR=(mainnet_guard.py mainnet_verify.py)

# --- reponun gercekte var oldugundan emin ol ---
if [ ! -d "$PQHAVEN/.git" ]; then
  echo "GUARD-SYNC-ERROR: sahip repo bulunamadi: $PQHAVEN"
  echo "  ( gate yalnizca bu makinede dogru calisir)"
  exit 2
fi

# Sahip repodan HEAD surumunu cikart ( work tree'yi KIRMA)
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

hata=0
for f in "${DOSYALAR[@]}"; do
  # KOK'ta 25'in HEAD'i ile karsilastir
  if ! git -C "$PQHAVEN" show "HEAD:$f" > "$tmpdir/kaynak" 2>/dev/null; then
    echo "GUARD-SYNC-ERROR: '$f' sahip repoda ( HEAD) YOK"
    hata=1
    continue
  fi
  hedef="$BURADAN/$f"
  if [ ! -f "$hedef" ]; then
    echo "GUARD-SYNC-FAIL: '$f' burada YOK — kopyalanmali"
    echo "  cp $PQHAVEN/$f $hedef"
    hata=1
    continue
  fi

  # --- KASITLI TEST MODU: gecici bir fark ekle ---
  if [ "${GUARD_SYNC_TEST:-0}" = "1" ]; then
    printf '# KASITLI-TEST-FARK ( gate denemesi)\n' >> "$tmpdir/kaynak"
  fi

  if cmp -s "$tmpdir/kaynak" "$hedef"; then
    echo "GUARD-SYNC-OK: $f ( birebir ayni)"
  else
    echo "GUARD-SYNC-FAIL: $f FARKLI — sync bozuldu"
    echo "  diff:"
    diff -u "$tmpdir/kaynak" "$hedef" | sed 's/^/    /' | head -20
    hata=1
  fi
done

if [ "$hata" != "0" ]; then
  echo
  echo "GUARD-SYNC-SONUC: FAIL — mainnet guard dosyalari senkron DEGIL"
  echo "  Duzelt: cp $PQHAVEN/{${DOSYALAR[*]}} $BURADAN/  ( sonra commit)"
  exit 1
fi

echo
echo "GUARD-SYNC-SONUC: OK — 2/2 dosya birebir ayni ( sync korundu)"
exit 0
