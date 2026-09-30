#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Denní synchronizace Shoptet ↔ Supabase (štítkovačka).

Co dělá při každém běhu:
1. stáhne export produktů ze Shoptetu (env SHOPTET_EXPORT_URL – kompletní XML
   productsComplete.xml s EAN i PART_NUMBER; umí i XLSX ze šablony)
2. NOVÉ produkty (code není v DB) vloží: name, part_number, ean
   – EAN ze Shoptetu se převezme, je-li platný a neobsazený; jinak se
     vygeneruje EAN-13 s prefixem 859 (Shoptet u nových produktů EAN buď nemá,
     nebo ho zdědil z kopírovaného produktu)
3. EXISTUJÍCÍ produkty srovná:
   – Shoptet má platný unikátní EAN a DB má náš vygenerovaný (859…) →
     DB převezme ten ze Shoptetu (je to skutečný čárový kód na zboží).
     Vyžaduje SUPABASE_SERVICE_KEY (anon klíč nesmí měnit ean – zámek RLS);
     bez něj se jen vypíše "k rozhodnutí".
   – Shoptet nemá EAN, nebo má duplicitní → do XLSX k importu (Shoptet
     dostane EAN z DB)
   – DB nemá part_number a Shoptet ho má → doplní (jen se service klíčem)
4. XLSX (code, pairCode, ean) = vše, co je potřeba naimportovat do Shoptetu
5. mail (SMTP_* + MAIL_TO), pokud je co hlásit; bez SMTP jen uloží soubor

