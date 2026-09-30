#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Denní synchronizace Shoptet ↔ Supabase (štítkovačka).

Zdroj pravdy pro sortiment a názvy je Shoptet, zdroj pravdy pro EAN je
databáze štítkovačky (protože EAN je na už vytištěných štítcích).

Co dělá při každém běhu:
1. stáhne export produktů ze Shoptetu (env SHOPTET_EXPORT_URL – kompletní XML
   productsComplete.xml s EAN, PART_NUMBER a parametry variant; umí i XLSX)
2. NOVÉ produkty (code není v DB) vloží: name, part_number, ean, dovozce,
   je_displej, potrebuje_sn (klasifikace = stejný kód jako na štítkovačce,
   Scripts/label_printer.py). EAN ze Shoptetu se převezme, je-li platný
   a neobsazený; jinak se vygeneruje EAN-13 s prefixem 859.
3. EXISTUJÍCÍ produkty srovná:
   – název: varianta = název produktu + hodnota parametru varianty
     ("Zadní sklo – Černá | iPhone 13"); liší-li se od DB → přepíše DB
   – part_number: DB nemá, Shoptet má → doplní
   – EAN: Shoptet má skutečný unikátní EAN a DB náš vygenerovaný (859…) →
     DB převezme ten ze Shoptetu; Shoptet nemá / má duplicitní → XLSX k importu
   – produkt zmizel ze Shoptetu → aktivni=false (nic se nemaže); vrátil se →
     aktivni=true. Vyžaduje sloupec products.aktivni (viz SQL v README).
   Zápisy do DB kromě INSERT vyžadují SUPABASE_SERVICE_KEY (anon má zámek RLS).
4. XLSX (code, pairCode, ean) = vše, co je potřeba naimportovat do Shoptetu
5. mail (SMTP_* + MAIL_TO), pokud je co hlásit; bez SMTP jen uloží soubor

