"""Experiments 1-5: fill the department templates in place."""

import docx

from docx_helpers import (add_paragraph_after, add_paragraphs_after, add_picture_after, add_table_after,
                          fill_key_value_table, fill_students, fill_table, find_paragraph, remove,
                          sdt_tables, set_cell, set_label_value, set_text)
from lab_data import PERIODS, STRATS, LabData, describe, fmt, metrics

TOPIC = ("Validating model-based option-mispricing trading signals on NSE NIFTY 50 index options "
         "under realistic Indian market frictions: a correction audit")

GAP_SHORT = ("Studies report pricing accuracy or simulated profits of option-pricing models, but none audits "
             "whether a model-versus-market mispricing signal on NIFTY 50 options stays profitable after "
             "pricing artifacts, execution timing, contract marking and full Indian statutory costs are "
             "corrected, with trade-level uncertainty and a hedged test of the signal itself.")

PAPERS = [
    ["Neural networks for option pricing and hedging: a literature review",
     "J. Ruf, W. Wang (2020)",
     "Survey of published studies on neural-network option pricing and hedging (several markets)",
     "Structured literature review of network designs, inputs, benchmarks and data splits",
     "Pricing and hedging errors reported by the reviewed studies",
     "Results across studies are hard to compare (different data, benchmarks and train/test splits); "
     "accuracy, not trading value after costs, is the usual yardstick"],
    ["Deep smoothing of the implied volatility surface",
     "D. Ackerer, N. Tagasovska, T. Vatter (2020)",
     "S&P 500 option quotes (CBOE via OptionMetrics), 2008 and 2018 samples; synthetic Bates surfaces",
     "Neural-network correction of a prior model (Black-Scholes / SSVI) with soft no-arbitrage penalties",
     "RMSE, MAPE, arbitrage-penalty losses",
     "Measures surface fit only; extrapolation errors larger; does not test whether deviations from the "
     "surface are tradeable"],
    ["Option pricing using machine learning",
     "C.-F. Ivașcu (2021)",
     "Crude oil call options",
     "Machine-learning regressors (incl. boosting) vs Black-Scholes and Corrado-Su",
     "Price-prediction error",
     "Evaluates prediction accuracy; economic value of acting on the model prices after trading costs is not assessed"],
    ["Lucky factors",
     "C. R. Harvey, Y. Liu (2021)",
     "Panel of individual US stocks",
     "Bootstrap-based multiple-testing procedure for selecting return factors",
     "Factor significance adjusted for multiple testing",
     "Equity factors, not options; does not address execution mechanics (fill timing, contract marking) "
     "that can create spurious backtest profits"],
    ["A novel machine learning approach for predicting the NIFTY50 index in India",
     "P. K. Nagula, C. Alexakis (2022)",
     "NIFTY 50 index with technical indicators",
     "Deep Cross Networks with feature-level rolling-window batch standardisation",
     "Directional hit rate (69.52% weekly, 79.17% monthly), RMSE, strategy profit vs buy-and-hold",
     "Forecasts the index, not option prices; the link to options trading and Indian option costs is not tested"],
    ["Option pricing and profitability: a comprehensive examination of machine learning, Black-Scholes, and Monte Carlo method",
     "S. Kim, J. Kim, J. Song (2024)",
     "KOSPI200 index options, 2023",
     "Black-Scholes, binomial tree, Monte Carlo with variance reduction, XGBoost, random forest, MLP; investment simulation",
     "RMSE by time frame; simulated investment returns",
     "One year of data; profitability of 'undervalued' options comes from a simulation that does not report "
     "transaction costs or execution lag"],
]

GAPS = [
    "G1. Pricing-accuracy studies rarely test whether model-market gaps are tradeable after costs.",
    "G2. Profit claims from mispricing signals are not audited for backtest artifacts (numerical error, "
    "carry bias, fill timing, contract marking).",
    "G3. Indian index options with the full statutory cost stack (STT, GST, stamp duty, exchange, SEBI) are under-studied.",
    "G4. Trade-level uncertainty (bootstrap CIs) and matched random baselines are seldom reported.",
    "G5. The value of the signal is not separated from the directional and time-decay risk of the trade (no hedged test).",
]

