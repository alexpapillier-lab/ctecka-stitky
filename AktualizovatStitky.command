#!/bin/bash
# Aktualizuje tiskové skripty ze serveru (nezasahuje do appky ani do Ctecka barcode)
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Aktualizace štítků ==="

# Stahuje se přes API GitHubu, ne přes raw.githubusercontent – ten drží starou
# verzi v cache několik minut po nahrání změn.
API="https://api.github.com/repos/alexpapillier-lab/ctecka-stitky/contents/Scripts"
FAILED=0

for f in label_printer.py scan_print.py weee.png; do
  TMP="$DIR/Scripts/.$f.new"
  if curl -fsSL -H "Accept: application/vnd.github.raw" "$API/$f" -o "$TMP" && [ -s "$TMP" ]; then
    mv "$TMP" "$DIR/Scripts/$f"     # přepiš až po úspěšném stažení
    echo "✓ $f"
  else
    rm -f "$TMP"
    echo "✗ Chyba při stahování $f – ponechána stávající verze"
    FAILED=1
  fi
done

if [ "$FAILED" = "1" ]; then
  echo "=== Dokončeno s chybami ==="
else
  echo "=== Hotovo ==="
fi
read -p "Stiskni Enter pro zavření..."
