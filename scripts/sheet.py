#!/usr/bin/env python3
"""Google Sheets bridge (via CSV). Stores no credentials.

  python3 sheet.py template --dir ./template      # write empty CSVs for the 3 tabs; import into Google Sheets
  python3 sheet.py positions --csv <path|url>     # normalize the Positions tab to JSON
  python3 sheet.py row --tab Journal --json '{"date":"2026-11-11",...}'   # order a row for appending

Reading: a CSV export of the Positions tab, or a "Publish to web (CSV)" / CSV export URL of the Sheet.
Writing (Journal, Snapshots): through the Google Drive/Sheets connector in Claude; this script only prepares the row.
The Positions tab is yours: the plugin never overwrites it.
"""
import argparse
import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http_get, load_config  # noqa: E402

# Header aliases (including Indonesian ones, so existing sheets keep working)
ALIASES = {"aset": "asset", "ticker": "asset", "symbol": "asset", "kelas": "class", "jumlah": "qty",
           "quantity": "qty", "harga_entry": "entry", "entry_price": "entry", "tanggal": "date",
           "invalidasi": "invalidation", "tesis": "thesis"}


def norm(h):
    h = h.strip().lower().replace(" ", "_")
    return ALIASES.get(h, h)


def num(x):
    if x is None:
        return None
    s = str(x).strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def read_csv(src):
    text = http_get(src) if src.startswith("http") else open(src, encoding="utf-8").read()
    return list(csv.DictReader(io.StringIO(text)))


def positions(rows):
    out = []
    for raw in rows:
        row = {norm(k): (v or "").strip() for k, v in raw.items() if k}
        if not row.get("asset"):
            continue
        out.append({
            "asset": row["asset"].upper(),
            "class": (row.get("class") or "crypto").lower(),
            "qty": num(row.get("qty")),
            "entry": num(row.get("entry")),
            "date": row.get("date") or None,
            "invalidation": num(row.get("invalidation")),
            "thesis": row.get("thesis") or None,
            "horizon": row.get("horizon") or None,
            "setup": row.get("setup") or None,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template")
    t.add_argument("--dir", default="template")
    p = sub.add_parser("positions")
    p.add_argument("--csv", required=True)
    rw = sub.add_parser("row")
    rw.add_argument("--tab", required=True)
    rw.add_argument("--json", required=True)
    a = ap.parse_args()
    tabs = load_config()["sheet"]["tabs"]

    if a.cmd == "template":
        os.makedirs(a.dir, exist_ok=True)
        for tab, cols in tabs.items():
            with open(os.path.join(a.dir, f"{tab}.csv"), "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(cols)
        print(json.dumps({"written": [f"{a.dir}/{t}.csv" for t in tabs]}))
    elif a.cmd == "positions":
        print(json.dumps({"positions": positions(read_csv(a.csv))}, ensure_ascii=False, indent=2))
    else:
        cols = tabs[a.tab]
        data = json.loads(a.json)
        print(json.dumps({"tab": a.tab, "columns": cols, "row": [data.get(c, "") for c in cols]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
