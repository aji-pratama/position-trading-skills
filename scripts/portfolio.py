#!/usr/bin/env python3
"""Portfolio summary and compliance checks. ANALYSIS ONLY: no position sizing.

Usage:
  python3 portfolio.py --positions pos.json [--cash 1200] [--prices p.json] [--out result.json]
        [--reset-peak] [--no-save]
pos.json = output of `sheet.py positions`. Prices: Binance (crypto, XAUT), Stooq (stocks).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Status, finish, http_json, load_config, load_state_json, now_iso, r,  # noqa: E402
                    state_dir, stooq_closes)

RISK_CLASSES = ("crypto", "alt", "stock", "saham")


def fetch_price(pos, status):
    a, cls = pos["asset"], pos["class"]
    if cls in ("cash", "usd", "usdt", "stablecoin"):
        return 1.0
    try:
        if cls == "gold":
            sym = "XAUTUSDT"
            return float(http_json(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}")["price"])
        if cls in ("crypto", "alt"):
            p = float(http_json(f"https://api.binance.com/api/v3/ticker/price?symbol={a}USDT")["price"])
            status.ok(a, "binance")
            return p
        c = stooq_closes(f"{a.lower()}.us", "d", status, a)
        return c[-1] if c else None
    except Exception as e:  # noqa: BLE001
        status.failed(a, e)
        return None


def analyze(positions, prices, cash, cfg, regime, peak_state, today=None):
    pc = cfg["portfolio"]
    rows = []
    for p in positions:
        price = prices.get(p["asset"])
        qty = p.get("qty")
        value = price * qty if price is not None and qty is not None else None
        row = {"asset": p["asset"], "class": p["class"], "qty": qty, "entry": p.get("entry"), "price": price,
               "value": r(value, 2)}
        if price is not None and p.get("entry"):
            row["pnl_pct"] = r(price / p["entry"] - 1, 4)
        inv = p.get("invalidation")
        if price is not None and inv:
            dist = price / inv - 1
            row["invalidation"] = inv
            row["distance_to_invalidation"] = r(dist, 4)
            row["invalidation_status"] = "HIT" if price <= inv else ("NEAR" if dist <= pc["near_invalidation_pct"] else "safe")
        row["thesis"] = p.get("thesis")
        row["horizon"] = p.get("horizon")
        rows.append(row)

    values = [x["value"] for x in rows if x["value"] is not None]
    equity = sum(values) + (cash or 0)
    missing = [x["asset"] for x in rows if x["value"] is None]
    for x in rows:
        x["weight"] = r(x["value"] / equity, 4) if x["value"] is not None and equity else None

    by_class = {}
    for x in rows:
        if x["value"] is not None:
            by_class[x["class"]] = by_class.get(x["class"], 0) + x["value"]
    if cash:
        by_class["cash"] = by_class.get("cash", 0) + cash
    cls_w = {k: r(v / equity, 4) for k, v in by_class.items()} if equity else {}
    risk_share = sum(v for k, v in cls_w.items() if k in RISK_CLASSES)
    crypto_share = sum(v for k, v in cls_w.items() if k in ("crypto", "alt"))

    flags = []
    reg = (regime or {}).get("regime")
    guide = pc["posture_risk_share_guidance"].get(reg) if reg else None
    if guide is not None and risk_share > guide:
        flags.append(f"Regime {reg}: risk-asset share {risk_share:.0%} is above the guidance of {guide:.0%} (config).")
    lim = pc["limits"]
    if lim.get("max_single_asset_pct") is not None:
        for x in rows:
            if x["weight"] and x["weight"] > lim["max_single_asset_pct"]:
                flags.append(f"{x['asset']} {x['weight']:.0%} exceeds the single-asset limit of {lim['max_single_asset_pct']:.0%}.")
    if lim.get("max_crypto_pct") is not None and crypto_share > lim["max_crypto_pct"]:
        flags.append(f"Crypto {crypto_share:.0%} exceeds the limit of {lim['max_crypto_pct']:.0%}.")
    if lim.get("max_alt_pct") is not None and cls_w.get("alt", 0) > lim["max_alt_pct"]:
        flags.append(f"Alts {cls_w['alt']:.0%} exceed the limit of {lim['max_alt_pct']:.0%}.")
    if lim.get("min_cash_pct") is not None and cls_w.get("cash", 0) < lim["min_cash_pct"]:
        flags.append(f"Cash {cls_w.get('cash', 0):.0%} is below the minimum of {lim['min_cash_pct']:.0%}.")
    for x in rows:
        if x.get("invalidation_status") == "HIT":
            flags.append(f"{x['asset']}: price is at/below the invalidation level {x['invalidation']}. Review the thesis now.")
        elif x.get("invalidation_status") == "NEAR":
            flags.append(f"{x['asset']}: near invalidation ({x['distance_to_invalidation']:.1%}).")
    if missing:
        flags.append("Price unavailable for: " + ", ".join(missing) + " (total equity is incomplete).")

    peak = max((peak_state or {}).get("peak", 0), equity)
    dd = equity / peak - 1 if peak else None
    cb = cfg["portfolio"]["circuit_breaker"]
    status_cb = "Normal"
    if dd is not None:
        if dd <= -cb["defensive_dd"]:
            status_cb = "Defensive"
        elif dd <= -cb["caution_dd"]:
            status_cb = "Caution"
    return {
        "asof": now_iso(), "equity_usd": r(equity, 2), "cash_usd": cash, "regime": reg,
        "weights_by_class": cls_w, "risk_asset_share": r(risk_share, 4), "crypto_share": r(crypto_share, 4),
        "positions": rows, "peak_equity": r(peak, 2), "drawdown_from_peak": r(dd, 4),
        "circuit_breaker": status_cb,
        "peak_note": "The peak is computed from equity tracked here. If you add or withdraw capital, reset with --reset-peak so the drawdown is not misleading.",
        "warnings": flags,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", required=True)
    ap.add_argument("--cash", type=float, default=0.0)
    ap.add_argument("--prices", help="JSON {ASSET: price} to override / test without network")
    ap.add_argument("--reset-peak", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config)
    with open(a.positions, encoding="utf-8") as f:
        positions = json.load(f)["positions"]
    status = Status()
    if a.prices:
        with open(a.prices, encoding="utf-8") as f:
            prices = json.load(f)
        status.ok("prices", "manual override")
    else:
        prices = {p["asset"]: fetch_price(p, status) for p in positions}
    peak_state = None if a.reset_peak else load_state_json("equity_peak.json")
    regime = load_state_json("regime.json")
    out = analyze(positions, prices, a.cash, cfg, regime, peak_state)
    out["data_status"] = status.items
    if not a.no_save and out["equity_usd"]:
        with open(os.path.join(state_dir(), "equity_peak.json"), "w", encoding="utf-8") as f:
            json.dump({"peak": out["peak_equity"]}, f)
    finish(out, a.out)


if __name__ == "__main__":
    main()
