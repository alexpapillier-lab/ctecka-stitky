#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generuje PNG štítku. Argumenty: code name length_mm output_path"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from label_printer import render_label_image

code      = sys.argv[1]
name      = sys.argv[2]
length_mm = int(sys.argv[3])
output    = sys.argv[4]
dpi_600   = (sys.argv[5] == "1") if len(sys.argv) > 5 else True
weee      = (sys.argv[6] == "1") if len(sys.argv) > 6 else True

img = render_label_image(code, name, length_mm=length_mm, dpi_600=dpi_600, show_weee=weee)
img.save(output)
