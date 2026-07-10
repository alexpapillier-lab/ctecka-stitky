# -*- coding: utf-8 -*-
"""Generování a tisk štítků na Brother QL-700 (29mm nekonečná páska, USB)."""

import os
from PIL import Image, ImageDraw, ImageFont

PRINTER_MODEL = "QL-700"

_DISPLAY_KEYWORDS = ["displej", "display", "lcd", "oled", "screen"]
_DISPLAY_EXCLUDE  = ["pod displej", "pod display", "těsnění", "lepidlo", "sklíčko", "kabel k", "rámeček"]

def is_display(name):
    """Vrátí True pokud jde o displej (→ 125mm štítek)."""
    t = (name or "").lower()
    if any(ex in t for ex in _DISPLAY_EXCLUDE):
        return False
    return any(kw in t for kw in _DISPLAY_KEYWORDS)

def default_length(name):
    return 125 if is_display(name) else 62
LABEL_SIZE_CODE = "29"          # brother_ql kód pro 29mm nekonečnou pásku
LABEL_HEIGHT_PX = 306           # tisknutelná šířka pásky při 300 DPI (brother_ql spec pro "29")
LABEL_HEIGHT_PX_600 = 612       # totéž při 600 DPI
PX_PER_MM = 300 / 25.4          # 300 DPI – délka
PX_PER_MM_600 = 600 / 25.4      # 600 DPI – délka
PRINT_DPI_600 = True            # zapnout 600 DPI tisk

DEFAULT_IMPORTER_TEXT = (
    "Dovozce: iSwap.cz s.r.o., U Vokovické školy 299/4, 160 00, Praha, "
    "Česká republika, tel.: +420 773 118 472. Určeno pro profesionální instalaci. Vyrobeno v Číně."
)


def mm_to_px(mm):
    return int(round(mm * PX_PER_MM))


def _font(size_px, bold=False):
    candidates = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"]
        if bold else
        ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_weee_icon(draw, x, y, size, _img_ref=None):
    """Použij PNG soubor weee.png místo kreslení."""
    if _img_ref is not None:
        weee_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weee.png")
        if os.path.exists(weee_path):
            weee = Image.open(weee_path).convert("RGBA").resize((int(size), int(size)), Image.LANCZOS)
            white_bg = Image.new("RGBA", weee.size, "WHITE")
            white_bg.paste(weee, mask=weee.split()[3])
            _img_ref.paste(white_bg.convert("RGB"), (int(x), int(y)))
            return


