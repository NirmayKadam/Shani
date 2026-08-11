# AlphaStreams — Commercialization, Corporate Setup & Quantitative Research Plan

This document outlines the strategic roadmap for transitioning **AlphaStreams V2** from a tested quantitative prototype into a registered corporate entity in Mumbai, India, executing proprietary capital testing under strict SEBI compliance, and publishing a formal quantitative finance research paper.

---

## 1. Executive Summary & Current Maturity

- **System Completion:** ~85–90% complete with full NSE option chain streaming, Black-Scholes-Merton (BSM) analytics, Crank-Nicolson PDE pricing, real-time technical indicators, and single-container event-driven architecture.
- **Immediate Objectives:**
  1. Register a legal corporate entity and open a corporate bank account in Mumbai, India.
  2. Implement execution safeguards and risk management kill switches for live testing with proprietary capital.
  3. Author and publish an empirical research paper comparing numerical PDE fair-pricing against standard retail technical indicators on Indian index options (NIFTY 50 / BANKNIFTY).

---

## 2. Legal Entity Incorporation & Corporate Banking (Mumbai, India)

```
                       ┌──────────────────────────────┐
                       │   MCA SPICe+ Incorporation   │
                       │   (ROC Mumbai, Maharashtra)  │
                       └──────────────┬───────────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
┌──────────────────────────────┐              ┌──────────────────────────────┐
│    Local Statutory Setup     │              │     Banking & Broker KYC     │
│  - BMC Gumasta (Shops Act)   │              │  - Corporate Bank (Current)  │
│  - Maharashtra P-Tax (PTRC)  │              │  - Corporate Demat / Trading │
│  - GSTIN (Reverse Charge)    │              │  - Static IP Whitelisting    │
└──────────────────────────────┘              └──────────────────────────────┘
```

### 2.1 Corporate Structure: Private Limited Company (Pvt Ltd)
- **Why Pvt Ltd:** Limited liability protection, separation of personal assets from trading risks, ability to hold intellectual property (IP), and eligibility for corporate trading accounts with tier-1 Indian brokerages.
- **Jurisdiction:** Registrar of Companies (ROC) Mumbai, Everest Building, 100 Marine Drive, Mumbai, Maharashtra 400002.

### 2.2 Incorporation Process (MCA SPICe+)
1. **Digital Signature Certificates (DSC):** Procure Class-3 DSC for at least 2 proposed Directors.
2. **Name Reservation (SPICe+ Part A):** Reserve an entity name (e.g., *AlphaStreams Quant Technologies Private Limited* or *NexusQuant Analytics Private Limited*).
3. **SPICe+ Part B Filing:**
   - **Memorandum of Association (MoA) & Articles of Association (AoA):** Specify main objects as *development of financial quantitative algorithms, software systems, and data analytics*.
   - **Statutory Identifiers:** Integrated generation of Corporate PAN, TAN, EPFO, and ESIC registrations.

### 2.3 Maharashtra & Mumbai Municipal Licenses
1. **BMC Gumasta License:** Online filing under the *Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act, 2017* via the Aaple Sarkar / BMC portal.
2. **Professional Tax (P-Tax):** Mandatory registration for Maharashtra employers:
   - **PTRC (Professional Tax Registration Certificate):** To deduct and remit employee professional tax.
   - **PTEC (Professional Tax Enrolment Certificate):** Payable by the company / directors.
3. **GST Registration (GSTIN):** Register for GST to claim Input Tax Credit (ITC) on cloud server hosting, broker APIs, market data feeds, and hardware infrastructure.

### 2.4 Corporate Banking & Broker Setup
1. **Current Account:** Open with a commercial bank (HDFC Bank, ICICI Bank, Kotak Mahindra Bank, or Axis Bank) using Certificate of Incorporation (COI), Board Resolution, PAN, and MOA/AOA.
2. **Corporate Trading & Demat Account:**
   - Open corporate algorithmic/F&O trading account with an API-enabled broker (Zerodha Corporate, Interactive Brokers India, AngelOne SmartAPI, or specialized prop desk technology providers).
   - Configure static IP address whitelisting and enforce hardware-backed token security for API gateways.

---

## 3. Regulatory & Legal Boundaries (SEBI Compliance)

> [!IMPORTANT]
> **Strict Operational Boundary:** Operating purely with internal **Proprietary Capital** does not require a SEBI Portfolio Manager (PMS) or Investment Adviser (RIA) license. Managing third-party funds or issuing advisory signals without proper licensing is strictly prohibited under SEBI regulations.