REFERENCES = [
    "[1] J. Ruf and W. Wang, “Neural networks for option pricing and hedging: a literature review,” "
    "J. Comput. Finance, 2020, doi: 10.21314/JCF.2020.390.",
    "[2] D. Ackerer, N. Tagasovska, and T. Vatter, “Deep smoothing of the implied volatility surface,” in "
    "Advances in Neural Information Processing Systems 33 (NeurIPS 2020), 2020. [Online]. Available: "
    "https://papers.neurips.cc/paper_files/paper/2020/file/858e47701162578e5e627cd93ab0938a-Paper.pdf",
    "[3] C.-F. Ivașcu, “Option pricing using machine learning,” Expert Syst. Appl., vol. 163, Art. no. 113799, "
    "2021, doi: 10.1016/j.eswa.2020.113799.",
    "[4] C. R. Harvey and Y. Liu, “Lucky factors,” J. Financ. Econ., vol. 141, no. 2, pp. 413–435, 2021, "
    "doi: 10.1016/j.jfineco.2021.04.014.",
    "[5] P. K. Nagula and C. Alexakis, “A novel machine learning approach for predicting the NIFTY50 index in "
    "India,” Int. Adv. Econ. Res., vol. 28, no. 3, pp. 155–170, 2022, doi: 10.1007/s11294-022-09861-8.",
    "[6] S. Kim, J. Kim, and J. Song, “Option pricing and profitability: A comprehensive examination of machine "
    "learning, Black-Scholes, and Monte Carlo method,” Commun. Stat. Appl. Methods, vol. 31, no. 5, "
    "pp. 585–599, 2024, doi: 10.29220/CSAM.2024.31.5.585.",
    "[7] Securities and Exchange Board of India, “Analysis of profit and loss of individual traders dealing in "
    "equity F&O segment,” SEBI study, Jan. 2023.",
]


def methodology_summary(d: LabData) -> str:
    return (f"Rebuild a full NIFTY option chain ({d.facts['sessions']} sessions, Jan 2021 – Jun 2024) from NSE "
            "Bhavcopy files; compute a Black-76 / cubic-spline mispricing signal; backtest the frozen Pure, "
            "Hybrid and Retail strategies with next-bar fills, contract-locked daily marks and full Indian costs "
            "in four independent periods; evaluate with bootstrap CIs, a matched random-put baseline, a "
            "180-session correction waterfall and a delta-hedged signal test.")


# ============================================================================= Experiment 1

def build_exp1(d: LabData, template: str, out: str) -> None:
    doc = docx.Document(template)
    fill_students(doc.tables[0])
    n = d.numbers

    p = find_paragraph(doc, "Choose one specific engineering")
    p = add_paragraph_after(p, TOPIC, label="Selected problem")
    add_paragraph_after(p, (
        "Retail participants dominate NSE index-options trading and most of them lose money. An earlier version "
        f"of our project reported that buying NIFTY 50 options priced below a Crank-Nicolson fair value returned "
        f"+{n['HeadlineReturn']}% after costs over 180 sessions. Such claims are common in the literature, but are "
        "rarely checked for the backtest artifacts that can manufacture them. The problem studied is whether the "
        "model-mispricing signal has any tradeable value once those artifacts are removed."), align="justify")

    t = doc.tables[1]
    fill_table(t, [row + [None] for row in PAPERS], start_row=1, size=8)
    set_cell(t.rows[1].cells[6], "\n".join(GAPS), size=8)

    gap = find_paragraph(doc, "Research Gap Statement")
    set_text(gap, (
        "Research Gap Statement: “Existing studies have addressed option-price prediction accuracy (classical, "
        "finite-difference and machine-learning models), volatility-surface fitting and multiple-testing "
        "corrections for equity trading factors. However, whether a model-versus-market mispricing signal on "
        "NIFTY 50 index options remains profitable once numerical error, carry bias, execution timing, contract "
        "marking and the full Indian statutory cost stack are corrected has not been adequately addressed. "
        "Therefore, there is a need to investigate a correction-by-correction audit of such a strategy, with "
        "trade-level confidence intervals, matched random baselines and a delta-hedged test of the signal itself.”"))

    blanks = [find_paragraph(doc, "_____", k) for k in (1, 2, 3)]
    set_text(blanks[0], (
        f"An earlier backtest reported that trading the gap between a Crank-Nicolson model price and the market "
        f"price of NIFTY 50 options returned +{n['HeadlineReturn']}% (Sharpe {n['HeadlineSharpe']}) after Indian "
        "costs. This research audits that claim by applying corrections for pricing artifacts and backtest "
        "mechanics one at a time, then re-tests the frozen strategies on a rebuilt full option chain for "
        f"January 2021 – June 2024 ({d.facts['sessions']} sessions) with independent periods, bootstrap "
        "confidence intervals and a matched random baseline. It also tests the signal itself, delta-hedged, "
        "against its round-trip cost, to decide whether any tradeable mispricing exists."))
    remove(blanks[1]); remove(blanks[2])

    p = find_paragraph(doc, "List the papers used for identifying")
    add_paragraphs_after(p, REFERENCES)
    doc.save(out)


# ============================================================================= Experiment 2

