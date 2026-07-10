#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tisk štítku. Argumenty: code name length_mm [copies]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from label_printer import render_label_image, print_label

code      = sys.argv[1]
name      = sys.argv[2]
length_mm = int(sys.argv[3])
copies    = int(sys.argv[4]) if len(sys.argv) > 4 else 1
dpi_600   = (sys.argv[5] == "1") if len(sys.argv) > 5 else True
weee      = (sys.argv[6] == "1") if len(sys.argv) > 6 else True

img = render_label_image(code, name, length_mm=length_mm, dpi_600=dpi_600, show_weee=weee)
ok, err = print_label(img, copies=copies)
if ok:
    print("OK")
else:
    print(f"ERROR: {err}", file=sys.stderr)
    sys.exit(1)
