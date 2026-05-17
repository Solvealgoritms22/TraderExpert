import unittest
from datetime import timedelta

from balance_service import BalanceService
from external_context import ExternalContextService
from prediction_engine import PredictionEngine
from signal_history import utc_now
from technical_analysis import compute_features


def make_bars(count=90, start=1.1000, step=0.0002):
    bars = []
    price = start
    now = utc_now() - timedelta(minutes=count)
    for i in range(count):
        price += step
        bars.append(
            {
                "time": (now + timedelta(minutes=i)).isoformat(),
                "open": price - step,
                "high": price + abs(step) * 1.5,
                "low": price - abs(step) * 1.5,
                "close": price,
                "tick_volume": 100 + i,
                "spread": 1,
                "real_volume": 0,
            }
        )
    return bars


class FakeAI:
    configured = False

    def complete_json(self, messages):
        raise RuntimeError("offline")


class FakeRAG:
    def load_context(self, query_terms=None, max_chars=5000, custom_dir=None):
        return "Reglas conservadoras."


class CoreTests(unittest.TestCase):
    def test_compute_features_detects_uptrend(self):
        features = compute_features(make_bars())
        self.assertEqual(features["local_direction"], "UP")
        self.assertGreater(features["local_confidence"], 0.6)

    def test_prediction_engine_falls_back_and_allows_wait_gate(self):
        engine = PredictionEngine(ai=FakeAI(), rag=FakeRAG())
        settings = {
            "market_type": "Forex",
            "symbol": "EURUSD",
            "timeframe": "M1",
            "prediction_horizon_minutes": 5,
            "stake_amount": 10,
            "payout_percent": 80,
            "confidence_threshold": 0.95,
        }
        signal = engine.analyze({"bars": make_bars(), "tick": {"price": 1.12}}, settings)
        self.assertEqual(signal["direction"], "WAIT")
        self.assertEqual(signal["status"], "WAIT")

    def test_balance_settlement_win_loss_tie(self):
        base = {"entry_price": 100, "stake_amount": 10, "payout_percent": 80}
        up_win = BalanceService.settle_signal({**base, "direction": "UP"}, 101)
        down_loss = BalanceService.settle_signal({**base, "direction": "DOWN"}, 101)
        tie = BalanceService.settle_signal({**base, "direction": "UP"}, 100)
        self.assertEqual(up_win["status"], "WIN")
        self.assertEqual(up_win["balance_delta"], 8)
        self.assertEqual(down_loss["status"], "LOSS")
        self.assertEqual(down_loss["balance_delta"], -10)
        self.assertEqual(tie["status"], "TIE")
        self.assertEqual(tie["balance_delta"], 0)

    def test_external_context_shape_without_required_keys(self):
        service = ExternalContextService()
        context = service.collect({"symbol": "EURUSD", "market_type": "Forex"})
        self.assertIn("items", context)
        self.assertIn("warnings", context)
        self.assertIn("links", context)

    def test_balance_settlement_real_mode(self):
        from unittest.mock import MagicMock
        settings = MagicMock()
        settings.get.side_effect = lambda k, default=None: {
            "trading_mode": "real",
            "virtual_balance": 1000.0,
            "mt5_path": ""
        }.get(k, default)
        
        sig = {
            "id": "1",
            "symbol": "EURUSD",
            "direction": "UP",
            "entry_price": 1.1000,
            "expires_at": (utc_now() - timedelta(minutes=1)).isoformat(),
            "mt5_ticket": None
        }
        
        history = MagicMock()
        history.pending.return_value = [sig]
        history.update.return_value = sig
        
        mt5 = MagicMock()
        mt5.get_tick.return_value = {"price": 1.1050}
        
        service = BalanceService(settings, history, mt5)
        evaluated = service.evaluate_due_signals()
        
        self.assertEqual(len(evaluated), 1)
        settings.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
