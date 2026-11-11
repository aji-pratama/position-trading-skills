#!/usr/bin/env python3
"""US sector ranking (RS vs SPY) + cycle fit + optional stock screening. Output: stocks.json.

Usage:  python3 stocks.py [--tickers AAPL,MSFT] [--out result.json] [--no-save] [--fixture f.json]
Source: Stooq (weekly). Earnings dates are not automatic: check manually or via web search.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Status, finish, load_config, load_state_json, mean, now_iso, r, roc, sma,  # noqa: E402
                    stooq_closes)


def rs(a, b, n):
    ra, rb = roc(a, n), roc(b, n)
    if ra is None or rb is None:
        return None
    return (1 + ra) / (1 + rb) - 1


def rank_sectors(series, spy, cfg, quadrant):
    favored = set(cfg["quadrant_favored"].get(quadrant, [])) if quadrant else set()
    rows = []
    for sym, c in series.items():
        r13, r26 = rs(c, spy, 13), rs(c, spy, 26)
        if r13 is None or r26 is None:
            continue
        rows.append({"sector": sym, "name": cfg["sectors"].get(sym, sym), "rs13": r(r13, 3), "rs26": r(r26, 3),
                     "score": mean([r13, r26]), "above_40wma": (c[-1] > sma(c, 40)) if len(c) >= 40 else None,
                     "cycle_fit": (sym in favored) if quadrant else None})
    rows.sort(key=lambda x: -x["score"])
    for i, x in enumerate(rows, 1):
        x["rank"] = i
        x["score"] = r(x["score"], 3)
    return rows


def stock_metrics(c):
    """Momentum 12-1 (52 weeks minus the last 4 weeks), trend, distance to the 52-week high."""
    if len(c) < 53:
        return None
    mom = c[-5] / c[-53] - 1
    return {"momentum_12_1": r(mom, 3), "above_40wma": c[-1] > sma(c, 40),
            "distance_to_high52w": r(c[-1] / max(c[-52:]) - 1, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", help="stocks to check, e.g. AAPL,MSFT")
    ap.add_argument("--fixture")
    ap.add_argument("--out")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config)["stocks"]
    status = Status()
    regime = load_state_json("regime.json") or {}
    quadrant = regime.get("quadrant")

    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            fx = json.load(f)
        spy, sectors, stocks = fx["spy"], fx["sectors"], fx.get("stocks", {})
        status.ok("fixture", a.fixture)
    else:
        spy = stooq_closes(cfg["benchmark"], "w", status, "SPY")
        if not spy:
            finish({"error": "SPY unavailable", "data_status": status.items})
            return
        sectors = {s: stooq_closes(f"{s.lower()}.us", "w", status, s) for s in cfg["sectors"]}
        sectors = {k: v for k, v in sectors.items() if v}
        stocks = {}
        for t in (a.tickers or "").split(","):
            t = t.strip().upper()
            if t:
                c = stooq_closes(f"{t.lower()}.us", "w", status, t)
                if c:
                    stocks[t] = c

    ranking = rank_sectors(sectors, spy, cfg, quadrant)
    picks = []
    for t, c in stocks.items():
        m = stock_metrics(c)
        if m:
            m["ticker"] = t
            m["rs_vs_spy_26w"] = r(rs(c, spy, 26), 3)
            picks.append(m)
    picks.sort(key=lambda x: -(x["momentum_12_1"] or -9))
    breadth = None
    if "XLY" in sectors and "XLP" in sectors:
        n = min(len(sectors["XLY"]), len(sectors["XLP"]))
        ratio = [sectors["XLY"][-n + i] / sectors["XLP"][-n + i] for i in range(n)]
        breadth = {"xly_xlp_roc13": r(roc(ratio, 13), 3)}
    out = {
        "asof": now_iso(), "regime": regime.get("regime"), "quadrant": quadrant,
        "spy_above_40wma": (spy[-1] > sma(spy, 40)) if len(spy) >= 40 else None,
        "sector_ranking": ranking, "stocks": picks, "risk_appetite": breadth,
        "notes": ["Earnings dates are not automatic: check before concluding.",
                  "The quadrant-to-sector map is an example in config.json; adjust it."],
        "data_status": status.items,
    }
    finish(out, a.out, None if a.no_save else "stocks.json")


if __name__ == "__main__":
    main()
