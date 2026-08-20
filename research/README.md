# AlphaStreams Quantitative Derivatives Research Engine

> **Paper Title:** *Alpha Generation in Indian Index Derivatives: An Empirical Comparison of Crank-Nicolson PDE Solvers versus Retail Technical Indicators*  
> **Target Venue:** IEEE Conference on Computational Intelligence for Financial Engineering (CIFEr) / Journal of Computational Finance  
> **Underlying Asset:** National Stock Exchange of India (NSE) NIFTY 50 Index Options

---

## 1. Overview & Research Innovation

This research package bridges continuous-time financial mathematics (Crank-Nicolson Partial Differential Equations with SuperLU factorization) and empirical algorithmic execution. It answers a central question in derivatives microstructure:

> *Can theoretical mispricing signals derived from an $O(M)$ Crank-Nicolson numerical PDE engine generate tradable alpha after Indian statutory frictions compared to retail momentum indicators?*

### Core Architectural Inventions & Contributions

1. **Cubic-Spline Volatility Surface (`domains.analytics.domain.services.volatility_surface`)**: Solves the *volatility circularity problem* by fitting a natural cubic spline across cross-sectional strikes, providing an independent model volatility parameter $\sigma_{\text{surface}}(K)$.
2. **$O(M)$ SuperLU Sparse Factorization (`pde_solver.py`)**: Pre-factorizes the implicit tridiagonal coefficient matrix $\mathbf{A}$ via `scipy.sparse.linalg.splu` outside the temporal loop, reducing per-timestep solving complexity from $O(M^3)$ to linear $O(M)$.
3. **Dynamic Indian Statutory Friction Model (`research.models.friction_model`)**: Accounts for Securities Transaction Tax (STT: 0.0625% on sell turnover), NSE exchange fees (0.050%), stamp duty (0.003%), SEBI fees, GST (18%), and bid-ask spreads to derive dynamic execution thresholds $\epsilon_t$.
4. **The Hybrid "Quant-Mental" Filter (`research.backtest.strategies`)**: Combines mathematical PDE undervaluation with directional trend momentum (MACD histogram + RSI bounds) to eliminate false mean-reversion signals.

---

## 2. Directory Structure

```text
research/
├── README.md                           # This documentation guide
├── run_experiment.py                   # Master end-to-end experiment orchestrator
├── data/
│   ├── collect_historical.py           # Historical data & option chain panel builder
│   └── raw/
│       ├── nifty_daily_ohlcv.parquet   # 180-day NIFTY 50 OHLCV + indicators
│       ├── nifty_daily_ohlcv.csv
│       ├── nifty_option_chains.parquet # 1,980 cross-sectional option chain records
│       └── nifty_option_chains.csv
├── models/
│   └── friction_model.py               # IndianOptionsFrictionModel & dynamic epsilon
├── backtest/
│   ├── engine.py                       # Deterministic backtester & portfolio metrics
│   └── strategies.py                   # Retail Baseline, Pure PDE, and Hybrid Filter
├── analysis/
│   ├── metrics.py                      # Markdown & LaTeX comparison tabulators
│   ├── robustness.py                   # Friction stress tests & VIX regime analysis
│   └── plots.py                        # Publication-quality figure generator (PNG/PDF)
├── output/
│   ├── figures/                        # Generated 300 DPI charts (Fig 1 - 4)
│   ├── tables/                         # Generated CSV and LaTeX tables
│   └── trade_logs/                     # Individual per-trade execution audits
└── paper/
    └── main.tex                        # Full IEEE LaTeX manuscript draft
```

---

## 3. How to Reproduce All Results

Run the master experiment runner:

```bash
# Execute master backtest, sensitivity sweeps, and figure generation
python research/run_experiment.py
```

To run unit tests validating the domain mathematical engines:

```bash
pytest tests/unit/test_volatility_surface.py tests/unit/test_analytics_domain.py -v
```

---

## 4. Key Empirical Findings (Summary Table)

| Strategy | Total Return (%) | Sharpe Ratio | Sortino Ratio | Max Drawdown (%) | Profit Factor | Win Rate (%) | Total Trades | Final Capital (INR) |
|---|---|---|---|---|---|---|---|---|
| **Retail Baseline (RSI + MACD)** | -25.29% | -0.41 | -0.69 | 30.85% | 0.88 | 37.50% | 88 | INR 74,709.26 |
| **Challenger A (Pure PDE)** | -20.89% | -0.34 | -0.54 | 44.09% | 0.84 | 18.35% | 109 | INR 79,114.72 |
| **Challenger B (Hybrid Filter)** | **-1.23%** | **0.20** | **0.36** | 54.71% | **0.99** | **22.73%** | 88 | **INR 98,773.96** |

### High Volatility Regime Performance (India VIX > 15.8)

In elevated volatility regimes, the **Hybrid Quant-Mental Filter** achieved exceptional alpha:
- **Net Return:** **+53.27%**
- **Annualized Sharpe Ratio:** **3.69**
- **Sortino Ratio:** **12.64**
- **Win Rate:** **41.67%** (Avg Win INR 5,204.75 vs Avg Loss INR 1,548.84)
- Outperformed Retail Baseline ($-5.38\%$ return, Sharpe $0.00$) by over 58 percentage points.

---

## 5. Generated Figures

- `output/figures/fig1_equity_curves.png`: Cumulative equity curves across all strategies under statutory frictions.
- `output/figures/fig2_drawdown_profiles.png`: Peak-to-trough drawdown profiles.
- `output/figures/fig3_mispricing_distribution.png`: Empirical probability density of $(C_{\text{market}} - C_{\text{PDE}})$.
- `output/figures/fig4_friction_stress_test.png`: Sharpe ratio sensitivity curve under $1.0\times, 1.5\times, 2.0\times, 3.0\times$ statutory frictions.
