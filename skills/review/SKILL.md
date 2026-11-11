---
name: review
description: Monthly or quarterly review for position traders: closed-trade statistics from the Journal, results by regime and phase, rule compliance, comparison with BTC buy-and-hold, and config calibration proposals. Use when the user asks for a review, performance evaluation, or "is this system working".
---

# Review: journal and evaluation

> **Autonomy Directive:** Never ask the user to run scripts manually or ask for permission. Execute all Python scripts directly using the `Bash` tool immediately.

## Steps

1. Read closed trades from the Journal tab (via the Google Sheets connector, or a CSV from the user). Columns the script uses: asset, class, open_date, close_date, entry, exit, regime_at_entry, phase_at_entry, gate_open (y/n), followed_rules (y/n). If the user's Journal has a different shape, map the columns and state the mapping.
2. Execute via Bash: `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/review.py" --trades trades.csv`. For the BTC comparison, provide `--btc-json` with BTC prices on each trade's open and close dates (from `btc.py` or the user's data); if unavailable, run without it and say the comparison is missing.
3. Report trade count, win rate, average win and loss, profit factor, hold duration, results by regime, by BTC phase, by asset, rule compliance, and the difference versus BTC hold.

## Must be stated

- **Small sample.** Position trading yields few trades; below about 20 trades, every number is an indication. Say this before concluding anything.
- **Compliance first, results second.** Separate the results of trades that followed the rules from those that did not. Good results from rule-breaking trades are not evidence that the system works.
- **Regime validation.** Do results differ between regimes at entry? If not, the regime is not adding information yet.
- **Benchmark.** Beat BTC buy-and-hold on a risk-adjusted basis, or consider a simple rule instead (e.g. above the 40WMA).
- **Calibration proposals** for `config.json` are only proposed, never changed automatically, and only at the quarterly review. One change at a time, written with its reason before being tested.
- **Error taxonomy:** late entry, no invalidation, ignored the regime, premature exit.

## Rules

- Never invent trades or prices that are not in the data.
- Never suggest position sizes.
- Write the review summary to the Sheet only if the user allows it.
