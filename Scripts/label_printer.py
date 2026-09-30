# -*- coding: utf-8 -*-
"""Generování a tisk štítků na Brother QL-700 (29mm nekonečná páska, USB)."""

import os
import re
import json
import socket
import ssl
import unicodedata
import urllib.request
from PIL import Image, ImageDraw, ImageFont

PRINTER_MODEL = "QL-700"

# ── Hlášení na dálku ─────────────────────────────────────────────────────
# Každá chyba a každý tisk se zapíše do Supabase (tabulka stitky_udalosti),
# aby šly vidět bez přístupu k iMacu. Fire-and-forget: krátký timeout, nikdy
# nevyhodí výjimku a nezdrží tisk. Když tabulka/síť není, tiše se přeskočí.
_TELEM_URL = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/stitky_udalosti"
_TELEM_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwi"
              "cm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4")


def nahlas(typ, zprava, kod=None):
    """typ: 'chyba' | 'tisk'. zprava se ořízne na 2000 znaků."""
    try:
        body = json.dumps({
            "typ": typ, "kod": kod, "zprava": str(zprava)[:2000],
            "stroj": socket.gethostname().split(".")[0],
        }).encode("utf-8")
        headers = {"apikey": _TELEM_KEY, "Authorization": f"Bearer {_TELEM_KEY}",
                   "Content-Type": "application/json", "Prefer": "return=minimal"}
        req = urllib.request.Request(_TELEM_URL, data=body, method="POST", headers=headers)
        try:
            urllib.request.urlopen(req, timeout=4)
        except ssl.SSLError:
            # Big Sur: zastaralé CA certy → zopakuj bez ověření (TLS zůstává)
            urllib.request.urlopen(req, timeout=4, context=ssl._create_unverified_context())
    except Exception:
        pass


def _norm(name):
    """Normalizuje na NFC (skládaná diakritika) a lowercase. Nutné, protože
    Swift/macOS řetězce (název produktu předaný appkou) často přicházejí
    v NFD (rozložená diakritika – "í" jako 'i' + samostatná čárka), zatímco
    porovnávané literály v tomhle souboru jsou NFC. Bez normalizace substring
    testy typu "originální" in name tiše selžou, i když text vypadá stejně."""
    return unicodedata.normalize("NFC", name or "").lower()


_DISPLAY_KEYWORDS = ["displej", "display", "lcd", "oled", "screen"]
_DISPLAY_EXCLUDE  = ["pod displej", "pod display", "těsnění", "lepidlo", "sklíčko", "kabel k", "rámeček"]

def is_display(name):
    """Vrátí True pokud jde o displej (→ 125mm štítek)."""
    t = _norm(name)
    if any(ex in t for ex in _DISPLAY_EXCLUDE):
        return False
    return any(kw in t for kw in _DISPLAY_KEYWORDS)

def needs_serial_number(name):
    """AirPods sluchátka/nabíjecí pouzdra se trackují podle sériového čísla
    jednotky (párování/záruka) – vyžadují ruční vepsání SN před tiskem.
    Nechytá baterie do nich (Ampsentrix/Baterie …), špunty ani příslušenství."""
    n = _norm(name).strip()
    if "airpod" not in n:
        return False
    if not n.startswith("náhradní"):
        return False
    return "sluchátko" in n or "pouzdr" in n


def default_length(name):
    return 125 if is_display(name) else 62
LABEL_SIZE_CODE = "29"          # brother_ql kód pro 29mm nekonečnou pásku
LABEL_HEIGHT_PX = 306           # tisknutelná šířka pásky při 300 DPI (brother_ql spec pro "29")
LABEL_HEIGHT_PX_600 = 612       # totéž při 600 DPI
PX_PER_MM = 300 / 25.4          # 300 DPI – délka
PX_PER_MM_600 = 600 / 25.4      # 600 DPI – délka
PRINT_DPI_600 = True            # zapnout 600 DPI tisk

