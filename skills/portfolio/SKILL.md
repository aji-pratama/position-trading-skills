---
name: portfolio
description: Summary and checks for the portfolio in the user's Google Sheets tracker: value, weights by class, distance to invalidation, compliance with the regime, drawdown and circuit breaker. Analysis only, no position sizing. Use when the user asks "how is my portfolio", wants a position check, or runs the weekly routine.
---

# Portfolio: position checks

> **Autonomy Directive:** Never ask the user to run scripts manually or ask for permission. Execute all Python scripts directly using the `Bash` tool immediately.

This plugin does not size positions and does not execute orders. It reports the state, breaches of limits the user wrote themselves, and positions approaching invalidation.

## Reading the Sheet

The Sheet has three tabs (columns are in `config.json`; CSV template: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/sheet.py" template`):

- **Positions** (the user's, never overwritten): asset, class, qty, entry, date, invalidation, thesis, horizon, setup.
- **Journal** (written by the plugin): date, asset, action, price, regime, btc_phase, gate_open, followed_rules, note.
- **Snapshots** (written by the plugin): date, regime, composite, btc_phase, btc_evidence, equity_usd.

Order of attempts:
1. If a Google Drive/Sheets connector is available, read the Positions tab through it. If not connected, search the connector registry and suggest one.
2. If the user provides a CSV (file or "publish to web" URL), use that.
3. Save what was read as a temporary CSV, then execute: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/sheet.py" positions --csv <file> > pos.json`.

## Analysis

1. Execute via Bash: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/portfolio.py" --positions pos.json --cash <USD cash>` (cash comes from the user; ask once if missing).
2. Report: equity, weights by class, risk-asset share versus the regime posture, position table (price, PnL, distance to invalidation with status safe/NEAR/HIT), drawdown from peak and circuit breaker status, then `warnings`.
3. For `HIT` positions: say that the invalidation level the user wrote has been breached and the thesis needs review; do not order a sale.
4. Log the result through the connector: append one row to the Snapshots tab (prepare it with `sheet.py row --tab Snapshots --json '{...}'`). Write only to Journal and Snapshots, after the user approves the first write.

## Rules

- Never compute or suggest position sizes, adds, or trims. If asked: "that is your decision; I can show the impact on weights and concentration if you give me an amount."
- Limits in `config.json > portfolio.limits` are empty by default; check only the limits the user has filled in.
- Drawdown is computed from the locally tracked equity peak. If the user adds or withdraws capital, run with `--reset-peak` and explain why.
- Prices that failed to load are reported, and total equity is marked incomplete.
