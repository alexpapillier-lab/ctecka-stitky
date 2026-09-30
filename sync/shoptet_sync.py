#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Denní synchronizace Shoptet → Supabase.

1. stáhne export produktů ze Shoptetu (URL v env SHOPTET_EXPORT_URL – obsahuje
   tajný hash, proto je v GitHub Secrets, ne v repu). Umí:
   - kompletní XML export (productsComplete.xml, SHOPITEM/VARIANT) – MÁ EAN i
     PART_NUMBER, preferovaný zdroj
   - XLSX/XLS export ze šablony (pandas) – záložně
2. najde produkty, které v Supabase ještě nejsou (podle `code`)
3. vloží je: name, pair_code, part_number (je-li), ean
   – EAN se vezme ze Shoptetu jen pokud tam je a není v DB obsazený;
     jinak se vygeneruje EAN-13 s prefixem 859 (CZ) – Shoptet totiž EAN
     u nových produktů buď nemá, nebo je zdědil z kopírovaného produktu
4. vytvoří XLSX (code, pairCode, ean) pro import zpět do Shoptetu – jen pro
   produkty, kterým se EAN generoval (u převzatého EANu není co importovat)
5. pošle ho mailem (SMTP_* + MAIL_TO v env); bez SMTP jen uloží soubor

