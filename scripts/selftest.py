#!/usr/bin/env python3
"""Offline self-test: python3 selftest.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import alts  # noqa: E402
import btc  # noqa: E402
import portfolio  # noqa: E402
import regime  # noqa: E402
import review  # noqa: E402
import sheet  # noqa: E402
import stocks  # noqa: E402
from common import load_config, pctrank, roc, slope_pct, sma  # noqa: E402

CFG = load_config()
PASSED = 0


def check(name, cond, detail=""):
    global PASSED
    if not cond:
        print(f"FAILED: {name} {detail}")
        sys.exit(1)
    PASSED += 1


def lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def macro(bull=True, vix=None, hy=None):
    up = 1 if bull else -1
    def ser(v, f):
        return {"values": v, "freq": f}
    walcl = lin(6.0e6, 7.2e6, 80) if bull else lin(7.2e6, 6.0e6, 80)
    spx = lin(3000, 4500, 80) if bull else lin(4500, 3000, 80)
    xly = lin(100, 150, 80) if bull else lin(150, 100, 80)
    return {
        "WALCL": ser(walcl, "W"), "WTREGEN": ser([8.0e5] * 80, "W"), "RRPONTSYD": ser([300.0] * 300, "D"),
        "M2SL": ser([20000 * (1 + 0.005 * up) ** i for i in range(40)], "M"),
        "DTWEXBGS": ser(lin(125, 118, 300) if bull else lin(118, 125, 300), "D"),
        "DFII10": ser(lin(2.0, 1.5, 300) if bull else lin(1.5, 2.2, 300), "D"),
        "CPILFESL": ser([300 * (1.002 if bull else 1.006) ** i for i in range(40)], "M"),
        "PAYEMS": ser([150000 + (150 if bull else -100) * i for i in range(40)], "M"),
        "UNRATE": ser([4.0] * 40 if bull else lin(4.0, 5.0, 40), "M"),
        "ICSA": ser([220000] * 60 if bull else lin(220000, 320000, 60), "W"),
        "VIXCLS": ser([vix or (15 if bull else 38)] * 300, "D"),
        "BAMLH0A0HYM2": ser([hy or (3.0 if bull else 8.0)] * 300, "D"),
        "T10Y2Y": ser([0.5 if bull else -1.0] * 300, "D"),
        "SPX": ser(spx, "W"), "XLY": ser(xly, "W"), "XLP": ser([100] * 80, "W"),
    }


def test_transforms():
    xs = list(range(1, 101))
    check("sma", sma(xs, 10) == 95.5)
    check("roc", abs(roc(xs, 10) - (100 / 90 - 1)) < 1e-9)
    check("slope", slope_pct(xs, 4, 10) > 0)
    check("pctrank", pctrank(xs) == 1.0)


def test_regime():
    bull, _ = regime.compute(macro(True), CFG, None)
    check("regime bull", bull["regime"] == "Risk-on", str(bull["composite"]))
    check("quadrant bull", bull["quadrant"] == "growth_up_inflation_down", str(bull["quadrant"]))
    bear, _ = regime.compute(macro(False), CFG, None)
    check("regime bear", bear["regime"] in ("Defensive", "Risk-off"), bear["regime"])
    check("tilt present", "crypto" in bear["tilt"])
    # hysteresis: one bad reading without an emergency does not change the regime
    calm_bear = macro(False, vix=28, hy=5.0)
    prev = {"confirmed": "Risk-on", "last_zone": "Risk-on"}
    out, st = regime.compute(calm_bear, CFG, prev)
    check("zone drops", out["zone_now"] in ("Defensive", "Risk-off"), out["zone_now"])
    check("hysteresis holds", out["regime"] == "Risk-on" and not out["regime_changed"], out["regime"])
    prev2 = {"confirmed": "Risk-on", "last_zone": out["zone_now"]}
    out2, _ = regime.compute(calm_bear, CFG, prev2)
    check("hysteresis switches after 2", out2["regime"] == out["zone_now"], out2["regime"])
    # emergency
    out3, _ = regime.compute(macro(False), CFG, prev)
    check("emergency", out3["regime"] in ("Defensive", "Risk-off") and out3["emergency_override"])
    # insufficient data
    thin, _ = regime.compute({"VIXCLS": {"values": [15] * 10, "freq": "D"}}, CFG, None)
    check("low coverage", thin["regime"] == "Insufficient data")
    # wrong units detected
    bad = macro(True)
    bad["WALCL"]["values"] = [v / 1e6 for v in bad["WALCL"]["values"]]
    o, _ = regime.compute(bad, CFG, None)
    check("wrong units noted", any("units" in n for n in o["notes"]))


def weekly(closes):
    return [{"c": c, "h": c * 1.03, "l": c * 0.97} for c in closes]


def test_btc():
    cfg = CFG["btc"]
    up = weekly(lin(20000, 70000, 260))
    mo = weekly(lin(20000, 70000, 60))
    regime_ok = {"regime": "Risk-on", "pillars": {"liquidity": 0.5}}
    onc = {"mvrv": 1.8, "mvrv_pct": 0.5, "realized_price": 30000, "asof": "2026-11-10"}
    fund = {"last": 0.0001, "pct": 0.4, "annualized": 0.1}
    eb = weekly(lin(0.03, 0.04, 60))
    o = btc.build(up, mo, onc, fund, eb, regime_ok, cfg, "test")
    check("btc markup", o["phase"] == "Markup", o["phase"])
    check("btc evidence 5/5", o["evidence"]["met"] == 5, str(o["evidence"]))
    check("btc alt_gate open", o["alt_gate"]["open"], str(o["alt_gate"]))
    check("btc invalidation present", o["invalidation"]["weekly_close_below_wma40"]["level"] > 0)
    down = weekly(lin(70000, 20000, 260))
    o2 = btc.build(down, weekly(lin(70000, 20000, 60)), onc, fund, eb, regime_ok, cfg, "test")
    check("btc markdown", o2["phase"] == "Markdown", o2["phase"])
    check("btc gate closed", not o2["alt_gate"]["open"])
    onc_hi = dict(onc, mvrv_pct=0.92)
    o3 = btc.build(up, mo, onc_hi, fund, eb, regime_ok, cfg, "test")
    check("btc distribution", o3["phase"] == "Distribution", o3["phase"])
    o4 = btc.build(up, mo, None, None, None, None, cfg, "test")
    check("btc missing data not invented", o4["evidence"]["known"] < 5 and o4["evidence"]["met"] <= o4["evidence"]["known"])
    check("btc short history", "error" in btc.build(up[:30], mo, None, None, None, None, cfg, "test"))


def test_alts_stocks():
    cfg = CFG["alts"]
    btc_c = lin(60000, 66000, 120)
    leader = {"c": lin(10, 16, 120), "v": [1000] * 100 + [3000] * 20}
    laggard = {"c": lin(10, 7, 120), "v": [1000] * 120}
    parabola = {"c": lin(10, 11, 116) + [14, 18, 24, 30], "v": [1000] * 120}
    rows = alts.analyze({"AAA": leader, "BBB": laggard, "CCC": parabola}, btc_c, cfg)
    ph = {x["symbol"]: x["phase"] for x in rows}
    check("alt exhausted", ph["BBB"] == "Exhausted", str(ph))
    check("alt late", ph["CCC"] == "Late", str(ph))
    check("alt strong leader", ph["AAA"] in ("Mid", "Early"), str(ph))

    scfg = CFG["stocks"]
    spy = lin(400, 450, 80)
    sec = {"XLK": lin(100, 140, 80), "XLU": lin(100, 95, 80)}
    rk = stocks.rank_sectors(sec, spy, scfg, "growth_up_inflation_down")
    check("sector order", rk[0]["sector"] == "XLK" and rk[0]["cycle_fit"] is True)
    check("sector XLU fit false", rk[1]["cycle_fit"] is False)
    check("stock momentum", stocks.stock_metrics(lin(50, 100, 80))["momentum_12_1"] > 0)


def test_sheet_portfolio_review():
    check("num comma", sheet.num("1,5") == 1.5 and sheet.num("1,234.5") == 1234.5 and sheet.num("$2") == 2.0)
    pos = sheet.positions([
        {"Aset": "btc", "Kelas": "crypto", "Jumlah": "0.5", "Harga Entry": "60000", "Invalidasi": "58000", "Tesis": "siklus"},
        {"Aset": "SOL", "class": "alt", "qty": "100", "entry": "150", "invalidation": "120"},
        {"asset": ""},
    ])
    check("positions", len(pos) == 2 and pos[0]["asset"] == "BTC" and pos[0]["invalidation"] == 58000.0)
    prices = {"BTC": 58500.0, "SOL": 110.0}
    out = portfolio.analyze(pos, prices, 1000.0, CFG, {"regime": "Defensive"}, {"peak": 60000})
    st = {p["asset"]: p["invalidation_status"] for p in out["positions"]}
    check("invalidation near/hit", st == {"BTC": "NEAR", "SOL": "HIT"}, str(st))
    check("posture warning", any("guidance" in f for f in out["warnings"]))
    check("no sizing", "sizing" not in json.dumps(out).lower() and "position size" not in json.dumps(out).lower())
    check("equity", abs(out["equity_usd"] - (0.5 * 58500 + 100 * 110 + 1000)) < 1e-6)
    out2 = portfolio.analyze(pos, {"BTC": 58500.0}, 0.0, CFG, None, None)
    check("missing price reported", any("unavailable" in f for f in out2["warnings"]))
    out3 = portfolio.analyze(pos, prices, 0.0, CFG, None, {"peak": 100000})
    check("circuit breaker", out3["circuit_breaker"] in ("Caution", "Defensive"), out3["circuit_breaker"])

    rows = [
        {"asset": "BTC", "class": "crypto", "open_date": "2026-01-05", "close_date": "2026-03-02", "entry": "50000", "exit": "60000",
         "regime_at_entry": "Risk-on", "phase_at_entry": "Markup", "gate_open": "y", "followed_rules": "y"},
        {"asset": "SOL", "class": "alt", "open_date": "2026-02-02", "close_date": "2026-03-02", "entry": "100", "exit": "80",
         "regime_at_entry": "Neutral", "phase_at_entry": "Transition", "gate_open": "n", "followed_rules": "n"},
    ]
    s = review.stats(review.parse(rows), {"2026-01-05": 50000, "2026-03-02": 55000, "2026-02-02": 52000})
    check("review n", s["n"] == 2 and s["win_rate"] == 0.5)
    check("review discipline", s["discipline"]["followed_rules"] == 0.5 and s["discipline"]["opened_with_gate_closed"] == 0.5)
    check("review small sample", any("Small sample" in p for p in s["warnings"]))
    check("review vs btc", s["diff_vs_btc_hold"]["n"] == 2)


def test_cli():
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, POSITION_TRADER_STATE=d)
        fx = os.path.join(d, "macro.json")
        json.dump(macro(True), open(fx, "w"))
        p = subprocess.run([sys.executable, os.path.join(HERE, "regime.py"), "--fixture", fx], capture_output=True, text=True, env=env)
        check("cli regime", p.returncode == 0 and json.loads(p.stdout)["regime"] == "Risk-on", p.stderr[-300:])
        check("state saved", os.path.exists(os.path.join(d, "regime.json")))
        bfx = os.path.join(d, "btc.json.fx")
        json.dump({"weekly": weekly(lin(20000, 70000, 260)), "monthly": weekly(lin(20000, 70000, 60)),
                   "onchain": {"mvrv": 1.8, "mvrv_pct": 0.5, "realized_price": 30000, "asof": "x"},
                   "funding": {"last": 0.0001, "pct": 0.4, "annualized": 0.1}, "ethbtc": weekly(lin(0.03, 0.04, 60))}, open(bfx, "w"))
        p = subprocess.run([sys.executable, os.path.join(HERE, "btc.py"), "--fixture", bfx], capture_output=True, text=True, env=env)
        check("cli btc", p.returncode == 0 and json.loads(p.stdout)["phase"] == "Markup", p.stderr[-300:])
        check("btc reads regime.json", json.loads(p.stdout)["evidence"]["items"][1]["met"] is True)
        t = subprocess.run([sys.executable, os.path.join(HERE, "sheet.py"), "template", "--dir", os.path.join(d, "tpl")], capture_output=True, text=True, env=env)
        check("cli template", t.returncode == 0 and os.path.exists(os.path.join(d, "tpl", "Positions.csv")), t.stderr[-300:])
        row = subprocess.run([sys.executable, os.path.join(HERE, "sheet.py"), "row", "--tab", "Journal", "--json", '{"date":"2026-11-11","asset":"BTC"}'],
                             capture_output=True, text=True, env=env)
        check("cli row", row.returncode == 0 and json.loads(row.stdout)["row"][1] == "BTC", row.stderr[-300:])


if __name__ == "__main__":
    test_transforms()
    test_regime()
    test_btc()
    test_alts_stocks()
    test_sheet_portfolio_review()
    test_cli()
    print(f"OK: {PASSED} checks passed")
