# Research: F&O Sentiment-Analytical Engine (Pivot)

This document outlines the strategic pivot to incorporate **Futures & Options (F&O)** analytics, Greeks calculation, and **Fair-Value Pricing** into the AlphaStreams. Current sentiment functionality (Phases 1-4) will act as an "overlay" filter for the quantitative engine.

---

## 🏗️ 1. The Core Greeks Engine (Math Layer)
Goal: Calculate the theoretical "Fair Value" of any Indian option strike using the **Black-Scholes-Merton (BSM)** model.

### Inputs Required (The 6 Constants)
1. **Spot Price (S)**: From Live Nifty/Stock Tick Ingestor.
2. **Strike Price (K)**: From Option Chain data.
3. **Time to Expiry (T)**: Calculated in years/days until expiry.
4. **Risk-Free Rate (r)**: Constant (e.g., 6.5% - 7% based on RBI T-Bills).
5. **Dividend Yield (q)**: Essential for indices like NIFTY to adjust for continuous dividends.
6. **Implied Volatility (σ)**: Back-calculated from market price per strike.

### BSM Formula Extension
We use the **Black-Scholes-Merton (BSM)** variant that adjusts the spot price for dividends:  
$d1 = \frac{\ln(S/K) + (r - q + \sigma^2/2)T}{\sigma\sqrt{T}}$  
$d2 = d1 - \sigma\sqrt{T}$  
$C = S e^{-qT} N(d1) - K e^{-rT} N(d2)$

### Solving the "Constant Volatility" Assumption
The standard BSM model assumes $\sigma$ is constant. However, we bypass this flaw by calculating the **Volatility Surface** (The "Volatility Smile"). We treat $\sigma$ as a variable that changes per strike ($K$) and maturity ($T$). Our **ML Layer** will then learn the patterns (the "Skew") of how this surface shifts over time relative to News Sentiment.

### Outputs (The Greeks)
* **Delta (Δ)**: Sensitivity to price changes.
* **Gamma (Γ)**: Speed of Delta change (Risk acceleration).
* **Theta (Θ)**: Sensitivity to time decay.
* **Vega (ν)**: Sensitivity to volatility changes.
* **Rho (ρ)**: Sensitivity to interest rate changes.

---

## ⚖️ 2. The Mispricing (Arbitrage) Algorithm
The primary goal is to **detect market inefficiency** by comparing the Theoretical Price ($P_{BS}$) vs the Live Market Price ($P_{Mkt}$).

* **UNDERVALUED ($P_{BS} > P_{Mkt}$)**: Potential Buying Opportunity.
* **OVERVALUED ($P_{BS} < P_{Mkt}$)**: Potential Writing (Selling) Opportunity.

---

## 🤖 3. ML-Enhanced "True" Fair Value (LSTM Engine)
While Black-Scholes provides the mathematical "floor," our **LSTM (Long Short-Term Memory)** model provides the "ceiling" by learning from historical market irrationality and news-driven shocks.

### A. Model Inputs (Feature Set)
The LSTM processes a sequence of the following vectors:
* **Quantitative:** `[Theoretical_Price, Delta, Gamma, Vega, Market_Price]`
* **Qualitative:** `[Sentiment_Polarity_SMA, News_Volume, Source_Authority]`
* **Microstructure:** `[Open_Interest_Change, Volume_Profile]`

### B. Fair-Value Correction Logic
Standard models assume efficiency. The LSTM is trained to predict the **"Residual Alpha"**:  
$P_{True} = P_{BS} + \text{LSTM}(\text{Greeks}, \text{Sentiment})$  
If Sentiment is +0.9 and the option is 5% underpriced, the LSTM determines if the market is likely to close that gap in the next 15 minutes.

### C. Multi-Scalar Resampling (Time-Bucketing)
To provide context, we use TimescaleDB's `time_bucket` to feed the model multiple resolutions:
1. **Yearly/Monthly Bucket:** Determines structural long-term market cycles.
2. **Weekly/Daily Bucket:** Determines the macro trend and mean-reversion levels.
3. **1-Minute Bucket:** The execution layer for catching the real-time mispricing signal.