def build_exp2(d: LabData, template: str, out: str, workflow_png: str) -> None:
    doc = docx.Document(template)
    fill_students(doc.tables[0])
    fill_key_value_table(doc.tables[1], [TOPIC, GAP_SHORT])

    objectives = [
        f"Reproduce the original +{d.numbers['HeadlineReturn']}% result exactly and quantify, one correction at "
        "a time, how much of it each backtest fix removes (correction waterfall).",
        "Rebuild a full NIFTY 50 option chain for January 2021 – June 2024 from NSE Bhavcopy files and re-test the "
        "frozen strategies with independent per-period backtests from fresh capital.",
        "Measure trade-level performance (net return on premium with bootstrap confidence intervals, profit "
        "factor, return without the largest trade) against a matched puts-only random baseline.",
        "Test the mispricing signal separately from the strategy with a delta-hedged next-bar test compared "
        "with the round-trip trading cost.",
        "Make every reported number reproducible from one script that records configuration, code version and "
        "input-data hashes.",
    ]
    o1 = find_paragraph(doc, "1.", exact=True)
    o2 = find_paragraph(doc, "2", exact=True)
    set_text(o1, f"1. {objectives[0]}")
    set_text(o2, f"2. {objectives[1]}")
    add_paragraphs_after(o2, [f"{i}. {o}" for i, o in enumerate(objectives[2:], start=3)])

    fill_key_value_table(doc.tables[2], [
        "After correcting pricing artifacts and execution mechanics, the mispricing strategy's mean net return per "
        "trade is not greater than zero in any period, and the delta-hedged excess of undervalued puts after a "
        "next-bar fill does not exceed the round-trip cost.",
        "The mean net return per trade is greater than zero (bootstrap 95% CI above zero) in at least three of the "
        "four periods, and the hedged excess after a next-bar fill exceeds the round-trip cost.",
        "Independent: pricing model (PDE / closed-form / Black-76), fill timing, contract marking, cost multiplier, "
        "strategy (Pure, Hybrid, Retail, random), period, India VIX regime.\nDependent: net return, return on "
        "premium per trade, win rate, profit factor, Sharpe ratio, maximum drawdown, delta-hedged P&L.\nControlled: "
        "capital INR 1 lakh, 50 units per trade, 35% stop / 60% target, entry threshold 1.5 × round-trip cost, "
        "strikes within 150 points of spot.",
    ], size=9)

    fill_key_value_table(doc.tables[3], [
        "Quantitative, experimental (empirical backtesting) with a correction audit and hypothesis testing.",
        f"NSE F&O Bhavcopy daily files ({d.facts['bhavcopy_files']} sessions, 2021–2024) for every NIFTY option; "
        "NIFTY 50 index closes and India VIX (Yahoo Finance); original 180-session panel for the audit.",
        "Python 3.11, NumPy, pandas, SciPy, PyArrow, Matplotlib; Git for version control; LaTeX (IEEEtran) for the paper.",
        "Black-76 pricing with an ATM put-call-parity forward, implied volatilities from traded CLOSE prices, a "
        "natural cubic-spline smile, and mispricing = market − model; strategies trade the signal under a "
        "cost-based entry threshold.",
        "Net return, mean / median net return on premium with bootstrap 95% CI, win rate, profit factor, Sharpe "
        "(RBI repo-rate hurdle), maximum drawdown, percentile vs random baseline, delta-hedged P&L vs cost.",
        "1. Reproduce the original result. 2. Apply corrections one at a time (waterfall). 3. Rebuild the full "
        "chain. 4. Run independent period backtests. 5. Compare with baselines. 6. Run the hedged signal test. "
        "7. Freeze outputs and write the paper.",
    ], size=9)

    add_picture_after(find_paragraph(doc, "Draw the proposed research workflow"), workflow_png, 17.0)

    fill_table(doc.tables[4], [
        ["1", "Reproduce the original pipeline", f"Original +{d.numbers['HeadlineReturn']}% (S0) and closed-form "
              f"+{d.numbers['ClosedFormReturn']}% (S1) reproduced exactly"],
        ["2", "Correction waterfall on 180 sessions", "Return, trades and Sharpe after each correction (S0–S6)"],
        ["3", "Rebuild the full option chain from Bhavcopy", f"{d.facts['full_chain_rows']:,} contract-days; "
              f"{d.facts['signal_panel_rows']:,}-row multi-expiry signal panel"],
        ["4", "Independent period backtests + random baseline", "12 strategy-period cells with trade-level CIs and "
              f"percentile vs {d.facts['random_draws']} random draws"],
        ["5", "Delta-hedged signal test; stress and VIX tests", "Hedged P&L of undervalued / rich / all puts vs "
              "round-trip cost; results under 1–3× costs and by VIX regime"],
    ], start_row=1, size=9)

    fill_table(doc.tables[5], [
        [None, "11-04-2026", "19-08-2026", "Completed — project repository started as an analytics app; research "
                                          "question finalised in Aug 2026 (git history)"],
        [None, "20-08-2026", "21-08-2026", "Completed — PDE pipeline, cost model and first paper draft"],
        [None, "20-08-2026", "11-10-2026", f"Completed — corrected pipeline (commit {d.manifest['git_commit'][:7]} "
                                          "outputs; tag paper-audit-v1)"],
        [None, "11-10-2026", "11-10-2026", f"Completed — {d.facts['bhavcopy_files']} Bhavcopy files rebuilt into the "
                                          "full chain"],
        [None, "11-10-2026", "11-10-2026", "Completed — waterfall, period results and signal test frozen"],
        [None, "11-10-2026", "12-10-2026", "Completed — paper rewritten as a correction audit; lab records"],
    ], start_row=1, size=9)

    p = find_paragraph(doc, "State what the research is expected to contribute")
    add_paragraphs_after(p, [
        "1. A quantified correction waterfall showing how much apparent profit each common backtest artifact "
        "creates in an options mispricing strategy.",
        "2. Independent, trade-level evidence on NIFTY 50 options over 2021–2024 with full Indian statutory costs, "
        "compared with a matched random baseline instead of zero.",
        "3. A direct, delta-hedged test that separates the value of the mispricing signal from the directional "
        "and time-decay risk of the trade.",
        "4. A fully reproducible research package (one script, recorded configuration and data hashes) that other "
        "students and researchers can re-run.",
    ])
    doc.save(out)