def _draw_weee_icon_fallback(draw, x, y, size):
    """Symbol přeškrtnuté popelnice (WEEE) – věrná kopie standardní ikony."""
    w = size
    lw  = max(1, int(w * 0.05))
    slw = max(1, int(w * 0.032))

    # ── Tělo – výrazný lichoběžník (nahoře výrazně širší) ────────
    btop_y = y + w * 0.275
    bbot_y = y + w * 0.905
    btop_l = x + w * 0.085
    btop_r = x + w * 0.915
    bbot_l = x + w * 0.200
    bbot_r = x + w * 0.800

    body_pts = [
        (btop_l, btop_y), (btop_r, btop_y),
        (bbot_r, bbot_y), (bbot_l, bbot_y),
    ]
    draw.polygon(body_pts, outline="black", fill="white")
    for a, b in zip(body_pts, body_pts[1:] + [body_pts[0]]):
        draw.line([a, b], fill="black", width=lw)

    # ── Tenký vodorovný pruh na těle ────────────────────────────
    t = 0.35
    sl = btop_l + (bbot_l - btop_l) * t + w * 0.03
    sr = btop_r + (bbot_r - btop_r) * t - w * 0.03
    sy = btop_y + (bbot_y - btop_y) * t
    sh = max(lw, int(w * 0.05))
    draw.rectangle([sl, sy, sr, sy + sh], fill="black")

    # ── Víko – zaoblený obdélník ─────────────────────────────────
    lid_t = y + w * 0.175
    lid_b = btop_y
    lid_l = btop_l - w * 0.03
    lid_r = btop_r + w * 0.03
    r = max(2, int(w * 0.05))
    draw.rounded_rectangle([lid_l, lid_t, lid_r, lid_b],
                            radius=r, outline="black", fill="white", width=lw)

    # ── Madlo – malý zaoblený obdélník uprostřed nahoře ─────────
    hl = x + w * 0.38
    hr = x + w * 0.62
    ht = y + w * 0.07
    hb = lid_t + w * 0.005
    draw.rounded_rectangle([hl, ht, hr, hb],
                            radius=max(1, int(w * 0.03)),
                            outline="black", fill="white", width=slw)

    # ── Kolečka ──────────────────────────────────────────────────
    wr = max(2, int(w * 0.065))
    draw.ellipse([bbot_l - wr, bbot_y - wr, bbot_l + wr, bbot_y + wr],
                 outline="black", fill="white", width=slw)
    draw.ellipse([bbot_r - wr, bbot_y - wr, bbot_r + wr, bbot_y + wr],
                 outline="black", fill="white", width=slw)

    # ── Křížek přes celou ikonu ──────────────────────────────────
    clw = max(2, int(w * 0.06))
    draw.line([(x, y), (x + w, y + w)], fill="black", width=clw)
    draw.line([(x, y + w), (x + w, y)], fill="black", width=clw)


def _wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        test = (cur + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_fitted_text(draw, text, x, y, max_width, font, max_lines=2):
    """Zalomí text na max_lines řádků; pokud nestačí, poslední řádek zkrátí s '…'."""
    lines = _wrap_text(draw, text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] - draw.textbbox((0, 0), "", font=font)[0] > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    line_h = int(font.size * 1.15)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_h), line, fill="black", font=font)
    return len(lines) * line_h


def _parse_display_name(name):
    """Rozdělí 'LCD displej bílý PREMIUM | iPhone 6S' na součásti."""
    parts = name.split("|", 1)
    type_raw = parts[0].strip()
    model    = parts[1].strip() if len(parts) > 1 else type_raw
    t = type_raw.lower()
    if any(w in t for w in ["černý", "černá", "cerny", "cerna", "black"]):
        color = "black"
    elif any(w in t for w in ["bílý", "bílá", "bily", "bila", "white"]):
        color = "white"
    else:
        color = None
    variant = next((v for v in ["PREMIUM", "ORIGINAL", "OEM", "COPY"] if v in type_raw.upper()), None)
    return model, type_raw, color, variant


