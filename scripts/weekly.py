#!/usr/bin/env python3
"""Run the full weekly analysis cycle in one command: regime, btc, and stocks.

Usage:  python3 scripts/weekly.py
Output: Consolidated JSON summary for Claude to read in a single turn.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run_script(name, args=None):
    script_path = os.path.join(HERE, name)
    cmd = [sys.executable, script_path] + (args or [])
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(res.stdout)
    except Exception:
        return {"raw_output": res.stdout, "error": res.stderr}


def main():
    print("--- Running weekly macro regime (regime.py) ---", file=sys.stderr)
    regime = run_script("regime.py")

    print("--- Running BTC & crypto analysis (btc.py) ---", file=sys.stderr)
    btc = run_script("btc.py")

    print("--- Running US stocks sector ranking (stocks.py) ---", file=sys.stderr)
    stocks = run_script("stocks.py")

    summary = {
        "regime": regime.get("regime") if isinstance(regime, dict) else None,
        "composite": regime.get("composite") if isinstance(regime, dict) else None,
        "btc_price": btc.get("price") if isinstance(btc, dict) else None,
        "btc_phase": btc.get("phase") if isinstance(btc, dict) else None,
        "alt_gate": btc.get("alt_gate") if isinstance(btc, dict) else None,
        "raw_regime": regime,
        "raw_btc": btc,
        "raw_stocks": stocks,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

