# AlphaStreams Empirical Research: Methodology, Diagnostics & Verification Guide

> **Paper Title:** *Alpha Generation in Indian Index Derivatives: An Empirical Comparison of Crank-Nicolson PDE Solvers versus Retail Technical Indicators*  
> **Target Venue:** IEEE CIFEr / Journal of Computational Finance  
> **Underlying:** National Stock Exchange of India (NSE) NIFTY 50 Index Options  
> **Investigation Horizon:** 3.5 Years (January 2021 – June 2024)

---

## 1. Executive Summary & Purpose

This master documentation log records the entire empirical research lifecycle, validation experiments, and methodological corrections. It is written to serve as the direct reference text for drafting and refining the academic manuscript ([research/paper/main.tex](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2%20-%20Copy/research/paper/main.tex)).

---

## 2. Phase 0: Core Signal Diagnostics & Resolution of the Circularity Critique

### 2.1 The Critical Methodological Critique
Prior to expanding the backtesting horizon to 3.5 years, a rigorous review challenged the central premise of the PDE mispricing strategy:
1. **The Volatility Inversion Cycle**: Implied volatility ($\sigma_{\text{IV}}$) is inverted from market settlement prices using Black-Scholes.
2. **Spline Interpolation**: If a cubic spline $\sigma_{\text{surface}}(K)$ interpolates these points, $\sigma_{\text{surface}}(K) \equiv \sigma_{\text{IV}}(K)$ at the traded strikes.
3. **Repricing with PDE**: Repricing with a Crank-Nicolson PDE should theoretically reproduce market price with zero discrepancy, meaning any observed "mispricing" $(V_{\text{mkt}} - V_{\text{PDE}})$ could merely be **numerical discretization error** or **price-field / interest rate mismatches**.

### 2.2 Empirical Phase 0 Diagnostic Results (180 Trading Days)
We evaluated all 1,980 cross-sectional option chain records across the 180-day Period D dataset ([research/phase0_diagnostics.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2%20-%20Copy/research/phase0_diagnostics.py)).

#### Diagnostic Metric Summary:
| Diagnostic Dimension | Empirical Measurement | Academic Implication |
|---|---|---|
| **Circularity Error $|V_{\text{PDE}} - V_{\text{BSM}}|$** | Mean: ₹1.70, Median: ₹1.31, Max: ₹10.83, 95th%: ₹4.52 | 42.88% of option contracts experience numerical grid truncation error exceeding ₹1.65 (half the typical entry threshold). |
| **Grid Error vs Signal Correlation** | Pearson: $-0.1354$, **Spearman Rank: $-0.9997$** | The rank-order of raw PDE call mispricing was heavily correlated with grid discretization error! |
| **Closed-Form BSM vs PDE Re-Run** | Original PDE (200×200): **+49.57%** (Sharpe 2.07)<br>Closed-Form BSM: **+36.63%** (Sharpe 1.59) | **Core edge survives!** Even with zero grid error, the strategy achieves +36.63% net return, confirming genuine alpha from smile mispricing and dynamic friction filtering, though ~13% return was numerical truncation artifact. |
| **Price-Field Audit (`SETTLE_PR` vs `CLOSE`)** | All Options: 55.49% mismatch, Mean Diff: ₹524.38<br>Traded Contracts: 18.93% mismatch | Inverting IV from `CLOSE` while trading against `SETTLE_PR` creates synthetic mean-reverting noise. Pipeline must use identical fields. |
| **ATM Put-Call Parity Residual** | Mean Residual: **+₹15.84**<br>Put Mispricing: **-₹11.28**, Call: **+₹4.57** | The -₹15 put bias is mathematically explained by $q=0$ carry error ($S - Ke^{-rT}$ vs $Fe^{-rT}$). Switching to Black-76 eliminates this bias completely. |
| **Daily Mark-to-Market Accounting** | Exit-only Step: Sharpe 2.07, Max DD 11.61%<br>True Daily MTM: **Sharpe 1.85, Max DD 15.07%** | Exit-only step accounting artificially smoothed drawdown. True daily MTM must be reported in the paper. |

