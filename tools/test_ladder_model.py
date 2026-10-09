"""Tests for the reference maths. Run: python3 -m unittest discover -s tools"""
import math
import random
import unittest

import ladder_model as m


class LadderTests(unittest.TestCase):
    def test_reference_ladder(self):
        lots = m.ladder_lots(0.01, 6, d=1, t=1, s=0, c=0, step=0.01)
        self.assertEqual([round(x, 2) for x in lots], [0.01, 0.03, 0.06, 0.12, 0.24, 0.48])

    def test_terminal14_feasibility_numbers(self):
        # Values measured on Terminal 14 on 2026-10-09: median ATR 7.70, V = 100 USC.
        d = t = 1.5 * 7.70
        lots = m.ladder_lots(0.01, 3, d, t, 0.4, 0, 0.01)
        self.assertEqual([round(x, 2) for x in lots], [0.01, 0.04, 0.09])
        self.assertAlmostEqual(100 * m.failed_loss(lots, d, t, 0.4, 0), 189, delta=1)

    def test_every_step_reaches_target_profit_and_loss_within_cap(self):
        rng = random.Random(7)
        for _ in range(2000):
            d = rng.uniform(0.5, 20)
            t = rng.uniform(0.5, 20)
            s = rng.uniform(0, 0.5)
            c = rng.uniform(0, 0.1) * t
            step = rng.choice([0.01, 0.1, 1.0])
            v = rng.choice([1, 100])
            balance = rng.uniform(1e3, 1e7)
            l1, n, lots = m.first_lot(balance, 0.05, rng.randint(3, 8), d, t, s, c,
                                      v, step, vmin=step, vmax=500)
            if lots is None:
                continue
            pi = l1 * (t - c)
            for k in range(1, n + 1):
                self.assertGreaterEqual(m.basket_profit_at_target(lots, k, d, t, s, c), pi - 1e-9)
            self.assertLessEqual(v * m.failed_loss(lots, d, t, s, c), balance * 0.05 + 1e-6)

    def test_first_lot_reduces_steps_then_gives_up(self):
        d = t = 11.55
        # 3775 USC is just enough for N = 3 at the minimum lot.
        l1, n, _ = m.first_lot(3800, 0.05, 6, d, t, 0.4, 0, 100, 0.01, 0.01, 500)
        self.assertEqual((round(l1, 2), n), (0.01, 3))
        l1, n, lots = m.first_lot(677.31, 0.05, 6, d, t, 0.4, 0, 100, 0.01, 0.01, 500)
        self.assertIsNone(lots)

    def test_margin_limit_binds(self):
        l1, n, lots = m.first_lot(1e7, 0.05, 4, 1, 1, 0, 0, 1, 0.01, 0.01, 500,
                                  margin_per_lot=100, free_margin=1000)
        self.assertLessEqual(100 * sum(lots), 500 + 1e-9)


class SignalTests(unittest.TestCase):
    def test_pure_uptrend_buys(self):
        closes = [100 * math.exp(0.001 * i) for i in range(64)]
        self.assertEqual(m.direction(closes), 1)

    def test_noisy_downtrend_sells(self):
        rng = random.Random(1)
        closes = [100 - 0.05 * i + rng.gauss(0, 0.05) for i in range(64)]
        self.assertEqual(m.direction(closes), -1)

    def test_flat_noise_stays_out(self):
        rng = random.Random(3)
        closes = [100 + rng.gauss(0, 0.2) for _ in range(64)]
        self.assertEqual(m.direction(closes), 0)

    def test_hand_computed_tstat(self):
        # ln-closes 0, 1, 1, 2 (x 0.01): slope 0.006, SSE 0.00002, se = sqrt(1e-5/5).
        closes = [math.exp(v * 0.01) for v in (0, 1, 1, 2)]
        self.assertAlmostEqual(m.regression_tstat(closes), 0.006 / math.sqrt(1e-5 / 5), places=6)
        self.assertAlmostEqual(m.efficiency_ratio([1, 2, 1, 3]), 0.5)



class SimulationTests(unittest.TestCase):
    def test_random_paths_win_pi_or_lose_at_most_the_cap(self):
        rng = random.Random(11)
        d, t, s, spread = 3.0, 3.0, 0.4, 0.1
        for _ in range(500):
            side1 = rng.choice([1, -1])
            n = rng.randint(3, 7)
            lots = m.ladder_lots(0.01, n, d, t, s, 0, 0.01)
            bids = [4000.0]
            for _ in range(20000):
                bids.append(bids[-1] + rng.choice([-0.05, 0.05]))
            res = m.simulate(bids, spread, side1, lots, d, t, s)
            if res is None:
                continue
            pnl, filled = res
            if pnl > 0:
                # Discrete 0.05 ticks can overshoot an edge by one tick.
                self.assertGreaterEqual(pnl, 0.01 * t - 0.05 * sum(lots[:filled]) - 1e-9)
            else:
                self.assertEqual(filled, n)
                self.assertLessEqual(-pnl, m.failed_loss(lots, d, t, s, 0) + 1e-9)


if __name__ == "__main__":
    unittest.main()
