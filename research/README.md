# NIFTY Options Mispricing: Correction Audit

> **Paper:** *How an Apparent Options Alpha Disappears: A Correction Audit of a Model-Mispricing Strategy on NIFTY 50 Index Options* (`paper/main.tex`)
> **Underlying:** NSE NIFTY 50 index options, January 2021 – June 2024

An earlier draft reported large returns from buying options priced below a Crank-Nicolson / cubic-spline fair value. This package audits that result: it reproduces the original headline, removes one artifact at a time (grid error, zero-dividend carry bias, same-bar fills, positions marked against the wrong contract, exit-only accounting, stale prices), re-tests the frozen strategies on a rebuilt 3.5-year full option chain, and tests the mispricing signal on its own with a delta hedge. The corrected strategies show no per-trade edge; the signal reverts overnight but too little remains after a realistic fill to pay for costs.

**Results are not restated here.** Every number lives in generated files so that none can go stale:

| What | Where |
|---|---|
| Every number quoted in the paper | `output/paper/numbers.tex` (also `numbers.json`) |
| Paper tables (LaTeX + CSV) | `output/paper/tables/` |
| Paper figures | `output/paper/figures/` |
| Config, git commit, package versions, input SHA-256 | `output/paper/manifest.json` |
| Phase 0 diagnostics (original 180-session sample) | `output/phase0_diagnostics/` |
| Superseded pre-correction outputs (do not cite) | `output/legacy/` |

## Reproduce

```bash
# 1. (Only if rebuilding data) full chain + multi-expiry signal panel from NSE Bhavcopy files
python research/data/build_3_5_year_dataset.py --from-cache --bhavcopy-dir bhavcopy_cache

# 2. Every table, figure, number and the manifest
python research/reproduce_all.py --random-draws 500

# Re-render tables/figures/numbers from saved results without re-running backtests
python research/reproduce_all.py --tables-only
```

The derived panels needed for step 2 are committed in `data/raw/`; the 613 MB Bhavcopy cache is not (it is git-ignored) and is needed only for step 1 and the Phase 0 price-field audit.

## Layout

```text
research/
├── reproduce_all.py               # single entry point for all paper outputs
├── run_3_5y_experiments.py        # strategy executor + independent per-period runs
├── phase0_diagnostics.py          # grid error, price field, carry bias, MTM audit (180 sessions)
├── data/
│   ├── build_3_5_year_dataset.py  # Bhavcopy -> full chain + signal panels
│   └── raw/                       # committed panels (legacy 180-session, legacy 3.5y, v2 full chain)
├── models/                        # friction model, lot sizes, repo rate, STT schedule, Black-76
├── backtest/
│   ├── engine.py                  # contract-keyed daily MTM, metrics
│   └── strategies.py              # ORIGINAL strategy code (kept to reproduce the headline)
├── analysis/
│   ├── waterfall.py               # 180-session correction waterfall
│   ├── signal_test.py             # delta-hedged next-bar signal test
│   └── trade_stats.py             # bootstrap CIs, ex-largest-trade, matched random baseline
├── output/
└── paper/main.tex
```

## Key methodological choices

- Each period (A 2021, B 2022, C Jan–Sep 2023, D Oct 2023–Jun 2024) is an **independent backtest from fresh capital**; a continuous run is not sliced.
- Fills at the **next** session's close, on the signal's own contract, only if it traded; positions are marked daily on their own contract and squared off before expiry.
- Strategy rules (stops, κ, strike choice, RSI bands) were **frozen** before the 3.5-year test and have not been tuned since.
- Periods A–C have now been examined: any new signal variant tested on them must be reported as exploratory.
