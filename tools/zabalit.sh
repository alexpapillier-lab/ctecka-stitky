#!/bin/bash
# Vydání nové verze appky: tools/zabalit.sh N
#   1. Intel build (macOS 11) + libswift_Concurrency.dylib + Spustit.command → CteckaStitkySW_intel_vN.zip
#   2. upload do release v1.0
#   3. bump verze_appky.txt v repu → iMac si to stáhne při příštím spuštění (start.sh, s rollbackem)
# Pořadí je důležité: zip musí být nahraný DŘÍV, než se zvedne verze.
set -e
N="$1"; [ -n "$N" ] || { echo "pouziti: tools/zabalit.sh N"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
R=alexpapillier-lab/ctecka-stitky
WORK="$SRC/tools/release"
OUT="$WORK/v$N/CteckaStitkySW_release"
rm -rf "$WORK/v$N" && mkdir -p "$OUT"

# libswift_Concurrency.dylib (back-deploy pro Big Sur) – vezme se z předchozího release
DYLIB="$WORK/libswift_Concurrency.dylib"
if [ ! -f "$DYLIB" ]; then
  PREV=$(( N - 1 ))
  gh release download v1.0 -R $R -p "CteckaStitkySW_intel_v$PREV.zip" -D "$WORK" --clobber
  unzip -o -j -q "$WORK/CteckaStitkySW_intel_v$PREV.zip" "*/libswift_Concurrency.dylib" -d "$WORK"
fi
file "$DYLIB" | grep -q x86_64 || { echo "CHYBA: dylib neni x86_64"; exit 1; }

cd "$SRC"
# Xcode 27+ tiše zvedá minimum na macOS 12 (i když Package.swift říká .v11) → iMac s Big Sur
# by binárku nespustil. Cíl 11.0 se proto vynucuje pro kompilátor i linker.
FLAGS=(-c release --arch x86_64 -Xswiftc -target -Xswiftc x86_64-apple-macosx11.0
       -Xlinker -platform_version -Xlinker macos -Xlinker 11.0 -Xlinker "$(xcrun --show-sdk-version)")
swift build "${FLAGS[@]}" 2>&1 | grep -E "error|Build complete" | tail -3
BIN=$(swift build "${FLAGS[@]}" --show-bin-path)/CteckaStitkySW
cp "$BIN" "$OUT/CteckaStitkySW"
cp "$DYLIB" "$OUT/"
cp "$SRC/Spustit.command" "$OUT/"
chmod +x "$OUT/CteckaStitkySW" "$OUT/Spustit.command"
install_name_tool -add_rpath "@executable_path" "$OUT/CteckaStitkySW" 2>&1 | grep -v "would duplicate" || true
file "$OUT/CteckaStitkySW" | grep -q "x86_64" || { echo "CHYBA: neni x86_64"; exit 1; }
otool -l "$OUT/CteckaStitkySW" | grep -q "minos 11.0" || { echo "CHYBA: minos != 11.0"; exit 1; }
# debug-only demo kód se do release nesmí dostat
if strings "$OUT/CteckaStitkySW" | grep -q STITKY_DEMO; then echo "CHYBA: release obsahuje demo kod"; exit 1; fi

cd "$WORK/v$N" && zip -qr "CteckaStitkySW_intel_v$N.zip" CteckaStitkySW_release
gh release upload v1.0 -R $R "CteckaStitkySW_intel_v$N.zip" --clobber
echo "$N" > "$SRC/verze_appky.txt"
SHA=$(gh api "repos/$R/contents/verze_appky.txt" --jq .sha 2>/dev/null || true)
gh api -X PUT "repos/$R/contents/verze_appky.txt" -f message="Appka v$N

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -f content="$(printf '%s\n' "$N" | base64)" ${SHA:+-f sha="$SHA"} --jq '"verze_appky.txt = '"$N"' (" + .commit.sha[0:8] + ")"'
stat -f "v$N binárka: %z B" "$OUT/CteckaStitkySW"
