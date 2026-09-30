#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regresní test klasifikace produktů podle názvu (dovozce / displej / sériové číslo).

Stáhne všechny produkty ze Supabase, pro každý spočítá importer_key_for(name),
is_display(name) a needs_serial_number(name) a porovná s uloženým snapshotem
klasifikace_snapshot.json ({code: {"dovozce", "je_displej", "potrebuje_sn"}}).

  python3 test_klasifikace.py            # porovná, exit 1 při rozdílu
  python3 test_klasifikace.py --ulozit   # přepíše snapshot aktuálním stavem
"""
import sys, os, json, ssl
import urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from label_printer import importer_key_for, is_display, needs_serial_number

SUPABASE_URL = "https://osinlzagjimyrzjpdxai.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zaW5semFnamlteXJ6anBkeGFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDUzMDcsImV4cCI6MjA5NzE4MTMwN30.aWkcUv9jpwbqQ3fSHZ_damRGwSqxC_YtH3siySoMgq4"
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SELECT = "select=code,name"
PAGE = 1000

SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "klasifikace_snapshot.json")

IMPORTER_LABELS = {"apple": "Apple", "mobilesentrix": "MobileSentrix", "iswap": "iSwap", "dyson": "Dyson"}


def _default_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

_CTX = _default_ctx()
_UNVERIFIED = ssl._create_unverified_context()


def _get(query):
    # Stejný přístup jako scan_print.py: ověřené spojení, při chybě CA certů
    # (starý Python na Big Sur) zopakovat bez ověření.
    url = f"{SUPABASE_URL}/rest/v1/products?{SELECT}&{query}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_CTX) as r:
            return json.loads(r.read())
    except ssl.SSLError:
        with urllib.request.urlopen(req, timeout=15, context=_UNVERIFIED) as r:
            return json.loads(r.read())


def fetch_all_products():
    products = []
    offset = 0
    while True:
        page = _get(f"order=code.asc&limit={PAGE}&offset={offset}")
        products.extend(page)
        if len(page) < PAGE:
            return products
        offset += PAGE


def classify(products):
    """{code: {"dovozce", "je_displej", "potrebuje_sn"}} + {code: name}"""
    result, names = {}, {}
    for p in products:
        code, name = p.get("code"), p.get("name") or ""
        if not code:
            continue
        result[code] = {
            "dovozce": importer_key_for(name),
            "je_displej": is_display(name),
            "potrebuje_sn": needs_serial_number(name),
        }
        names[code] = name
    return result, names


def summary(classified):
    counts = {k: 0 for k in IMPORTER_LABELS}
    displays = serials = 0
    for v in classified.values():
        counts[v["dovozce"]] = counts.get(v["dovozce"], 0) + 1
        displays += bool(v["je_displej"])
        serials += bool(v["potrebuje_sn"])
    lines = [f"Produktů celkem: {len(classified)}"]
    lines.append("Dovozci: " + ", ".join(f"{IMPORTER_LABELS.get(k, k)} {n}" for k, n in counts.items()))
    lines.append(f"Displeje (125 mm): {displays}, vyžadují SN: {serials}")
    return "\n".join(lines)


def main():
    save = "--ulozit" in sys.argv[1:]

    products = fetch_all_products()
    current, names = classify(products)

    if save:
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        print(f"Snapshot uložen: {SNAPSHOT_PATH}")
        print(summary(current))
        return 0

    if not os.path.exists(SNAPSHOT_PATH):
        print(f"Snapshot neexistuje: {SNAPSHOT_PATH} – vytvoř ho pomocí --ulozit", file=sys.stderr)
        return 1
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        snapshot = json.load(f)

    diffs = []
    for code in sorted(set(snapshot) | set(current)):
        old, new = snapshot.get(code), current.get(code)
        if old == new:
            continue
        name = names.get(code, "")
        if old is None:
            diffs.append(f"+ {code} | {name}\n    nový produkt (není ve snapshotu): {new}")
        elif new is None:
            diffs.append(f"- {code}\n    chybí v DB (byl ve snapshotu): {old}")
        else:
            changed = ", ".join(f"{k}: {old.get(k)!r} → {new.get(k)!r}" for k in new if old.get(k) != new.get(k))
            diffs.append(f"! {code} | {name}\n    {changed}")

    if diffs:
        print(f"ROZDÍLY proti snapshotu ({len(diffs)}):")
        print("\n".join(diffs))
        print()
        print(summary(current))
        return 1

    print("OK – klasifikace odpovídá snapshotu")
    print(summary(current))
    return 0


if __name__ == "__main__":
    sys.exit(main())
