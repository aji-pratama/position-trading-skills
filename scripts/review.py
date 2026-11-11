#!/usr/bin/env python3
"""Review statistics from closed trades. Output: review.json.

Usage:  python3 review.py --trades trades.csv [--btc-json btc_prices.json] [--out result.json]
trades.csv columns: asset,class,open_date,close_date,entry,exit,regime_at_entry,phase_at_entry,gate_open,followed_rules
(gate_open and followed_rules are y/n). Optional --btc-json {"2026-01-05": 95000, ...} for the BTC buy-and-hold comparison
(BTC price on each open/close date; trades with missing dates are skipped).
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import finish, mean, now_iso, r  # noqa: E402


def yes(x):
    return str(x).strip().lower() in ("y", "yes", "ya", "true", "1")


def parse(rows):
    out = []
    for x in rows:
        try:
            e, c = float(x["entry"]), float(x["exit"])
            od = dt.date.fromisoformat(x["open_date"])
            cd = dt.date.fromisoformat(x["close_date"])
        except (ValueError, KeyError):
            continue
        out.append({"asset": x.get("asset", "?").upper(), "class": x.get("class", ""), "ret": c / e - 1,
                    "days": (cd - od).days, "open": od.isoformat(), "close": cd.isoformat(),
                    "regime": x.get("regime_at_entry") or "?", "phase": x.get("phase_at_entry") or "?",
                    "gate": yes(x.get("gate_open", "y")), "followed": yes(x.get("followed_rules", "y"))})
    return out


def bucket(trades, key):
    g = {}
    for t in trades:
        g.setdefault(t[key], []).append(t["ret"])
    return {k: {"n": len(v), "mean": r(mean(v)), "win_rate": r(sum(1 for x in v if x > 0) / len(v), 2)} for k, v in g.items()}


def stats(trades, btc=None):
    n = len(trades)
    if not n:
        return {"n": 0, "note": "No closed trades yet."}
    rets = [t["ret"] for t in trades]
    wins = [x for x in rets if x > 0]
    losses = [x for x in rets if x <= 0]
    gp, gl = sum(wins), -sum(losses)
    out = {
        "n": n, "win_rate": r(len(wins) / n, 3), "avg_return": r(mean(rets)),
        "avg_win": r(mean(wins)) if wins else None, "avg_loss": r(mean(losses)) if losses else None,
        "profit_factor": r(gp / gl, 2) if gl else None, "avg_hold_days": r(mean([t["days"] for t in trades]), 1),
        "per_regime": bucket(trades, "regime"), "per_btc_phase": bucket(trades, "phase"), "per_asset": bucket(trades, "asset"),
        "discipline": {"followed_rules": r(sum(t["followed"] for t in trades) / n, 3),
                       "opened_with_gate_closed": r(sum(1 for t in trades if not t["gate"]) / n, 3)},
        "warnings": [],
    }
    if n < 20:
        out["warnings"].append(f"Small sample ({n} trades): these numbers are indications, not evidence. Position trading produces few trades by nature.")
    if btc:
        diffs = []
        for t in trades:
            if t["open"] in btc and t["close"] in btc:
                diffs.append(t["ret"] - (btc[t["close"]] / btc[t["open"]] - 1))
        if diffs:
            out["diff_vs_btc_hold"] = {"n": len(diffs), "mean": r(mean(diffs)),
                                       "beat_btc": r(sum(1 for d in diffs if d > 0) / len(diffs), 2)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--btc-json")
    ap.add_argument("--out")
    a = ap.parse_args()
    with open(a.trades, encoding="utf-8") as f:
        trades = parse(list(csv.DictReader(f)))
    btc = None
    if a.btc_json:
        with open(a.btc_json, encoding="utf-8") as f:
            btc = json.load(f)
    out = stats(trades, btc)
    out["asof"] = now_iso()
    finish(out, a.out)


if __name__ == "__main__":
    main()
