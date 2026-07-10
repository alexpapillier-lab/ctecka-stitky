#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scan-to-print mód. Čte EAN/kód ze sériového portu, vyhledá produkt
v Supabase (nebo lokálním SQLite) a vytiskne štítek.
Výstup: JSON řádky  {"status": "ok"|"error"|"info", "msg": "..."}
"""
import sys, os, json, time, signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

SUPABASE_URL = "https://cjrnfjjfqzjxtzrzscpn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqcm5mampmcXpqeHR6cnpzY3BuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDYxMDkwNjAsImV4cCI6MjA2MTY4NTA2MH0.jWt1er9lXHE_-Y8qLXFr0XqzY3bpYRZOGsNUxGmxanw"
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

def emit(status, msg):
    print(json.dumps({"status": status, "msg": msg}), flush=True)

def lookup(barcode):
    """Najde produkt podle EAN nebo kódu."""
    for field in ("ean", "code"):
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/products?select=code,name&{field}=eq.{barcode}&limit=1",
            headers=HEADERS, timeout=6
        )
        if r.ok and r.json():
            return r.json()[0]
    return None

def print_it(code, name):
    from label_printer import render_label_image, print_label, default_length
    length_mm = default_length(name)
    img = render_label_image(code, name, length_mm=length_mm)
    ok, err = print_label(img)
    return ok, err

def find_serial_port():
    import glob
    candidates = glob.glob("/dev/tty.usb*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/cu.usb*")
    return candidates[0] if candidates else None

def run():
    import serial
    port = find_serial_port()
    if not port:
        emit("error", "Sériový port nenalezen – zkontroluj připojení čtečky")
        sys.exit(1)

    emit("info", f"Připojeno: {port} – skenuj produkt")

    try:
        ser = serial.Serial(port, baudrate=9600, timeout=0.1)
    except Exception as e:
        emit("error", f"Nelze otevřít port {port}: {e}")
        sys.exit(1)

    buf = b""
    while True:
        chunk = ser.read(64)
        if chunk:
            buf += chunk
            if b"\r" in buf or b"\n" in buf:
                barcode = buf.replace(b"\r", b"").replace(b"\n", b"").decode("utf-8", errors="ignore").strip()
                buf = b""
                if not barcode:
                    continue
                emit("info", f"Naskenováno: {barcode}")
                product = lookup(barcode)
                if not product:
                    emit("error", f"Produkt nenalezen: {barcode}")
                    continue
                emit("info", f"Tisknu: {product['code']} – {product['name']}")
                ok, err = print_it(product["code"], product["name"])
                if ok:
                    emit("ok", f"Vytištěno: {product['name']}")
                else:
                    emit("error", f"Tisk selhal: {err}")
        time.sleep(0.05)

signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
run()
