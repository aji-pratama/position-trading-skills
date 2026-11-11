---
name: outlook
description: Weekly macro regime analysis for position trading (liquidity, USD and yields, growth x inflation, stress and risk appetite), plus a view on gold (XAUT) and USD/cash. Use when the user asks about the macro backdrop, the regime, "is the environment supportive of risk assets", or starts the weekly run.
---

# Outlook: macro regime

Run this first in the weekly run. The other modes read its output (`regime.json`).

## Steps

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/regime.py`. The script pulls FRED and Stooq, computes the four pillars, and writes `regime.json` to the state folder.
2. Read the JSON. **Always** report: `regime`, `composite`, each pillar's score, `quadrant`, `conflicts`, `regime_changed`, and `data_status`.
3. If any source `failed` or `coverage` is low, say plainly which pillars could not be assessed. Never fill in numbers from memory.
4. Use web search for the qualitative layer (not part of the score): the two-week event calendar (FOMC, CPI, NFP, PCE, BoJ), Fed communication tone, geopolitics and oil, crypto regulatory news. Cite sources.
5. Give a view on gold (XAUT) and USD/cash as macro assets, based on the USD/yield and growth x inflation pillars.

## Answer format

- One opening sentence: the regime and its direction versus last week.
- Pillar table: score, main driver, one line of meaning.
- Conflicts between pillars (if any) and what would resolve them.
- Risk calendar and short conditional scenarios ("if CPI beats expectations, which pillar shifts").
- Posture and tilt from the JSON (`posture`, `tilt`), presented as a view, not an instruction.
- Data status.

## Rules

- The regime changes only after two consecutive readings (hysteresis), except for the emergency override. Explain when `emergency_override` is active.
- Do not state position sizes or allocation percentages: those are the user's decisions. Posture is direction only.
- Thresholds and weights live in `config.json` and are still starting examples; remind the user if they ask "how accurate is this".
- Wrong FRED series units can corrupt net liquidity; if `notes` mentions units, report it.