---

## 3. Phase 1: Institutional Market Rules & Infrastructure Specifications

To guarantee institutional rigor across the full 3.5-year sample (January 2021 – June 2024), the following institutional models were built in [research/models/nifty_market_rules.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2%20-%20Copy/research/models/nifty_market_rules.py):

### 3.1 Date-and-Expiry-Dependent Lot Sizing
Per National Stock Exchange (NSE) circulars, contract lot sizes transition as follows:
- **Prior to July 2021 Expiry**: **75 units** (*NSE Circular NSE/FAOP/47035*). May and June 2021 expiries remained at 75.
- **July 2021 to June 2024 Expiry**: **50 units**.
- **July 2024 Expiry Onwards**: **25 units** (*NSE Circular NSE/FAOP/61582* dated April 26, 2024). Contracts existing on April 26, 2024 expiring in May and June 2024 maintained 50 units.
- **Backtest Standardization**: Rather than arbitrary "1-lot" scaling across changes (75 → 50 → 25), positions are sized by **fixed 50 units** (or reported on a per-unit basis) to maintain stationary risk profiles.

### 3.2 Time-Varying RBI Repo Rate Schedule
Replaces the static 6.50% assumption with the exact historical Monetary Policy Committee (MPC) resolution steps:
$$\begin{cases}
4.00\%, & \text{Jan 01, 2021} \le t < \text{May 04, 2022} \\
4.40\%, & \text{May 04, 2022} \le t < \text{Jun 08, 2022} \\
4.90\%, & \text{Jun 08, 2022} \le t < \text{Aug 05, 2022} \\
5.40\%, & \text{Aug 05, 2022} \le t < \text{Sep 30, 2022} \\
5.90\%, & \text{Sep 30, 2022} \le t < \text{Dec 07, 2022} \\
6.25\%, & \text{Dec 07, 2022} \le t < \text{Feb 08, 2023} \\
6.50\%, & \text{Feb 08, 2023} \le t \le \text{Jun 30, 2024}
\end{cases}$$

### 3.3 Statutory Fee & STT Evolution
- **Securities Transaction Tax (STT)** on option sell turnover:
  - $\le$ March 31, 2023: $0.0500\%$ (₹500 per ₹10 Lakhs premium)
  - April 01, 2023 – September 30, 2024: $0.0625\%$ (Finance Act 2023)
  - October 01, 2024 onwards: $0.1000\%$ (Union Budget 2024)
- **NSE Exchange Transaction Charges**: $0.050\%$ on premium turnover.
- **SEBI Turnover Charges**: ₹10 per crore ($0.0001\%$).
- **Stamp Duty**: $0.003\%$ on buy turnover.
- **GST**: $18\%$ on (Exchange Fees + SEBI Charges + Brokerage).
- **Brokerage**: Fixed ₹20 per order.

### 3.4 Black-76 Synthetic Forward Pricing Engine
To resolve dividend yield uncertainty and eliminate carry error:
1. **Synthetic Forward Extraction**: From European Put-Call Parity at ATM strike $K_{\text{ATM}}$:
   $$F_t = K_{\text{ATM}} + (C_{\text{ATM}} - P_{\text{ATM}}) e^{r_t T}$$
2. **Black-76 Valuation**:
   $$d_1 = \frac{\ln(F / K) + \frac{1}{2}\sigma^2 T}{\sigma \sqrt{T}}, \quad d_2 = d_1 - \sigma \sqrt{T}$$
   $$C = e^{-r_t T} [F N(d_1) - K N(d_2)], \quad P = e^{-r_t T} [K N(-d_2) - F N(-d_1)]$$

