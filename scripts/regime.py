#!/usr/bin/env python3
"""Macro regime score (weekly, confirmed monthly). Output: regime.json.

Usage:  python3 regime.py [--fixture f.json] [--out result.json] [--no-save]
Sources: FRED (public CSV, no API key) and Stooq. Source failures are reported in data_status.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Status, finish, http_get, load_config, load_state_json, mean, now_iso,  # noqa: E402
                    parse_fred, r, roc, sign, sma, state_dir, stooq_closes)

# (series, frequency): W weekly, D daily, M monthly
FRED_SERIES = {
    "WALCL": "W", "WTREGEN": "W", "RRPONTSYD": "D", "M2SL": "M", "DTWEXBGS": "D",
    "DFII10": "D", "CPILFESL": "M", "PAYEMS": "M", "UNRATE": "M", "ICSA": "W",
    "VIXCLS": "D", "BAMLH0A0HYM2": "D", "T10Y2Y": "D",
}
BACK13W = {"W": 13, "D": 65, "M": 3}


def fetch_all(status):
    data = {}
    for name, freq in FRED_SERIES.items():
        try:
            rows = parse_fred(http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={name}"))
            if not rows:
                raise ValueError("empty data")
            data[name] = {"values": [v for _, v in rows], "freq": freq, "last": rows[-1][0]}
            status.ok(name, f"last {rows[-1][0]}")
        except Exception as e:  # noqa: BLE001
            status.failed(name, e)
    for key, sym in {"SPX": "^spx", "XLY": "xly.us", "XLP": "xlp.us"}.items():
        c = stooq_closes(sym, "w", status, key)
        if c:
            data[key] = {"values": c, "freq": "W"}
    return data


def _vals(d, name):
    x = d.get(name)
    return x["values"] if x else None


def _back(d, name):
    return BACK13W[d[name]["freq"]]


def pillar_liquidity(d, cfg, notes):
    t = cfg["thresholds"]
    s_net = None
    for k in ("WALCL", "WTREGEN", "RRPONTSYD"):
        if k not in d:
            break
    else:
        u = cfg["units"]

        def net(i_w, i_d):
            return (d["WALCL"]["values"][i_w] * u["WALCL"] - d["WTREGEN"]["values"][i_w] * u["WTREGEN"]
                    - d["RRPONTSYD"]["values"][i_d] * u["RRPONTSYD"])
        try:
            now, prev = net(-1, -1), net(-14, -66)
            lo, hi = cfg["net_liquidity_sane_range"]
            if not (lo <= now <= hi):
                notes.append(f"Net liquidity {now:.3g} is outside the sane range; check units in config.regime.units. Signal ignored.")
            else:
                s_net = sign(now / prev - 1, t["netliq_roc13"])
        except IndexError:
            notes.append("Net liquidity history is too short.")
    m2 = _vals(d, "M2SL")
    s_m2 = sign(roc(m2, 3), t["m2_roc3"]) if m2 else None
    parts = [(s_net, 2), (s_m2, 1)]
    parts = [(s, w) for s, w in parts if s is not None]
    if not parts:
        return None, {}
    score = sum(s * w for s, w in parts) / sum(w for _, w in parts)
    return score, {"net_liquidity_signal": s_net, "m2_signal": s_m2}


def pillar_usd(d, cfg, notes):
    t = cfg["thresholds"]
    sig = {}
    if "DTWEXBGS" in d:
        v = d["DTWEXBGS"]["values"]
        x = roc(v, _back(d, "DTWEXBGS"))
        sig["dollar"] = -sign(x, t["dollar_roc13"]) if x is not None else None
    if "DFII10" in d:
        v = d["DFII10"]["values"]
        n = _back(d, "DFII10")
        if len(v) > n:
            sig["real_yield"] = -sign(v[-1] - v[-1 - n], t["real_yield_chg13"])
    vals = [x for x in sig.values() if x is not None]
    return (mean(vals) if vals else None), sig


def pillar_growth_inflation(d, cfg, notes):
    t = cfg["thresholds"]
    g = []
    detail = {}
    icsa = _vals(d, "ICSA")
    if icsa and len(icsa) >= 26:
        ratio = sma(icsa, 4) / sma(icsa, 26)
        g.append(-sign(ratio - 1, t["claims_ratio"]))
    un = _vals(d, "UNRATE")
    if un and len(un) > 3:
        g.append(-sign(un[-1] - un[-4], t["unrate_chg3"]))
    pay = _vals(d, "PAYEMS")
    if pay and len(pay) > 3:
        diffs = [pay[-i] - pay[-i - 1] for i in (1, 2, 3)]
        avg = sum(diffs) / 3
        g.append(1 if avg > t["payroll_3m_avg_k"] else (-1 if avg < 0 else 0))
    growth = mean(g)
    cpi = _vals(d, "CPILFESL")
    infl_up = None
    if cpi and len(cpi) > 3:
        ann = (cpi[-1] / cpi[-4]) ** 4 - 1
        detail["core_cpi_3m_annualized"] = r(ann)
        infl_up = ann > t["core_cpi_3m_ann_high"]
    if growth is None or infl_up is None:
        return None, detail
    growth_up = growth > 0
    quad = ("growth_up" if growth_up else "growth_down") + "_" + ("inflation_up" if infl_up else "inflation_down")
    score = {"growth_up_inflation_down": 1.0, "growth_up_inflation_up": 0.0,
             "growth_down_inflation_up": -1.0, "growth_down_inflation_down": 0.0}[quad]
    detail.update({"growth_signal": r(growth), "quadrant": quad})
    return score, detail


def pillar_risk(d, cfg, notes):
    t = cfg["thresholds"]
    sig = {}
    vix = _vals(d, "VIXCLS")
    if vix:
        sig["vix"] = 1 if vix[-1] < t["vix_low"] else (-1 if vix[-1] > t["vix_high"] else 0)
    hy = _vals(d, "BAMLH0A0HYM2")
    if hy:
        sig["hy_spread"] = 1 if hy[-1] < t["hy_low"] else (-1 if hy[-1] > t["hy_high"] else 0)
    cv = _vals(d, "T10Y2Y")
    if cv:
        sig["curve_2s10s"] = 1 if cv[-1] > t["curve_pos"] else (-1 if cv[-1] < t["curve_neg"] else 0)
    spx = _vals(d, "SPX")
    if spx and len(spx) >= 40:
        sig["spx_vs_40wma"] = 1 if spx[-1] > sma(spx, 40) else -1
    if "XLY" in d and "XLP" in d:
        a, b = d["XLY"]["values"], d["XLP"]["values"]
        n = min(len(a), len(b))
        if n > 13:
            ratio = [a[-n + i] / b[-n + i] for i in range(n)]
            sig["xly_xlp"] = sign(roc(ratio, 13), t["xly_xlp_roc13"])
    vals = [x for x in sig.values() if x is not None]
    return (mean(vals) if vals else None), sig


def zone_of(score, zones):
    if score >= zones["risk_on"]:
        return "Risk-on"
    if score >= zones["neutral"]:
        return "Neutral"
    if score >= zones["defensive"]:
        return "Defensive"
    return "Risk-off"


def compute(d, cfg_all, prev_state):
    cfg = cfg_all["regime"]
    notes = []
    pillars = {}
    detail = {}
    for name, fn in (("liquidity", pillar_liquidity), ("usd_yield", pillar_usd),
                     ("growth_inflation", pillar_growth_inflation), ("risk", pillar_risk)):
        score, det = fn(d, cfg, notes)
        pillars[name] = r(score)
        detail[name] = det

    w = cfg["weights"]
    avail = {k: v for k, v in pillars.items() if v is not None}
    coverage = sum(w[k] for k in avail) / sum(w.values())
    if coverage < cfg["min_coverage"]:
        return {"regime": "Insufficient data", "composite": None, "pillars": pillars,
                "coverage": r(coverage, 2),
                "notes": notes + ["Data coverage is below the minimum; do not draw conclusions."],
                "detail": detail}, None

    composite = sum(avail[k] * w[k] for k in avail) / sum(w[k] for k in avail)
    zone = zone_of(composite, cfg["zones"])

    # emergency: extreme VIX/HY forces Defensive immediately
    emergency = False
    em = cfg["emergency"]
    vix = _vals(d, "VIXCLS")
    hy = _vals(d, "BAMLH0A0HYM2")
    if (vix and vix[-1] >= em["vix"]) or (hy and hy[-1] >= em["hy_spread"]):
        emergency = True

    # hysteresis: change regime only after two consecutive readings in the same zone
    prev_state = prev_state or {}
    prev_confirmed = prev_state.get("confirmed")
    prev_zone = prev_state.get("last_zone")
    if prev_confirmed is None:
        confirmed = zone
    elif zone == prev_confirmed:
        confirmed = prev_confirmed
    elif zone == prev_zone:
        confirmed = zone
    else:
        confirmed = prev_confirmed
    if emergency and confirmed in ("Risk-on", "Neutral"):
        confirmed = "Defensive"
        notes.append("Emergency override: VIX or HY spread crossed its threshold; regime lowered to Defensive.")

    conflicts = [k for k, v in avail.items() if abs(v) >= 0.3 and v * composite < 0]
    state = {"confirmed": confirmed, "last_zone": zone, "composite": r(composite), "asof": now_iso()}
    out = {
        "asof": now_iso(),
        "regime": confirmed,
        "zone_now": zone,
        "composite": r(composite),
        "pillars": pillars,
        "coverage": r(coverage, 2),
        "quadrant": detail["growth_inflation"].get("quadrant"),
        "posture": cfg["posture"][confirmed],
        "tilt": cfg["tilt"][confirmed],
        "conflicts": conflicts,
        "regime_changed": (prev_confirmed is not None and prev_confirmed != confirmed),
        "previous_regime": prev_confirmed,
        "emergency_override": emergency,
        "detail": detail,
        "notes": notes,
    }
    return out, state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="JSON {name: {values:[...], freq:'W'}} for offline testing")
    ap.add_argument("--out")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config)
    status = Status()
    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            data = json.load(f)
        status.ok("fixture", a.fixture)
    else:
        data = fetch_all(status)
    prev = load_state_json("regime_state.json")
    out, state = compute(data, cfg, prev)
    out["data_status"] = status.items
    if state and not a.no_save:
        with open(os.path.join(state_dir(), "regime_state.json"), "w", encoding="utf-8") as f:
            json.dump(state, f)
    finish(out, a.out, None if a.no_save else "regime.json")


if __name__ == "__main__":
    main()
