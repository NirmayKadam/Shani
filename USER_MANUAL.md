# AlphaStreams Option Chain Analytics — User Manual

Welcome to **AlphaStreams Option Chain Analytics**. This dashboard replicates the official National Stock Exchange of India (NSE) equity derivatives option chain layout, enhanced with real-time derivative valuations, theoretical Black-Scholes-Merton (BSM) prices, and real-time Greek computations.

---

## Table of Contents
1. [Overview](#1-overview)
2. [Dynamic Instrument Search](#2-dynamic-instrument-search)
3. [Black-Scholes-Merton Control Panel](#3-black-scholes-merton-control-panel)
4. [Option Chain & Price Highlights](#4-option-chain--price-highlights)
5. [Strike Greeks Analysis](#5-strike-greeks-analysis)
6. [Data Export (.csv)](#6-data-export-csv)

---

## 1. Overview
The AlphaStreams dashboard combines live-updating market quotes with active pricing solvers. By comparing real-time market quotes (LTP) against theoretical option prices derived from the BSM model, the platform exposes market mispricings ("Theoretical Edge") for active option traders and risk managers.

---

## 2. Dynamic Instrument Search
Use the top autocomplete filter bar to scan active NSE instruments:
- **Autocomplete Suggestions:** As you type (e.g., `NIFTY`, `RELIANCE`, `TCS`), the system debounces query requests to retrieve matching symbols and names.
- **Selector Navigation:** Use `Up/Down` arrow keys and press `Enter` to resolve a search suggestion immediately.
- **Automatic Setup:** Selecting an instrument updates the Spot Price, Expiry list, Strike Price filters, and resets BSM sliders to standard local parameters.

---

## 3. Black-Scholes-Merton Control Panel
The interactive control panel recalculates Option Chain pricing and Greeks on-the-fly. Adjust these parameters:
* **Spot Price:** Underlying stock/index valuation. Scale using the fine-tuned slider.
* **Volatility (σ %):** Standard deviation of underlying asset returns. Represents market pricing of risk.
* **Days to Expiry (T):** Days remaining to derivative contract expiration.
* **Risk-Free Rate (r %):** The annualized risk-free rate of return (defaults to prevailing MIBOR or Treasury yields).
* **Dividend Yield (q %):** Annual continuous dividend payout percentage of index or stock.

> [!TIP]
> Click the **"Reset to Market Values"** button at any time to restore BSM inputs to default market feed parameters.

---

## 4. Option Chain & Price Highlights
The Option Chain is structured as a standard dual-sided grid (Calls on left, Puts on right, Strike prices centered):
* **ITM Shading (In-The-Money):** Strikes that are ITM (Calls with Strike < Spot; Puts with Strike > Spot) are highlighted in pale yellow.
* **BS PRICE Columns:** Rendered theoretical pricing from the active BSM model.
* **Edge Color Coding:**
  - <span style="color: #0d9488; font-weight: bold;">Teal Green (Underpriced):</span> Market Last Traded Price (LTP) is lower than BSM theoretical value. Indicates buying opportunity.
  - <span style="color: #ea580c; font-weight: bold;">Orange-Red (Overpriced):</span> Market LTP exceeds BSM theoretical value. Indicates writing/selling opportunity.

---

## 5. Strike Greeks Analysis
Click on any **Strike Price** or **LTP** cell to display the **Greeks Inspection Modal**:
* **Greeks Summary:** Displays Delta ($\Delta$), Gamma ($\Gamma$), Vega ($\nu$), Theta ($\theta$), and Rho ($\rho$) for both Calls and Puts side-by-side.
* **Model Parameters:** Shows exact inputs utilized during calculation.
* **Math Breakdown:** Exposes intermediary BSM pricing variables ($d_1, d_2, N(d_1), N(d_2)$) to trace mathematical outputs.

---

## 6. Data Export (.csv)
Click the **"Download (.csv)"** button to export Option Chain pricing. The generated CSV captures all standard columns, implied volatilities, and BSM calculations for physical storage or custom algorithmic analysis in spreadsheet applications.