# ============================================================================= Experiment 3

def build_exp3(d: LabData, template: str, out: str) -> None:
    doc = docx.Document(template)
    tpl_tables = list(doc.tables)  # template tables, before new ones are inserted
    fill_students(tpl_tables[0])
    fill_key_value_table(tpl_tables[1], [TOPIC, methodology_summary(d)], size=9)

    f = d.facts
    fill_key_value_table(tpl_tables[2], [
        f"{f['bhavcopy_files']} trading sessions (01-01-2021 to 28-06-2024); full chain: {f['full_chain_rows']:,} "
        f"contract-days; signal panel: {f['signal_panel_rows']:,} rows over {f['signal_panel_expiries']} expiries; "
        f"original audit sample: 180 sessions, {f['legacy_180_rows']:,} rows.",
        "Per contract-day: date, expiry, days to expiry, strike, option type, open/high/low/close, settlement "
        "price, contracts traded, open interest, index spot. Derived: forward, implied volatility, surface IV, "
        "model price, mispricing, entry threshold ε. Index: OHLCV, RSI(14), MACD(12/26/9), India VIX.",
        "Not a classification dataset. Options: call / put. Signals: undervalued (mispricing < −ε), rich "
        "(> +ε), inside band. Trade outcomes: win / loss; exit reasons: stop-loss, take-profit, mean-reverted, "
        "time, pre-expiry square-off.",
        "No model is fitted, so there is no train/test split. Strategy rules were frozen before testing. "
        "Evaluation uses four independent periods: A 2021, B 2022, C Jan–Sep 2023 (not used in development) and "
        "D Oct 2023 – Jun 2024 (overlaps the development sample).",
        "Raw: NSE Bhavcopy (one file per session) cached as Parquet. Derived panels: Parquet and CSV.",
        "Filter NIFTY index options (OPTIDX); keep strikes within ±12% of spot and expiries ≤ 60 days; drop "
        "zero-volume CLOSE prices (stale); use only traded contracts for the forward and IVs; choose the signal "
        "expiry as the nearest with ≥ 14 days to expiry; date-dependent lot size, repo rate and STT.",
    ], size=9)

    p = find_paragraph(doc, "4. Experimental Setup Details")
    add_table_after(doc, p, [
        ["Parameter", "Setting"],
        ["Initial capital / sizing", "INR 1,00,000 per period (fresh); 50 units per trade; at most 95% of equity per position"],
        ["Fill and marking", "Signal at close t, fill at close t+1 on the same contract if it traded; daily marks on the "
                             "position's own contract; square-off before expiry day"],
        ["Exits", "35% stop-loss, 60% take-profit, mean reversion (|δ| < ε/2 after ≥ 2 bars), 5 sessions"],
        ["Entry threshold", "ε = 1.5 × round-trip cost; strikes within 150 points of spot; premium > INR 10"],
        ["Costs", "STT on sell leg (0.05% before 1 Apr 2023, 0.0625% after), exchange 0.05%, stamp 0.003%, SEBI fee, "
                  "GST 18%, INR 20 per order, half-spread 0.5% of premium per leg"],
        ["Sharpe hurdle", "RBI repo-rate step function"],
        ["Hardware / software", "Intel Core i5-12450H (8 cores), 16 GB RAM, Windows 11; Python 3.11"],
    ], widths_cm=[4.5, 13.0], size=9, first_col_bold=True)

    p = find_paragraph(doc, "Define the metrics that will be used")
    add_table_after(doc, p, [
        ["Metric", "Definition", "Purpose"],
        ["Net return (%)", "Sum of net P&L ÷ INR 1 lakh, per period", "Headline outcome"],
        ["Return on premium (RoP)", "Net P&L ÷ premium paid, per trade; mean, median, bootstrap 95% CI",
         "Capital-path-free edge per trade"],
        ["Return without largest trade", "Period return excluding the trade with the largest |P&L|", "Single-trade dependence"],
        ["Win rate / profit factor", "Share of profitable trades; gross wins ÷ gross losses", "Trade quality"],
        ["Sharpe ratio / max drawdown", "Annualised excess daily return ÷ SD (repo hurdle); peak-to-trough fall", "Risk-adjusted return"],
        ["Percentile vs random", "Rank of the strategy return among matched random-put draws", "Better than chance?"],
        ["Delta-hedged P&L", "ΔP − Δ_F·ΔF per unit, from the signal close and after a next-bar fill", "Value of the signal itself"],
    ], widths_cm=[4.2, 8.3, 5.0], size=9, first_col_bold=True)

    fill_table(tpl_tables[3], [
        ["1", "Retail Baseline (RSI + MACD)", "Buys ATM calls/puts on RSI(14) and MACD-histogram rules",
         "Represents the indicator rules most retail traders use"],
        ["2", "Hybrid Filter", "Mispricing signal plus MACD/RSI momentum confirmation",
         "Tests whether a trend filter rescues the signal"],
        ["3", "Matched random-put baseline", "Random near-ATM puts with identical fills, exits and costs, "
         f"entry rate matched to trade count ({d.facts['random_draws']} draws)", "Long puts lose to time decay; "
         "the fair comparison is chance, not zero"],
        ["4", "Original pipeline (S0)", "PDE fair value with q = 0, same-bar fills, strike-only marks",
         "Reference point for the correction waterfall"],
    ], start_row=1, size=9)

    fill_table(tpl_tables[4], [
        ["1", "Mean net return per trade with bootstrap 95% CI above zero in ≥ 3 of 4 periods",
         "Period results table (trade-level CI per cell)"],
        ["2", "Strategy return above the 95th percentile of the matched random baseline",
         "Percentile of each cell within the random-draw distribution"],
        ["3", "Delta-hedged excess of undervalued puts after a next-bar fill exceeds the round-trip cost",
         "Hedged signal test with date-clustered bootstrap CI"],
        ["4", "Every number reproducible from one command with recorded commit and data hashes",
         "Re-run reproduce_all.py; manifest.json shows a clean commit"],
    ], start_row=1, size=9)
    doc.save(out)


