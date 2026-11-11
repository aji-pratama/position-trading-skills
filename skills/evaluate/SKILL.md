---
name: evaluate
description: The "evaluate this trade" flow: the user names an asset, level and thesis (e.g. "long BTC at 68k, cycle accumulation thesis"), and Claude assesses fit based on regime, phase, evidence, invalidation, and impact on portfolio concentration. Gives no position size.
---

# Evaluate: assess this trade

> **Autonomy Directive:** Never ask the user to run scripts manually or ask for permission. Execute all Python scripts directly using the `Bash` tool immediately.

Input from the user: asset, level under consideration, thesis, horizon. If one is missing, ask at most one question, then proceed with stated assumptions.

## Steps

1. Gather context for the asset (execute automatically via Bash; reuse results younger than a week):
   - All assets: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/regime.py" || python3 scripts/regime.py`.
   - BTC and alts: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/btc.py" || python3 scripts/btc.py`, then `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/alts.py" --coins <SYMBOL>` for alts.
   - Stocks: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/stocks.py" --tickers <TICKER>`.
   - Gold/XAUT and USD: the view from the USD/yield pillar in `regime.json`.
2. If the user gives an amount, execute `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/portfolio.py"` (see the `portfolio` skill) to show the **impact on weights and concentration**: the asset's new weight, risk-asset share, crypto share. Without an amount, skip this part.
3. Compose the assessment.

## Answer format

1. **Verdict**: Aligned / Mixed / Not aligned with the analysis, one sentence of reasoning. This is a fit assessment, not an order.
2. **Gates**: regime, phase (BTC) or `alt_gate`, and whether any are closed.
3. **Evidence**: what supports and what opposes the thesis, each with its numbers from the JSON.
4. **Invalidation**: the level and its distance from the level under consideration. If there is no clear invalidation level, say the thesis cannot be tested yet.
5. **Portfolio impact** (if an amount was given).
6. **Scenarios**: what would change the assessment (levels, macro data, events).
7. **Practical risks**: nearest event calendar, unlocks/earnings (web search, labeled), fees and taxes on the user's venue where relevant.
8. Data status.

## Rules

- No position sizes, price targets, or promised outcomes.
- Do not agree because the user sounds confident; assess the evidence. If the user's thesis conflicts with the data, say so clearly and show the data.
- Data that failed to load is reported as failed; unknown evidence is not counted as supportive.
- Log the assessment to the Journal (prepare the row with `sheet.py row --tab Journal`) only if the user allows it.
