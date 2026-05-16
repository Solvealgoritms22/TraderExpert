from __future__ import annotations

from signal_history import parse_dt, utc_now


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

    def evaluate_due_signals(self):
        now = utc_now()
        evaluated = []
        for signal in self.history.pending():
            expires_at = signal.get("expires_at")
            if not expires_at or parse_dt(expires_at) > now:
                continue
            tick = self.mt5.get_tick(
                signal["symbol"],
                self.settings.get("mt5_path", ""),
                self.settings.get("mt5_account", ""),
                self.settings.get("mt5_password", ""),
                self.settings.get("mt5_server", ""),
            )
            result = self.settle_signal(signal, float(tick["price"]))
            updated = self.history.update(signal["id"], result)
            if updated:
                balance = float(self.settings.get("virtual_balance", 0.0)) + result["balance_delta"]
                self.settings.set("virtual_balance", round(balance, 2))
                evaluated.append(updated)
        return evaluated