def _render_display_label(code, name, height_px, width_px, importer_text, img):
    """Speciální layout pro displeje: vlevo standard, uprostřed vert. model, vpravo kruh+text."""
    draw = ImageDraw.Draw(img)
    margin = int(height_px * 0.05)

    model, type_raw, color, variant = _parse_display_name(name)

    # ── Proporce sekcí ───────────────────────────────────────────
    left_w   = int(width_px * 0.40)
    mid_w    = int(width_px * 0.13)
    right_x  = left_w + mid_w
    right_w  = width_px - right_x

    top_h    = int(height_px * 0.62)
    bottom_h = height_px - top_h

    # ── LEVÁ SEKCE – ikona, čárový kód, dovozce ──────────────────
    icon_size = int((top_h - 2 * margin) * 0.45)
    icon_y = margin + ((top_h - 2 * margin) - icon_size) // 2
    _draw_weee_icon(draw, margin, icon_y, icon_size, _img_ref=img)

    col_x   = margin + icon_size + int(height_px * 0.06)
    col_w   = left_w - col_x - margin
    cur_y   = margin

    # Název (typ displeje) – nahoře v pravém sloupci levé sekce
    name_font_size = int(height_px * 0.115)
    while name_font_size > int(height_px * 0.07):
        f = _font(name_font_size, bold=True)
        lines = _wrap_text(draw, type_raw, f, col_w)
        if len(lines) <= 2:
            break
        name_font_size -= 1
    name_f  = _font(name_font_size, bold=True)
    name_lh = int(name_font_size * 1.18)
    for line in lines[:2]:
        draw.text((col_x, cur_y), line, fill="black", font=name_f)
        cur_y += name_lh
    cur_y += int(height_px * 0.03)

    # Čárový kód pod názvem
    import barcode as bc_mod
    from barcode.writer import ImageWriter
    bc = bc_mod.get("code128", str(code), writer=ImageWriter())
    bc_img = bc.render({"module_height": 8.0, "font_size": 0, "text_distance": 1,
                        "quiet_zone": 1, "write_text": False})
    bc_avail_h = top_h - cur_y - int(height_px * 0.14) - margin
    bc_target_h = max(int(height_px * 0.2), bc_avail_h)
    bc_ratio    = bc_target_h / bc_img.height
    bc_w        = min(int(bc_img.width * bc_ratio), col_w)
    bc_target_h = int(bc_w / bc_img.width * bc_img.height)
    bc_img      = bc_img.resize((bc_w, bc_target_h))
    img.paste(bc_img, (col_x, cur_y))
    cur_y += bc_target_h + int(height_px * 0.01)

    code_font = _font(int(height_px * 0.09))
    draw.text((col_x, cur_y), str(code), fill="black", font=code_font)

    # Dovozce (levá dolní část)
    max_tw = left_w - 2 * margin
    imp_size = int(height_px * 0.07)
    while imp_size > int(height_px * 0.04):
        imp_font = _font(imp_size)
        imp_lines = _wrap_text(draw, importer_text, imp_font, max_tw)
        if int(imp_size * 1.25) * len(imp_lines) <= bottom_h - margin:
            break
        imp_size -= 1
    imp_lh = int(imp_size * 1.25)
    for i, line in enumerate(imp_lines):
        draw.text((margin, top_h + int(margin * 0.4) + i * imp_lh),
                  line, fill="black", font=imp_font)

    # ── STŘEDNÍ SEKCE – vertikální model ─────────────────────────
    vert_font_size = int(height_px * 0.16)
    vert_font = _font(vert_font_size, bold=True)
    vert_text = model
    # Zkrátit pokud se nevejde
    while vert_font_size > int(height_px * 0.08):
        vert_font = _font(vert_font_size, bold=True)
        tw = draw.textlength(vert_text, font=vert_font)
        if tw <= height_px - 2 * margin:
            break
        vert_font_size -= 1

    # Nakresli text do temp obrázku a rotuj 90°
    tw = int(draw.textlength(vert_text, font=vert_font))
    th = int(vert_font_size * 1.2)
    tmp = Image.new("RGB", (tw + 4, th + 4), "white")
    ImageDraw.Draw(tmp).text((2, 2), vert_text, fill="black", font=vert_font)
    tmp = tmp.rotate(90, expand=True)  # rotace = čtení zdola nahoru
    paste_x = left_w + (mid_w - tmp.width) // 2
    paste_y = (height_px - tmp.height) // 2
    img.paste(tmp, (paste_x, paste_y))

    # Svislá čára jako oddělovač (vlevo od střední sekce)
    draw.line([(left_w, margin), (left_w, height_px - margin)], fill="#cccccc", width=1)

    # ── PRAVÁ SEKCE – model + typ + (kruh pokud je barva) ────────
    r_margin = int(right_w * 0.06)
    rx = right_x + r_margin
    rw = right_w - 2 * r_margin

    # Spočítej výšky všech prvků
    mod_size = int(height_px * 0.22)
    while mod_size > int(height_px * 0.10):
        f = _font(mod_size, bold=True)
        if draw.textlength(model, font=f) <= rw:
            break
        mod_size -= 1
    mod_font = _font(mod_size, bold=True)
    mod_h    = int(mod_size * 1.2)

    typ_size = int(height_px * 0.13)
    while typ_size > int(height_px * 0.07):
        f = _font(typ_size)
        typ_lines = _wrap_text(draw, type_raw, f, rw)
        if len(typ_lines) <= 2:
            break
        typ_size -= 1
    typ_font  = _font(typ_size)
    typ_lh    = int(typ_size * 1.2)
    typ_lines = typ_lines[:2]

    circle_r = int(height_px * 0.10) if color else 0
    circle_h = circle_r * 2 + int(height_px * 0.03) if color else 0

    gap = int(height_px * 0.04)
    total_h = mod_h + gap + len(typ_lines) * typ_lh + (gap + circle_h if color else 0)
    cy = (height_px - total_h) // 2

    # Model
    draw.text((rx, cy), model, fill="black", font=mod_font)
    cy += mod_h + gap

    # Typ
    for line in typ_lines:
        draw.text((rx, cy), line, fill="black", font=typ_font)
        cy += typ_lh

    # Kruh (jen pokud má bílý/černý)
    if color:
        cy += gap
        lw_c = max(2, int(height_px * 0.022))
        if color == "black":
            draw.ellipse([rx, cy, rx + circle_r * 2, cy + circle_r * 2],
                         fill="black", outline="black")
        else:
            draw.ellipse([rx, cy, rx + circle_r * 2, cy + circle_r * 2],
                         fill="white", outline="black", width=lw_c)


