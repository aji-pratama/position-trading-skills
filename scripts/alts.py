#!/usr/bin/env python3
"""Altcoin spot scan: relative strength vs BTC, phase, exhaustion. Output: alts.json.

Usage:  python3 alts.py [--coins SOL,LINK] [--out result.json] [--no-save] [--fixture f.json]
Runs only when btc.json says alt_gate is open, unless --ignore-gate is given.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Status, dist_ma, finish, http_json, load_config, load_state_json,  # noqa: E402
                    now_iso, pctrank, r, roc, sma)

BAD_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")


def klines(symbol, status, limit=120):
    try:
        rows = http_json(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1w&limit={limit}")
        import time
        now_ms = time.time() * 1000
        rows = [x for x in rows if x[6] < now_ms]
        return {"c": [float(x[4]) for x in rows], "v": [float(x[5]) for x in rows]}
    except Exception as e:  # noqa: BLE001
        status.failed(symbol, e)
        return None


def universe(cfg, status):
    try:
        tk = http_json("https://api.binance.com/api/v3/ticker/24hr", timeout=40)
    except Exception as e:  # noqa: BLE001
        status.failed("binance_ticker", e)
        return []
    status.ok("binance_ticker", f"{len(tk)} pairs")
    out = []
    for t in tk:
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in cfg["exclude_bases"] or base.endswith(BAD_SUFFIX):
            continue
        qv = float(t["quoteVolume"])
        if qv >= cfg["min_quote_volume_usd"]:
            out.append((base, qv))
    out.sort(key=lambda x: -x[1])
    return [b for b, _ in out[: cfg["universe_size"]]]


def classify(m, cfg):
    """Coin cycle phase. Example rules."""
    if m["close"] < m["ma10"] and m["rs4"] < 0 and m["rs12"] < 0:
        return "Exhausted"
    if m["ret4"] > cfg["late_ret4"] or m["dist10"] > cfg["late_dist10"]:
        return "Late"
    if m["close"] > m["ma10"] and m["rs12"] > cfg["mid_rs12"]:
        return "Mid"
    if m["close"] > m["ma10"] and m["rs4"] > 0:
        return "Early"
    return "Neutral"


def metrics(k, btc_c):
    c, v = k["c"], k["v"]
    if len(c) < 14 or len(btc_c) < 14:
        return None
    ret4, ret12 = roc(c, 4), roc(c, 12)
    b4, b12 = roc(btc_c, 4), roc(btc_c, 12)
    vexp = None
    if len(v) >= 16 and sum(v[-16:-4]) > 0:
        vexp = (sum(v[-4:]) / 4) / (sum(v[-16:-4]) / 12)
    return {"close": c[-1], "ma10": sma(c, 10), "ret4": ret4, "ret12": ret12,
            "rs4": (1 + ret4) / (1 + b4) - 1, "rs12": (1 + ret12) / (1 + b12) - 1,
            "dist10": dist_ma(c, 10), "vol_expansion": vexp, "age_weeks": len(c)}


def analyze(series, btc_c, cfg):
    rows = []
    for base, k in series.items():
        m = metrics(k, btc_c)
        if not m:
            continue
        m["phase"] = classify(m, cfg)
        m["symbol"] = base
        rows.append(m)
    rs = [x["rs12"] for x in rows]
    for x in rows:
        x["rs12_pct_rank"] = r(pctrank(rs, x["rs12"]), 2)
    rows.sort(key=lambda x: -x["rs12"])
    return rows


def fmt(x):
    return {"symbol": x["symbol"], "phase": x["phase"], "rs4": r(x["rs4"], 3), "rs12": r(x["rs12"], 3),
            "rs12_pct_rank": x["rs12_pct_rank"], "ret4": r(x["ret4"], 3), "distance_to_ma10w": r(x["dist10"], 3),
            "volume_expansion": r(x["vol_expansion"], 2), "age_weeks": x["age_weeks"],
            "invalidation_ref_ma10w": r(x["ma10"], 6)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", help="comma-separated symbols for extra profiles, e.g. SOL,LINK")
    ap.add_argument("--ignore-gate", action="store_true")
    ap.add_argument("--fixture")
    ap.add_argument("--out")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config)["alts"]
    status = Status()

    btc = load_state_json("btc.json")
    gate = (btc or {}).get("alt_gate", {}).get("open")
    if gate is None:
        gate_note = "btc.json missing: run the crypto skill for BTC first"
    elif not gate:
        gate_note = "alt_gate closed: " + "; ".join(btc["alt_gate"]["closed_reasons"])
    else:
        gate_note = "alt_gate open"

    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            fx = json.load(f)
        btc_c, series = fx["btc"], fx["series"]
        status.ok("fixture", a.fixture)
    else:
        if gate is not True and not a.ignore_gate and not a.coins:
            finish({"asof": now_iso(), "gate": gate_note, "candidates": [],
                    "notes": "Alt scan skipped because the gate is not open. Use --ignore-gate to force it, or --coins for specific profiles."})
            return
        bk = klines("BTCUSDT", status)
        if not bk:
            finish({"error": "BTC price unavailable", "data_status": status.items})
            return
        btc_c = bk["c"]
        names = universe(cfg, status)
        if a.coins:
            names += [x.strip().upper() for x in a.coins.split(",") if x.strip().upper() not in names]
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda b: (b, klines(b + "USDT", status)), names))
        series = {b: k for b, k in res if k}
        status.ok("universe", f"{len(series)} coins analyzed")

    rows = analyze(series, btc_c, cfg)
    cand = [x for x in rows if x["phase"] in ("Early", "Mid") and x["rs12"] > 0 and x["age_weeks"] >= cfg["min_age_weeks"]]
    req = []
    if a.coins:
        want = {x.strip().upper() for x in a.coins.split(",")}
        req = [fmt(x) for x in rows if x["symbol"] in want]
    phases = {}
    for x in rows:
        phases[x["phase"]] = phases.get(x["phase"], 0) + 1
    out = {
        "asof": now_iso(), "gate": gate_note,
        "candidates": [fmt(x) for x in cand[: cfg["top_n"]]],
        "requested_profiles": req,
        "phase_distribution": phases,
        "warnings": [fmt(x) for x in rows if x["phase"] == "Late"][:5],
        "notes": ["Sector/narrative, unlock schedules and catalysts are not automatic: search the web before concluding.",
                  "Coins younger than min_age_weeks are not candidates."],
        "data_status": status.items,
    }
    finish(out, a.out, None if a.no_save else "alts.json")


if __name__ == "__main__":
    main()