### 3.5 Execution Protocol ($i+1$ Lag & Liquidity Filters)
1. **Execution Lag**: Signals generated at Bar $i$ close are executed at Bar $i+1$ close (or next bar fill), eliminating look-ahead bias.
2. **Zero-Volume Filter**: If traded contracts at Bar $i+1$ equals zero, trade is rejected (no stale price fills).
3. **Fixed Horizon & Expiry Exit**: Positions held for $H=5$ bars, with mandatory square-off prior to contract expiration.
4. **No-Iteration Rule**: Parameters fixed during Period D development are frozen across Out-of-Sample Periods A, B, and C.

---

## 4. Manuscript Integration Map (Sections & Tables for `main.tex`)

| Section in Paper | Key Contribution & Data Source |
|---|---|
| **Section I (Intro) & Section II (Related Work)** | Incorporate SEBI 2023 study citation precisely (average loss of ₹1.1 lakh across 89% losing retail traders; transaction costs equal to 28% of net losses). |
| **Section III (Mathematical Model)** | Present the Black-76 forward derivation and cubic-spline surface formulation. |
| **Section III-C (Validation & Grid Diagnostics)** | Add the Phase 0 Circularity table showing $|V_{\text{PDE}} - V_{\text{BSM}}|$ error distribution, proving signal survives in closed form (+36.63%, Sharpe 1.59). |
| **Section IV (Statutory Friction Model)** | Detail dynamic $\epsilon_t$ formulation with time-varying STT, exchange charges, and RBI repo rate lookup. |
| **Section VI (Backtesting & Execution Engine)** | Detail the $i+1$ fill lag, true daily MTM accounting, and fixed 50-unit position sizing. |
| **Section VII (Results & Robustness)** | Report the headline 3.5-year out-of-sample results across Periods A, B, C, and re-run Period D. |

---

## 5. Phase 1 Empirical Results: Period D Upgraded Protocol

*Evaluated on Period D (October 2023 – June 2024, 180 trading sessions) under full institutional protocol with true daily mark-to-market accounting, fixed 50-unit sizing, and $i+1$ execution lag:*

| Strategy / Specification | Return (%) | Sharpe Ratio | Sortino Ratio | Max DD (%) | Win Rate (%) | Trades | Final Capital (INR) |
|---|---|---|---|---|---|---|---|
| **Retail Baseline (RSI+MACD, MTM)** | -5.58% | -0.03 | -0.04 | 19.57% | 50.00% | 38 | INR 94,417.87 |
| **Random Entry Baseline (1,000 Draws Mean)** | -18.86% | -1.62 | 0.00 | — | — | 41 | INR 81,142.26 |
| **Challenger A PDE (Original Step)** | +49.57% | 2.07 | 5.09 | 11.61% | 29.85% | 67 | INR 1,49,571.51 |
| **Challenger A PDE (True Daily MTM)** | +49.57% | 1.85 | 3.55 | 15.07% | 29.85% | 67 | INR 1,49,571.51 |
| **Challenger A PDE (Lag 1 + True MTM)** | **+11.33%** | **0.45** | **0.79** | **11.31%** | 24.39% | 41 | **INR 1,11,329.93** |

### Statistical Significance vs 1,000-Draw Monte Carlo Baseline
- **Random Baseline Distribution**: Mean Sharpe = $-1.62$, Standard Deviation = $0.98$, 95th Percentile Sharpe = $+0.10$.
- **Challenger Strategy Rank**: With Sharpe $0.45$ and net return $+11.33\%$, the strategy places in the **97.70th percentile** of random allocations ($p = 0.023$).
- **Core Conclusion**: Even after penalizing the strategy with an $i+1$ execution delay (giving the market a full session to mean-revert before fill) and full statutory frictions, the strategy demonstrates statistically significant positive alpha $(p < 0.05)$ relative to both retail momentum benchmarks and zero-intelligence random allocations.