Lokálně: --nanecisto (nic nezapisuje, neposílá); --test-mail (jen zkušební mail)
"""
import io, os, re, sys, json, random, smtplib, ssl, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from datetime import date

SUPABASE = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/products"
ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwi"
            "cm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or ""
KEY = SERVICE_KEY or ANON_KEY
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

NANECISTO = "--nanecisto" in sys.argv


def log(msg):
    print(msg, flush=True)


# ── Supabase ─────────────────────────────────────────────────────────────
def db_all():
    out, off = [], 0
    while True:
        req = urllib.request.Request(f"{SUPABASE}?select=code,ean,name,pair_code,part_number&limit=1000&offset={off}", headers=H)
        b = json.loads(urllib.request.urlopen(req, timeout=30).read())
        out += b
        if len(b) < 1000:
            return out
        off += 1000


def db_insert(rec):
    req = urllib.request.Request(SUPABASE, data=json.dumps(rec, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={**H, "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30)


def db_update(code, fields):
    req = urllib.request.Request(f"{SUPABASE}?code=eq.{urllib.parse.quote(code, safe='')}",
                                 data=json.dumps(fields, ensure_ascii=False).encode("utf-8"),
                                 method="PATCH", headers={**H, "Prefer": "return=minimal"})
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
    """Kompletní XML: prodejní jednotka = SHOPITEM bez variant, nebo každá VARIANT.
    Varianta dědí NAME a PART_NUMBER. XML nemá PAIR_CODE (interní párování je jen
    v CSV/XLSX), import EANu do Shoptetu ale páruje podle code, takže nevadí."""
    root = ET.fromstring(raw)

    def t(e, tag):
        x = e.find(tag)
        return (x.text or "").strip() if x is not None and x.text else ""

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
                     "name": clean(r.get("name")) or "", "ean": (clean(r.get("ean")) or "") if ma_ean else "",
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


def platny_ean(e):
    return bool(e) and e.isdigit() and 8 <= len(e) <= 14


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
def posli_mail(subject, text, xlsx_bytes=None, nazev=None):
    host, port, user, pw, to = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))
    if not all([host, port, user, pw, to]):
        log("SMTP není nastaveno (SMTP_HOST/PORT/USER/PASS, MAIL_TO) – mail neposílám")
        return False
    m = EmailMessage()
    m["From"] = user
    m["To"] = to
    m["Subject"] = subject
    m.set_content(text + "\n— automatická synchronizace Shoptet ↔ štítkovačka\n")
    if xlsx_bytes:
        m.add_attachment(xlsx_bytes, maintype="application",
                         subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=nazev)
    with smtplib.SMTP(host, int(port), timeout=60) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, pw)
        s.send_message(m)
    log(f"mail odeslán na {to}")
    return True


def radek(r, poznamka=""):
    return f"  {r['code']:<12} {r['ean']:<14} {poznamka:<28} {r['name'][:55]}"


# ── Hlavní běh ────────────────────────────────────────────────────────────
def main():
    if "--test-mail" in sys.argv:
        ok = posli_mail("Štítky: testovací mail", "Ahoj,\n\ntohle je zkušební zpráva – SMTP nastavení funguje.\n")
        raise SystemExit(0 if ok else 1)

    url = os.environ.get("SHOPTET_EXPORT_URL")
    if not url:
        raise SystemExit("chybí env SHOPTET_EXPORT_URL")

    export, ma_ean, ma_pn = stahni_export(url)
    log(f"export: {len(export)} produktů (ean: {'ano' if ma_ean else 'ne'}, partNumber: {'ano' if ma_pn else 'ne'})"
        f" | klíč: {'service' if SERVICE_KEY else 'anon (jen vkládání)'}")

    db = db_all()
    dbc = {p["code"]: p for p in db}
    obsazene = {p["ean"] for p in db if p.get("ean")}
    log(f"databáze: {len(dbc)} produktů")

    nove, prevzate, doplneny_pn, k_importu, k_rozhodnuti = [], [], [], [], []

    # ── 1) nové produkty ─────────────────────────────────────────────
    for r in export:
        if r["code"] in dbc:
            continue
        e = clean(r.get("ean"))
        ze_shoptetu = platny_ean(e) and e not in obsazene
        if e and not ze_shoptetu:
            log(f"  {r['code']}: EAN {e} ze Shoptetu je obsazený/neplatný – generuji nový")
        ean = e if ze_shoptetu else ean13_859(obsazene)
        obsazene.add(ean)
        rec = {"code": r["code"], "name": clean(r["name"]) or r["code"], "ean": ean}
        pc = clean(r.get("pairCode"))
        if pc:
            rec["pair_code"] = pc
        pn = part_number(r.get("partNumber"))
        if pn:
            rec["part_number"] = pn
        nove.append((rec, ze_shoptetu))
        log(f"  + nový {rec['code']:<12} ean={ean} {'(shoptet)' if ze_shoptetu else '(nový)'} pn={rec.get('part_number', '-')} {rec['name'][:45]}")
        if not ze_shoptetu:
            k_importu.append((rec, "nový produkt"))

    # ── 2) existující produkty: srovnání EAN a part_number ───────────
    if ma_ean:
        for r in export:
            d = dbc.get(r["code"])
            if not d:
                continue
            se, de = clean(r.get("ean")), d.get("ean") or ""
            if se == de:
                pass
            elif not se:
                k_importu.append((d, "v Shoptetu chybí EAN"))
            elif platny_ean(se) and se not in obsazene and de.startswith("859"):
                # Shoptet má skutečný EAN, DB jen náš placeholder → převzít do DB
                if SERVICE_KEY:
                    prevzate.append((d, se))
                    obsazene.discard(de); obsazene.add(se)
                else:
                    k_rozhodnuti.append((d, se))
            else:
                k_importu.append((d, f"v Shoptetu jiný EAN ({se})"))
    if ma_pn and SERVICE_KEY:
        for r in export:
            d = dbc.get(r["code"])
            pn = part_number(r.get("partNumber")) if d else None
            if d and pn and not d.get("part_number"):
                doplneny_pn.append((d, pn))

    log(f"nových: {len(nove)} | EAN převzít ze Shoptetu do DB: {len(prevzate)}"
        + (f" (k rozhodnutí bez service klíče: {len(k_rozhodnuti)})" if k_rozhodnuti else "")
        + f" | doplnit part_number: {len(doplneny_pn)} | k importu do Shoptetu: {len(k_importu)}")

    if not (nove or prevzate or doplneny_pn or k_importu or k_rozhodnuti):
        log("vše je sjednocené – nic k odeslání")
        return
    if NANECISTO:
        for d, se in prevzate: log(f"  ~ EAN {d['code']}: {d['ean']} → {se}")
        for d, pn in doplneny_pn: log(f"  ~ PN  {d['code']}: → {pn}")
        for d, proc in k_importu: log(f"  → import {d['code']:<12} {d['ean']}  ({proc})")
        for d, se in k_rozhodnuti: log(f"  ? {d['code']}: Shoptet {se} vs DB {d['ean']}")
        log("NANEČISTO – nic nezapisuji, neposílám")
        return

    # ── 3) zápisy ─────────────────────────────────────────────────────
    chyby = []
    for rec, _ in nove:
        try: db_insert(rec)
        except Exception as ex: chyby.append(f"vložení {rec['code']}: {ex}")
    for d, se in prevzate:
        try: db_update(d["code"], {"ean": se}); d["ean_puvodni"], d["ean"] = d["ean"], se
        except Exception as ex: chyby.append(f"EAN {d['code']}: {ex}")
    for d, pn in doplneny_pn:
        try: db_update(d["code"], {"part_number": pn})
        except Exception as ex: chyby.append(f"part_number {d['code']}: {ex}")
    for ch in chyby:
        log("  ! " + ch)

    # ── 4) XLSX + mail ────────────────────────────────────────────────
    nazev = f"shoptet_import_ean_{date.today():%Y-%m-%d}.xlsx"
    data = None
    if k_importu:
        data = xlsx_import([d for d, _ in k_importu])
        os.makedirs("vystup", exist_ok=True)
        with open(os.path.join("vystup", nazev), "wb") as f:
            f.write(data)
        log(f"XLSX k importu do Shoptetu: {len(k_importu)} → vystup/{nazev}")

    text = "Ahoj,\n\n"
    if nove:
        text += f"NOVÉ PRODUKTY ({len(nove)}) – přidány do databáze štítkovačky:\n"
        text += "\n".join(radek(rec, "EAN ze Shoptetu" if zs else "nový EAN") for rec, zs in nove) + "\n\n"
    if prevzate:
        text += f"EAN PŘEVZATÝ ZE SHOPTETU DO DATABÁZE ({len(prevzate)}) – Shoptet měl skutečný čárový kód:\n"
        text += "\n".join(radek(d, f"dřív {d.get('ean_puvodni', '?')}") for d, _ in prevzate) + "\n\n"
    if doplneny_pn:
        text += f"DOPLNĚN KÓD DODAVATELE ({len(doplneny_pn)}):\n"
        text += "\n".join(f"  {d['code']:<12} {pn:<28} {d['name'][:55]}" for d, pn in doplneny_pn) + "\n\n"
    if k_importu:
        text += (f"K IMPORTU DO SHOPTETU ({len(k_importu)}) – v příloze XLSX (code, pairCode, ean),\n"
                 "stejný formát jako dosud. Po importu se tenhle seznam vyprázdní:\n")
        text += "\n".join(radek(d, proc) for d, proc in k_importu) + "\n\n"
    if k_rozhodnuti:
        text += (f"K ROZHODNUTÍ ({len(k_rozhodnuti)}) – Shoptet má jiný platný EAN než databáze a sync nemá\n"
                 "právo databázi měnit (chybí SUPABASE_SERVICE_KEY):\n")
        text += "\n".join(f"  {d['code']:<12} Shoptet {se}  DB {d['ean']}  {d['name'][:45]}" for d, se in k_rozhodnuti) + "\n\n"
    if chyby:
        text += "CHYBY:\n" + "\n".join("  " + c for c in chyby) + "\n\n"

    casti = [f"{len(nove)} nových" if nove else "", f"{len(k_importu)} k importu" if k_importu else "",
             f"{len(prevzate)} EAN převzato" if prevzate else "", "CHYBY" if chyby else ""]
    subject = "Štítky: " + ", ".join(c for c in casti if c) + f" ({date.today():%d.%m.%Y})"
    posli_mail(subject, text, data, nazev)
    if chyby:
        sys.exit(1)


if __name__ == "__main__":
    main()
