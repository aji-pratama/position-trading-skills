#!/usr/bin/env python3
"""BTC analysis: cycle phase, levels, invalidation, on-chain valuation, evidence, alt_gate. Output: btc.json.

Usage:   python3 btc.py [--fixture f.json] [--out result.json] [--no-save]
Sources: Binance spot (primary), Coin Metrics community (price fallback + on-chain), Binance futures (funding data only).
Spot only: funding is used as a crowding marker, never for execution.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Status, dist_ma, drawdown_from_max, finish, http_json, load_config,  # noqa: E402
                    load_state_json, now_iso, pctrank, r, roc, slope_pct, sma)

CM = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"


def binance_klines(symbol, interval, limit, status, key):
    try:
        rows = http_json(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")
        now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000
        rows = [x for x in rows if x[6] < now_ms]  # closed candles only
        out = [{"t": x[0], "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in rows]
        if not out:
            raise ValueError("empty")
        status.ok(key, f"{len(out)} {interval} candles")
        return out
    except Exception as e:  # noqa: BLE001
        status.failed(key, e)
        return None


def coinmetrics(metrics, start, status, key):
    try:
        url = f"{CM}?assets=btc&metrics={metrics}&frequency=1d&start_time={start}&page_size=10000"
        data = http_json(url, timeout=40)["data"]
        status.ok(key, f"{len(data)} days")
        return data
    except Exception as e:  # noqa: BLE001
        status.failed(key, e)
        return None


def group_closes(rows, keyfn):
    """rows: [(date, close)] daily -> last close per period; the running period is dropped."""
    groups = {}
    order = []
    for d, c in rows:
        k = keyfn(d)
        if k not in groups:
            order.append(k)
        groups[k] = c
    today_k = keyfn(dt.date.today())
    return [{"c": groups[k], "h": groups[k], "l": groups[k]} for k in order if k != today_k]


def load_price(status):
    wk = binance_klines("BTCUSDT", "1w", 1000, status, "binance_btc_1w")
    mo = binance_klines("BTCUSDT", "1M", 200, status, "binance_btc_1M")
    if wk and mo:
        return wk, mo, "binance"
    data = coinmetrics("PriceUSD", "2013-01-01", status, "coinmetrics_price")
    if not data:
        return None, None, None
    rows = [(dt.date.fromisoformat(x["time"][:10]), float(x["PriceUSD"])) for x in data if x.get("PriceUSD")]
    wk = group_closes(rows, lambda d: d.isocalendar()[:2])
    mo = group_closes(rows, lambda d: (d.year, d.month))
    status.stale("price", "Coin Metrics fallback: closes only, no high/low")
    return wk, mo, "coinmetrics"


def onchain(status):
    data = coinmetrics("CapMVRVCur,CapRealUSD,SplyCur", "2013-01-01", status, "coinmetrics_onchain")
    if not data:
        return None
    mv = [float(x["CapMVRVCur"]) for x in data if x.get("CapMVRVCur")]
    last = data[-1]
    realized = None
    if last.get("CapRealUSD") and last.get("SplyCur"):
        realized = float(last["CapRealUSD"]) / float(last["SplyCur"])
    if not mv:
        return None
    return {"mvrv": r(mv[-1], 3), "mvrv_pct": r(pctrank(mv), 3), "realized_price": r(realized, 0),
            "asof": last["time"][:10]}


def funding(status):
    try:
        rows = http_json("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=270")
        f = [float(x["fundingRate"]) for x in rows]
        status.ok("binance_funding", f"{len(f)} observations")
        return {"last": r(f[-1], 6), "pct": r(pctrank(f), 3), "annualized": r(f[-1] * 3 * 365, 3)}
    except Exception as e:  # noqa: BLE001
        status.failed("binance_funding", e)
        return None


def halving_info(cfg, today=None):
    today = today or dt.date.today()
    hs = [dt.date.fromisoformat(x) for x in cfg["halvings"]]
    last = max(h for h in hs if h <= today)
    days = (today - last).days
    return {"last_halving": last.isoformat(), "days_since": days, "months_since": round(days / 30.44, 1),
            "note": "Weak prior: use as context, not as a signal."}


def classify_phase(m, cfg):
    """BTC cycle phase. Example rules; calibrate through the review skill."""
    close, w40, slope, mv = m["close"], m["wma40"], m["wma40_slope4"], m.get("mvrv_pct")
    dist40 = close / w40 - 1
    if close < w40 and slope < 0:
        return "Markdown", "close below 40WMA and 40WMA falling"
    if dist40 >= cfg["euphoria_dist40"] or (mv is not None and mv >= cfg["euphoria_mvrv_pct"]):
        return "Distribution", "price far above 40WMA or MVRV at euphoria percentile"
    if close > w40 and slope > 0:
        return "Markup", "close above 40WMA and 40WMA rising"
    if close < w40 * (1 + cfg["accum_band"]) and (mv is None or mv < cfg["accum_mvrv_pct"]):
        return "Accumulation", "price near or below 40WMA with low valuation"
    return "Transition", "mixed signals"


def evidence(m, phase, regime, fund, cfg):
    """Five independent pieces of evidence. True/False/None (unknown). Analysis, not position sizing."""
    ev = []
    ev.append(("cycle_phase_supportive", phase in ("Accumulation", "Markup"), f"phase {phase}"))
    if regime:
        ok = regime.get("regime") in ("Risk-on", "Neutral") and (regime.get("pillars", {}).get("liquidity") or 0) > 0
        ev.append(("regime_and_liquidity", ok, f"regime {regime.get('regime')}, liquidity {regime.get('pillars', {}).get('liquidity')}"))
    else:
        ev.append(("regime_and_liquidity", None, "regime.json missing; run the outlook skill"))
    mm = m.get("mma10")
    ev.append(("structure", (m["close"] > m["wma40"] and m["monthly_close"] > mm) if mm else None,
               "weekly above 40WMA and monthly above 10MMA"))
    mv = m.get("mvrv_pct")
    ev.append(("fair_valuation", (mv < cfg["evidence_mvrv_pct_max"]) if mv is not None else None, f"MVRV percentile {mv}"))
    ev.append(("not_crowded", (fund["pct"] < cfg["funding_crowded_pct"]) if fund else None,
               f"funding percentile {fund['pct']}" if fund else "funding unavailable"))
    known = [e for e in ev if e[1] is not None]
    return {"items": [{"name": n, "met": v, "note": c} for n, v, c in ev],
            "met": sum(1 for e in known if e[1]), "known": len(known), "of": 5}


def build(wk, mo, onc, fund, ethbtc, regime, cfg, source, today=None):
    cw = [x["c"] for x in wk]
    cm = [x["c"] for x in mo]
    if len(cw) < 45 or len(cm) < 10:
        return {"error": "history too short for 40WMA/10MMA"}
    m = {
        "close": cw[-1], "monthly_close": cm[-1],
        "wma40": sma(cw, 40), "wma40_slope4": slope_pct(cw, 4, 40),
        "wma200": sma(cw, 200), "mma10": sma(cm, 10),
        "high20w": max(x["h"] for x in wk[-20:]), "low10w": min(x["l"] for x in wk[-10:]),
        "ath": max(cw), "mvrv_pct": onc["mvrv_pct"] if onc else None,
    }
    phase, basis = classify_phase(m, cfg)
    ev = evidence(m, phase, regime, fund, cfg)

    def pct_to(level):
        return None if not level else r(level / m["close"] - 1)

    reasons = []
    gate_open = True
    if not regime or regime.get("regime") not in ("Risk-on", "Neutral"):
        gate_open = False
        reasons.append("regime is not Risk-on/Neutral or has not been computed")
    if m["close"] < m["wma40"]:
        gate_open = False
        reasons.append("BTC below 40WMA")
    rot = roc([x["c"] for x in ethbtc], 12) if ethbtc and len(ethbtc) > 13 else None
    if rot is None:
        reasons.append("ETH/BTC unavailable (not evaluated)")
    elif rot <= 0:
        gate_open = False
        reasons.append("ETH/BTC not rising over 12 weeks: no rotation out of BTC yet")
    if fund and fund["pct"] >= cfg["funding_crowded_pct"]:
        gate_open = False
        reasons.append("BTC funding extreme")
    return {
        "asof": now_iso(), "price_source": source,
        "price": r(m["close"], 0), "phase": phase, "phase_basis": basis,
        "halving_cycle": halving_info(cfg, today),
        "levels": {"wma40": r(m["wma40"], 0), "mma10": r(m["mma10"], 0), "wma200": r(m["wma200"], 0),
                   "high20w": r(m["high20w"], 0), "low10w": r(m["low10w"], 0), "ath_close": r(m["ath"], 0),
                   "drawdown_from_ath": r(drawdown_from_max(cw)), "dist_to_wma200": r(dist_ma(cw, 200)) if len(cw) >= 200 else None},
        "invalidation": {
            "weekly_close_below_wma40": {"level": r(m["wma40"], 0), "distance": pct_to(m["wma40"])},
            "monthly_close_below_mma10": {"level": r(m["mma10"], 0), "distance": pct_to(m["mma10"])},
            "structural_wma200": {"level": r(m["wma200"], 0), "distance": pct_to(m["wma200"])},
        },
        "onchain": onc, "funding": fund,
        "eth_btc_roc12": r(rot),
        "evidence": ev,
        "alt_gate": {"open": gate_open, "closed_reasons": reasons},
        "scenarios": [
            f"Weekly close above {r(m['high20w'], 0)}: confirms trend continuation.",
            f"Weekly close below {r(m['wma40'], 0)}: intermediate trend broken; phase shifts to Markdown if the 40WMA is falling.",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture")
    ap.add_argument("--out")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config)["btc"]
    status = Status()
    regime = load_state_json("regime.json")
    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            fx = json.load(f)
        wk, mo, onc, fund, eb, src = fx["weekly"], fx["monthly"], fx.get("onchain"), fx.get("funding"), fx.get("ethbtc"), "fixture"
        regime = fx.get("regime", regime)
        status.ok("fixture", a.fixture)
    else:
        wk, mo, src = load_price(status)
        if not wk:
            finish({"error": "BTC price unavailable", "data_status": status.items})
            return
        onc = onchain(status)
        fund = funding(status)
        eb = binance_klines("ETHBTC", "1w", 60, status, "binance_ethbtc")
    out = build(wk, mo, onc, fund, eb, regime, cfg, src)
    out["data_status"] = status.items
    finish(out, a.out, None if a.no_save else "btc.json")


if __name__ == "__main__":
    main()
