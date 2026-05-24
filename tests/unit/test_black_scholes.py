import unittest
from domains.analytics.application.derivatives.black_scholes import BlackScholesMerton

class TestBlackScholes(unittest.TestCase):
    def test_black_scholes_call(self):
        # S=100, K=100, T=1, r=0.05, sigma=0.2, q=0.0
        # Expected call price is ~10.450585
        pricer = BlackScholesMerton(S0=100.0, K=100.0, T=1.0, r=0.05, sigma=0.2, option_type='call')
        price = pricer.solve()
        self.assertAlmostEqual(price, 10.450585, places=4)

    def test_black_scholes_put(self):
        # S=100, K=100, T=1, r=0.05, sigma=0.2, q=0.0
        # Expected put price is ~5.573526
        pricer = BlackScholesMerton(S0=100.0, K=100.0, T=1.0, r=0.05, sigma=0.2, option_type='put')
        price = pricer.solve()
        self.assertAlmostEqual(price, 5.573526, places=4)

    def test_black_scholes_with_dividends(self):
        # S=100, K=95, T=0.5, r=0.08, sigma=0.3, q=0.03
        # Expected call price is ~12.144378
        pricer = BlackScholesMerton(S0=100.0, K=95.0, T=0.5, r=0.08, sigma=0.3, option_type='call', q=0.03)
        price = pricer.solve()
        self.assertAlmostEqual(price, 12.144378, places=4)

if __name__ == '__main__':
    unittest.main()
