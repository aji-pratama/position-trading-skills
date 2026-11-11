---
name: crypto
description: Spot crypto analysis for position traders: BTC as the anchor (cycle phase accumulation/markup/distribution/markdown, levels, invalidation, on-chain valuation, five-evidence checklist) and altcoins (relative strength vs BTC, phase, exhaustion). Use for questions about BTC, the cycle, alt season, or alt candidates.
---

# Crypto: BTC anchor and alts

> **Autonomy Directive:** Never ask the user to run scripts manually or ask for permission. Execute all Python scripts directly using the `Bash` tool immediately.

Spot only. Funding and open interest are crowding markers only, never for execution.

## BTC (always first)

1. Make sure `regime.json` exists in state directory. If missing, automatically execute `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/regime.py" || python3 scripts/regime.py` first.
2. Execute via Bash: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/btc.py" || python3 scripts/btc.py`. Output `btc.json`: `phase`, `phase_basis`, `halving_cycle`, `levels`, `invalidation`, `onchain`, `funding`, `evidence`, `alt_gate`, `scenarios`, `data_status`.
3. Report:
   - **Phase** and its basis. The phase rules are examples that need calibration; say so when the signal is mixed (`Transition`).
   - **Five evidence items** (`evidence.items`): supportive phase, regime and liquidity, weekly-monthly structure, valuation, not crowded. Show met out of known; an item that is `null` is written as "unknown", neither passed nor failed.
   - **Levels and invalidation**: 40WMA, 10MMA, 200WMA and their distances. State that invalidation is judged on weekly and monthly closes, not daily wicks.
   - Halving is context only (weak prior).
   - `alt_gate` and the reasons it is closed.

## Alts (only when `alt_gate` is open, or the user asks about specific coins)

1. Execute via Bash: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/alts.py" || python3 scripts/alts.py` (add `--coins SOL,LINK` for specific profiles; `--ignore-gate` only if the user asks to look despite a closed gate, and say so).
2. Report candidates (RS vs BTC at 4 and 12 weeks, phase, volume expansion, distance to the 10-week MA) and `warnings` (Late phase).
3. Complete with web search, because the script cannot: sector/narrative, token unlocks over the next 30 days, catalysts and listings, delisting or restriction risk on the user's venue. Label clearly what is script output and what is search output.

## Rules

- Never give position sizes, portfolio percentages, or profit targets.
- Coins younger than `min_age_weeks` are not candidates; do not force them.
- Report `data_status`. Binance may be blocked in some regions or in cloud workspaces; the BTC script has a Coin Metrics fallback (closes only). If everything fails, say so and do not guess prices.