DEFAULT_IMPORTER_TEXT = (
    "Dovozce: MobileSentrix Europe B. V. Beursplein 37, 3011AA Rotterdam, Netherlands. "
    "Email: info@mobilesentrix.com Vyrobeno v Číně. Určeno pro profesionální instalaci."
)

APPLE_IMPORTER_TEXT = (
    "Dovozce: Apple Distribution International Ltd. Hollyhill Industrial Estate, "
    "Hollyhill, Cork T23 YK84, Ireland. Email: RegulatoryEU@group.apple.com "
    "Web: support.apple.com/self-service-repair"
)

DYSON_IMPORTER_TEXT = (
    "Dovozce: DYSON GMBH Lichtstr. 43e, 50825 Köln, Germany. "
    "Email: infoline@dyson.com Web: dyson.de"
)

ISWAP_IMPORTER_TEXT = (
    "Dovozce: iSwap.cz s.r.o. U Vokovické školy 299/4, 160 00 Praha. "
    "IČ: 14340101, DIČ: CZ14340101"
)

# Nářadí (šroubováky, pinzety, otvíráky, skalpely/čepelky, pistole, podložky…) = iSwap.cz.
# Lepicí pásky, lepidla a SIM šuplíky sem NEPATŘÍ – ty jsou MobileSentrix.
_TOOL_KEYWORDS = [
    "šroubovák", "nářadí", "otevírací", "otevírák", "otevíra", "skalpel", "pinzeta",
    "sání", "přísavk",
    "čistič", "izopropyl", "stěrka", "kartáč", "kladívko", "kleště", "žiletka",
    "trsátko", "iopener", "opener", "tavná pistole", "pistole na aplikaci",
    "rukavice", "brýle", "lupa", "mikroskop", "podložka", "štípací", "čepel",
    "břity", "páčidlo", "wowpad",
]


def classify_importer(name):
    """Podle názvu produktu určí, kdo je na štítku uveden jako dovozce.

    Priorita: Dyson > Apple (originální baterie / těsnění / AirPods) >
    iSwap.cz (ostatní originální díly + nářadí a spotřební materiál) >
    výchozí MobileSentrix.
    """
    n = _norm(name)

    if "dyson" in n:
        return DYSON_IMPORTER_TEXT

    # "originální baterie" i "originální Apple baterie" (slovo Apple mezi nimi).
    # AirPods = Apple, ale baterie DO AirPods (Ampsentrix apod.) ne – ty jsou
    # MobileSentrix, proto "baterie" z AirPods pravidla vyjmuta.
    is_airpods_part = "airpod" in n and "baterie" not in n
    if re.search(r"origin\w*\s+(?:apple\s+)?baterie", n) or "originální těsnění" in n or is_airpods_part:
        return APPLE_IMPORTER_TEXT

    # Originální kabely a nabíječky (MagSafe, USB-C, Watch) jsou výjimka
    # z "ostatní originální = iSwap" – ty jsou MobileSentrix.
    is_cable_or_charger = "kabel" in n or "nabíječk" in n
    if ("originální" in n and not is_cable_or_charger) or any(kw in n for kw in _TOOL_KEYWORDS):
        return ISWAP_IMPORTER_TEXT

    return DEFAULT_IMPORTER_TEXT


# Klíč dovozce (hodnota sloupce products.dovozce v Supabase) → text na štítek.
IMPORTER_BY_KEY = {
    "apple": APPLE_IMPORTER_TEXT,
    "iswap": ISWAP_IMPORTER_TEXT,
    "dyson": DYSON_IMPORTER_TEXT,
    "mobilesentrix": DEFAULT_IMPORTER_TEXT,
}
_KEY_BY_IMPORTER_TEXT = {text: key for key, text in IMPORTER_BY_KEY.items()}


def importer_key_for(name):
    """Klíč dovozce ("apple"/"iswap"/"dyson"/"mobilesentrix") podle názvu –
    stejná logika jako classify_importer, jen vrací klíč místo textu.
    Používá se pro naplnění sloupce products.dovozce v DB."""
    return _KEY_BY_IMPORTER_TEXT[classify_importer(name)]


