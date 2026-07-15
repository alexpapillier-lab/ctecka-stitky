#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scan-to-print mód. Čte kód ze sériového portu, vyhledá produkt v Supabase
a vytiskne štítek. Rozpozná EAN, náš kód produktu i kód dodavatele
(MobileSentrix / Apple part number).
Výstup: JSON řádky  {"status": "ok"|"error"|"info", "msg": "..."}
"""
import sys, os, json, time, signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

SUPABASE_URL = "https://osinlzagjimyrzjpdxai.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4"
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

SELECT = "select=code,name,ean,part_number,show_weee"


def emit(status, msg):
    print(json.dumps({"status": status, "msg": msg}), flush=True)


def _get(query):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/products?{SELECT}&{query}",
                     headers=HEADERS, timeout=6)
    return r.json() if r.ok else []


def lookup(barcode):
    """
    Najde produkt podle EAN, našeho kódu, nebo kódu dodavatele.
    Vrací (produkty, zdroj). Více produktů = nejednoznačné.
    """
    for field, label in (("ean", "EAN"), ("code", "kód produktu")):
        found = _get(f"{field}=eq.{barcode}&limit=2")
        if found:
            return found, label

    # Kód dodavatele: přesná shoda, pak částečná (pole může nést více kódů)
    found = _get(f"part_number=eq.{barcode}&limit=5")
    if found:
        return found, "kód dodavatele"

    found = _get(f"part_number=like.*{barcode}*&limit=5")
    # like.*X* by chytlo i kód, který je jen podřetězcem jiného – ověř po tokenech
    exact = [p for p in found if barcode in (p.get("part_number") or "").split()]
    if exact:
        return exact, "kód dodavatele"

    return [], None


def print_it(product):
    from label_printer import render_label_image, print_label, default_length
    name = product["name"]
    show_weee = product.get("show_weee")
    img = render_label_image(
        product["code"], name,
        length_mm=default_length(name),
        show_weee=True if show_weee is None else show_weee,
    )
    return print_label(img)


def find_serial_port():
    import glob
    candidates = glob.glob("/dev/tty.usb*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/cu.usb*")
    return candidates[0] if candidates else None


def handle(barcode):
    emit("info", f"Naskenováno: {barcode}")
    try:
        products, source = lookup(barcode)
    except Exception as e:
        emit("error", f"Chyba spojení s databází: {e}")
        return

    if not products:
        emit("error", f"Produkt nenalezen: {barcode}")
        return

    if len(products) > 1:
        codes = ", ".join(p["code"] for p in products)
        emit("error", f"{barcode} má více produktů ({codes}) – vyber ručně")
        return

    product = products[0]
    emit("info", f"Nalezeno přes {source}: {product['code']} – {product['name']}")
    try:
        ok, err = print_it(product)
    except Exception as e:
        emit("error", f"Tisk selhal: {e}")
        return
    emit("ok", f"Vytištěno: {product['name']}") if ok else emit("error", f"Tisk selhal: {err}")


def run():
    import serial
    port = find_serial_port()
    if not port:
        emit("error", "Sériový port nenalezen – zkontroluj připojení čtečky")
        sys.exit(1)

    try:
        ser = serial.Serial(port, baudrate=9600, timeout=0.1)
    except Exception as e:
        emit("error", f"Nelze otevřít port {port}: {e}")
        sys.exit(1)

    emit("info", f"Připojeno: {port} – skenuj produkt")

    buf = b""
    while True:
        chunk = ser.read(64)
        if chunk:
            buf += chunk
            if b"\r" in buf or b"\n" in buf:
                barcode = buf.replace(b"\r", b"").replace(b"\n", b"").decode("utf-8", errors="ignore").strip()
                buf = b""
                if barcode:
                    handle(barcode)
        time.sleep(0.05)


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

if __name__ == "__main__":
    # Ruční test bez čtečky:  python3 scan_print.py 107082001032
    if len(sys.argv) > 1:
        handle(sys.argv[1])
    else:
        run()
