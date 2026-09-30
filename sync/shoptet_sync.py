#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Denní synchronizace Shoptet → Supabase.

1. stáhne export produktů ze Shoptetu (URL v env SHOPTET_EXPORT_URL – obsahuje
   tajný hash, proto je v GitHub Secrets, ne v repu)
2. najde produkty, které v Supabase ještě nejsou (podle `code`)
3. vloží je: name, pair_code, part_number (je-li v exportu), ean
   – EAN se vezme z exportu jen pokud tam je a není v DB obsazený;
     jinak se vygeneruje EAN-13 s prefixem 859 (CZ) – Shoptet totiž EAN
     u nových produktů buď nemá, nebo je zdědil z kopírovaného produktu
4. vytvoří XLSX (code, pairCode, ean) pro import zpět do Shoptetu
5. pošle ho mailem (SMTP_* + MAIL_TO v env); bez SMTP jen uloží soubor

Bez nových produktů nic nevkládá, nic neposílá.
Spouští se z .github/workflows/shoptet-sync.yml; lokálně: --nanecisto
"""
import io, os, re, sys, json, random, smtplib, ssl, urllib.request, urllib.parse
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


# ── Shoptet export ───────────────────────────────────────────────────────
def stahni_export(url):
    import pandas as pd
    raw = urllib.request.urlopen(url, timeout=180).read()
    df = pd.read_excel(io.BytesIO(raw), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    if "code" not in df.columns or "name" not in df.columns:
        raise SystemExit(f"export nemá sloupce code/name – má: {df.columns.tolist()[:10]}")
    df["code"] = df["code"].astype(str).str.strip()
    df = df[df["code"].notna() & (df["code"] != "") & (df["code"] != "nan")].drop_duplicates("code")
    return df


def clean(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "nan", "None"):
        return None
    if s.endswith(".0") and s[:-2].isdigit():   # pandas občas EAN načte jako float
        s = s[:-2]
    return s


def part_number(row):
    """Shoptet ořezává pole na 32 znaků; občas je tam URL nebo useknutý fragment."""
    raw = clean(row.get("partNumber")) or clean(row.get("externalCode"))
    if not raw or raw.lower().startswith("http"):
        return None
    good = []
    for t in re.split(r"[,\s]+", raw):
        t = t.strip()
        if len(t) >= 6 and re.fullmatch(r"(?i)[a-z0-9][a-z0-9\-]{4,}", t) and t not in good:
            good.append(t)
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
def posli_mail(rows, xlsx_bytes, nazev):
    host, port, user, pw, to = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))
    if not all([host, port, user, pw, to]):
        log("SMTP není nastaveno (SMTP_HOST/PORT/USER/PASS, MAIL_TO) – mail neposílám")
        return False
    m = EmailMessage()
    m["From"] = user
    m["To"] = to
    m["Subject"] = f"Štítky: {len(rows)} nových produktů – EAN k importu do Shoptetu ({date.today():%d.%m.%Y})"
    radky = "\n".join(f"  {r['code']:<12} {r['ean']}  {r['name'][:60]}" for r in rows)
    m.set_content(
        "Ahoj,\n\nv Shoptetu přibyly nové produkty. Přidal jsem je do databáze štítkovačky\n"
        "a vygeneroval jim EAN. V příloze je XLSX (code, pairCode, ean) k importu\n"
        "do Shoptetu – stejný formát jako dosud.\n\n"
        f"{radky}\n\n"
        + ("Pozn.: export ze Shoptetu neobsahuje sloupec partNumber, takže tyhle produkty\n"
           "nemají kód dodavatele pro skenování. Přidej do exportní šablony sloupce EAN\n"
           "a Part number a příště se doplní automaticky.\n\n" if not any(r.get("part_number") for r in rows) else "")
        + "— automatická synchronizace Shoptet → štítkovačka\n"
    )
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

    df = stahni_export(url)
    ma_ean = "ean" in df.columns
    ma_pn = "partNumber" in df.columns or "externalCode" in df.columns
    log(f"export: {len(df)} produktů (sloupec ean: {'ano' if ma_ean else 'ne'}, partNumber: {'ano' if ma_pn else 'ne'})")

    db = db_all()
    kody = {p["code"] for p in db}
    obsazene = {p["ean"] for p in db if p.get("ean")}
    log(f"databáze: {len(kody)} produktů")

    nove = df[~df["code"].isin(kody)]
    log(f"nových: {len(nove)}")
    if nove.empty:
        return

    rows = []
    for _, r in nove.iterrows():
        e = clean(r.get("ean")) if ma_ean else None
        if e and e in obsazene:
            log(f"  {r['code']}: EAN {e} ze Shoptetu je už obsazený – generuji nový")
            e = None
        if e:
            obsazene.add(e)
        rec = {"code": r["code"], "name": clean(r["name"]) or r["code"], "ean": e or ean13_859(obsazene)}
        pc = clean(r.get("pairCode"))
        if pc:
            rec["pair_code"] = pc
        pn = part_number(r) if ma_pn else None
        if pn:
            rec["part_number"] = pn
        rows.append(rec)
        log(f"  + {rec['code']:<12} ean={rec['ean']}  pn={rec.get('part_number', '-'):<16} {rec['name'][:55]}")

    if NANECISTO:
        log("NANEČISTO – nic nevkládám, neposílám")
        return

    chyby = 0
    for rec in rows:
        try:
            db_insert(rec)
        except Exception as ex:
            chyby += 1
            log(f"  ! {rec['code']}: vložení selhalo: {ex}")
    log(f"vloženo: {len(rows) - chyby}, chyb: {chyby}")
    rows = [r for r in rows]  # všechny (i při chybě vložení chceme EAN v mailu vidět)

    nazev = f"nove_produkty_shoptet_import_{date.today():%Y-%m-%d}.xlsx"
    data = xlsx_import(rows)
    os.makedirs("vystup", exist_ok=True)
    with open(os.path.join("vystup", nazev), "wb") as f:
        f.write(data)
    log(f"soubor: vystup/{nazev}")
    posli_mail(rows, data, nazev)
    if chyby:
        sys.exit(1)


if __name__ == "__main__":
    main()