def importer_text_for(name, key=None):
    """Text dovozce na štítek. Platný klíč (viz IMPORTER_BY_KEY) má přednost;
    prázdný/None/neznámý klíč → rozhodne se podle názvu (classify_importer).
    Nikdy nevyhazuje – neznámá hodnota z DB nesmí shodit tisk."""
    if key:
        text = IMPORTER_BY_KEY.get(str(key).strip().lower())
        if text:
            return text
    return classify_importer(name)


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


def _parse_display_name(name):
    """Rozdělí 'LCD displej černý PREMIUM | iPhone 6S' na součásti."""
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

    # Typ bez barvy (pro levou sekci)
    color_words = ["černý", "černá", "bílý", "bílá", "cerny", "cerna", "bily", "bila", "black", "white"]
    type_no_color = type_raw
    for w in color_words:
        type_no_color = type_no_color.replace(w, "").replace("  ", " ").strip()

    # Typ bez varianty (pro pravý střední řádek)
    type_no_variant = type_raw
    if variant:
        type_no_variant = type_raw.replace(variant, "").replace("  ", " ").strip()

    # Typ bez barvy a bez varianty
    type_base = type_no_color
    if variant:
        type_base = type_base.replace(variant, "").replace("  ", " ").strip()

    # Zkrácený model pro střední sekci (např. "iPhone 6S" → "iPh 6S")
    words = model.split()
    if words:
        abbr = words[0][:3] + (" " + " ".join(words[1:]) if len(words) > 1 else "")
    else:
        abbr = model

    return model, type_raw, color, variant, type_no_color, type_base, abbr


