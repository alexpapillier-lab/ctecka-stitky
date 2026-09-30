#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tisk štítku. Argumenty: code name length_mm [copies] [dpi600] [weee] [serial] [importer]

importer = klíč dovozce z DB ("apple"/"iswap"/"dyson"/"mobilesentrix"); prázdný,
chybějící nebo neznámý → dovozce se určí podle názvu (jako dosud).
Každý tisk i chyba se hlásí do Supabase (viz nahlas v label_printer)."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

kod = sys.argv[1] if len(sys.argv) > 1 else None
try:
    from label_printer import render_label_image, print_label, print_labels, importer_text_for, nahlas

    code      = sys.argv[1]
    name      = sys.argv[2]
    length_mm = int(sys.argv[3])
    copies    = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    dpi_600   = (sys.argv[5] == "1") if len(sys.argv) > 5 else True
    weee      = (sys.argv[6] == "1") if len(sys.argv) > 6 else True
    serial    = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
    importer  = sys.argv[8] if len(sys.argv) > 8 and sys.argv[8] else None

    product_img = render_label_image(code, name, length_mm=length_mm, dpi_600=dpi_600, show_weee=weee,
                                     importer_text=importer_text_for(name, importer))

    if serial:
        # Dva samostatné fyzické štítky: produktový (produktový čárový kód) +
        # čistě jen sériové číslo (jeho vlastní čárový kód).
        from label_printer import render_serial_label_image
        serial_img = render_serial_label_image(serial, dpi_600=dpi_600)
        ok, err = print_labels([product_img, serial_img], copies=copies, dpi_600=dpi_600)
    else:
        ok, err = print_label(product_img, copies=copies, dpi_600=dpi_600)

    if ok:
        nahlas("tisk", f"{name} | dovozce={importer or 'auto'} dpi={600 if dpi_600 else 300} "
                       f"kopie={copies} serial={serial or '-'} weee={'ano' if weee else 'ne'}", code)
        print("OK")
    else:
        nahlas("chyba", f"tisk selhal: {err}", code)
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
except SystemExit:
    raise
except Exception:
    # Neočekávaná chyba (traceback) – nahlas a nech propadnout do stderr,
    # aby ji appka zobrazila.
    try:
        from label_printer import nahlas
        nahlas("chyba", "print_label.py: " + traceback.format_exc()[-1500:], kod)
    except Exception:
        pass
    raise