def _calc_min_length_mm(code, name, importer_text, height_px, ppm, min_mm=38, max_mm=62):
    """Najde nejkratší délku (v mm) kde se obsah malého štítku vejde."""
    from PIL import Image as _Img, ImageDraw as _ID
    for mm in range(min_mm, max_mm + 1):
        w = int(mm * ppm)
        margin = int(height_px * 0.05)
        top_h = int(height_px * 0.62)
        bottom_h = height_px - top_h
        icon_size = int((top_h - 2 * margin) * 0.45)
        after_icon = margin + icon_size + int(height_px * 0.06)

        # Čárový kód rotovaný 90° – šířka = výška originálního * ratio
        import barcode as _bc
        from barcode.writer import ImageWriter
        bc_raw = _bc.get("code128", str(code), writer=ImageWriter())
        bc_img = bc_raw.render({"module_height": 8.0, "font_size": 0,
                                "text_distance": 1, "quiet_zone": 1, "write_text": False})
        bc_img_rot = bc_img.rotate(90, expand=True)
        bc_avail_h = top_h - 2 * margin
        bc_ratio   = bc_avail_h / bc_img_rot.height
        bc_col_w   = int(bc_img_rot.width * bc_ratio)  # šířka rotovaného kódu

        text_area_w = int((w - after_icon - margin) * 0.52)
        bc_space = w - after_icon - text_area_w - int(height_px * 0.06) - margin
        if bc_space < bc_col_w:
            continue

        # Importer text – musí se vejít do bottom_h
        tmp = _Img.new("RGB", (w, height_px), "white")
        d = _ID.Draw(tmp)
        fs = int(height_px * 0.075)
        while fs > int(height_px * 0.04):
            f = _font(fs)
            lines = _wrap_text(d, importer_text, f, w - 2 * margin)
            if int(fs * 1.25) * len(lines) <= bottom_h - margin:
                break
            fs -= 1
        else:
            continue  # importer se nevejde ani při min fontu

        return mm
    return max_mm


