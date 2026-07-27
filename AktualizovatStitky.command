#!/bin/bash
# Aktualizuje tiskové skripty ze serveru (nezasahuje do appky ani do Ctecka barcode)
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Aktualizace štítků ==="

# Stahuje se přes API GitHubu, ne přes raw.githubusercontent – ten drží starou
# verzi v cache několik minut po nahrání změn.
API="https://api.github.com/repos/alexpapillier-lab/ctecka-stitky/contents/Scripts"
FAILED=0

# Seznam souborů se načítá ze serveru, aby nově přidaný skript nezůstal
# neaktualizovaný – dřív byl natvrdo a chyběly v něm print_label.py
# a generate_label.py, takže appka volala jejich starou verzi.
FILES=$(curl -fsSL "$API" 2>/dev/null \
  | /usr/bin/python3 -c "import sys,json;print(' '.join(f['name'] for f in json.load(sys.stdin)))" 2>/dev/null)

if [ -z "$FILES" ]; then
  echo "… seznam ze serveru nelze načíst, používám záložní"
  FILES="label_printer.py generate_label.py print_label.py scan_print.py weee.png"
fi

for f in $FILES; do
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

# Smaž zkompilovanou cache – jinak Python za určitých okolností (např.
# posunuté systémové hodiny) může spustit starou verzi místo právě stažené.
rm -rf "$DIR/Scripts/__pycache__"

if [ "$FAILED" = "1" ]; then
  echo "=== Dokončeno s chybami ==="
else
  echo "=== Hotovo ==="
fi
read -p "Stiskni Enter pro zavření..."
