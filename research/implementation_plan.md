# Execution Plan: PDE Alpha Research Paper

> **Paper Title:** *Alpha Generation in Indian Index Options: An Empirical Comparison of Crank-Nicolson PDE Solvers versus Retail Technical Indicators*

---

## Inventory: What Exists vs What Must Be Built

### ✅ Already Built & Paper-Ready

| Component | File | Status |
|---|---|---|
| Crank-Nicolson PDE Solver | [pde_solver.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/services/derivatives/pde_solver.py) | 200×200 grid, SuperLU, CFL guard. Ready. |
| BSM Analytical Pricer | [bsm_calculator.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/domain/services/bsm_calculator.py) | Full BSM + 5 Greeks + Newton-Raphson IV solver. Ready. |
| Technical Indicators (Domain) | [technical_indicators_engine.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/domain/services/technical_indicators_engine.py) | RSI, MACD, Bollinger Bands. **EMA bug must be fixed.** |
| Technicals Calculator (App) | [technicals_calculator.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/technicals_calculator.py) | RSI, MACD, BB, SMA, EMA, ATR, Pivots + signal classification. Correct EMA at L50-61. |
| Historical Data Export | [export_cli.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/scripts/export_cli.py) → [historical_research_exporter.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/historical_research_exporter.py) | Multi-day Excel export via yfinance. Extend to 180 days. |
| TimescaleDB Schema | [init_schema.sql](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/scripts/init_schema.sql) | TickData hypertable with 90-day retention already set. |
| Existing Unit Tests | [tests/unit/](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/tests/unit/) | 17 test files covering BSM, PDE, adapters, subscribers. |

### 🔴 Must Be Built

| Component | New File(s) | Purpose |
|---|---|---|
| Volatility Surface Builder | `domains/analytics/domain/services/volatility_surface.py` | Cubic spline IV interpolation across strikes to break circularity |
| Dynamic Friction Model | `research/models/friction_model.py` | Compute $\epsilon_t$ from bid-ask spread + STT + exchange fees |
| Data Collection Pipeline | `research/data/collect_historical.py` | Download 180 days of NIFTY/BANKNIFTY OHLC + option chain data |
| Backtesting Engine | `research/backtest/engine.py` | Vectorized strategy executor with equity curve tracking |
| Strategy Definitions | `research/backtest/strategies.py` | Three strategies: Baseline, Challenger A, Challenger B |
| Results Generator | `research/analysis/metrics.py` | Sharpe, Sortino, MDD, Profit Factor, Win Rate calculator |
| Statistical Tests | `research/analysis/robustness.py` | Walk-forward validation, Hansen's SPA test, friction stress test |
| Paper Plots | `research/analysis/plots.py` | Equity curves, comparison tables, VIX regime charts |

---

## Phase 0: Bug Fixes & Foundation (Day 1)

> **Goal:** Fix known issues before any research code touches the math engines.

### Task 0.1: Fix EMA Implementation in Domain Engine