# ============================================================================= Experiment 4

def build_exp4(d: LabData, template: str, out: str, figs: dict) -> None:
    doc = docx.Document(template)
    fill_students(doc.tables[0])
    f, n = d.facts, d.numbers
    for label, value in [
        ("Programming Language/Technology", "Python 3.11"),
        ("Software/Tools Used", "NumPy, pandas, SciPy, PyArrow, Matplotlib, python-docx; Git; LaTeX (IEEEtran)"),
        ("Hardware/Platform Used", "Intel Core i5-12450H (8 cores / 12 threads), 16 GB RAM, Windows 11"),
        ("Dataset/Input Used", "NSE F&O Bhavcopy files (NIFTY options) Jan 2021 – Jun 2024; NIFTY 50 and India VIX closes"),
        ("Number of Samples/Records", f"{f['bhavcopy_files']} sessions; {f['full_chain_rows']:,} contract-days; "
                                      f"{f['signal_panel_rows']:,} signal-panel rows; {int(d.periods['Trades'].sum())} trades "
                                      "across 12 strategy-period runs"),
        ("Important Parameters", "Capital INR 1 lakh; 50 units; stop 35%, target 60%; ε = 1.5 × cost; ±150 points; "
                                 "signal expiry ≥ 14 DTE; 5-session hold"),
    ]:
        set_label_value(find_paragraph(doc, label), label, value)

    steps = [
        "Build the full chain and signal panel from the Bhavcopy cache (research/data/build_3_5_year_dataset.py --from-cache).",
        "Compute forward, implied volatilities, spline surface and mispricing per expiry; flag the signal expiry (≥ 14 DTE).",
        "Run the Pure, Hybrid and Retail strategies with next-bar fills and contract-locked marks "
        "(research/run_3_5y_experiments.py, RobustBacktestStrategy).",
        "Book costs per trade with the Indian friction model (date-dependent STT) and mark equity daily (research/backtest/engine.py).",
        "Repeat each strategy independently in periods A–D from fresh capital; compute trade-level statistics and "
        "the matched random baseline (research/analysis/trade_stats.py).",
        "Reproduce the original pipeline and apply corrections one at a time on 180 sessions (research/analysis/waterfall.py).",
        "Run the delta-hedged signal test (research/analysis/signal_test.py).",
        "Regenerate all tables, figures and numbers with a manifest (research/reproduce_all.py).",
    ]
    s1, s2 = find_paragraph(doc, "1. ____"), find_paragraph(doc, "2. ____")
    set_text(s1, f"1. {steps[0]}")
    set_text(s2, f"2. {steps[1]}")
    add_paragraphs_after(s2, [f"{i}. {s}" for i, s in enumerate(steps[2:], start=3)])

    p = find_paragraph(doc, "Describe the experiments conducted")
    add_paragraphs_after(p, [
        ("E1 – Correction waterfall", f"On the original 180 sessions, the headline +{n['HeadlineReturn']}% was "
         "reproduced and corrections were added one at a time (closed-form pricing, forward-consistent pricing, "
         "next-bar fill, contract lock, stale-price removal and daily marking, full-chain data)."),
        ("E2 – Independent period backtests", "Pure, Hybrid and Retail were each run in periods A–D from INR 1 lakh "
         "(12 cells), with trade-level statistics."),
        ("E3 – Random baseline", f"For every cell, {f['random_draws']} draws of random near-ATM puts with the same "
         "fills, exits and costs and a matched trade count."),
        ("E4 – Delta-hedged signal test", f"{n['SigN']} put observations; hedged P&L from the signal close and "
         "after a next-bar fill, compared with round-trip cost."),
        ("E5 – Robustness", "Costs scaled 1–3× (entry threshold fixed or scaled) and results by India VIX regime."),
    ])

    # Comparison table (content-controlled table in the template)
    t = sdt_tables(doc)[0]
    header = ["Period / method (trades)", "Net return (%)", "Mean RoP % [95% CI]", "Return without largest trade (%)", "Win rate (%)"]
    for c, h in zip(t.rows[0].cells, header):
        set_cell(c, h, bold=True, size=9)
    rows = []
    for per in PERIODS:
        pure = d.periods[(d.periods["Period"] == per) & (d.periods["Strategy"] == "Pure Mispricing")].iloc[0]
        ret = d.periods[(d.periods["Period"] == per) & (d.periods["Strategy"] == "Retail Baseline")].iloc[0]
        rows.append([f"{per}: Proposed – Pure Mispricing ({int(pure.Trades)})", fmt(pure.Return_Pct, 1, True),
                     f"{pure.RoP_Mean_Pct:.1f} [{pure.RoP_CI_Lo_Pct:.1f}, {pure.RoP_CI_Hi_Pct:.1f}]",
                     fmt(pure.Return_Ex_Largest_Pct, 1, True), fmt(pure.Win_Rate_Pct, 1)])
        rows.append([f"{per}: Baseline – Retail RSI/MACD ({int(ret.Trades)})", fmt(ret.Return_Pct, 1, True),
                     f"{ret.RoP_Mean_Pct:.1f} [{ret.RoP_CI_Lo_Pct:.1f}, {ret.RoP_CI_Hi_Pct:.1f}]",
                     fmt(ret.Return_Ex_Largest_Pct, 1, True), fmt(ret.Win_Rate_Pct, 1)])
        rows.append([f"{per}: Baseline – random puts (mean of {f['random_draws']})", fmt(pure.Random_Mean_Return_Pct, 1, True),
                     "—", "—", "—"])
    fill_table(t, rows, start_row=1, size=8.5)

    p = find_paragraph(doc, "Note: Suggested graphs")
    p = add_picture_after(p, figs["return_vs_method"], 16.5, "Figure 1: Net return vs method, per period (independent backtests).")
    p = add_picture_after(p, figs["rop_ci"], 16.5, "Figure 2: Mean net return per trade with bootstrap 95% CI vs method.")
    add_picture_after(p, figs["waterfall"], 16.0, "Figure 3: Correction waterfall on the original 180 sessions.")

    pure_cells = d.periods[d.periods["Strategy"] == "Pure Mispricing"]
    p = find_paragraph(doc, "Write the important observations")
    add_paragraphs_after(p, [
        f"1. The original +{n['HeadlineReturn']}% was reproduced exactly; closed-form pricing alone reduced it to "
        f"+{n['ClosedFormReturn']}%, and forward-consistent pricing to +{n['ForwardReturn']}% on {n['ForwardTrades']} "
        "trades — the zero-dividend carry bias created most of the profit.",
        f"2. Only {n['CellsPositive']} of the 12 strategy-period cells were profitable, and {n['CellsCIAboveZero']} "
        "had a per-trade confidence interval entirely above zero.",
        f"3. The Pure Mispricing strategy lost money in {int((pure_cells['Return_Pct'] < 0).sum())} of 4 periods; "
        f"its per-trade CI lay entirely below zero in Period C (upper bound {n['PureCRoPHi']}%).",
        f"4. Results depend heavily on single trades: Hybrid in 2021 fell from +{n['HybridAReturn']}% to "
        f"+{n['HybridAExMax']}% without its largest trade; Pure in Period D moved from {n['PureDReturn']}% to "
        f"{n['PureDExMax']}% without its largest loss (INR {n['PureDLargest']}, election-result day).",
        "5. The random-put baseline also lost money in most cells, so comparing strategies against zero overstates "
        "how bad they are; none was consistently better than chance.",
        f"6. Every Pure and Hybrid trade was a put ({n['PureTradesTotal']} and {n['HybridTradesTotal']} trades): "
        "with consistent pricing the spline reproduces call prices, so calls carry no signal.",
    ])
    doc.save(out)


