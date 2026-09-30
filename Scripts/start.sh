#!/bin/bash
# Spouštěč appky s automatickou aktualizací binárky.
# Volá ho Spustit.command (stub) po stažení skriptů. Postup:
#   1. zjisti nejnovější verzi appky (verze_appky.txt v repu) vs. lokální .verze_appky
#   2. je-li novější: stáhni CteckaStitkySW_intel_vN.zip z release, ověř, že je to
#      x86_64 Mach-O + dylib, zálohuj současnou binárku (.prev), vyměň
#   3. spusť appku; když do 6 s spadne → vrať .prev a spusť ji (rollback)
#   4. výsledek nahlas do stitky_aktualizace (jen když se něco měnilo)
# Bez internetu se aktualizace přeskočí a appka startuje jako dosud.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$DIR/CteckaStitkySW"
DYLIB="$DIR/libswift_Concurrency.dylib"
VERZE_FILE="$DIR/.verze_appky"
LOG="$DIR/aktualizace.log"
REPO="alexpapillier-lab/ctecka-stitky"
SB_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4'

log() { echo "$1"; echo "$(date '+%Y-%m-%d %H:%M:%S')  [app] $1" >> "$LOG"; }

nahlas() {  # $1 vysledek, $2 zmeneno
  curl -s -o /dev/null --max-time 10 -X POST \
    "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/stitky_aktualizace" \
    -H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY" \
    -H "Content-Type: application/json" -H "Prefer: return=minimal" \
    -d "$(printf '{"stroj":"%s","macos":"%s","arch":"%s","vysledek":"%s","zmeneno":"%s"}' \
         "$(hostname -s 2>/dev/null)" "$(sw_vers -productVersion 2>/dev/null)" "$(uname -m)" "$1" "$2")" 2>/dev/null || true
}

spust() {  # spustí appku a čeká na ni (Terminál zůstává rodičem jako dřív)
  "$BIN" & APP_PID=$!
  wait $APP_PID
}

LOCAL=$(cat "$VERZE_FILE" 2>/dev/null | tr -dc '0-9'); LOCAL=${LOCAL:-0}
REMOTE=$(curl -fsSL --max-time 15 -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/$REPO/contents/verze_appky.txt" 2>/dev/null | tr -dc '0-9')

if [ -z "$REMOTE" ]; then
  log "verzi appky nelze zjistit (offline?) – spouštím v$LOCAL"
  spust; exit $?
fi

if [ "$REMOTE" -le "$LOCAL" ] && [ -x "$BIN" ]; then
  spust; exit $?
fi

# ── Nová verze ──────────────────────────────────────────────────────────
log "appka v$LOCAL → v$REMOTE: stahuji"
TMP=$(mktemp -d)
ZIP="CteckaStitkySW_intel_v$REMOTE.zip"
if ! curl -fsSL --max-time 120 "https://github.com/$REPO/releases/download/v1.0/$ZIP" -o "$TMP/app.zip" \
   || ! unzip -o -q "$TMP/app.zip" -d "$TMP"; then
  log "stažení v$REMOTE selhalo – nechávám v$LOCAL"; nahlas "app-stazeni-selhalo" "v$LOCAL→v$REMOTE"
  rm -rf "$TMP"; spust; exit $?
fi
NEW="$TMP/CteckaStitkySW_release"
if ! file "$NEW/CteckaStitkySW" | grep -q "Mach-O 64-bit executable x86_64" || [ ! -s "$NEW/libswift_Concurrency.dylib" ]; then
  log "stažený balíček v$REMOTE není platná Intel appka – nechávám v$LOCAL"; nahlas "app-neplatny-balicek" "v$REMOTE"
  rm -rf "$TMP"; spust; exit $?
fi

# záloha + výměna
[ -f "$BIN" ] && cp -f "$BIN" "$BIN.prev"
[ -f "$DYLIB" ] && cp -f "$DYLIB" "$DYLIB.prev"
cp -f "$NEW/CteckaStitkySW" "$BIN" && cp -f "$NEW/libswift_Concurrency.dylib" "$DYLIB"
chmod +x "$BIN"
# nový stub Spustit.command (pokud je v balíčku jiný) – bezpečné, stub už neběží (exec)
if [ -f "$NEW/Spustit.command" ] && ! cmp -s "$NEW/Spustit.command" "$DIR/Spustit.command"; then
  cp -f "$NEW/Spustit.command" "$DIR/Spustit.command" && chmod +x "$DIR/Spustit.command"
fi
rm -rf "$TMP"

# zkušební start: když spadne do 6 s, vrať předchozí verzi
"$BIN" & APP_PID=$!
sleep 6
if kill -0 $APP_PID 2>/dev/null; then
  echo "$REMOTE" > "$VERZE_FILE"
  log "appka v$REMOTE běží – aktualizace OK"; nahlas "app-aktualizovana" "v$LOCAL→v$REMOTE"
  wait $APP_PID; exit $?
fi
wait $APP_PID; ST=$?
if [ "$ST" -eq 0 ]; then
  echo "$REMOTE" > "$VERZE_FILE"
  log "appka v$REMOTE skončila hned, ale bez chyby (zavřena?) – beru jako OK"; nahlas "app-aktualizovana" "v$LOCAL→v$REMOTE"
  exit 0
fi
log "appka v$REMOTE spadla při startu (kód $ST) – ROLLBACK na v$LOCAL"
[ -f "$BIN.prev" ] && cp -f "$BIN.prev" "$BIN"
[ -f "$DYLIB.prev" ] && cp -f "$DYLIB.prev" "$DYLIB"
chmod +x "$BIN"
nahlas "app-ROLLBACK" "v$REMOTE spadla (kód $ST), vráceno v$LOCAL"
spust; exit $?