**File:** [technical_indicators_engine.py L47-52](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/domain/services/technical_indicators_engine.py#L47-L52)

**Problem:** The `_ema()` function inside `calculate_macd()` uses convolution with exponential weights instead of the standard EMA recurrence. The application layer's `calculate_ema()` in [technicals_calculator.py L50-61](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/technicals_calculator.py#L50-L61) has the correct implementation.

**Fix:**
```python
# Replace the nested _ema function inside calculate_macd with:
def _ema(data: np.ndarray, window: int) -> np.ndarray:
    """Standard EMA: α = 2/(N+1), EMA_t = α·P_t + (1-α)·EMA_{t-1}"""
    alpha = 2.0 / (window + 1)
    ema = np.empty_like(data)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema
```

**Acceptance:** Run `pytest tests/unit/test_analytics_domain.py -v` — all tests pass. Manually verify that `calculate_macd([100]*50)` returns histogram ≈ 0.

### Task 0.2: Verify Data Retention Supports 180 Days

**File:** [init_schema.sql L28](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/scripts/init_schema.sql#L28)

**Status:** Already set to 90 days. For the paper, 180 days of OHLC candle data will be sourced directly from yfinance (not from TimescaleDB), so no schema change is strictly required. The TickData table's 90-day retention is sufficient for storing option chain snapshots during data collection.

**Action:** No change needed — yfinance will be the primary historical data source for the backtest.

---

## Phase 1: Volatility Surface Construction (Days 2-3)

> **Goal:** Build the cubic spline IV surface to break the volatility circularity problem.

### Task 1.1: Create Volatility Surface Domain Service

**New file:** `domains/analytics/domain/services/volatility_surface.py`

**Specification:**
```python
class VolatilitySurface:
    """
    Constructs a smooth implied volatility surface from discrete strike-level IVs
    using cubic spline interpolation. This surface provides model-implied σ for
    any strike, breaking the circularity of using a strike's own IV to price itself.
    """
    
    def __init__(self, strikes: List[float], ivs: List[float], spot: float):
        """
        Args:
            strikes: Strike prices with known market IVs
            ivs: Corresponding implied volatilities (as decimals, e.g., 0.15)
            spot: Current underlying spot price
        """
        # 1. Filter out invalid IV values (≤ 0 or NaN)
        # 2. Require minimum 5 valid strike-IV pairs
        # 3. Fit scipy.interpolate.CubicSpline through (strike, IV) pairs
        # 4. Store the fitted spline for fast lookup
    
    def get_surface_iv(self, strike: float) -> float:
        """
        Return the surface-interpolated IV for a given strike.
        This is the 'model' IV — distinct from the strike's own market-implied IV.
        """
    
    def get_mispricing(
        self, strike: float, market_price: float, spot: float,
        expiry_years: float, rate: float, option_type: str,
        dividend_yield: float = 0.0
    ) -> float:
        """
        Compute mispricing = C_market - C_PDE(surface_IV).
        Uses the surface IV (not the strike's own IV) as σ input to CN PDE.
        Returns positive value when market overprices vs model.
        """
```

**Key Design Decision:** The surface IV for strike $K_i$ is derived from the spline fitted through *neighboring* strikes' IVs. This means:
- For ATM strikes: surface IV ≈ market IV (small mispricing signal)
- For strikes deviating from the smooth smile: surface IV ≠ market IV (larger mispricing signal)
- This detects strikes whose IV is an outlier relative to the volatility smile — the exact inefficiency we want to capture.

**Acceptance:**
- Unit test: Fit surface to 10 known NIFTY strikes with IVs, verify `get_surface_iv()` output matches hand-calculated cubic spline values within 1e-4.
- Verify that mispricing for ATM strike is near zero, and deliberately perturbed OTM strikes show nonzero mispricing.

### Task 1.2: Add ATR Calculation to Domain Engine

**File:** [technical_indicators_engine.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/domain/services/technical_indicators_engine.py)

The domain engine is missing `calculate_atr()`. The application layer has a simplified version at [technicals_calculator.py L185-189](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/technicals_calculator.py#L185-L189) that only uses close-to-close differences (not true range with H/L/C).

**Add proper ATR to domain engine:**
```python
@staticmethod
def calculate_atr(
    highs: List[float], lows: List[float], closes: List[float], period: int = 14
) -> Optional[float]:
    """Calculate Average True Range using proper True Range formula."""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    # EMA smoothing over the last `period` TRs
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return float(round(atr, 4))
```

---

## Phase 2: Dynamic Friction Model (Day 4)

> **Goal:** Model realistic Indian market trading costs that adapt to market conditions.

### Task 2.1: Create Friction Model

**New file:** `research/models/friction_model.py`

**Specification:**
```python
@dataclass(frozen=True)
class FrictionEstimate:
    stt: float          # Securities Transaction Tax
    exchange_fee: float  # NSE exchange transaction charge
    stamp_duty: float    # Stamp duty
    gst: float           # GST on (brokerage + exchange)
    brokerage: float     # Broker commission (0 for discount brokers)
    spread_cost: float   # Half bid-ask spread (market impact)
    total_one_way: float # Sum of all above
    total_round_trip: float  # Buy + Sell

class IndianOptionsFrictionModel:
    """
    Dynamic transaction cost model for NSE index options.
    All rates sourced from SEBI/NSE published statutory rates.
    """
    STT_SELL_RATE = 0.000625      # 0.0625% on sell side premium turnover
    EXCHANGE_CHARGE_RATE = 0.0005  # ~0.05% of premium turnover
    STAMP_DUTY_BUY_RATE = 0.00003  # 0.003% on buy side
    GST_RATE = 0.18                # 18% on (brokerage + exchange charges)
    SEBI_TURNOVER_FEE = 10 / 1e7   # ₹10 per crore
    
    def estimate(
        self, premium: float, bid: Optional[float] = None, 
        ask: Optional[float] = None, brokerage_per_order: float = 20.0,
        lot_size: int = 50
    ) -> FrictionEstimate:
        """
        Compute all-in friction for a single option trade.
        If bid/ask are unavailable, estimate spread as 0.5% of premium.
        """
    
    def compute_epsilon(
        self, premium: float, bid: Optional[float] = None,
        ask: Optional[float] = None, buffer_multiplier: float = 1.5
    ) -> float:
        """
        Compute the dynamic epsilon threshold for strategy execution.
        ε_t = round_trip_friction + buffer
        Only enter trade when |C_market - C_PDE| > ε_t
        """
```

**Acceptance:** For a ₹200 premium ATM NIFTY option:
- `total_round_trip` should be approximately ₹0.30–0.50 per unit (0.15–0.25%)
- `compute_epsilon()` should return ~₹0.45–0.75 with buffer

---

## Phase 3: Data Collection (Days 5-7)

> **Goal:** Collect 180 trading days of NIFTY and BANKNIFTY data for backtesting.

### Task 3.1: Historical Underlying Price Data

**New file:** `research/data/collect_historical.py`

**Data source:** yfinance (`^NSEI` for NIFTY 50, `^NSEBANK` for BANKNIFTY)

**Collect:**
- 180 trading days of daily OHLCV (High, Low, Close needed for ATR + Pivots)
- Store as Parquet files: `research/data/raw/nifty_daily_ohlcv.parquet`, `research/data/raw/banknifty_daily_ohlcv.parquet`

### Task 3.2: Historical Option Chain Data

**This is the hardest data problem.** yfinance does not provide historical Indian option chains. You have two options:

| Source | Pros | Cons |
|---|---|---|
| **A) Your own TimescaleDB TickData** | Already collecting via ingestion pipeline | Only 90 days max retention; need to start collecting NOW for future backtest |
| **B) NSE Bhav Copy / EOD Archives** | Free from NSE website, covers years of history | End-of-day only (no intraday), requires parsing |
| **C) Paid data vendor** (e.g., Global Data Feeds, TrueData) | Tick-level with bid/ask | Costs ₹5,000–15,000/month |

