#!/bin/bash
# Aktualizuje pouze label_printer.py a weee.png ze serveru
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Aktualizace štítků ==="
BASE="https://raw.githubusercontent.com/alexpapillier-lab/ctecka-stitky/main/Scripts"
for f in label_printer.py scan_print.py weee.png; do
  curl -fsSL "$BASE/$f" -o "$DIR/Scripts/$f" && echo "✓ $f" || echo "✗ Chyba při stahování $f"
done
echo "=== Hotovo ==="
read -p "Stiskni Enter pro zavření..."