---

## 📊 4. The Dashboard Vision
A real-time "F&O Heatmap" displaying:
1. **Option Chain Overlay**: Greeks per strike.
2. **Mispricing Column**: Visual RED/GREEN bars showing $|P_{BS} - P_{Mkt}|$.
3. **Sentiment Overlay**: Correlation between News-Flow and IV Expansion.
4. **Prediction Signal**: "Strong Buy (Undervalued + Bullish Sentiment)."

---

## 📰 5. Pivoted News Aggregation Strategy
For a professional F&O platform, simple stock-name matching isn't enough. We are upgrading the `NewsIngestor` logic:

### A. Macro-Economic Broadening
We will track "Master Keywords" that affect all F&O strikes:
* **Keywords:** `RBI Monetary Policy`, `Fed Interest Rates`, `Nifty Index`, `NSE India`.
* **Impact:** These news items provide a "Market Mood" coefficient that multiplies the individual stock sentiment.

### B. Sectoral Correlation
If a user is trading a BankNifty Option (e.g., HDFC Bank strike), the system will ingest news for the entire **Banking Sector**:
* **Logic:** If "ICICI Bank" and "Axis Bank" have bad news, it negatively weights the specific "HDFC Bank" signal even if HDFC news is neutral.

### C. Source Authority Weighting
We will implement a **Source-Tier System** in the Sentiment calculation:
* **Tier 1 (Weight 1.5):** Bloomberg, Reuters, Economic Times.
* **Tier 2 (Weight 1.0):** General News Aggregators.
* **Tier 3 (Weight 0.5):** Social Media/Reddit/Telegram (to be added in Phase 6).

---

## 🛡️ 6. The Consensus Score (Anti-Lobbying Filter)
To protect the system from "Lobbying" or "Paid News," we move from a single Sentiment Score to a **Consensus Weighted Score** across three data tiers.

### A. The 3-Factor Divergence Model
1. **Media Sentiment (33%)**: NewsAPI/FinBERT (Existing Layer).
2. **Crowd Sentiment (33%)**: Twitter/Reddit/Telegram scraper (Phase 6).  
3. **Institutional Logic (33%)**: Real price action, Bulk & Block deals, and OI (Open Interest) changes.

### B. Detecting Case Logic (Paid News Filter)
The LSTM uses a **Contradiction Threshold** to flag suspicious headlines:  
* **Rule 1:** If Media is Bullish (+0.9) but Institutional Logic is Bearish (-0.8) and Crowd is Neutral, the system flags the article as **"Potential Lobbying/Paid Content"** and ignores the buy signal.
* **Rule 2 (Golden Signal):** If all 3 tiers are synchronized (In Sync), the confidence multiplier is set to **2x**.

### C. Source Authority Weighting
As discussed, top-tier sources (Reuters, Bloomberg) receive a **1.5x Weighting**, while social media "rumors" are treated as a **0.5x Weighting** unless they are supported by a sudden **LTP (Last Traded Price)** breakout.

---

## 📅 7. Phased Implementation Timeline (Old vs New)
To ensure the pivot is successful, we are moving from a linear sentiment model to a complex multi-factor derivatives engine.

### Roadmap Comparison
| **Phase** | **OLD Plan** | **NEW Plan (Pivoted)** |
| :--- | :--- | :--- |
| **0-2 (Now)** | Basic Sentiment (Done) | **Upgrade Base (Sentiment + Consensus)** |
| **3** | Simple PCR/IV Calcs | **Greeks Engine (BSM Math)** |
| **4** | Generic Ticks | **High-Speed Option WebSockets** |
| **5** | Basic Dashboard | **LSTM Fair-Value Model** |
| **6** | *(None)* | **Alt-Data (Social/Institutional)** |
| **7** | *(None)* | **Advanced F&O Dashboard** |