> [!IMPORTANT]
> **Recommended approach:** Use **Option B (NSE Bhav Copy)** for the paper backtest. NSE publishes daily option chain settlement data including strike prices, expiry dates, close prices, OI, and volume. This gives you EOD-level option chain snapshots for 180+ days at zero cost.
> 
> Simultaneously, start running your ingestion pipeline NOW to collect intraday TickData for a future follow-up paper or to validate EOD results against intraday dynamics.

**Collect from NSE Bhav Copy:**
- Download daily F&O Bhav Copy CSV files from [NSE Historical Data](https://www.nseindia.com/all-reports-listing) for the target 180-day window
- Parse into structured DataFrame: `[date, symbol, expiry, strike, option_type, close, settle_price, oi, volume]`
- Store as: `research/data/raw/nifty_option_chains.parquet`

### Task 3.3: Supplementary Data

- **India VIX:** Daily close from yfinance (`^INDIAVIX`) — needed for VIX regime segmentation
- **RBI Repo Rate:** Manual lookup from RBI website (changes ~4x/year, use step function) — this is `r` in BSM/PDE
- **NIFTY Dividend Yield:** From NSE index factsheet (~1.2–1.5%) — this is `q` in BSM/PDE

**Deliverable:** All raw data files in `research/data/raw/` as Parquet, ready for the backtest engine.

---

## Phase 4: Backtesting Engine (Days 8-12)

> **Goal:** Build a vectorized backtester that executes three strategies on historical data and records trade logs + equity curves.

### Task 4.1: Core Backtest Engine

**New file:** `research/backtest/engine.py`

```python
@dataclass
class Trade:
    entry_date: date
    exit_date: date
    symbol: str
    strike: float
    option_type: str  # "CE" | "PE"
    entry_price: float
    exit_price: float
    entry_signal: str  # Which signal triggered entry
    pnl_gross: float   # Before frictions
    pnl_net: float     # After frictions
    friction_paid: float
    holding_bars: int

@dataclass  
class BacktestResult:
    strategy_name: str
    trades: List[Trade]
    equity_curve: pd.Series     # Cumulative equity indexed by date
    daily_returns: pd.Series    # Daily percentage returns
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # Trading days
    profit_factor: float
    win_rate: float
    avg_win: float
    avg_loss: float
    total_trades: int
    total_friction_paid: float

class BacktestEngine:
    """
    Deterministic vectorized backtester.
    
    Rules:
    - Entry on signal bar's close price
    - Exit on next signal bar's close OR fixed holding period (configurable)
    - No lookahead bias: signals computed from data available at decision time
    - All trades include friction via IndianOptionsFrictionModel
    - Initial capital: ₹1,00,000
    - Position sizing: fixed fraction (5% of capital per trade)
    """
    
    def run(self, strategy: BaseStrategy, data: pd.DataFrame) -> BacktestResult:
        """Execute strategy over historical data and return results."""
```

### Task 4.2: Strategy Definitions

**New file:** `research/backtest/strategies.py`

#### Strategy 1: Baseline (Retail Technical Indicators)

```python
class RetailBaselineStrategy(BaseStrategy):
    """
    Entry: RSI < 30 (oversold) AND MACD histogram crosses above 0 (bullish crossover)
           → Buy ATM Call option
    
    Entry: RSI > 70 (overbought) AND MACD histogram crosses below 0 (bearish crossover)
           → Buy ATM Put option
    
    Exit: Opposite RSI signal, OR 5-bar holding period, OR 2% stop-loss
    """
```

Uses: [technicals_calculator.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/technicals_calculator.py) functions directly.

#### Strategy 2: Challenger A (Pure PDE Mispricing)

```python
class PDEMispricingStrategy(BaseStrategy):
    """
    For each strike in the option chain:
    1. Build volatility surface from all strikes' IVs (VolatilitySurface)
    2. Get surface IV for this strike
    3. Run CrankNicolsonPDE with surface IV → C_PDE
    4. Compute mispricing: δ = C_market - C_PDE
    5. Compute dynamic epsilon: ε_t from IndianOptionsFrictionModel
    
    Entry: δ < -ε_t (market underprices vs PDE model) → Buy the option
    Entry: δ > +ε_t (market overprices vs PDE model) → Sell/avoid the option
    
    Exit: Mispricing reverts to |δ| < ε_t/2, OR 5-bar holding period, OR 2% stop-loss
    """
```

Uses: [pde_solver.py](file:///c:/Users/pushk/Desktop/coding/MarketSentimentAnalysis2/domains/analytics/application/services/derivatives/pde_solver.py) + `VolatilitySurface` (Phase 1) + `IndianOptionsFrictionModel` (Phase 2).

#### Strategy 3: Challenger B (Hybrid Quant-Mental Filter)

```python
class HybridFilterStrategy(BaseStrategy):
    """
    Requires BOTH conditions to align:
    
    Entry (Long Call):
        - PDE mispricing: C_market < C_PDE - ε_t (option is undervalued)
        - AND MACD histogram > 0 (momentum confirming upward trend)
        - AND RSI < 65 (not already overbought)
    
    Entry (Long Put):
        - PDE mispricing: P_market < P_PDE - ε_t (option is undervalued)
        - AND MACD histogram < 0 (momentum confirming downward trend)  
        - AND RSI > 35 (not already oversold)
    
    Exit: Either signal condition breaks, OR 5-bar holding period, OR 2% stop-loss
    """
```

Uses: All three engines combined.

### Task 4.3: Walk-Forward Validation

**Implementation:** Rolling 60-day in-sample / 30-day out-of-sample windows.

```
Window 1: Train on days 1-60,   Test on days 61-90
Window 2: Train on days 31-90,  Test on days 91-120  
Window 3: Train on days 61-120, Test on days 121-150
Window 4: Train on days 91-150, Test on days 151-180
```

"Training" = calibrate strategy parameters (epsilon buffer, holding period, stop-loss percentage).
"Testing" = execute with frozen parameters and record results.

Final reported metrics = aggregate over all out-of-sample windows only.

---

## Phase 5: Statistical Analysis & Visualization (Days 13-15)

> **Goal:** Generate all tables, figures, and robustness checks for the paper.

### Task 5.1: Performance Metrics Calculator

**New file:** `research/analysis/metrics.py`

Compute for each strategy:

| Metric | Formula |
|---|---|
| Annualized Sharpe Ratio | $SR = \frac{\bar{R} - R_f}{\sigma_R} \times \sqrt{252}$ |
| Sortino Ratio | $Sortino = \frac{\bar{R} - R_f}{\sigma_{downside}} \times \sqrt{252}$ |
| Maximum Drawdown | $MDD = \max_t \left(\frac{\text{Peak}_t - \text{Trough}_t}{\text{Peak}_t}\right)$ |
| Profit Factor | $PF = \frac{\sum \text{Winning Trades}}{\sum |\text{Losing Trades}|}$ |
| Win Rate | $WR = \frac{N_{win}}{N_{total}}$ |
| Calmar Ratio | $Calmar = \frac{\text{Annualized Return}}{|MDD|}$ |

### Task 5.2: Robustness Checks

**New file:** `research/analysis/robustness.py`

1. **VIX Regime Segmentation:** Split results by India VIX quartiles (Q1: <12, Q2: 12-16, Q3: 16-22, Q4: >22). Report metrics separately per regime.

2. **Friction Stress Test:** Re-run backtest with 1×, 1.5×, 2×, 3× base friction costs. Plot Sharpe degradation curve.

3. **Hansen's Superior Predictive Ability (SPA) Test:** Bootstrap test to verify alpha is not from data snooping. Use `arch` Python package (`from arch.bootstrap import SPA`).

### Task 5.3: Paper Figures

**New file:** `research/analysis/plots.py`

Generate with matplotlib (already in requirements-dev.txt):

1. **Figure 1:** Equity curves for all 3 strategies on same axes (₹ vs trading days)
2. **Figure 2:** Drawdown profile chart (% drawdown vs time) for all 3 strategies
3. **Figure 3:** Mispricing distribution histogram — distribution of $(C_{market} - C_{PDE})$ across all observations
4. **Figure 4:** VIX regime performance heatmap — Sharpe ratio by strategy × VIX quartile
5. **Figure 5:** Friction stress test — Sharpe ratio degradation as friction multiplier increases
6. **Table 1:** Strategy comparison metrics (the main results table)
7. **Table 2:** Walk-forward per-window results
8. **Table 3:** VIX regime segmented results

Save all as high-DPI PNGs and LaTeX-compatible PDFs in `research/output/figures/`.

---

## Phase 6: Paper Writing (Days 16-21)

> **Goal:** Draft the complete LaTeX manuscript.

### Task 6.1: Manuscript Structure

**New file:** `research/paper/main.tex`

```
Section I:    Introduction & Motivation (1.5 pages)
Section II:   Literature Review (2 pages)
Section III:  Mathematical Framework (3 pages)
              - BSM closed-form with continuous dividend yield
              - CN PDE discretization scheme  
              - SuperLU factorization and O(M) complexity argument
              - Cubic spline volatility surface construction
              - Technical indicator formulas (RSI, MACD, Bollinger Bands)
Section IV:   Strategy Design (2 pages)
              - Baseline: Retail TA rules
              - Challenger A: PDE mispricing with dynamic ε_t
              - Challenger B: Hybrid filter
              - Position sizing, stop-loss, and exit rules
Section V:    Data & Experimental Setup (1.5 pages)
              - NSE NIFTY 50 / BANKNIFTY option chain data description
              - Indian statutory friction model (STT, exchange, stamp, GST)
              - Walk-forward validation protocol
Section VI:   Empirical Results (3 pages)
              - Main comparison table (Table 1)
              - Equity curves and drawdown charts
              - Per-window walk-forward results
Section VII:  Robustness & Sensitivity Analysis (2 pages)
              - VIX regime segmentation
              - Friction stress test
              - Hansen's SPA test for data-snooping
Section VIII: Conclusion & Practical Implications (1 page)
```

**Target:** 16–18 pages, suitable for submission to:
- *Journal of Computational Finance*
- *International Journal of Financial Engineering*
- *IEEE CIFEr* conference proceedings

---

## Phase 7: Validation & Submission (Days 22-25)

### Task 7.1: Reproducibility Check
- Ensure all scripts run end-to-end from raw data → figures → tables
- Create `research/README.md` with exact reproduction instructions
- Verify all random seeds are fixed for deterministic results

### Task 7.2: Preprint Submission
- Upload to SSRN or arXiv (q-fin.TR or q-fin.CP)
- Generate BibTeX citation for the preprint

---

## File Structure Summary

```
research/                           # NEW — all research paper code lives here
├── README.md                       # Reproduction instructions
├── data/
│   ├── collect_historical.py       # Phase 3: Data download script
│   └── raw/                        # Downloaded Parquet files
│       ├── nifty_daily_ohlcv.parquet
│       ├── banknifty_daily_ohlcv.parquet
│       ├── nifty_option_chains.parquet
│       ├── banknifty_option_chains.parquet
│       └── india_vix_daily.parquet
├── models/
│   └── friction_model.py           # Phase 2: Indian options friction model
├── backtest/
│   ├── engine.py                   # Phase 4: Core backtest executor
│   └── strategies.py               # Phase 4: Three strategy definitions
├── analysis/
│   ├── metrics.py                  # Phase 5: Sharpe, Sortino, MDD calculators
│   ├── robustness.py               # Phase 5: SPA test, VIX segmentation
│   └── plots.py                    # Phase 5: Figure generation
├── output/
│   ├── figures/                    # Generated PNGs and PDFs
│   ├── tables/                     # Generated LaTeX tables
│   └── trade_logs/                 # Per-strategy trade-level CSVs
├── paper/
│   └── main.tex                    # Phase 6: LaTeX manuscript
│
domains/analytics/domain/services/
├── volatility_surface.py           # Phase 1: NEW — cubic spline IV surface
├── technical_indicators_engine.py  # Phase 0: FIX — EMA bug in MACD
└── bsm_calculator.py              # EXISTING — no changes needed
```

---

## Timeline Summary

| Phase | Days | Deliverable | Dependencies |
|---|---|---|---|
| **Phase 0** | Day 1 | EMA bug fix, domain engine ATR | None |
| **Phase 1** | Days 2-3 | `VolatilitySurface` class with cubic spline + unit tests | Phase 0 |
| **Phase 2** | Day 4 | `IndianOptionsFrictionModel` with dynamic ε_t | None |
| **Phase 3** | Days 5-7 | 180-day NIFTY/BANKNIFTY OHLCV + option chain Parquet files | None (parallel with Phases 1-2) |
| **Phase 4** | Days 8-12 | Backtest engine + 3 strategies + walk-forward runs | Phases 0-3 |
| **Phase 5** | Days 13-15 | All metrics, robustness tests, figures, and tables | Phase 4 |
| **Phase 6** | Days 16-21 | Complete LaTeX manuscript draft | Phase 5 |
| **Phase 7** | Days 22-25 | Reproducibility check + preprint submission | Phase 6 |

**Total estimated calendar time: ~25 working days (5 weeks)**

---

## Open Questions For You

> [!IMPORTANT]
> **Decide these before starting Phase 3 (data collection):**
>
> 1. **Data source for option chains:** Do you want to use NSE Bhav Copy (free, EOD only) or a paid vendor (tick-level)? This affects the granularity of your backtest. EOD is sufficient for a publishable paper; intraday is a "nice to have."
>
> 2. **Backtest universe:** NIFTY 50 only, BANKNIFTY only, or both? Running both doubles the data work but significantly strengthens the paper's generalizability claim.
>
> 3. **Holding period:** The plan uses 5-bar default. Do you want to parameterize this (1, 3, 5, 10 bars) and report sensitivity? This adds ~1 day to Phase 4 but makes the paper more robust.
>
> 4. **Initial capital assumption:** ₹1,00,000 is used above. Confirm or adjust — this affects position sizing and therefore the number of simultaneous trades the strategy can take.
