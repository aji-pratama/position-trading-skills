<div align="center">

# 📈 Position-Trader Skills

**Cyclical, spot-only position trading analysis assistant for Claude**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-D97706?style=for-the-badge&logo=anthropic&logoColor=white)](https://claude.ai)
[![Version](https://img.shields.io/badge/Version-0.1.0-blue?style=for-the-badge)](./.claude-plugin/plugin.json)
[![Selftest Status](https://img.shields.io/badge/Selftest-47%20Passed-2ea44f?style=for-the-badge&logo=checkmarx&logoColor=white)](#-quick-start--installation)
[![License/Scope](https://img.shields.io/badge/Scope-Spot%20Only%20%7C%20Analysis%20Only-red?style=for-the-badge)](#-important-considerations--disclaimers)

<p align="center">
  A Claude plugin for position-trading analysis: <b>weekly-monthly</b>, <b>cyclical</b>, and <b>spot only</b>.<br />
  <i>Pure analysis engine • No sizing algorithms • No automated execution • Non-destructive Google Sheets integration</i>
</p>

---

</div>

> [!IMPORTANT]
> **Analysis only.** This plugin does not size positions, does not execute orders, and never overwrites your `Positions` tab in Google Sheets. All decisions remain strictly manual.

---

## 🧭 Skills Overview

| Skill | Icon | Focus & Purpose |
|---|:---:|---|
| `outlook` | 🌐 | **Macro Regime**: Liquidity (WALCL, RRP, TGA), USD & yields, growth × inflation, stress indicators, Gold, USD, and risk calendar. |
| `crypto` | ₿ | **Bitcoin & Alts**: BTC cycle phase, key levels, invalidation, on-chain valuation, 5-evidence checklist, `alt_gate`. Altcoins: Relative Strength vs BTC, market phase, and exhaustion signals. |
| `stocks` | 📊 | **US Equities**: SPDR sector ranking vs SPY, cycle alignment, and systematic stock screening. |
| `portfolio` | 💼 | **Portfolio Health**: Summary from Google Sheets, distance to invalidation, regime compliance check, and circuit breaker monitor. |
| `evaluate` | 🎯 | **Trade Evaluation**: "Evaluate this trade" flow (setup fit verdict + portfolio concentration impact, deliberately no sizing). |
| `review` | 🔍 | **Journal & Analytics**: Journal statistics, rule compliance metrics, performance vs BTC hold, and quarterly calibration proposals. |

> [!TIP]
> **Design Philosophy**: Skills are lightweight conversational frontends. All heavy, deterministic logic lives in `scripts/` powered strictly by **Python standard library** with JSON output (`regime.py`, `btc.py`, `alts.py`, `stocks.py`, `sheet.py`, `portfolio.py`, `review.py`, `common.py`).
>
> *Rule of thumb: A step done twice becomes a script.*

---

## 🚀 Quick Start & Installation

### 1️⃣ Install or Load Plugin

**Option A: Via Claude Code Marketplace (Recommended)**
Di dalam sesi Claude Code:
```text
/plugin marketplace add aji-pratama/position-trading-skills
/plugin install position-trader@position-trader-marketplace
```

**Option B: Via Local Directory Flag**
Jalankan Claude Code dengan flag direktori lokal:
```bash
claude --plugin-dir ./position-trader
```

### 2️⃣ Verify Environment (Offline Selftest)
Run the self-contained suite to verify logic without external API calls:
```bash
python3 scripts/selftest.py
# Output: OK: 47 checks passed
```

### 3️⃣ Typical Weekly Workflow
Run after the weekly candle close:
```text
Ask Claude:
1. "run outlook"   -> Analyze macro regime & liquidity
2. "run crypto"    -> Evaluate BTC phase & alt rotation gate
3. "run portfolio" -> Assess health, risk limits & invalidation distances
```

> [!NOTE]
> Persistent state files (`regime.json`, `btc.json`, hysteresis tracking, peak equity) are saved to `~/.position-trader/`. Override this path anytime with the `POSITION_TRADER_STATE` environment variable.

---

## 📋 Google Sheets Integration

Generate CSV starter templates ready for Google Sheets:
```bash
python3 scripts/sheet.py template --dir template
```

### Tab Architecture

| Tab | Managed By | Fields / Content |
|---|:---:|---|
| 📌 **`Positions`** | **User (Manual)** | `asset`, `class` (`crypto`\|`alt`\|`stock`\|`gold`\|`cash`), `qty`, `entry`, `date`, `invalidation`, `thesis`, `horizon`, `setup` |
| 📓 **`Journal`** | **Plugin (Appends)** | `date`, `asset`, `action`, `price`, `regime`, `btc_phase`, `gate_open`, `followed_rules`, `note` |
| 📷 **`Snapshots`** | **Plugin (Appends)** | `date`, `regime`, `composite`, `btc_phase`, `btc_evidence`, `equity_usd` |

> [!TIP]
> The Sheet is accessed via Claude's Google Drive / Sheets connector. The scripts store zero credentials and only normalize CSV payloads. If you don't use the connector, simply export the `Positions` tab as CSV and paste it into Claude. Indonesian column headers (`aset`, `kelas`, `jumlah`, etc.) are natively supported!

---

## ⚠️ Important Considerations & Disclaimers

> [!WARNING]
> Please review these operational boundaries before trading:

* 🎚️ **Heuristic Thresholds**: Weights in [`config.json`](file:///Users/aji/Projects/position-trader/config.json) are initial benchmarks and not universally calibrated. Always paper trade and test via the `review` skill first.
* 🏦 **FRED Liquidity Series**: Fed net liquidity series (`WALCL`, `WTREGEN`, `RRPONTSYD`) assume standard scaling units defined in `config.regime.units`. Out-of-bounds anomalies are flagged and excluded automatically.
* 🌐 **Network Dependencies**: Scripts fetch public data from FRED, Stooq, Binance, and Coin Metrics. When running inside restricted cloud environments, run locally in Claude Code if queries fail. Note that `btc.py` provides an automatic Coin Metrics fallback for Binance-restricted regions.
* 🔎 **Manual Context Ingestion**: Earnings releases, token unlock dates, alt narrative hype cycles, ETF net flows, and scheduled economic releases are identified by Claude via live web search rather than hardcoded APIs.
* 🚫 **Intentional Omissions**: No automatic sizing formulas, no 1%-risk rules, no automated order execution, and strictly no leverage/shorting.
* 🏛️ **Regulatory & Tax Notice**: Check local regulations (e.g., Indonesian crypto tax under PMK 50/2025 and OJK/Bappebti whitelists, US stock tax treatments).
* 📉 **Sample Size Caution**: Position trading generates low trade frequency; statistical significance in `review` will naturally reflect small-sample caveats.

---

## 🗺️ Suggested Next Steps

- [ ] **Backtesting**: Run historical backtests on BTC phase rules using point-in-time macro data prior to introducing new indicators.
- [ ] **Quarterly Calibration**: Keep parameter tuning to a quarterly cadence to avoid overfitting noise.
