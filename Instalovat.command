#!/bin/bash
# Instalace závislostí pro Štítkovou appku
cd "$(dirname "$0")"

echo "=== Instalace Python závislostí ==="

PYTHON=""
for p in /usr/local/bin/python3.11 /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
    if [ -f "$p" ]; then PYTHON="$p"; break; fi
done

if [ -z "$PYTHON" ]; then
    echo "CHYBA: Python 3 nenalezen. Nainstaluj Python z https://python.org"
    read -p "Stiskni Enter pro zavření..."
    exit 1
fi

echo "Python: $PYTHON ($($PYTHON --version))"
echo ""

$PYTHON -m pip install --upgrade pip --quiet
$PYTHON -m pip install pillow python-barcode brother_ql pyserial --upgrade

echo ""
echo "=== Hotovo ==="
read -p "Stiskni Enter pro zavření..."
