#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generuje PNG štítku. Argumenty: code name length_mm output_path [dpi600] [weee] [serial]"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from label_printer import render_label_image, classify_importer

# DOČASNÝ DEBUG LOG – smazat po vyřešení dovozce v appce.
try:
    with open(os.path.expanduser("~/Desktop/CteckaStitkySW/debug_log.txt"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now()}  argv={sys.argv!r}\n")
        if len(sys.argv) > 2:
            f.write(f"    classify_importer(name)[:40] = {classify_importer(sys.argv[2])[:40]!r}\n")
except Exception as e:
    pass

code      = sys.argv[1]
name      = sys.argv[2]
length_mm = int(sys.argv[3])
output    = sys.argv[4]
dpi_600   = (sys.argv[5] == "1") if len(sys.argv) > 5 else True
weee      = (sys.argv[6] == "1") if len(sys.argv) > 6 else True
serial    = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None

img = render_label_image(code, name, length_mm=length_mm, dpi_600=dpi_600, show_weee=weee,
                          serial_number=serial)
img.save(output)
