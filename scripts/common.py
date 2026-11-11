"""Shared utilities: HTTP, data status, transforms, I/O. Standard library only."""
import csv
import datetime as dt
import io
import json
import math
import os
import sys
import urllib.request

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path=None):
    p = path or os.environ.get("POSITION_TRADER_CONFIG") or os.path.join(ROOT, "config.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def state_dir():
    d = os.environ.get("POSITION_TRADER_STATE") or os.path.expanduser("~/.position-trader")
    os.makedirs(d, exist_ok=True)
    return d


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url, timeout=5):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_json(url, timeout=5):
    return json.loads(http_get(url, timeout))


class Status:
    """Per-source data status: ok / stale / failed. Always reported in the output."""

    def __init__(self):
        self.items = {}

    def _set(self, key, status, note):
        self.items[key] = {"status": status, "note": note, "at": now_iso()}

    def ok(self, key, note=""):
        self._set(key, "ok", note)

    def stale(self, key, note=""):
        self._set(key, "stale", note)

    def failed(self, key, err):
        self._set(key, "failed", str(err)[:200])

    def has_failures(self):
        return any(v["status"] == "failed" for v in self.items.values())


# ---------- transforms (names follow the catalog) ----------

def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def roc(xs, n):
    if len(xs) > n and xs[-1 - n]:
        return xs[-1] / xs[-1 - n] - 1
    return None


def slope_pct(xs, n, window):
    """Percent change of SMA(window) over the last n periods."""
    now = sma(xs, window)
    prev = sma(xs[:-n], window) if len(xs) > n else None
    if now is None or prev in (None, 0):
        return None
    return now / prev - 1


def dist_ma(xs, n):
    m = sma(xs, n)
    return xs[-1] / m - 1 if m else None


def zscore(xs, window):
    w = xs[-window:]
    if len(w) < 5:
        return None
    m = sum(w) / len(w)
    sd = math.sqrt(sum((x - m) ** 2 for x in w) / len(w))
    return (w[-1] - m) / sd if sd else 0.0


def pctrank(xs, value=None, window=None):
    w = xs[-window:] if window else xs
    if not w:
        return None
    v = w[-1] if value is None else value
    return sum(1 for x in w if x <= v) / len(w)


def sign(x, thr=0.0):
    if x is None:
        return None
    return 1 if x > thr else (-1 if x < -thr else 0)


def drawdown_from_max(xs):
    if not xs:
        return None
    return xs[-1] / max(xs) - 1


# ---------- parsing ----------

def parse_fred(text):
    out = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2 or parts[1] in (".", ""):
            continue
        try:
            out.append((parts[0], float(parts[1])))
        except ValueError:
            continue
    return out


def parse_stooq(text):
    rows = []
    if "Date" not in text[:20]:
        return rows
    for r in csv.DictReader(io.StringIO(text)):
        try:
            rows.append({"date": r["Date"], "o": float(r["Open"]), "h": float(r["High"]),
                         "l": float(r["Low"]), "c": float(r["Close"]),
                         "v": float(r["Volume"] or 0)})
        except (ValueError, KeyError):
            continue
    return rows


def stooq_closes(symbol, interval="w", status=None, key=None):
    """Fetch closes from Stooq (w = weekly, d = daily). The running weekly candle is dropped."""
    k = key or symbol
    try:
        sym = symbol.replace("^", "%5E")
        rows = parse_stooq(http_get(f"https://stooq.com/q/d/l/?s={sym}&i={interval}"))
        if not rows:
            raise ValueError("empty data")
        if interval == "w" and rows:
            last = dt.date.fromisoformat(rows[-1]["date"])
            if (dt.date.today() - last).days < 5 and dt.date.today().weekday() < 5:
                rows = rows[:-1]
        if status:
            status.ok(k, f"{len(rows)} rows, last {rows[-1]['date']}")
        return [r["c"] for r in rows]
    except Exception as e:  # noqa: BLE001
        if status:
            status.failed(k, e)
        return None


# ---------- output ----------

def finish(obj, out=None, save_as=None):
    """Print JSON; optionally write to --out and to the state dir (save_as)."""
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    if save_as:
        with open(os.path.join(state_dir(), save_as), "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


def load_state_json(name, default=None):
    p = os.path.join(state_dir(), name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default
    return default


def r(x, n=4):
    return None if x is None else round(x, n)