def _render_display_label(code, name, height_px, width_px, importer_text, img):
    """
    Layout podle .lbx šablony:
      LEVÁ sekce  (~43%): typ nahoře | WEEE + čárový kód | dovozce dole
      STŘEDNÍ sekce (~8%): model rotovaný 90° + barevný kruh
      PRAVÁ sekce (~49%): velký model + typ + (kvalita)
    """
    draw  = ImageDraw.Draw(img)
    margin = int(height_px * 0.05)

    model, type_raw, color, variant, type_no_color, type_base, abbr = _parse_display_name(name)

    # ── Proporce sekcí (odpovídá .lbx: 354.7pt total) ───────────
    left_w  = int(width_px * 0.43)
    mid_w   = int(width_px * 0.08)
    right_x = left_w + mid_w
    right_w = width_px - right_x

    top_h    = int(height_px * 0.62)
    bottom_h = height_px - top_h

    # ── LEVÁ SEKCE ───────────────────────────────────────────────
    # Typ displeje nahoře (tučně)
    type_area_w = left_w - 2 * margin
    typ_size = int(height_px * 0.13)
    while typ_size > int(height_px * 0.07):
        f = _font(typ_size, bold=True)
        typ_lines = _wrap_text(draw, type_no_color, f, type_area_w)
        if len(typ_lines) <= 2:
            break
        typ_size -= 1
    typ_font = _font(typ_size, bold=True)
    typ_lh   = int(typ_size * 1.2)
    for i, line in enumerate(typ_lines[:2]):
        draw.text((margin, margin + i * typ_lh), line, fill="black", font=typ_font)
    typ_end_y = margin + len(typ_lines[:2]) * typ_lh + int(height_px * 0.02)

    # WEEE ikona vlevo (střední část výšky)
    icon_avail_h = top_h - typ_end_y - margin
    icon_size    = int(icon_avail_h * 0.85)
    icon_y       = typ_end_y + (icon_avail_h - icon_size) // 2
    _draw_weee_icon(draw, margin, icon_y, icon_size, _img_ref=img)

    # Čárový kód napravo od ikony
    import barcode as bc_mod
    from barcode.writer import ImageWriter
    bc = bc_mod.get("code128", str(code), writer=ImageWriter())
    bc_img = bc.render({"module_height": 3.0, "font_size": 0, "text_distance": 1,
                        "quiet_zone": 0, "write_text": False})
    bc_x      = margin + icon_size + int(height_px * 0.04)
    bc_avail_w = left_w - bc_x - margin
    bc_avail_h = icon_avail_h - int(height_px * 0.12)
    bc_ratio_w = bc_avail_w / bc_img.width
    bc_w       = bc_avail_w
    bc_h       = int(bc_img.height * bc_ratio_w)
    if bc_h > bc_avail_h:
        bc_h = bc_avail_h
        bc_w = int(bc_img.width * bc_h / bc_img.height)
    bc_img = bc_img.resize((bc_w, bc_h))
    bc_y   = typ_end_y + (icon_avail_h - bc_h - int(height_px * 0.11)) // 2
    img.paste(bc_img, (bc_x, bc_y))

    # Kód pod čárovým kódem
    code_font = _font(int(height_px * 0.09))
    code_tw   = int(draw.textlength(str(code), font=code_font))
    draw.text((bc_x + (bc_w - code_tw) // 2, bc_y + bc_h + int(height_px * 0.01)),
              str(code), fill="black", font=code_font)

    # Dovozce dole (levá sekce)
    imp_size = int(height_px * 0.07)
    while imp_size > int(height_px * 0.04):
        imp_font  = _font(imp_size)
        imp_lines = _wrap_text(draw, importer_text, imp_font, type_area_w)
        if int(imp_size * 1.2) * len(imp_lines) <= bottom_h - margin:
            break
        imp_size -= 1
    imp_lh = int(imp_size * 1.2)
    for i, line in enumerate(imp_lines):
        draw.text((margin, top_h + int(margin * 0.3) + i * imp_lh),
                  line, fill="black", font=imp_font)

    # ── STŘEDNÍ SEKCE – model rotovaný 90° + barevný kruh ────────
    draw.line([(left_w, margin), (left_w, height_px - margin)], fill="#cccccc", width=1)

    vert_size = int(height_px * 0.17)
    while vert_size > int(height_px * 0.08):
        vf = _font(vert_size, bold=True)
        if draw.textlength(abbr, font=vf) <= height_px - 2 * margin:
            break
        vert_size -= 1
    vf = _font(vert_size, bold=True)
    tw = int(draw.textlength(abbr, font=vf))
    th = int(vert_size * 1.2)
    tmp = Image.new("RGB", (tw + 4, th + 4), "white")
    ImageDraw.Draw(tmp).text((2, 2), abbr, fill="black", font=vf)
    tmp = tmp.rotate(90, expand=True)

    circle_r = int(height_px * 0.09) if color else 0
    circle_gap = int(height_px * 0.03) if color else 0
    total_mid_h = tmp.height + (circle_gap + circle_r * 2 if color else 0)
    paste_y = (height_px - total_mid_h) // 2
    paste_x = left_w + (mid_w - tmp.width) // 2
    img.paste(tmp, (paste_x, paste_y))

    if color:
        cy = paste_y + tmp.height + circle_gap
        cx = left_w + (mid_w - circle_r * 2) // 2
        lw_c = max(2, int(height_px * 0.022))
        if color == "black":
            draw.ellipse([cx, cy, cx + circle_r * 2, cy + circle_r * 2],
                         fill="black", outline="black")
        else:
            draw.ellipse([cx, cy, cx + circle_r * 2, cy + circle_r * 2],
                         fill="white", outline="black", width=lw_c)

    # ── PRAVÁ SEKCE – velký model + typ + kvalita ────────────────
    draw.line([(right_x, margin), (right_x, height_px - margin)], fill="#cccccc", width=1)

    r_margin = int(right_w * 0.05)
    rx = right_x + r_margin
    rw = right_w - 2 * r_margin

    # Model (velký, tučný)
    mod_size = int(height_px * 0.25)
    while mod_size > int(height_px * 0.10):
        f = _font(mod_size, bold=True)
        if draw.textlength(model, font=f) <= rw:
            break
        mod_size -= 1
    mod_font = _font(mod_size, bold=True)
    mod_h    = int(mod_size * 1.2)

    # Typ bez varianty (střední řádek)
    type_mid = type_base  # bez barvy i varianty
    t_size = int(height_px * 0.15)
    while t_size > int(height_px * 0.07):
        f = _font(t_size)
        t_lines = _wrap_text(draw, type_mid, f, rw)
        if len(t_lines) <= 1:
            break
        t_size -= 1
    t_font = _font(t_size)
    t_lh   = int(t_size * 1.2)

    # Varianta (velká, tučná) – jen pokud existuje
    var_size = int(height_px * 0.22)
    while var_size > int(height_px * 0.10) and variant:
        f = _font(var_size, bold=True)
        if draw.textlength(variant, font=f) <= rw:
            break
        var_size -= 1
    var_font = _font(var_size, bold=True)
    var_h    = int(var_size * 1.2) if variant else 0

    gap = int(height_px * 0.03)
    total_h = mod_h + gap + t_lh + (gap + var_h if variant else 0)
    cy = (height_px - total_h) // 2

    draw.text((rx, cy), model, fill="black", font=mod_font)
    cy += mod_h + gap
    for line in t_lines[:1]:
        draw.text((rx, cy), line, fill="black", font=t_font)
        cy += t_lh
    if variant:
        cy += gap
        draw.text((rx, cy), variant, fill="black", font=var_font)


def render_label_image(code, name, length_mm=125, importer_text=None, dpi_600=None, show_weee=True):
    """Vytvoří obrázek štítku – 29mm páska, délka length_mm. Vrací PIL Image (landscape)."""
    if importer_text is None:
        importer_text = classify_importer(name)
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
    # Horní pásmo = text+ikona, střední = čárový kód, dolní = dovozce
    text_h = int(height_px * 0.30)
    bc_h_area = int(height_px * 0.40)
    bottom_h = height_px - text_h - bc_h_area

    # Ikona – menší (45% výšky textu)
    icon_size = int((text_h - 2 * margin) * 0.8)
    icon_y = margin + ((text_h - 2 * margin) - icon_size) // 2
    if show_weee:
        _draw_weee_icon(draw, margin, icon_y, icon_size, _img_ref=img)

    after_icon = margin + icon_size + int(height_px * 0.06)
    available_name_h = text_h - 2 * margin
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
    text_area_w = width_px - after_icon - margin
    name_x = after_icon

    def _cx(line, font, area_x, area_w):
        tw = int(draw.textlength(line, font=font))
        return area_x + max(0, (area_w - tw) // 2)

    if "|" in name:
        desc, device = [p.strip() for p in name.split("|", 1)]
        dev_font, dev_lines = _fit_name(device, True, text_area_w, int(available_name_h * 0.55), 2, int(height_px * 0.24))
        dev_lh = int(dev_font.size * 1.15)
        used_h = len(dev_lines) * dev_lh
        for i, line in enumerate(dev_lines):
            draw.text((_cx(line, dev_font, name_x, text_area_w), margin + i * dev_lh), line, fill="black", font=dev_font)
        desc_start_y = margin + used_h + int(height_px * 0.02)
        desc_avail_h = text_h - desc_start_y - margin
        desc_font, desc_lines = _fit_name(desc, False, text_area_w, desc_avail_h, 3, int(height_px * 0.19))
        desc_lh = int(desc_font.size * 1.15)
        for i, line in enumerate(desc_lines):
            draw.text((_cx(line, desc_font, name_x, text_area_w), desc_start_y + i * desc_lh), line, fill="black", font=desc_font)
    else:
        name_font, name_lines = _fit_name(name, True, text_area_w, available_name_h, 4, int(height_px * 0.24))
        name_lh = int(name_font.size * 1.15)
        for i, line in enumerate(name_lines):
            draw.text((_cx(line, name_font, name_x, text_area_w), margin + i * name_lh), line, fill="black", font=name_font)

    # ── Čárový kód – pod textem, přes celou šířku štítku. Text s kódem/SN
    # jede VEDLE čárového kódu (ne pod ním), aby měl kód celou výšku bc_h_area
    # k dispozici – jinak se při málo místě zmenšuje i šířka a kód je nečitelný.
    import barcode
    from barcode.writer import ImageWriter
    bc = barcode.get("code128", str(code), writer=ImageWriter())

    code_font_size = int(height_px * 0.075)
    code_font = _font(code_font_size)
    code_text = str(code)
    code_tw = int(draw.textlength(code_text, font=code_font))
    text_gap = int(width_px * 0.02)

    bc_avail_h = bc_h_area - int(margin * 1.2)
    bc_avail_w = width_px - 2 * margin - code_tw - text_gap

    bc_img = bc.render({"module_height": 3.0, "font_size": 0, "text_distance": 1,
                        "quiet_zone": 0, "write_text": False})
    # Škáluj na celou dostupnou šířku, pak ořízni výšku pokud přesahuje
    bc_ratio_w = bc_avail_w / bc_img.width
    bc_w_scaled = bc_avail_w
    bc_h_scaled = int(bc_img.height * bc_ratio_w)
    if bc_h_scaled > bc_avail_h:
        bc_h_scaled = bc_avail_h
        bc_w_scaled = int(bc_img.width * bc_avail_h / bc_img.height)
    bc_img = bc_img.resize((bc_w_scaled, bc_h_scaled))

    bc_x = margin
    bc_y = text_h + (bc_h_area - bc_h_scaled) // 2
    img.paste(bc_img, (bc_x, bc_y))

    # Kód produktu (nebo sériové číslo) vedle čárového kódu, svisle na střed
    code_text_h = int(code_font_size * 1.15)
    code_text_y = text_h + (bc_h_area - code_text_h) // 2
    draw.text((bc_x + bc_w_scaled + text_gap, code_text_y), code_text, fill="black", font=code_font)

    # Dolní pásmo – text o dovozci
    max_text_width = width_px - 2 * margin
    available_h = bottom_h - margin
    footer_top = text_h + bc_h_area  # y offset pro dovozce
    font_size = int(height_px * 0.075)
    while font_size > int(height_px * 0.04):
        importer_font = _font(font_size)
        lines = _wrap_text(draw, importer_text, importer_font, max_text_width)
        line_h = int(font_size * 1.25)
        if line_h * len(lines) <= available_h:
            break
        font_size -= 1
    footer_y = footer_top + int(margin * 0.5)
    for i, line in enumerate(lines):
        draw.text((margin, footer_y + i * line_h), line, fill="black", font=importer_font)

    return img


def render_serial_label_image(serial_number, length_mm=50, dpi_600=None):
    """Samostatný štítek jen se sériovým číslem (barcode + text), bez dovozce
    ani názvu produktu. Tiskne se navíc vedle běžného produktového štítku
    u AirPods sluchátek/pouzder (viz needs_serial_number)."""
    if dpi_600 is None:
        dpi_600 = PRINT_DPI_600

    if dpi_600:
        height_px = LABEL_HEIGHT_PX_600
        ppm = PX_PER_MM_600
    else:
        height_px = LABEL_HEIGHT_PX
        ppm = PX_PER_MM
    width_px = int(length_mm * ppm)

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)
    margin = int(height_px * 0.08)

    import barcode
    from barcode.writer import ImageWriter
    bc = barcode.get("code128", str(serial_number), writer=ImageWriter())

    label_font_size = int(height_px * 0.14)
    label_font = _font(label_font_size, bold=True)
    label_text = "SN"
    label_h = int(label_font_size * 1.2)
    draw.text((margin, margin), label_text, fill="black", font=label_font)

    sn_font_size = int(height_px * 0.16)
    sn_font = _font(sn_font_size, bold=True)
    sn_text = str(serial_number)
    sn_tw = int(draw.textlength(sn_text, font=sn_font))
    sn_h = int(sn_font_size * 1.2)
    sn_y = height_px - margin - sn_h
    draw.text(((width_px - sn_tw) // 2, sn_y), sn_text, fill="black", font=sn_font)

    bc_avail_w = width_px - 2 * margin
    bc_avail_h = sn_y - (margin + label_h) - int(margin * 0.5)

    bc_img = bc.render({"module_height": 3.0, "font_size": 0, "text_distance": 1,
                        "quiet_zone": 0, "write_text": False})
    bc_ratio_w = bc_avail_w / bc_img.width
    bc_w_scaled = bc_avail_w
    bc_h_scaled = int(bc_img.height * bc_ratio_w)
    if bc_h_scaled > bc_avail_h:
        bc_h_scaled = bc_avail_h
        bc_w_scaled = int(bc_img.width * bc_avail_h / bc_img.height)
    bc_img = bc_img.resize((bc_w_scaled, bc_h_scaled))

    bc_x = (width_px - bc_w_scaled) // 2
    bc_y = margin + label_h + (bc_avail_h - bc_h_scaled) // 2
    img.paste(bc_img, (bc_x, bc_y))

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


def print_labels(images, copies=1, printer_identifier=None, rotate="90", dpi_600=None):
    """Vytiskne sadu obrázků (jeden tiskový job) na Brother QL-700, každý
    'copies'-krát za sebou. Vrací (ok: bool, error: str|None).

    Používá se pro AirPods se sériovým číslem: images = [produktový_štítek,
    sn_štítek] – vyjedou dva fyzické štítky v jedné dávce.

    dpi_600 musí odpovídat DPI, na kterém byly obrázky vyrenderovány; None =
    výchozí (PRINT_DPI_600). 300 DPI tiskne zhruba 2× rychleji než 600 DPI.
    """
    # brother_ql sype na stderr neškodná varování ("devicedependent is deprecated",
    # "Trying to switch the operating mode…" – to druhé QL-700 hlásí při KAŽDÉM
    # tisku). Appka zobrazuje jen první 2 řádky stderr, takže tahle varování
    # zakrývala skutečnou chybu. Proto je potlačíme.
    import logging, warnings, time
    warnings.filterwarnings("ignore")
    logging.getLogger("brother_ql").setLevel(logging.ERROR)

    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster
    from brother_ql.backends.helpers import send

    if dpi_600 is None:
        dpi_600 = PRINT_DPI_600

    if printer_identifier is None:
        printer_identifier = find_printer()
    if printer_identifier is None:
        return False, "Tiskárna nenalezena – zkontroluj USB připojení a že je zapnutá."

    qlr = BrotherQLRaster(PRINTER_MODEL)
    qlr.exception_on_warning = False

    copies = max(1, int(copies))
    all_images = []
    for _ in range(copies):
        all_images.extend(images)

    try:
        instructions = convert(
            qlr=qlr,
            images=all_images,
            label=LABEL_SIZE_CODE,
            rotate=rotate,
            threshold=70.0,
            dither=True,
            compress=True,      # bezztrátová komprese → rychlejší USB přenos
            red=False,
            dpi_600=dpi_600,    # musí odpovídat DPI obrázků
            hq=True,
            cut=True,
        )
    except Exception as e:
        return False, f"Chyba při přípravě tisku: {e}"

    # USB spojení s QL-700 občas uprostřed dávky vypadne (stalo se při 7 kopiích).
    # Druhý pokus si tiskárnu znovu najde – když se jen na chvíli odpojila,
    # projde; když je opravdu pryč, vrátíme čitelnou chybu.
    last_err = None
    for attempt in (1, 2):
        try:
            send(instructions=instructions, printer_identifier=printer_identifier,
                 backend_identifier="pyusb", blocking=True)
            return True, None
        except Exception as e:
            last_err = e
            if attempt == 1:
                time.sleep(2)
                printer_identifier = find_printer() or printer_identifier
    return False, f"Tisk selhal (2 pokusy): {last_err}"


def print_label(image, copies=1, printer_identifier=None, rotate="90", dpi_600=None):
    """Vytiskne jeden obrázek štítku 'copies'-krát. Tenký wrapper nad print_labels
    pro zpětnou kompatibilitu (scan_print.py apod.)."""
    return print_labels([image], copies=copies, printer_identifier=printer_identifier,
                         rotate=rotate, dpi_600=dpi_600)
