"""
File Overview: Trade-level statistics, bootstrap intervals, and matched random baselines.

Portfolio returns over a sub-period are dominated by a handful of trades and by the capital
path (an account that is drawn down cannot afford later entries). The functions here report
statistics that do not depend on the capital path: net return on premium per trade, its
bootstrap confidence interval, profit factor, the period return without its largest trade,
and the percentile of the strategy against a puts-only random baseline with identical
fills, exits and costs.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from research.backtest.engine import Trade


def net_return_on_premium(trades: Sequence[Trade]) -> np.ndarray:
    """Per-trade net P&L divided by premium paid (entry price x quantity)."""
    return np.array([t.pnl_net / (t.entry_price * t.quantity) for t in trades if t.entry_price > 0], dtype=float)


def bootstrap_mean_ci(
    values: np.ndarray,
    n_boot: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
    clusters: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """
    Percentile bootstrap interval for the mean. If clusters is given, whole clusters
    (e.g. signal dates) are resampled together.
    """
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    if clusters is None:
        idx = rng.integers(0, len(values), size=(n_boot, len(values)))
        means = values[idx].mean(axis=1)
    else:
        clusters = np.asarray(clusters)
        uniq, inv = np.unique(clusters, return_inverse=True)
        sums = np.bincount(inv, weights=values)
        counts = np.bincount(inv)
        pick = rng.integers(0, len(uniq), size=(n_boot, len(uniq)))
        means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    return {
        "mean": float(values.mean()),
        "lo": float(np.quantile(means, alpha / 2)),
        "hi": float(np.quantile(means, 1 - alpha / 2)),
    }


def trade_level_stats(trades: Sequence[Trade], initial_capital: float, seed: int = 0) -> Dict[str, Any]:
    """Capital-path-free statistics for one strategy-period cell."""
    pnl = np.array([t.pnl_net for t in trades], dtype=float)
    rop = net_return_on_premium(trades)
    ci = bootstrap_mean_ci(rop, seed=seed)
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    if len(pnl):
        largest = int(np.argmax(np.abs(pnl)))
        ret_ex_largest = (pnl.sum() - pnl[largest]) / initial_capital * 100.0
        largest_pnl = float(pnl[largest])
    else:
        ret_ex_largest, largest_pnl = 0.0, 0.0
    return {
        "Trades": len(trades),
        "Puts": sum(t.option_type == "put" for t in trades),
        "Win_Rate_Pct": float((pnl > 0).mean() * 100.0) if len(pnl) else float("nan"),
        "Profit_Factor": float(wins / losses) if losses > 0 else float("nan"),
        "RoP_Mean_Pct": ci["mean"] * 100.0,
        "RoP_CI_Lo_Pct": ci["lo"] * 100.0,
        "RoP_CI_Hi_Pct": ci["hi"] * 100.0,
        "RoP_Median_Pct": float(np.median(rop) * 100.0) if len(rop) else float("nan"),
        "Largest_Trade_PnL": largest_pnl,
        "Return_Ex_Largest_Pct": float(ret_ex_largest),
    }


def matched_random_baseline(
    run_random: Callable[[float, int], List[Trade]],
    target_trades: int,
    initial_capital: float,
    n_draws: int = 500,
    calib_draws: int = 20,
    calib_iters: int = 10,
    seed: int = 12345,
) -> Dict[str, Any]:
    """
    Puts-only random entries matched to a strategy's trade count.

    run_random(entry_prob, seed) -> trades must use the same fills, exits and costs as the
    strategy. entry_prob is calibrated by bisection so the mean trade count matches target_trades.
    """
    if target_trades == 0:
        return {"entry_prob": 0.0, "returns": np.array([]), "rop_means": np.array([]), "trade_counts": np.array([])}

    lo, hi = 0.0, 1.0
    for it in range(calib_iters):
        mid = (lo + hi) / 2.0
        mean_n = np.mean([len(run_random(mid, seed + 1_000_000 + it * calib_draws + k)) for k in range(calib_draws)])
        if mean_n < target_trades:
            lo = mid
        else:
            hi = mid
    entry_prob = (lo + hi) / 2.0

    returns, rop_means, counts = [], [], []
    for k in range(n_draws):
        trades = run_random(entry_prob, seed + k)
        returns.append(sum(t.pnl_net for t in trades) / initial_capital * 100.0)
        rop = net_return_on_premium(trades)
        rop_means.append(rop.mean() * 100.0 if len(rop) else np.nan)
        counts.append(len(trades))
    return {
        "entry_prob": entry_prob,
        "returns": np.array(returns),
        "rop_means": np.array(rop_means),
        "trade_counts": np.array(counts),
    }


def percentile_of(value: float, distribution: np.ndarray) -> float:
    """Share of the distribution strictly below value, in percent (ties count half)."""
    d = distribution[np.isfinite(distribution)]
    if len(d) == 0:
        return float("nan")
    return float(((d < value).sum() + 0.5 * (d == value).sum()) / len(d) * 100.0)
