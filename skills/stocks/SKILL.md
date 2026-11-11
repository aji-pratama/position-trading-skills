---
name: stocks
description: US stock analysis for position traders: SPDR sector ranking by relative strength vs SPY, sector fit with the growth x inflation quadrant, and stock screening (12-1 momentum, trend, distance to the 52-week high). Use for questions about which sectors lead or to check specific stocks.
---

# Stocks: US sectors and stocks

## Steps

1. Make sure `regime.json` exists (`outlook` skill); the quadrant is used for sector cycle fit.
2. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stocks.py` (add `--tickers AAPL,MSFT` for stocks to check).
3. Report:
   - SPY above or below its 40WMA and risk appetite (XLY/XLP).
   - Sector ranking (RS at 13 and 26 weeks), which are above their 40WMA, and which have `cycle_fit`. A strong sector that does not fit the cycle is reported as a conflict, not ignored.
   - For stocks: 12-1 momentum, RS vs SPY, above 40WMA, distance to the 52-week high.
4. Use web search for earnings dates within the horizon, catalysts, and material news. The script does not fetch earnings.

## Rules

- For decisions, the ranking is recomputed monthly at most often; do not suggest rotating on a one-week change.
- The quadrant-to-sector map (`config.json`) is an example; say so if the user questions it.
- No position sizes or price targets. US stock tax treatment and broker access from Indonesia are not verified in this plugin; point the user to check them themselves.
- Report `data_status` (Stooq can fail for some symbols).
