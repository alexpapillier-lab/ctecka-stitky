#!/bin/bash
# Instalace Python závislostí pro Štítkovou appku do vlastního venv
# ("$DIR/venv", vedle Scripts/). Appka hledá venv/bin/python3 jako první
# interpret. Opakované spuštění venv nezakládá znovu, jen doinstaluje/aktualizuje.
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/venv"

pause() { if [ -t 0 ]; then read -p "Stiskni Enter pro zavření..."; fi; }

echo "=== Instalace Python závislostí ==="

if [ -x "$VENV/bin/python3" ]; then
    echo "venv už existuje: $VENV – jen aktualizuji balíčky"
else
    PYTHON=""
    for p in /usr/local/bin/python3.11 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then PYTHON="$p"; break; fi
    done

    if [ -z "$PYTHON" ]; then
        echo "CHYBA: Python 3 nenalezen. Nainstaluj Python z https://python.org"
        pause
        exit 1
    fi

    echo "Python: $PYTHON ($("$PYTHON" --version))"
    echo "Vytvářím venv: $VENV"
    if ! "$PYTHON" -m venv "$VENV"; then
        echo "CHYBA: nepodařilo se vytvořit venv"
        pause
        exit 1
    fi
fi
echo ""

PY="$VENV/bin/python3"
"$PY" -m pip install --upgrade pip --quiet
# certifi = aktuální CA certifikáty; Big Sur má systémové zastaralé a bez
# certifi padá ověřené HTTPS spojení na Supabase (skripty mají zálohu, ale
# s certifi jde vše ověřeně).
if ! "$PY" -m pip install --upgrade pillow python-barcode brother_ql pyserial pyusb certifi; then
    echo ""
    echo "CHYBA: instalace balíčků selhala"
    pause
    exit 1
fi

echo ""
echo "=== Kontrola ==="
if "$PY" -c "import PIL, barcode, brother_ql, serial, usb; print('OK')"; then
    echo "=== Hotovo ==="
else
    echo "CHYBA: některý balíček se nepodařilo naimportovat"
    pause
    exit 1
fi
pause