Bez nových produktů nic nevkládá, nic neposílá.
Spouští se z .github/workflows/shoptet-sync.yml; lokálně: --nanecisto
"""
import io, os, re, sys, json, random, smtplib, ssl, urllib.request
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from datetime import date

SUPABASE = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/products"
ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwi"
            "cm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4")
H = {"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}", "Content-Type": "application/json"}

NANECISTO = "--nanecisto" in sys.argv


def log(msg):
    print(msg, flush=True)


# ── Supabase ─────────────────────────────────────────────────────────────
def db_all():
    out, off = [], 0
    while True:
        req = urllib.request.Request(f"{SUPABASE}?select=code,ean&limit=1000&offset={off}", headers=H)
        b = json.loads(urllib.request.urlopen(req, timeout=30).read())
        out += b
        if len(b) < 1000:
            return out
        off += 1000


def db_insert(rec):
    req = urllib.request.Request(SUPABASE, data=json.dumps(rec, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={**H, "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30)


# ── Shoptet export → jednotný seznam řádků ───────────────────────────────
def clean(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "nan", "None"):
        return None
    if s.endswith(".0") and s[:-2].isdigit():   # pandas občas EAN načte jako float
        s = s[:-2]
    return s


def _xml_rows(raw):
    """Kompletní XML: každá prodejní jednotka = SHOPITEM bez variant, nebo každá VARIANT.
    Varianta dědí NAME a PART_NUMBER z položky; pairCode = CODE nadřazené položky."""
    root = ET.fromstring(raw)

    def t(e, tag):
        x = e.find(tag)
        return (x.text or "").strip() if x is not None and x.text else ""

    # Kompletní XML nemá PAIR_CODE ani CODE u nadřazené položky s variantami
    # (to číslo je interní párování Shoptetu, které je jen v CSV/XLSX exportu),
    # takže pairCode zůstává prázdný – import EANu do Shoptetu páruje podle code.
    # PART_NUMBER je na položce (varianty ho dědí); EXTERNAL_CODE je záloha
    # (Ampsentrix baterie mají kód dodavatele právě tam).
    rows = []
    for it in root.iter("SHOPITEM"):
        name = t(it, "NAME")
        pn_item = t(it, "PART_NUMBER") or t(it, "EXTERNAL_CODE")
        variants = it.findall("./VARIANTS/VARIANT")
        if variants:
            for v in variants:
                rows.append({"code": t(v, "CODE"), "pairCode": "", "name": name,
                             "ean": t(v, "EAN"), "partNumber": t(v, "PART_NUMBER") or pn_item})
        else:
            rows.append({"code": t(it, "CODE"), "pairCode": "", "name": name,
                         "ean": t(it, "EAN"), "partNumber": pn_item})
    return rows, True, True


def _excel_rows(raw):
    import pandas as pd
    df = pd.read_excel(io.BytesIO(raw), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    if "code" not in df.columns or "name" not in df.columns:
        raise SystemExit(f"export nemá sloupce code/name – má: {df.columns.tolist()[:10]}")
    ma_ean = "ean" in df.columns
    ma_pn = "partNumber" in df.columns or "externalCode" in df.columns
    rows = []
    for _, r in df.iterrows():
        rows.append({"code": clean(r.get("code")) or "", "pairCode": clean(r.get("pairCode")) or "",
                     "name": clean(r.get("name")) or "", "ean": clean(r.get("ean")) or "" if ma_ean else "",
                     "partNumber": (clean(r.get("partNumber")) or clean(r.get("externalCode")) or "") if ma_pn else ""})
    return rows, ma_ean, ma_pn


def stahni_export(url):
    raw = urllib.request.urlopen(url, timeout=300).read()
    head = raw.lstrip()[:200]
    rows, ma_ean, ma_pn = _xml_rows(raw) if (head.startswith(b"<?xml") or b"<SHOP" in head) else _excel_rows(raw)
    seen, out = set(), []
    for r in rows:
        r["code"] = (r["code"] or "").strip()
        if r["code"] and r["code"] not in seen:
            seen.add(r["code"]); out.append(r)
    return out, ma_ean, ma_pn


def part_number(raw):
    """Shoptet ořezává pole na 32 znaků; občas je tam URL nebo useknutý fragment."""
    raw = clean(raw)
    if not raw or raw.lower().startswith("http"):
        return None
    good = []
    for tok in re.split(r"[,\s]+", raw):
        tok = tok.strip()
        if len(tok) >= 6 and re.fullmatch(r"(?i)[a-z0-9][a-z0-9\-]{4,}", tok) and tok not in good:
            good.append(tok)
    return " ".join(good) or None


# ── EAN ───────────────────────────────────────────────────────────────────
def ean13_859(obsazene):
    while True:
        d = [8, 5, 9] + [random.randint(0, 9) for _ in range(9)]
        s = sum(d[i] for i in range(0, 12, 2)) + 3 * sum(d[i] for i in range(1, 12, 2))
        d.append((10 - s % 10) % 10)
        e = "".join(map(str, d))
        if e not in obsazene:
            obsazene.add(e)
            return e


# ── XLSX pro Shoptet ──────────────────────────────────────────────────────
def xlsx_import(rows):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "import"
    ws.append(["code", "pairCode", "ean"])
    for r in rows:
        ws.append([r["code"], r.get("pair_code") or "", r["ean"]])
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


# ── E-mail ────────────────────────────────────────────────────────────────
def posli_mail(vsechny, k_importu, xlsx_bytes, nazev):
    host, port, user, pw, to = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))
    if not all([host, port, user, pw, to]):
        log("SMTP není nastaveno (SMTP_HOST/PORT/USER/PASS, MAIL_TO) – mail neposílám")
        return False
    m = EmailMessage()
    m["From"] = user
    m["To"] = to
    m["Subject"] = f"Štítky: {len(vsechny)} nových produktů ({date.today():%d.%m.%Y})"
    radky = "\n".join(f"  {r['code']:<12} {r['ean']}  {'(EAN ze Shoptetu)' if r.get('ean_ze_shoptetu') else '(nový EAN)':<19} {r['name'][:55]}"
                      for r in vsechny)
    text = ("Ahoj,\n\nv Shoptetu přibyly nové produkty, přidal jsem je do databáze štítkovačky:\n\n"
            f"{radky}\n\n")
    if k_importu:
        text += (f"{len(k_importu)} z nich nemělo v Shoptetu použitelný EAN, tak jsem ho vygeneroval.\n"
                 "V příloze je XLSX (code, pairCode, ean) k importu do Shoptetu – stejný formát jako dosud.\n\n")
    else:
        text += "Všechny měly v Shoptetu platný EAN – není co importovat.\n\n"
    text += "— automatická synchronizace Shoptet → štítkovačka\n"
    m.set_content(text)
    if k_importu and xlsx_bytes:
        m.add_attachment(xlsx_bytes, maintype="application",
                         subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=nazev)
    with smtplib.SMTP(host, int(port), timeout=60) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, pw)
        s.send_message(m)
    log(f"mail odeslán na {to}")
    return True


# ── Hlavní běh ────────────────────────────────────────────────────────────
def main():
    url = os.environ.get("SHOPTET_EXPORT_URL")
    if not url:
        raise SystemExit("chybí env SHOPTET_EXPORT_URL")

    export, ma_ean, ma_pn = stahni_export(url)
    log(f"export: {len(export)} produktů (ean: {'ano' if ma_ean else 'ne'}, partNumber: {'ano' if ma_pn else 'ne'})")

    db = db_all()
    kody = {p["code"] for p in db}
    obsazene = {p["ean"] for p in db if p.get("ean")}
    log(f"databáze: {len(kody)} produktů")

    nove = [r for r in export if r["code"] not in kody]
    log(f"nových: {len(nove)}")
    if not nove:
        return

    rows = []
    for r in nove:
        e = clean(r.get("ean"))
        ze_shoptetu = False
        if e and e in obsazene:
            log(f"  {r['code']}: EAN {e} ze Shoptetu je už obsazený – generuji nový")
            e = None
        if e:
            obsazene.add(e); ze_shoptetu = True
        rec = {"code": r["code"], "name": clean(r["name"]) or r["code"], "ean": e or ean13_859(obsazene)}
        pc = clean(r.get("pairCode"))
        if pc:
            rec["pair_code"] = pc
        pn = part_number(r.get("partNumber"))
        if pn:
            rec["part_number"] = pn
        rec["ean_ze_shoptetu"] = ze_shoptetu
        rows.append(rec)
        log(f"  + {rec['code']:<12} ean={rec['ean']} {'(shoptet)' if ze_shoptetu else '(nový)   '} pn={rec.get('part_number', '-'):<16} {rec['name'][:50]}")

    if NANECISTO:
        log("NANEČISTO – nic nevkládám, neposílám")
        return

    chyby = 0
    for rec in rows:
        try:
            db_insert({k: v for k, v in rec.items() if k != "ean_ze_shoptetu"})
        except Exception as ex:
            chyby += 1
            log(f"  ! {rec['code']}: vložení selhalo: {ex}")
    log(f"vloženo: {len(rows) - chyby}, chyb: {chyby}")

    k_importu = [r for r in rows if not r["ean_ze_shoptetu"]]
    nazev = f"nove_produkty_shoptet_import_{date.today():%Y-%m-%d}.xlsx"
    data = None
    if k_importu:
        data = xlsx_import(k_importu)
        os.makedirs("vystup", exist_ok=True)
        with open(os.path.join("vystup", nazev), "wb") as f:
            f.write(data)
        log(f"k importu do Shoptetu: {len(k_importu)} → vystup/{nazev}")
    else:
        log("všechny nové měly platný EAN ze Shoptetu – XLSX k importu není potřeba")
    posli_mail(rows, k_importu, data, nazev)
    if chyby:
        sys.exit(1)


if __name__ == "__main__":
    main()
