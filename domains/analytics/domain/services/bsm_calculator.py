"""
File Overview: Pure domain service for Black-Scholes-Merton option pricing, Greeks sensitivities calculation, and implied volatility solving (Newton-Raphson with a Brent fallback).
Pure domain code with zero external infrastructure dependencies.
"""
import math
from dataclasses import dataclass
from typing import Dict, Optional
from scipy.optimize import brentq
from scipy.stats import norm
import numpy as np

from domains.analytics.domain.value_objects import GreekValueObject

# Implied volatility search range (0.01% to 500%)
_IV_MIN = 1e-4
_IV_MAX = 5.0


@dataclass(frozen=True)
class BsmPriceResult:
    price: float
    greeks: GreekValueObject


class BsmCalculatorDomainService:
    """
    Pure analytical engine for Black-Scholes-Merton option valuation,
    Greeks calculation, and implied volatility solving.
    """

    @staticmethod
    def calculate_price(
        spot: float,
        strike: float,
        expiry_years: float,
        rate: float,
        volatility: float,
        option_type: str = "call",
        dividend_yield: float = 0.0,
    ) -> float:
        """Calculate theoretical option price using BSM formula."""
        if spot <= 0 or strike <= 0:
            return 0.0

        t = max(expiry_years, 1e-6)
        sigma = max(volatility, 1e-6)
        opt_type = option_type.lower()

        d1 = (np.log(spot / strike) + (rate - dividend_yield + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
        d2 = d1 - sigma * np.sqrt(t)

        if opt_type in ("call", "ce"):
            price = spot * np.exp(-dividend_yield * t) * norm.cdf(d1) - strike * np.exp(-rate * t) * norm.cdf(d2)
        elif opt_type in ("put", "pe"):
            price = strike * np.exp(-rate * t) * norm.cdf(-d2) - spot * np.exp(-dividend_yield * t) * norm.cdf(-d1)
        else:
            raise ValueError(f"Invalid option type: {option_type}")

        return float(max(price, 0.0))

    @staticmethod
    def calculate_greeks(
        spot: float,
        strike: float,
        expiry_years: float,
        rate: float,
        volatility: float,
        option_type: str = "call",
        dividend_yield: float = 0.0,
    ) -> GreekValueObject:
        """Calculate analytical Greeks sensitivities: Delta, Gamma, Theta, Vega, Rho."""
        if spot <= 0 or strike <= 0:
            return GreekValueObject(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

        t = max(expiry_years, 1e-6)
        sigma = max(volatility, 1e-6)
        opt_type = option_type.lower()

        d1 = (np.log(spot / strike) + (rate - dividend_yield + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
        d2 = d1 - sigma * np.sqrt(t)
        n_prime_d1 = norm.pdf(d1)

        # Gamma (identical for Call and Put)
        gamma = (n_prime_d1 * np.exp(-dividend_yield * t)) / (spot * sigma * np.sqrt(t))

        # Vega (identical for Call and Put, scaled by 0.01 per 1% vol change)
        vega = (spot * np.exp(-dividend_yield * t) * n_prime_d1 * np.sqrt(t)) / 100.0

        if opt_type in ("call", "ce"):
            delta = np.exp(-dividend_yield * t) * norm.cdf(d1)
            theta_term1 = -(spot * sigma * np.exp(-dividend_yield * t) * n_prime_d1) / (2 * np.sqrt(t))
            theta_term2 = rate * strike * np.exp(-rate * t) * norm.cdf(d2)
            theta_term3 = dividend_yield * spot * np.exp(-dividend_yield * t) * norm.cdf(d1)
            theta = (theta_term1 - theta_term2 + theta_term3) / 365.0
            rho = (strike * t * np.exp(-rate * t) * norm.cdf(d2)) / 100.0
        else:
            delta = -np.exp(-dividend_yield * t) * norm.cdf(-d1)
            theta_term1 = -(spot * sigma * np.exp(-dividend_yield * t) * n_prime_d1) / (2 * np.sqrt(t))
            theta_term2 = rate * strike * np.exp(-rate * t) * norm.cdf(-d2)
            theta_term3 = dividend_yield * spot * np.exp(-dividend_yield * t) * norm.cdf(-d1)
            theta = (theta_term1 + theta_term2 - theta_term3) / 365.0
            rho = (-strike * t * np.exp(-rate * t) * norm.cdf(-d2)) / 100.0

        return GreekValueObject(
            delta=float(delta),
            gamma=float(gamma),
            theta=float(theta),
            vega=float(vega),
            rho=float(rho),
        )

    @classmethod
    def solve_implied_volatility(
        cls,
        market_price: float,
        spot: float,
        strike: float,
        expiry_years: float,
        rate: float,
        option_type: str = "call",
        dividend_yield: float = 0.0,
        initial_vol: float = 0.25,
        max_iterations: int = 100,
        precision: float = 1e-5,
    ) -> float:
        """Implied volatility for a market price: Newton-Raphson, then a bracketed Brent search.

        Newton converges in a few steps near the money but stalls where vega is tiny (deep
        in/out of the money, near expiry). Brent on [1e-4, 5.0] always converges when a solution
        exists. Returns 0.0 when no volatility reproduces the price (e.g. below intrinsic value),
        which callers treat as "IV unavailable"; it never returns an unconverged guess.
        """
        if market_price <= 0 or spot <= 0 or strike <= 0 or expiry_years <= 0:
            return 0.0

        def price_error(vol: float) -> float:
            return cls.calculate_price(spot, strike, expiry_years, rate, vol, option_type, dividend_yield) - market_price

        vol = initial_vol
        for _ in range(max_iterations):
            diff = price_error(vol)
            if abs(diff) < precision:
                return float(vol)
            vega = cls.calculate_greeks(spot, strike, expiry_years, rate, vol, option_type, dividend_yield).vega * 100.0
            if abs(vega) < 1e-8:
                break
            vol = vol - diff / vega
            if vol <= 0 or vol > _IV_MAX:
                break

        low, high = _IV_MIN, _IV_MAX
        if price_error(low) * price_error(high) > 0:
            return 0.0  # price outside what any volatility can produce
        try:
            return float(brentq(price_error, low, high, xtol=1e-8, maxiter=200))
        except (ValueError, RuntimeError):
            return 0.0
