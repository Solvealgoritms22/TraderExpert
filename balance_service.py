from __future__ import annotations

import logging
from typing import Any

from signal_history import parse_dt, utc_now

logger = logging.getLogger(__name__)


class BalanceService:
    def __init__(self, settings_manager, history, mt5_client):
        self.settings = settings_manager
        self.history = history
        self.mt5 = mt5_client

    @staticmethod
    def settle_signal(signal: dict, exit_price: float) -> dict:
        direction = signal.get("direction")
        entry = float(signal.get("entry_price") or 0)
        stake = float(signal.get("stake_amount") or 0)
        payout = float(signal.get("payout_percent") or 0) / 100
        if not entry or not exit_price:
            result = "TIE"
        elif direction == "UP":
            result = "WIN" if exit_price > entry else "LOSS" if exit_price < entry else "TIE"
        elif direction == "DOWN":
            result = "WIN" if exit_price < entry else "LOSS" if exit_price > entry else "TIE"
        else:
            result = "WAIT"
        if result == "WIN":
            delta = stake * payout
        elif result == "LOSS":
            delta = -stake
        else:
            delta = 0.0
        return {"status": result, "exit_price": exit_price, "balance_delta": round(delta, 2)}

    def evaluate_due_signals(self) -> list[dict[str, Any]]:
        now = utc_now()
        trading_mode = self.settings.get("trading_mode", "simulation")

        if trading_mode == "real":
            return self._evaluate_real(now)
        return self._evaluate_simulation(now)

    def _evaluate_simulation(self, now) -> list[dict[str, Any]]:
        """Original virtual balance settlement."""
        evaluated = []
        for signal in self.history.pending():
            expires_at = signal.get("expires_at")
            if not expires_at or parse_dt(expires_at) > now:
                continue
            tick = self.mt5.get_tick(
                signal["symbol"],
                self.settings.get("mt5_path", ""),
            )
            result = self.settle_signal(signal, float(tick["price"]))
            updated = self.history.update(signal["id"], result)
            if updated:
                balance = float(self.settings.get("virtual_balance", 0.0)) + result["balance_delta"]
                self.settings.set("virtual_balance", round(balance, 2))
                evaluated.append(updated)
        return evaluated

    def _evaluate_real(self, now) -> list[dict[str, Any]]:
        """Close MT5 positions when signals expire and record actual P&L."""
        evaluated = []
        for signal in self.history.pending():
            expires_at = signal.get("expires_at")
            if not expires_at or parse_dt(expires_at) > now:
                continue

            ticket = signal.get("mt5_ticket")
            if ticket:
                # Close the real position in MT5
                close_result = self.mt5.close_position(int(ticket))
                if close_result.get("success"):
                    exit_price = close_result.get("price", 0.0)
                    profit = close_result.get("profit", 0.0)
                    update_data = {
                        "status": "WIN" if profit > 0 else "LOSS" if profit < 0 else "TIE",
                        "exit_price": exit_price,
                        "balance_delta": round(profit, 2),
                        "mt5_close_price": exit_price,
                        "mt5_profit": profit,
                    }
                else:
                    # Position may have been manually closed or hit SL/TP
                    logger.warning("Could not close position %d: %s", ticket, close_result.get("message"))
                    tick = self.mt5.get_tick(signal["symbol"], self.settings.get("mt5_path", ""))
                    update_data = self.settle_signal(signal, float(tick["price"]))
                    update_data["mt5_close_note"] = close_result.get("message", "auto-closed or SL/TP hit")
            else:
                # Signal had no MT5 ticket (order failed), settle virtually
                tick = self.mt5.get_tick(signal["symbol"], self.settings.get("mt5_path", ""))
                update_data = self.settle_signal(signal, float(tick["price"]))

            updated = self.history.update(signal["id"], update_data)
            if updated:
                evaluated.append(updated)
        return evaluated