# ============================================================================= Experiment 5

def build_exp5(d: LabData, template: str, out: str, figs: dict) -> None:
    doc = docx.Document(template)
    perf_table = doc.tables[1]  # template table, before new ones are inserted
    fill_students(doc.tables[0])
    n, f = d.numbers, d.facts

    p = find_paragraph(doc, "The experimental data obtained from the implemented system")
    add_paragraph_after(p, (
        f"Data analysed: {len(d.trades)} trades from the 12 independent strategy-period backtests (Pure "
        f"{int((d.trades['Strategy'] == 'Pure Mispricing').sum())}, Hybrid {int((d.trades['Strategy'] == 'Hybrid Filter').sum())}, "
        f"Retail {int((d.trades['Strategy'] == 'Retail Baseline').sum())}) and {n['SigN']} near-ATM put observations "
        "from the delta-hedged signal test. The unit of analysis is the trade (net return on premium) or the "
        "option-day (hedged P&L), which avoids the capital-path effects of portfolio returns."), align="justify")

    stats_rows = []
    for s in STRATS:
        stats_rows.append((f"Net return on premium per trade, {s} (%)", d.trades[d.trades["Strategy"] == s]["rop_pct"]))
    o = d.obs.dropna(subset=["hedged_t1_t2"])
    stats_rows.append(("Hedged P&L after fill, undervalued puts (INR/unit)", o[o["group"] == "undervalued"]["hedged_t1_t2"]))
    stats_rows.append(("Hedged P&L after fill, all near-ATM puts (INR/unit)", o["hedged_t1_t2"]))
    stats_rows.append(("Period return, Pure Mispricing (%), 4 periods",
                       d.periods[d.periods["Strategy"] == "Pure Mispricing"]["Return_Pct"]))
    t = sdt_tables(doc)[0]
    rows = []
    for label, vals in stats_rows:
        s = describe(vals)
        rows.append([f"{label} (n={s['n']})", fmt(s["mean"]), fmt(s["median"]), fmt(s["var"], 1), fmt(s["sd"]),
                     fmt(s["min"]), fmt(s["max"])])
    fill_table(t, rows, start_row=1, size=8.5)

    p = find_paragraph(doc, "The experimental results should be organized in tabular form")
    add_table_after(doc, p, [
        ["Strategy", "Trades", "Win rate (%)", "Profit factor", "Mean RoP % [95% CI]"],
        *[[s, str(int(d.periods[d.periods["Strategy"] == s]["Trades"].sum())),
           fmt((d.trades[d.trades["Strategy"] == s]["pnl_net"] > 0).mean() * 100, 1),
           fmt(d.trades[(d.trades["Strategy"] == s) & (d.trades["pnl_net"] > 0)]["pnl_net"].sum()
               / -d.trades[(d.trades["Strategy"] == s) & (d.trades["pnl_net"] < 0)]["pnl_net"].sum()),
           "{:.1f} [{:.1f}, {:.1f}]".format(*_boot(d.trades[d.trades["Strategy"] == s]["rop_pct"].values))]
          for s in STRATS],
    ], widths_cm=[4.5, 2.2, 2.8, 2.8, 5.2], size=9)
    add_paragraph_after(p, "Table 2: Pooled trade-level results over the four independent periods.", italic=True, size=9)

    p = find_paragraph(doc, "Graphs should be prepared to visualize")
    p = add_picture_after(p, figs["boxplot"], 15.0, "Figure 1: Distribution of net return on premium per trade, by strategy.")
    p = add_picture_after(p, figs["periods"], 16.5, "Figure 2: Period returns vs the matched random-put baseline.")
    add_picture_after(p, figs["signal"], 15.5, "Figure 4: Delta-hedged P&L of the signal (all periods, 95% CI).")

    cm = f["confusion"]["t1_t2"]; cm0 = f["confusion"]["t0_t1"]
    p = find_paragraph(doc, "False Negative (FN)")
    add_paragraph_after(p, (
        "Our study is not a classifier, so the confusion matrix treats the mispricing signal as one. Population: "
        f"{f['confusion']['n']:,} near-ATM signal-expiry put observations. Predicted positive: the put is flagged "
        "undervalued (mispricing < −ε). Actual positive: after a next-bar fill, its delta-hedged P&L beats the "
        "same-day average of all near-ATM puts by more than its round-trip cost, i.e. a trade would have earned its "
        f"costs back on relative value ({cm['actual_pos']} of {f['confusion']['n']:,} observations, "
        f"{cm['actual_pos'] / f['confusion']['n'] * 100:.1f}%)."), align="justify")
    ph = find_paragraph(doc, "[Insert confusion matrix here]")
    add_picture_after(ph, figs["confusion"], 9.5)
    remove(ph)

    m = metrics(cm["tp"], cm["fp"], cm["fn"], cm["tn"])
    m0 = metrics(cm0["tp"], cm0["fp"], cm0["fn"], cm0["tn"])
    rb = metrics(**f["baselines"]["random"])
    ab = metrics(**f["baselines"]["always"])
    tm = f["timing_s"]
    t = perf_table
    for c, h in zip(t.rows[0].cells, ["Performance Measure", "Proposed (mispricing signal)",
                                      "Baseline 1 (random flag, same rate)", "Baseline 2 (flag every put)"]):
        set_cell(c, h, bold=True, size=9)
    pct = lambda x: f"{x * 100:.1f}%"
    fill_table(t, [
        ["Accuracy", pct(m["accuracy"]), pct(rb["accuracy"]), pct(ab["accuracy"])],
        ["Precision", pct(m["precision"]), pct(rb["precision"]), pct(ab["precision"])],
        ["Recall", pct(m["recall"]), pct(rb["recall"]), pct(ab["recall"])],
        ["F1-Score", f"{m['f1']:.3f}", f"{rb['f1']:.3f}", f"{ab['f1']:.3f}"],
        ["Error (1 − accuracy)", pct(m["error"]), pct(rb["error"]), pct(ab["error"])],
        ["Execution time (4-period backtest)", f"{tm['PURE_PDE']:.2f} s (Pure strategy)",
         f"{tm['RANDOM_PUT']:.2f} s (random-put strategy)", "— (no model)"],
    ], start_row=1, size=9)
    add_paragraph_after(t, (
        "Baseline 1 and 2 values are expected counts for the same population. Accuracy is high for every rule "
        f"because only {cm['actual_pos'] / f['confusion']['n'] * 100:.1f}% of observations are positives, so "
        "precision and F1 are the informative measures. Measured from the signal close instead (not tradeable), "
        f"the same signal reaches precision {pct(m0['precision'])} and F1 {m0['f1']:.3f}."), italic=True, size=9)

    obs_lines = [
        f"The proposed method achieved weak performance: after a next-bar fill, {pct(m['precision'])} of flagged "
        f"puts earned their costs back on relative value, against {pct(rb['precision'])} for a random flag.",
        "The statistical analysis showed that the mean net return per trade is "
        + ", ".join(f"{s.split()[0]} {describe(d.trades[d.trades['Strategy'] == s]['rop_pct'])['mean']:.1f}%" for s in STRATS)
        + ", with standard deviations of "
        + ", ".join(f"{describe(d.trades[d.trades['Strategy'] == s]['rop_pct'])['sd']:.0f}%" for s in STRATS)
        + "; outcomes are dominated by dispersion and single trades rather than by any edge.",
        f"The proposed method performed better than the random flag (Baseline 1) with respect to precision and F1 "
        f"({m['f1']:.3f} vs {rb['f1']:.3f}), but not better than flagging every put (Baseline 2) on F1 ({ab['f1']:.3f}).",
        f"The confusion matrix indicates poor classification performance: of {cm['tp'] + cm['fp']} flagged puts, "
        f"{cm['tp']} were true positives and {cm['fp']} false positives, and the signal missed {cm['fn']} of the "
        f"{cm['actual_pos']} profitable opportunities.",
        f"The graphical analysis shows that undervalued puts do revert relative to other puts from the signal close "
        f"to the next close (+{n['SigUnderHzeroExcess']} INR/unit), but after a next-bar fill the excess is "
        f"{n['SigUnderHoneExcess']} INR/unit, below the {n['SigCost']} INR round-trip cost.",
        f"The overall performance of the proposed method was not economically better compared with the baseline "
        f"methods: {n['CellsPositive']} of 12 strategy-period cells were profitable and {n['CellsCIAboveZero']} "
        "had a per-trade confidence interval above zero.",
    ]
    for i, line in enumerate(obs_lines):
        set_text(find_paragraph(doc, ["The proposed method achieved", "The statistical analysis showed",
                                      "The proposed method performed better", "The confusion matrix indicates",
                                      "The graphical analysis shows", "The overall performance"][i]), line)

    concl = find_paragraph(doc, "The experimental results were analyzed using statistical methods")
    set_text(concl, concl.text.replace(
        "The analysis indicates that the proposed method __________.",
        "The analysis indicates that the proposed method contains a small, short-lived relative-value signal "
        "but provides no tradeable edge after realistic fills and Indian transaction costs; the large profits "
        "reported earlier were produced by pricing artifacts and backtest mechanics."))
    doc.save(out)


def _boot(values, n_boot: int = 10_000, seed: int = 0):
    import numpy as np
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    means = v[rng.integers(0, len(v), size=(n_boot, len(v)))].mean(axis=1)
    return v.mean(), np.quantile(means, 0.025), np.quantile(means, 0.975)
