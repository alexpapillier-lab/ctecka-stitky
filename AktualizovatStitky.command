#!/bin/bash
# Aktualizuje pouze label_printer.py a weee.png ze serveru
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Aktualizace štítků ==="
curl -fsSL "https://raw.githubusercontent.com/alexpapillier-lab/ctecka/main/label_printer.py" -o "$DIR/Scripts/label_printer.py" && echo "✓ label_printer.py" || echo "✗ Chyba při stahování label_printer.py"
curl -fsSL "https://raw.githubusercontent.com/alexpapillier-lab/ctecka/main/weee.png" -o "$DIR/Scripts/weee.png" && echo "✓ weee.png" || echo "✗ Chyba při stahování weee.png"
echo "=== Hotovo ==="
read -p "Stiskni Enter pro zavření..."
