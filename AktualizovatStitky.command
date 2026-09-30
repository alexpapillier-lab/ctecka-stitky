#!/bin/bash
# Aktualizuje tiskové skripty ze serveru (nezasahuje do appky ani do Ctecka barcode).
# Spouští se buď ručně (dvojklik), nebo automaticky přes launchd
# (viz InstalovatAutoAktualizaci.command) – v tom případě neběží v terminálu,
# nečeká na Enter a výstup jde jen do logu.
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/aktualizace.log"

# Log drž malý – nech posledních ~200 řádků
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 400 ]; then
  tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

log() { echo "$1"; echo "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }

log "=== Aktualizace štítků === (macOS $(sw_vers -productVersion 2>/dev/null), $(uname -m), $(hostname -s 2>/dev/null))"

# Stahuje se přes API GitHubu, ne přes raw.githubusercontent – ten drží starou
# verzi v cache několik minut po nahrání změn.
API="https://api.github.com/repos/alexpapillier-lab/ctecka-stitky/contents/Scripts"
FAILED=0
CHANGED=0

# Seznam souborů se načítá ze serveru, aby nově přidaný skript nezůstal
# neaktualizovaný – dřív byl natvrdo a chyběly v něm print_label.py
# a generate_label.py, takže appka volala jejich starou verzi.
FILES=$(curl -fsSL --max-time 20 "$API" 2>/dev/null \
  | /usr/bin/python3 -c "import sys,json;print(' '.join(f['name'] for f in json.load(sys.stdin)))" 2>/dev/null)

if [ -z "$FILES" ]; then
  log "… seznam ze serveru nelze načíst, používám záložní"
  FILES="label_printer.py generate_label.py print_label.py scan_print.py weee.png"
fi

for f in $FILES; do
  TMP="$DIR/Scripts/.$f.new"
  if curl -fsSL --max-time 30 -H "Accept: application/vnd.github.raw" "$API/$f" -o "$TMP" && [ -s "$TMP" ]; then
    if [ -f "$DIR/Scripts/$f" ] && cmp -s "$TMP" "$DIR/Scripts/$f"; then
      rm -f "$TMP"
      log "= $f (beze změny)"
    else
      mv "$TMP" "$DIR/Scripts/$f"     # přepiš až po úspěšném stažení
      log "✓ $f AKTUALIZOVÁN"
      CHANGED=1
      ZMENENO="${ZMENENO:+$ZMENENO }$f"
    fi
  else
    rm -f "$TMP"
    log "✗ Chyba při stahování $f – ponechána stávající verze"
    FAILED=1
  fi
done

# Smaž zkompilovanou cache jen když se něco změnilo – jinak Python za určitých
# okolností (např. posunuté hodiny) může spustit starou verzi místo nové.
if [ "$CHANGED" = "1" ]; then
  rm -rf "$DIR/Scripts/__pycache__"
fi

if [ "$FAILED" = "1" ]; then
  log "=== Dokončeno s chybami ==="; VYSLEDEK="chyba"
elif [ "$CHANGED" = "1" ]; then
  log "=== Hotovo – staženy nové verze ==="; VYSLEDEK="aktualizovano"
else
  log "=== Hotovo – vše už bylo aktuální ==="; VYSLEDEK="beze-zmeny"
fi

# Pošli záznam o běhu do Supabase (tabulka stitky_aktualizace), aby šlo
# na dálku ověřit, že se změny na stroj dostaly. Jen curl, žádné závislosti;
# když to selže (bez internetu), nic se neděje – lokální log stačí.
SB_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4'
JSON=$(printf '{"stroj":"%s","macos":"%s","arch":"%s","vysledek":"%s","zmeneno":"%s"}' \
  "$(hostname -s 2>/dev/null)" "$(sw_vers -productVersion 2>/dev/null)" "$(uname -m)" \
  "$VYSLEDEK" "${ZMENENO:-"-"}")
curl -s -o /dev/null --max-time 10 -X POST \
  "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/stitky_aktualizace" \
  -H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY" \
  -H "Content-Type: application/json" -H "Prefer: return=minimal" \
  -d "$JSON" 2>/dev/null || true

# Na Enter čekej jen když běžíme v terminálu (dvojklik), ne pod launchd.
if [ -t 0 ]; then
  read -p "Stiskni Enter pro zavření..."
fi
