"""Accuracy of the Crank-Nicolson solver against the closed-form Black-Scholes-Merton price."""
import math

import numpy as np
import pytest

from domains.analytics.domain.services.pde_solver import CrankNicolsonPDE, price_grid
from domains.analytics.application.services.derivatives.black_scholes import BlackScholesMerton

S0, R = 24000.0, 0.065


def _errors(q: float):
    for days in (1, 3, 7, 30, 60):
        T = days / 365
        for sigma in (0.10, 0.25, 0.40):
            for K in np.linspace(0.9 * S0, 1.1 * S0, 9):
                for kind in ("call", "put"):
                    pde = CrankNicolsonPDE(S0, K, T, R, sigma, kind, q=q).solve()
                    bsm = BlackScholesMerton(S0, K, T, R, sigma, kind, q=q).solve()
                    yield days, abs(pde - bsm)


@pytest.mark.unit
@pytest.mark.parametrize("q", [0.0, 0.012])
def test_matches_black_scholes_across_strikes_maturities_and_vols(q):
    # Before the grid / Rannacher / dividend changes: max error 21.20, mean 0.94 (INR).
    errors = list(_errors(q))
    abs_err = np.array([e for _, e in errors])
    assert abs_err.max() < 0.30
    assert abs_err.mean() < 0.05


@pytest.mark.unit
def test_short_dated_atm_has_no_crank_nicolson_oscillation():
    # The old solver priced this 1-day ATM put at 26.80 against 48.00.
    T = 1 / 365
    pde = CrankNicolsonPDE(S0, S0, T, R, 0.10, "put").solve()
    bsm = BlackScholesMerton(S0, S0, T, R, 0.10, "put").solve()
    assert pde == pytest.approx(bsm, abs=0.05)


@pytest.mark.unit
def test_dividend_yield_lowers_calls_like_the_closed_form():
    T, K, sigma = 30 / 365, 24200.0, 0.14
    no_div = CrankNicolsonPDE(S0, K, T, R, sigma, "call").solve()
    with_div = CrankNicolsonPDE(S0, K, T, R, sigma, "call", q=0.012).solve()
    assert with_div < no_div
    assert with_div == pytest.approx(BlackScholesMerton(S0, K, T, R, sigma, "call", q=0.012).solve(), abs=0.1)


@pytest.mark.unit
def test_put_call_parity():
    T, K, sigma, q = 45 / 365, 23500.0, 0.2, 0.01
    call = CrankNicolsonPDE(S0, K, T, R, sigma, "call", q=q).solve()
    put = CrankNicolsonPDE(S0, K, T, R, sigma, "put", q=q).solve()
    assert call - put == pytest.approx(S0 * math.exp(-q * T) - K * math.exp(-R * T), abs=0.2)


@pytest.mark.unit
def test_grid_covers_spot_and_strike_with_room_to_spare():
    nodes = price_grid(S0, 26000.0, 7 / 365, 0.15, 300)
    assert nodes[0] < S0 < 26000.0 < nodes[-1]
    assert len(nodes) == 301
    # Tiny sigma*sqrt(T) still gets a usable grid
    tiny = price_grid(S0, S0, 1e-6, 1e-6, 300)
    assert tiny[-1] > tiny[0]


@pytest.mark.unit
def test_batched_chain_matches_single_contract_solver_exactly():
    from domains.analytics.domain.services.pde_solver import price_chain_cn
    strikes = [23500.0, 24000.0, 24000.0, 24600.0, 25000.0]
    sigmas = [0.18, 0.14, 0.15, 0.13, 0.16]
    is_call = [True, True, False, False, True]
    T, q = 9 / 365, 0.012
    batched = price_chain_cn(S0, T, R, strikes, sigmas, is_call, q=q)
    single = [CrankNicolsonPDE(S0, K, T, R, s, "call" if c else "put", q=q).solve()
              for K, s, c in zip(strikes, sigmas, is_call)]
    assert batched.tolist() == pytest.approx(single, abs=1e-9)


@pytest.mark.unit
def test_batched_chain_handles_empty_input():
    from domains.analytics.domain.services.pde_solver import price_chain_cn
    assert price_chain_cn(S0, 0.1, R, [], [], []).size == 0


@pytest.mark.unit
def test_vectorised_bsm_matches_scalar():
    from domains.analytics.application.services.derivatives.black_scholes import bsm_prices
    strikes, sigmas, calls = [23000.0, 24000.0, 25000.0], [0.2, 0.14, 0.12], [True, False, True]
    vec = bsm_prices(S0, strikes, 20 / 365, R, sigmas, calls, q=0.01)
    scalar = [BlackScholesMerton(S0, K, 20 / 365, R, s, "call" if c else "put", q=0.01).solve()
              for K, s, c in zip(strikes, sigmas, calls)]
    assert vec.tolist() == pytest.approx(scalar, abs=1e-9)