> [!WARNING]
> **REVISED INTERPRETATION (post Phase 1 corrected pipeline, Period D only)**: The Sharpe of 0.45 and return of +11.33% from Period D under the corrected pipeline is a substantial reduction from the initial +49.57% (Sharpe 2.07). This degradation is primarily due to the $i+1$ execution lag cutting available trades from 67 to 41 (the signal mean-reverts quickly — the surface is re-calibrated daily). This is a structural property of the strategy that must be declared prominently.

---

## 6. Phase 2: Full 3.5-Year (2021–2024) Empirical Results

> [!CAUTION]
> **NULL RESULT FINDING**: The strategy that appeared to generate substantial alpha (+49.57%) over the 180-day development period does NOT hold up on the extended 3.5-year out-of-sample dataset. This is the correct, honest empirical finding and must be the primary conclusion of the paper.

### 6.1 Sub-Period Performance Summary (860 Trading Sessions)

| Sub-Period | Strategy | Return (%) | Sharpe | Sortino | Max DD (%) | Win Rate (%) | Trades |
|---|---|---|---|---|---|---|---|
| **Period A (2021 OOS)** | Pure Mispricing | **-26.44%** | -2.06 | -2.49 | 27.02% | 9.09% | 22 |
| **Period A (2021 OOS)** | Retail Baseline | **+8.74%** | +0.22 | +0.34 | 22.30% | 34.62% | 52 |
| **Period B (2022 OOS)** | Pure Mispricing | **+5.04%** | -0.01 | -0.01 | 10.32% | 39.13% | 23 |
| **Period B (2022 OOS)** | Retail Baseline | **-35.60%** | -0.74 | -1.03 | 41.86% | 23.91% | 46 |
| **Period C (Jan–Sep 2023 OOS)** | Pure Mispricing | **-11.28%** | -2.29 | -2.64 | 12.41% | 25.00% | 8 |
| **Period C (Jan–Sep 2023 OOS)** | Retail Baseline | **+3.92%** | 0.00 | 0.00 | 22.95% | 40.00% | 40 |
| **Combined OOS (A+B+C)** | Pure Mispricing | **-32.68%** | -1.09 | -1.44 | 33.73% | 24.53% | 53 |
| **Combined OOS (A+B+C)** | Retail Baseline | **-22.94%** | -0.24 | -0.35 | 58.56% | 32.61% | 138 |
| **Period D (Dev Sample)** | Pure Mispricing | **+0.17%** | -0.61 | -0.88 | 6.39% | 18.18% | 11 |
| **Period D (Dev Sample)** | Retail Baseline | **-4.58%** | -0.23 | -0.33 | 25.53% | 22.86% | 35 |
| **Full Sample (3.5 Years)** | Pure Mispricing | **-32.52%** | -0.97 | -1.29 | 34.82% | 23.44% | 64 |
| **Full Sample (3.5 Years)** | Retail Baseline | **-27.52%** | -0.18 | -0.26 | 58.56% | 30.64% | 173 |

### 6.2 VIX Regime Analysis (3.5 Years)

| VIX Regime | Strategy | Return (%) | Sharpe | Win Rate (%) | Trades |
|---|---|---|---|---|---|
| Low VIX (< 12.6) | Pure Mispricing | -10.17% | -1.31 | 11.11% | 9 |
| Low VIX (< 12.6) | Retail Baseline | **+38.91%** | +0.58 | 42.86% | 42 |
| Normal VIX (12.6–14.5) | Pure Mispricing | **+10.95%** | +0.81 | 45.45% | 11 |
| Normal VIX (12.6–14.5) | Retail Baseline | -9.80% | +0.10 | 28.57% | 35 |
| High VIX (> 14.5) | Pure Mispricing | -33.30% | -1.12 | 20.45% | 44 |
| High VIX (> 14.5) | Retail Baseline | -56.63% | -0.27 | 26.04% | 96 |

### 6.3 Dual Friction Stress Tests (3.5 Years)