```
┌──────────────────────────────────────────────┬──────────────────────────────────────────────┐
│         PROPRIETARY TRADING (ALLOWED)        │        EXTERNAL CAPITAL / SIGNALS (SEBI)     │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ • Trades company-owned balance sheet capital │ • Pooling client or investor funds           │
│ • No outside investor money accepted         │ • Requiring SEBI PMS / AIF Cat-III License   │
│ • No subscription fees for trade signals     │ • Selling buy/sell advisory (SEBI RA needed) │
│ • No public advisory / tip-sheet operations  │ • Regulated by SEBI (RA / IA / PMS) Rules    │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

### 3.1 Regulatory Classifications
- **Proprietary Trading:** Trading 100% company-owned capital. Free from retail advisory compliance, provided orders conform to exchange rate limits and broker API terms.
- **SEBI (Research Analysts) Regulations, 2014:** If signals, indicators, or recommendation services are sold to retail clients, registration as a SEBI Registered Research Analyst (RA) is legally mandatory (requires NISM-Series-XV certification and minimum net-worth criteria).
- **SEBI (Alternative Investment Funds) Regulations, 2012:** If raising outside capital for quantitative trading, an AIF Category III structure is required (minimum corpus ₹20 Crores, minimum ₹1 Crore per investor).

### 3.2 Indian Derivative Market Statutory Costs
All execution models and backtests must factor in statutory trading frictions:

| Charge / Friction | Rate / Basis | Impact on High-Frequency Options |
|---|---|---|
| **STT (Securities Transaction Tax)** | 0.0625% on option sell turnover / 0.125% on exercise | Major drag on intraday scalping |
| **Exchange Transaction Charges** | NSE: ~0.05% of premium turnover | Scales linearly with volume |
| **SEBI Turnover Fee** | ₹10 per ₹1 Crore turnover | Minor baseline cost |
| **Stamp Duty** | 0.003% on option buy turnover | Applied per transaction |
| **GST** | 18% on (Brokerage + Exchange fees) | Significant on multi-leg strategies |

---

## 4. Real-Money Risk Management & Execution Architecture

```
                    ┌──────────────────────────────┐
                    │   AlphaStreams Risk Engine   │
                    └──────────────┬───────────────┘
                                   │
      ┌────────────────────────────┼────────────────────────────┐
      ▼                            ▼                            ▼
┌──────────────┐             ┌──────────────┐             ┌──────────────┐
│ Daily Equity │             │ Position Size│             │ Hard Kill    │
│ Drawdown Cap │             │  per Strike  │             │   Switch     │
│   (Max 2%)   │             │   (Max 5%)   │             │ (REST/Hook)  │
└──────────────┘             └──────────────┘             └──────────────┘
```

### 4.1 Automated Safeguards (Pre-Trade Risk Engine)
1. **Hard Maximum Daily Drawdown:** If the portfolio equity declines by **2.0%** in a single trading session, the risk engine immediately halts new orders, cancels all pending orders, and gracefully liquidates open positions.
2. **Single-Strike Exposure Cap:** Maximum capital allocated to any single strike price or expiry contract is capped at **5.0%** of total liquid margin.
3. **Defined-Risk Spreads Exclusively:** Prohibit naked short options during initial pilot trading. Execute defined-risk structures only (e.g., Vertical Spreads, Iron Condors, Calendar Spreads) to eliminate theoretical infinite gamma risk during overnight gap openings.
4. **Hardware / Software Kill Switch:** Dedicated FastAPI endpoint (`/v1/risk/kill-switch`) and independent CLI script to instantly invoke broker mass-cancellation APIs and cancel all WebSocket streams.
5. **Feed Latency & Heartbeat Monitor:** If broker market data WebSocket tick staleness exceeds **500 ms** or connection drops for > **3.0 seconds**, trading defaults to risk-off safe mode.

---

## 5. Quantitative Research Paper Blueprint

### 5.1 Working Title
> **"Alpha Over Heuristics: Numerical PDE Fair-Pricing vs Conventional Technical Indicators in Indian Index Derivatives"**

### 5.2 Core Hypothesis
- **Null Hypothesis ($H_0$):** Heuristic momentum and trend indicators (RSI, MACD, Bollinger Bands, Moving Average crossovers) generate risk-adjusted returns equal to or exceeding numerical PDE mispricing arbitrage on the National Stock Exchange of India (NSE).
- **Alternative Hypothesis ($H_1$):** Crank-Nicolson finite difference PDE pricing with calibrated implied volatility surfaces delivers statistically significant alpha, higher Sharpe/Sortino ratios, and reduced maximum drawdowns compared to retail heuristic indicators after full accounting for market frictions (STT, slippage, exchange fees).

### 5.3 Comparative Framework

```
                          ┌───────────────────────────────┐
                          │   Historical Tick Data Feed   │
                          │     (NSE NIFTY 50 Options)    │
                          └───────────────┬───────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
   ┌─────────────────────────────┐                 ┌─────────────────────────────┐
   │    Retail Baseline Models   │                 │    AlphaStreams PDE Model   │
   │  • RSI (14) Mean Reversion  │                 │  • 1D Crank-Nicolson Solver │
   │  • MACD Signal Crossover    │                 │  • Implied Vol Smile Spline │
   │  • Bollinger Band Squeeze   │                 │  • Mispricing Delta Edge    │
   └──────────────┬──────────────┘                 └──────────────┬──────────────┘
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                          ┌───────────────────────────────┐
                          │  Statistical & Alpha Metrics  │
                          │  - Sharpe, Sortino, Calmar    │
                          │  - Max Drawdown (MDD)         │
                          │  - White's Reality Check      │
                          │  - Post-STT Friction Drag     │
                          └───────────────────────────────┘