### 🛡️ Architectural Strategy: Refactor First
We will prioritize **Refactoring Phases 1 & 2** before building Phase 3.  
**Rationale:** The "Greeks Engine" requires a sophisticated sentiment and macro-economic "Context" to be accurate. By upgrading the `NewsIngestor` and `SentimentScores` schema now, we guarantee that the math engine receives perfectly weighted data from Day 1, avoiding a massive rewrite in the future.

---

## 🎯 8. The Working Principle (The 4-Step Sniper)
This is the definitive operational sequence of the F&O Sentiment-Arbitrage Engine:

### Step 1: Parallel Data Ingestion
Two separate streams of data flow into the platform:
* **Qualitative (The News):** Financial news is ingested and scored by the FinBERT NLP model to generate a Sentiment Score (-1.0 to 1.0).
* **Quantitative (The Ticks):** Live market data (spot prices, option premiums, and volume) streams via WebSockets.

### Step 2: The Math Layer (Finding IV & Theoretical Price)
Before any ML happens, we apply traditional financial mathematics:
* **Calculating IV:** Whenever a live option premium ticks, the `MetricsComputer` uses SciPy solvers to back-calculate the **Implied Volatility (IV)** directly from the live market price.
* **Calculating BSM:** We take that IV—along with spot price, strike, time to expiry, risk-free rate, and dividend yield—and plug it into the **Black-Scholes-Merton (BSM)** formula.
* **Output:** This gives us the foundational **Theoretical Fair Value ($P_{BS}$)** and all **Greeks** (Delta, Gamma, Vega, etc.).

### Step 3: The ML Layer (The LSTM Correction)
Standard math models assume market efficiency; the LSTM identifies the irrationality:
* **The Inputs:** Combined Math vectors (Theoretical Price, Greeks, Market Price) and Qualitative vectors (Sentiment Score).
* **The Calculation:** The LSTM is trained to predict the **"Residual Alpha."** It calculates how much the market is irrationally mispricing the option based on current news-flow.
* **The Result:** The **True Fair Value ($P_{True}$)**.  
  *Formula: $P_{True} = P_{BS} + \text{LSTM}(\text{Sentiment Correction})$*

### Step 4: The Arbitrage Signal
Finally, the platform looks for exploitable inefficiencies:
* It compares the LSTM's **True Price** against the **Actual Market Price**.
* If **$P_{True} > P_{Market}$**, the system flags the option as **UNDERVALUED** (A high-probability buying opportunity).

---

## ⚠️ 9. Technical Edge Cases & Mitigations
F&O markets introduce brutal technical traps that must be handled in Phases 3 & 4.

### A. Math Solver Failures (`MetricsComputer.py`)
* **The Risk:** SciPy solvers (Newton-Raphson) often fail to converge for deep OTM/ITM options or those minutes from expiry.
* **The Fix:** Implement a fallback hierarchy. If the solver fails, interpolate IV from adjacent strikes or use the **Corrado-Miller** approximation to prevent pipeline stalling.

### B. WebSocket Resilience (`TickIngestor.py`)
* **The Risk:** Indian broker WebSockets often drop or burst "stale" data upon reconnection.
* **The Fix:** Implement exponential backoff for reconnections. Suppress `AnomalyDetector` triggers for the first 5 seconds after a reconnect to avoid false-positive volume sweeps.

### C. Message Queue Throughput (Celery/Redis)
* **The Risk:** Thousands of ticks per second will overwhelm a 1-task-per-tick Celery architecture.
* **The Fix:** Implement **Micro-Batching**. Collect ticks in a 250ms buffer and send a single array payload to the `MetricsComputer`.

---

## 🚀 10. Future Scalability (V2 Roadmap)
* **Discrete Dividends:** Upgrade BSM to **Binomial Trees** for individual stocks to handle lump-sum dividend payouts precisely.
* **Triggered LSTM Inference:** To save CPU, only run the LSTM inference at the 1-Minute bucket level or when the Anomaly Detector flags massive OI shifts.
* **Volatility Surface Smoothing:** Implement **Cubic Splines** across strikes to create a professional, smooth "Volatility Smile" and eliminate noise from single bad ticks.
