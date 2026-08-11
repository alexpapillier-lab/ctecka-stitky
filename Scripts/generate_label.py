#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generuje PNG štítku. Argumenty: code name length_mm output_path [dpi600] [weee] [serial]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from label_printer import render_label_image

code      = sys.argv[1]
name      = sys.argv[2]
length_mm = int(sys.argv[3])
output    = sys.argv[4]
dpi_600   = (sys.argv[5] == "1") if len(sys.argv) > 5 else True
weee      = (sys.argv[6] == "1") if len(sys.argv) > 6 else True
serial    = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None

product_img = render_label_image(code, name, length_mm=length_mm, dpi_600=dpi_600, show_weee=weee)

if serial:
    # Tisknou se dva samostatné fyzické štítky (produktový + SN) – v náhledu
    # je pro jednoduchost složíme pod sebe do jednoho obrázku.
    from label_printer import render_serial_label_image
    from PIL import Image

    serial_img = render_serial_label_image(serial, dpi_600=dpi_600)
    gap = int(product_img.height * 0.06)
    width = max(product_img.width, serial_img.width)
    combined = Image.new("RGB", (width, product_img.height + gap + serial_img.height), "white")
    combined.paste(product_img, (0, 0))
    combined.paste(serial_img, (0, product_img.height + gap))
    combined.save(output)
else:
    product_img.save(output)