```

### 5.4 Empirical Methodology & Dataset
1. **Universe:** High-liquidity NSE NIFTY 50 and BANKNIFTY weekly and monthly option chains.
2. **Data Scope:** 1-minute historical tick records spanning 3 to 5 years (including high-VIX regimes like general elections/union budgets and low-VIX consolidation regimes).
3. **Data Hygiene:** Bid-ask bounce elimination, dividend yield adjustments, RBI repo rate term structure integration, zero-volume strike filtering.
4. **Baseline Models (Retail Heuristics):**
   - **Model A (Momentum):** RSI(14) overbought (>70) / oversold (<30) + 20/50 EMA crossover.
   - **Model B (Volatility Band):** Bollinger Bands (20, 2) breakout/reversion with ATR stop-loss.
   - **Model C (Moving Average Convergence):** Standard MACD (12, 26, 9) signal triggers.
5. **Proposed Model (AlphaStreams Analytical Engine):**
   - Discretization of the 1D Black-Scholes PDE via the unconditional stable **Crank-Nicolson scheme**.
   - Cubic spline interpolation across strike implied volatilities for accurate smile/skew pricing.
   - Theoretical edge trigger $\Delta = P_{\text{market}} - P_{\text{PDE}} > \text{Threshold}$ (calibrated dynamically to exceed the current bid-ask spread $+ 2 \times \text{friction}$).

### 5.5 Statistical Validation & Robustness Checks
- **Walk-Forward Optimization (WFO):** Rolling in-sample training and out-of-sample testing windows to eliminate lookahead bias.
- **White's Reality Check & Hansen's SPA Test:** Superior Predictive Ability (SPA) tests to prove alpha is not a result of data-snooping across multiple indicator parameters.
- **Transaction Cost Stress Testing:** Re-evaluate Sharpe ratio degradation at $1\times$, $2\times$, and $3\times$ base slippage and STT rates.

### 5.6 Proposed Paper Outline
1. **Section I: Introduction** — Retail option trading dynamics in the Indian derivative market; the dominance of heuristic technical indicators.
2. **Section II: Literature Review** — Shortcomings of classic BSM closed-form assumptions in discrete emerging markets; numerical finite difference PDE literature.
3. **Section III: Mathematical Formulation** — Crank-Nicolson discretization scheme, boundary condition enforcement, local volatility surface calibration.
4. **Section IV: Experimental Design & Data** — NSE option chain microstructure, tick data preprocessing, friction models.
5. **Section V: Empirical Results** — Comparative performance tables, drawdown profiles, win rates, and Sharpe/Sortino distribution.
6. **Section VI: Robustness & Sensitivity Analysis** — Regime shifts (high vs low India VIX), execution latency decay, transaction cost stress tests.
7. **Section VII: Conclusion & Practical Implications** — Quantifying the edge of quantitative PDE valuation over retail indicators.

---

## 6. Phased Milestone Roadmap

```
Week 1-2                 Week 3-4                 Week 5-6                 Week 7+
┌────────────────┐       ┌────────────────┐       ┌────────────────┐       ┌────────────────┐
│  MCA SPICe+    │──────▶│ Corporate Bank │──────▶│ Paper Trading  │──────▶│ Small Capital  │
│ Incorporation  │       │ & Broker KYC   │       │ & Risk Tests   │       │ Live Pilot     │
│ Backtest Core  │       │ Paper Draft    │       │ Preprint Post  │       │ Real Execution │
└────────────────┘       └────────────────┘       └────────────────┘       └────────────────┘
```

| Phase | Timeframe | Core Deliverables | Success Criteria |
|---|---|---|---|
| **Phase 1** | Week 1–2 | • File MCA SPICe+ for Pvt Ltd incorporation (Mumbai)<br>• Finalize backtesting pipeline for NSE NIFTY 1-min options | Certificate of Incorporation (COI) received; backtest engine benchmarked against RSI/MACD |
| **Phase 2** | Week 3–4 | • Open Current Bank Account & Corporate Broker Trading Account<br>• Draft Mathematical Formulation and Methodology sections of paper | Corporate bank account active; API credentials issued; draft paper text complete |
| **Phase 3** | Week 5–6 | • Execute 2 weeks of live dry-run (paper trading) via broker WebSocket<br>• Stress-test automated kill switches and latency monitors<br>• Upload preprint to SSRN / arXiv | Zero execution exceptions during simulated feed bursts; preprint submitted |
| **Phase 4** | Week 7+ | • Launch live pilot with initial proprietary capital (₹50,000 – ₹1,00,000)<br>• Validate real-world slippage against theoretical PDE edge predictions | Strategy executes within risk limits; real-world slippage aligns with backtest model |