Lokálně: --nanecisto (nic nezapisuje, neposílá); --test-mail (jen zkušební mail)
"""
import io, os, re, sys, json, random, smtplib, ssl, unicodedata, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Scripts"))
from label_printer import importer_key_for, is_display, needs_serial_number  # noqa: E402

SUPABASE = "https://osinlzagjimyrzjpdxai.supabase.co/rest/v1/products"
ANON_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwi"
            "cm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or ""
KEY = SERVICE_KEY or ANON_KEY
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

NANECISTO = "--nanecisto" in sys.argv
MAX_V_MAILU = 40      # delší seznamy se v mailu zkrátí (celé jsou v logu Actions)


def log(msg):
    print(msg, flush=True)


def nfc(s):
    return unicodedata.normalize("NFC", (s or "").strip())


# ── Supabase ─────────────────────────────────────────────────────────────
MA_AKTIVNI = True     # sloupec products.aktivni existuje? (zjistí db_all)


def db_all():
    global MA_AKTIVNI
    for sloupce in ("code,ean,name,pair_code,part_number,dovozce,aktivni", "code,ean,name,pair_code,part_number,dovozce"):
        out, off = [], 0
        try:
            while True:
                req = urllib.request.Request(f"{SUPABASE}?select={sloupce}&limit=1000&offset={off}", headers=H)
                b = json.loads(urllib.request.urlopen(req, timeout=30).read())
                out += b
                if len(b) < 1000:
                    return out
                off += 1000
        except urllib.error.HTTPError as e:
            if e.code == 400 and "aktivni" in sloupce:
                MA_AKTIVNI = False
                continue
            raise


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


def nazev_varianty(zaklad, hodnota):
    """'Zadní sklo | iPhone 13' + 'Černá' → 'Zadní sklo – Černá | iPhone 13'.
    Hodnota parametru (barva, šířka, stav, počet kusů…) patří k dílu, ne
    k zařízení za '|' – štítkovačka dělí název na popis | zařízení."""
    zaklad, hodnota = nfc(zaklad), nfc(hodnota)
    if not hodnota:
        return zaklad
    if "|" in zaklad:
        popis, zarizeni = [p.strip() for p in zaklad.split("|", 1)]
        return f"{popis} – {hodnota} | {zarizeni}"
    return f"{zaklad} – {hodnota}"


def _xml_rows(raw):
    """Kompletní XML: prodejní jednotka = SHOPITEM bez variant, nebo každá VARIANT.
    Varianta dědí PART_NUMBER a název doplněný o hodnotu svého parametru.
    XML nemá PAIR_CODE (import EANu do Shoptetu páruje podle code, nevadí)."""
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
                hodnoty = [t(p, "VALUE") for p in v.findall(".//PARAMETER")]
                rows.append({"code": t(v, "CODE"), "pairCode": "", "name": nazev_varianty(name, " ".join(h for h in hodnoty if h)),
                             "ean": t(v, "EAN"), "partNumber": t(v, "PART_NUMBER") or pn_item})
        else:
            rows.append({"code": t(it, "CODE"), "pairCode": "", "name": nfc(name),
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
                     "name": nfc(clean(r.get("name"))), "ean": (clean(r.get("ean")) or "") if ma_ean else "",
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


def sekce(nadpis, radky):
    """Blok do mailu; dlouhé seznamy zkrátí (celý seznam je v logu Actions)."""
    if not radky:
        return ""
    text = f"{nadpis} ({len(radky)}):\n" + "\n".join(radky[:MAX_V_MAILU])
    if len(radky) > MAX_V_MAILU:
        text += f"\n  … a dalších {len(radky) - MAX_V_MAILU} (celý seznam v logu GitHub Actions)"
    return text + "\n\n"


DOVOZCE_NAZEV = {"apple": "Apple", "iswap": "iSwap.cz", "dyson": "Dyson", "mobilesentrix": "MobileSentrix"}


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
    v_shoptetu = {r["code"] for r in export}
    log(f"databáze: {len(dbc)} produktů" + ("" if MA_AKTIVNI else " (sloupec aktivni chybí – vyřazené se nehlídají)"))

    nove, prevzate, doplneny_pn, prejmenovane, vyrazene, vracene, k_importu, k_rozhodnuti = [], [], [], [], [], [], [], []
    bez_klice = 0    # změny, které by se udělaly, kdyby byl service klíč

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
        name = r["name"] or r["code"]
        rec = {"code": r["code"], "name": name, "ean": ean,
               "dovozce": importer_key_for(name), "je_displej": is_display(name),
               "potrebuje_sn": needs_serial_number(name)}
        pc = clean(r.get("pairCode"))
        if pc:
            rec["pair_code"] = pc
        pn = part_number(r.get("partNumber"))
        if pn:
            rec["part_number"] = pn
        nove.append((rec, ze_shoptetu))
        log(f"  + nový {rec['code']:<12} ean={ean} {'(shoptet)' if ze_shoptetu else '(nový)'} "
            f"dovozce={rec['dovozce']} pn={rec.get('part_number', '-')} {name[:45]}")
        if not ze_shoptetu:
            k_importu.append((rec, "nový produkt"))

    # ── 2) existující produkty ────────────────────────────────────────
    for r in export:
        d = dbc.get(r["code"])
        if not d:
            continue
        # název
        if r["name"] and nfc(d.get("name")) != r["name"]:
            if SERVICE_KEY:
                prejmenovane.append((d, d.get("name") or "", r["name"]))
            else:
                bez_klice += 1
        # part_number
        pn = part_number(r.get("partNumber")) if ma_pn else None
        if pn and not d.get("part_number"):
            if SERVICE_KEY:
                doplneny_pn.append((d, pn))
            else:
                bez_klice += 1
        # aktivita
        if MA_AKTIVNI and d.get("aktivni") is False:
            (vracene if SERVICE_KEY else k_rozhodnuti).append((d, "je zpět v Shoptetu, v DB neaktivní"))
        # EAN
        if ma_ean:
            se, de = clean(r.get("ean")), d.get("ean") or ""
            if se == de:
                pass
            elif not se:
                k_importu.append((d, "v Shoptetu chybí EAN"))
            elif platny_ean(se) and se not in obsazene and de.startswith("859"):
                if SERVICE_KEY:
                    prevzate.append((d, se)); obsazene.discard(de); obsazene.add(se)
                else:
                    k_rozhodnuti.append((d, f"Shoptet má skutečný EAN {se}, DB {de}"))
            else:
                k_importu.append((d, f"v Shoptetu jiný EAN ({se})"))

    # ── 3) produkty, které ze Shoptetu zmizely ────────────────────────
    if MA_AKTIVNI:
        for p in db:
            if p["code"] not in v_shoptetu and p.get("aktivni") is not False:
                (vyrazene if SERVICE_KEY else k_rozhodnuti).append((p, "už není v Shoptetu"))

    log(f"nových: {len(nove)} | přejmenovat: {len(prejmenovane)} | doplnit part_number: {len(doplneny_pn)}"
        f" | EAN převzít: {len(prevzate)} | vyřadit: {len(vyrazene)} | vrátit: {len(vracene)}"
        f" | k importu do Shoptetu: {len(k_importu)} | k rozhodnutí: {len(k_rozhodnuti)}"
        + (f" | bez service klíče nelze: {bez_klice}" if bez_klice else ""))

    for d, stary, novy in prejmenovane: log(f"  ~ název {d['code']:<12} {stary[:50]!r} → {novy[:50]!r}")
    for d, pn in doplneny_pn: log(f"  ~ PN    {d['code']:<12} → {pn}")
    for d, se in prevzate: log(f"  ~ EAN   {d['code']:<12} {d['ean']} → {se}")
    for d, _ in vyrazene: log(f"  ~ vyřazen {d['code']:<10} {d['name'][:50]}")
    for d, _ in vracene: log(f"  ~ vrácen  {d['code']:<10} {d['name'][:50]}")
    for d, proc in k_importu: log(f"  → import {d['code']:<12} {d['ean']}  ({proc})")
    for d, proc in k_rozhodnuti: log(f"  ? {d['code']:<12} {proc}")

    if not (nove or prevzate or doplneny_pn or prejmenovane or vyrazene or vracene or k_importu or k_rozhodnuti):
        log("vše je sjednocené – nic k odeslání")
        return
    if NANECISTO:
        log("NANEČISTO – nic nezapisuji, neposílám")
        return

    # ── 4) zápisy ─────────────────────────────────────────────────────
    chyby = []

    def zapis(popis, fn):
        try:
            fn()
        except Exception as ex:
            chyby.append(f"{popis}: {ex}")

    for rec, _ in nove:
        zapis(f"vložení {rec['code']}", lambda rec=rec: db_insert(rec))
    for d, _, novy in prejmenovane:
        zapis(f"název {d['code']}", lambda d=d, novy=novy: db_update(d["code"], {"name": novy}))
    for d, pn in doplneny_pn:
        zapis(f"part_number {d['code']}", lambda d=d, pn=pn: db_update(d["code"], {"part_number": pn}))
    for d, se in prevzate:
        zapis(f"EAN {d['code']}", lambda d=d, se=se: db_update(d["code"], {"ean": se}))
        d["ean_puvodni"], d["ean"] = d["ean"], se
    for d, _ in vyrazene:
        zapis(f"vyřazení {d['code']}", lambda d=d: db_update(d["code"], {"aktivni": False}))
    for d, _ in vracene:
        zapis(f"vrácení {d['code']}", lambda d=d: db_update(d["code"], {"aktivni": True}))
    for ch in chyby:
        log("  ! " + ch)

    # ── 5) XLSX + mail ────────────────────────────────────────────────
    nazev = f"shoptet_import_ean_{date.today():%Y-%m-%d}.xlsx"
    data = None
    if k_importu:
        data = xlsx_import([d for d, _ in k_importu])
        os.makedirs("vystup", exist_ok=True)
        with open(os.path.join("vystup", nazev), "wb") as f:
            f.write(data)
        log(f"XLSX k importu do Shoptetu: {len(k_importu)} → vystup/{nazev}")

    text = "Ahoj,\n\n"
    text += sekce("NOVÉ PRODUKTY – přidány do databáze štítkovačky (zkontroluj dovozce)",
                  [radek(rec, ("EAN ze Shoptetu" if zs else "nový EAN") + f", {DOVOZCE_NAZEV[rec['dovozce']]}") for rec, zs in nove])
    text += sekce("K IMPORTU DO SHOPTETU – v příloze XLSX (code, pairCode, ean), po importu zmizí",
                  [radek(d, proc) for d, proc in k_importu])
    text += sekce("PŘEJMENOVÁNO PODLE SHOPTETU (štítek teď tiskne nový název)",
                  [f"  {d['code']:<12} {stary[:40]!s}  →  {novy[:60]}" for d, stary, novy in prejmenovane])
    text += sekce("VYŘAZENO – produkt už není v Shoptetu (v DB označen neaktivní, nic se nemaže)",
                  [f"  {d['code']:<12} {d['ean']:<14} {d['name'][:55]}" for d, _ in vyrazene])
    text += sekce("ZPĚT V SHOPTETU – znovu aktivní",
                  [f"  {d['code']:<12} {d['ean']:<14} {d['name'][:55]}" for d, _ in vracene])
    text += sekce("EAN PŘEVZATÝ ZE SHOPTETU DO DATABÁZE – Shoptet měl skutečný čárový kód",
                  [radek(d, f"dřív {d.get('ean_puvodni', '?')}") for d, _ in prevzate])
    text += sekce("DOPLNĚN KÓD DODAVATELE",
                  [f"  {d['code']:<12} {pn:<28} {d['name'][:55]}" for d, pn in doplneny_pn])
    text += sekce("K ROZHODNUTÍ – sync nemá právo do databáze zapisovat (chybí SUPABASE_SERVICE_KEY)",
                  [f"  {d['code']:<12} {proc:<45} {d['name'][:40]}" for d, proc in k_rozhodnuti])
    if bez_klice:
        text += f"Dalších {bez_klice} změn (názvy/part_number) čeká na SUPABASE_SERVICE_KEY.\n\n"
    if not MA_AKTIVNI:
        text += "POZN.: v databázi chybí sloupec products.aktivni – vyřazené produkty se nehlídají.\n\n"
    text += sekce("CHYBY", ["  " + c for c in chyby])

    casti = [f"{len(nove)} nových" if nove else "", f"{len(k_importu)} k importu" if k_importu else "",
             f"{len(prejmenovane)} přejmenováno" if prejmenovane else "", f"{len(vyrazene)} vyřazeno" if vyrazene else "",
             f"{len(vracene)} vráceno" if vracene else "", f"{len(prevzate)} EAN převzato" if prevzate else "",
             f"{len(k_rozhodnuti)} k rozhodnutí" if k_rozhodnuti else "", "CHYBY" if chyby else ""]
    subject = "Štítky: " + ", ".join(c for c in casti if c) + f" ({date.today():%d.%m.%Y})"
    posli_mail(subject, text, data, nazev)
    if chyby:
        sys.exit(1)


if __name__ == "__main__":
    main()