def render_label_image(code, name, length_mm=125, importer_text=None, dpi_600=None, show_weee=True):
    """Vytvoří obrázek štítku – 29mm páska, délka length_mm. Vrací PIL Image (landscape)."""
    if importer_text is None:
        importer_text = DEFAULT_IMPORTER_TEXT
    if dpi_600 is None:
        dpi_600 = PRINT_DPI_600

    if dpi_600:
        height_px = LABEL_HEIGHT_PX_600
        ppm = PX_PER_MM_600
    else:
        height_px = LABEL_HEIGHT_PX
        ppm = PX_PER_MM

    width_px = int(length_mm * ppm)

    # Pro malé štítky fixní délka 50mm
    if length_mm <= 62 and not (is_display(name) and "|" in name):
        length_mm = 50
        width_px = int(length_mm * ppm)

    img = Image.new("RGB", (width_px, height_px), "white")

    if is_display(name) and "|" in name:
        _render_display_label(code, name, height_px, width_px, importer_text, img)
        return img

    draw = ImageDraw.Draw(img)

    margin = int(height_px * 0.05)

    # Štítek je rozdělen na horní pásmo (ikona, čárový kód, kód, název)
    # a dolní pásmo (text o dovozci) – aby se nepřekrývaly.
    top_h = int(height_px * 0.62)
    bottom_h = height_px - top_h

    # Ikona – menší (45% výšky místo 100%)
    icon_size = int((top_h - 2 * margin) * 0.45)
    icon_y = margin + ((top_h - 2 * margin) - icon_size) // 2
    if show_weee:
        _draw_weee_icon(draw, margin, icon_y, icon_size, _img_ref=img)

    after_icon = margin + icon_size + int(height_px * 0.06)
    available_name_h = top_h - 2 * margin
    name = name or ""

    def _fit_name(text, bold, max_w, max_h, max_lines, start_size):
        size = start_size
        while size > int(height_px * 0.07):
            f = _font(size, bold=bold)
            lines = _wrap_text(draw, text, f, max_w)
            line_h = int(size * 1.15)
            if len(lines) <= max_lines and line_h * min(len(lines), max_lines) <= max_h:
                return f, lines
            size -= 1
        return _font(size, bold=bold), _wrap_text(draw, text, _font(size, bold=bold), max_w)[:max_lines]

    # ── Text (model + popis) hned za ikonou ──────────────────────
    text_area_w = int((width_px - after_icon - margin) * 0.52)
    name_x = after_icon

    def _cx(line, font, area_x, area_w):
        tw = int(draw.textlength(line, font=font))
        return area_x + max(0, (area_w - tw) // 2)

    if "|" in name:
        desc, device = [p.strip() for p in name.split("|", 1)]
        dev_font, dev_lines = _fit_name(device, True, text_area_w, int(available_name_h * 0.5), 2, int(height_px * 0.16))
        dev_lh = int(dev_font.size * 1.15)
        used_h = len(dev_lines) * dev_lh
        for i, line in enumerate(dev_lines):
            draw.text((_cx(line, dev_font, name_x, text_area_w), margin + i * dev_lh), line, fill="black", font=dev_font)
        desc_start_y = margin + used_h + int(height_px * 0.02)
        desc_avail_h = top_h - desc_start_y - margin
        desc_font, desc_lines = _fit_name(desc, False, text_area_w, desc_avail_h, 3, int(height_px * 0.13))
        desc_lh = int(desc_font.size * 1.15)
        for i, line in enumerate(desc_lines):
            draw.text((_cx(line, desc_font, name_x, text_area_w), desc_start_y + i * desc_lh), line, fill="black", font=desc_font)
    else:
        name_font, name_lines = _fit_name(name, True, text_area_w, available_name_h, 4, int(height_px * 0.16))
        name_lh = int(name_font.size * 1.15)
        for i, line in enumerate(name_lines):
            draw.text((_cx(line, name_font, name_x, text_area_w), margin + i * name_lh), line, fill="black", font=name_font)

    # ── Čárový kód vpravo – rotovaný 90° (úspora místa) ─────────
    import barcode
    from barcode.writer import ImageWriter
    bc = barcode.get("code128", str(code), writer=ImageWriter())
    bc_img = bc.render({"module_height": 22.0, "font_size": 0, "text_distance": 1,
                        "quiet_zone": 1, "write_text": False})
    # Rotuj 90° – barcode se stane sloupeček
    bc_img = bc_img.rotate(90, expand=True)
    # Škáluj na výšku dostupné oblasti
    code_font_size = int(height_px * 0.09)
    code_row_h = int(code_font_size * 1.3)
    bc_avail_h = top_h - 2 * margin - code_row_h
    bc_ratio   = bc_avail_h / bc_img.height
    bc_h_scaled = bc_avail_h
    bc_w_scaled = int(bc_img.width * bc_ratio)
    bc_img = bc_img.resize((bc_w_scaled, bc_h_scaled))

    # Kód pod čárovým kódem (rotovaný text)
    code_font = _font(int(height_px * 0.09))
    code_tw   = int(draw.textlength(str(code), font=code_font))
    code_h    = int(height_px * 0.12)

    bc_x = after_icon + text_area_w + int(height_px * 0.06)
    img.paste(bc_img, (bc_x, margin))

    # Kód produktu – pod čárovým kódem, centrovaný
    code_font = _font(code_font_size)
    code_tw = int(draw.textlength(str(code), font=code_font))
    code_y = margin + bc_h_scaled + int(height_px * 0.01)
    draw.text((bc_x + (bc_w_scaled - code_tw) // 2, code_y),
              str(code), fill="black", font=code_font)

    # Dolní pásmo – text o dovozci, font se postupně zmenší, pokud se nevejde
    max_text_width = width_px - 2 * margin
    available_h = bottom_h - margin
    font_size = int(height_px * 0.075)
    while font_size > int(height_px * 0.04):
        importer_font = _font(font_size)
        lines = _wrap_text(draw, importer_text, importer_font, max_text_width)
        line_h = int(font_size * 1.25)
        if line_h * len(lines) <= available_h:
            break
        font_size -= 1
    footer_y = top_h + int(margin * 0.5)
    for i, line in enumerate(lines):
        draw.text((margin, footer_y + i * line_h), line, fill="black", font=importer_font)

    return img


def find_printer():
    """Najde připojenou Brother QL tiskárnu přes USB. Vrátí identifikátor, nebo None."""
    # Přímé vyhledání přes pyusb (Brother QL-700: VID=0x04f9, PID=0x2042)
    try:
        import usb.core
        dev = usb.core.find(idVendor=0x04f9, idProduct=0x2042)
        if dev:
            return "usb://0x04f9:0x2042"
    except Exception as e:
        print(f"[label] pyusb hledání selhalo: {e}")
    # Fallback: discover
    try:
        from brother_ql.backends.helpers import discover
        devices = list(discover(backend_identifier="pyusb"))
        if devices:
            return devices[0]["identifier"]
    except Exception as e:
        print(f"[label] discover selhalo: {e}")
    return None


def print_label(image, copies=1, printer_identifier=None, rotate="90"):
    """Vytiskne obrázek štítku na Brother QL-700. Vrací (ok: bool, error: str|None)."""
    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster
    from brother_ql.backends.helpers import send

    if printer_identifier is None:
        printer_identifier = find_printer()
    if printer_identifier is None:
        return False, "Tiskárna nenalezena – zkontroluj USB připojení a že je zapnutá."

    qlr = BrotherQLRaster(PRINTER_MODEL)
    qlr.exception_on_warning = False

    try:
        instructions = convert(
            qlr=qlr,
            images=[image] * max(1, int(copies)),
            label=LABEL_SIZE_CODE,
            rotate=rotate,
            threshold=70.0,
            dither=True,
            compress=False,
            red=False,
            dpi_600=True,
            hq=True,
            cut=True,
        )
        send(instructions=instructions, printer_identifier=printer_identifier,
             backend_identifier="pyusb", blocking=True)
        return True, None
    except Exception as e:
        return False, str(e)