| Multiplier | Protocol | Return (%) | Sharpe | Max DD (%) | Trades |
|---|---|---|---|---|---|
| 1.0× | ε Fixed | -32.52% | -0.97 | 34.82% | 64 |
| 1.0× | ε Scaled | -32.52% | -0.97 | 34.82% | 64 |
| 1.5× | ε Fixed | -37.01% | -0.97 | 34.82% | 64 |
| 1.5× | ε Scaled | -15.26% | -0.89 | 25.71% | 32 |
| 2.0× | ε Fixed | -41.49% | -0.97 | 34.82% | 64 |
| 2.0× | ε Scaled | -25.52% | -1.73 | 23.65% | 18 |
| 3.0× | ε Fixed | -50.47% | -0.97 | 34.82% | 64 |
| 3.0× | ε Scaled | -3.69% | -2.21 | 5.87% | 7 |

---

## 7. Diagnosis of the Period D Anomaly

### 7.1 Why Period D Showed +49.57% (Original Pipeline)
1. **Same-bar Execution**: Signal and fill on the same bar inflated returns by capturing intra-day mispricing reversals not realistically tradeable.
2. **Exit-only Step Accounting**: Sharpe was computed on a step function (zero-variance days), artificially inflating Sharpe from 1.85 (MTM) to 2.07.
3. **170 out of 180 Bhavcopies Already Cached**: Period D data was the development sample — parameters (ATM filter ±150 pts, 2-bar minimum hold, 1.5× buffer) were set using this data, constituting data snooping.
4. **SETTLE_PR vs CLOSE Inconsistency**: IV inversion used CLOSE but trades priced on SETTLE_PR — this creates artificial signal in markets where settlement-vs-close gaps are predictable.

### 7.2 Why the Signal Collapsed OOS
1. **Low Trade Count**: The $i+1$ lag drastically cuts trades (64 total across 3.5 years vs 67 in 180 days alone). Statistical noise dominates with 8–22 trades per period.
2. **2021 High-Liquidity / Low-VIX Environment**: Period A (9.09% win rate, -26.44%) suggests the spline-vs-PDE signal fires heavily in low-volatility regimes where bid-ask spreads are wide relative to mispricing.
3. **Normal VIX is the Only Profitable Regime**: The strategy earns +10.95% (Sharpe 0.81) only in the Normal VIX band (12.6–14.5), consistent with the 180-day finding, but this regime produced only 11 trades across 3.5 years.

---

## 8. Revised Paper Narrative & Contribution

### What the Paper Should Claim (Honest Framing)
1. **Primary Contribution (unchanged)**: The Phase 0 diagnostic framework is the scientific contribution — we demonstrate how to detect and quantify PDE grid circularity, carry-error bias, and execution-lag sensitivity in Indian derivatives research.
2. **Empirical Finding (revised)**: Over 180 days, a naïve same-bar PDE mispricing signal appeared to generate large alpha (+49.57%). Under a rigorous $i+1$ execution lag, consistent price fields, and true MTM accounting, this collapses to +11.33% (Sharpe 0.45) on the development period and **does not generalize** to the 3.5-year OOS sample (Combined OOS: -32.68%).
3. **The Normal VIX Opportunity**: The one consistent positive finding is that the strategy earns positive Sharpe exclusively in the Normal VIX band (12.6–14.5), suggesting the spline mispricing signal is informative specifically when implied volatility is stable enough for the surface fit to be reliable, but high enough to create meaningful deviations.
4. **Null Result is a Valid Contribution**: A rigorously documented failure to find persistent alpha in Indian index options after correcting methodology is publishable and valuable. It directly informs practitioners about the dangers of data snooping in short-window backtests.

### Revised Title Suggestion
> *"Mispricing Signals in Indian Index Options: Evidence from a Crank-Nicolson PDE Approach and Its Failure to Generalize Across Market Regimes (2021–2024)"*

Or (if keeping positive framing on the methodology):
> *"Diagnosing Alpha Illusions in Quantitative Derivatives Research: A Case Study in NSE NIFTY 50 Options"*

