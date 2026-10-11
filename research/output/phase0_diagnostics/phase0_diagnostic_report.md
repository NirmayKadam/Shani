# Phase 0 Diagnostic Report: Core Signal & Methodology Audit

## 1. The Circularity Check (|PDE - BS| at Surface Volatility)
- **Call |PDE - BS|**: Mean = 1.7030 INR, Median = 1.3073 INR, Max = 10.8328 INR
- **Put |PDE - BS|**: Mean = 1.7030 INR, Median = 1.3073 INR, Max = 10.8328 INR
- **Fraction with Error >= 1.65 INR**: Calls = 42.88%, Puts = 42.88%
- **Correlation with Strategy Mispricing**: Pearson = -0.1354 (Calls), -0.1200 (Puts)

## 2. Price-Field Consistency (SETTLE_PR vs CLOSE)
- **Mismatch Rate**: 55.49% across all options, 18.93% for traded options
- **Mean Difference**: 524.3765 INR (Max absolute diff: 24044.45 INR)

## 3. Closed-Form BSM vs PDE Re-run
- **PDE Solver (200x200)**: 67 trades, Net Return = 49.57%, Sharpe = 2.07
- **Closed-Form BSM**: 66 trades, Net Return = 36.63%, Sharpe = 1.59

## 4. Put-Call Parity & Carry Error
- **ATM Put-Call Parity Residual**: Mean = 15.8448 INR, Median = 13.2012 INR
- **ATM Mispricing**: Calls = 4.5692 INR, Puts = -11.2755 INR
- **Finding**: The -15 INR put bias is mathematically explained by no-dividend Black-Scholes carry ($S - K e^{-r T}$) vs forward ($F e^{-r T}$).

## 5. Daily Mark-to-Market Accounting
- **Exit-Only Step Sharpe**: 2.07 (Max DD: 11.61%)
- **True Daily MTM Sharpe**: 1.85 (Max DD: 15.07%)
