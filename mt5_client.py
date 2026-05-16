from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import os
try:
    # pyrefly: ignore [missing-import]
    import keyring
except Exception:
    keyring = None
from app_metadata import APP_NAME


try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover - depends on Windows terminal install
    mt5 = None


class MarketDataError(RuntimeError):
    pass


TIMEFRAME_NAMES = ("M1", "M2", "M5", "M15", "M30", "H1")


def _timeframe_map() -> dict[str, Any]:
    if mt5 is None:
        return {}
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M2": mt5.TIMEFRAME_M2,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
    }


class MT5Client:
    def __init__(self):
        self.connected = False

    @property
    def available(self) -> bool:
        return mt5 is not None

    def initialize(self, path: str = "") -> bool:
        if mt5 is None:
            raise MarketDataError("MetaTrader5 no esta instalado. Ejecuta: pip install MetaTrader5")
        ok = mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            raise MarketDataError(f"No se pudo conectar a MT5: {mt5.last_error()}")

        # Optionally try to login using environment variables if present.
        acct = os.getenv("MT5_ACCOUNT")
        pwd = os.getenv("MT5_PASSWORD")
        srv = os.getenv("MT5_SERVER")
        if acct and pwd:
            try:
                acct_int = int(acct)
            except Exception:
                acct_int = acct
            login_ok = mt5.login(acct_int, pwd, srv) if srv else mt5.login(acct_int, pwd)
            if not login_ok:
                raise MarketDataError(f"MT5 login failed: {mt5.last_error()}")

        self.connected = True
        return True

    def shutdown(self):
        if mt5 is not None and self.connected:
            mt5.shutdown()
        self.connected = False

    def ensure_connected(self, path: str = "", account: Optional[str] = None, password: Optional[str] = None, server: Optional[str] = None):
        if not self.connected:
            self.initialize(path)
            # If account is provided, try to obtain password from env or keyring if not supplied
            if account:
                if not password:
                    # try environment
                    password = os.getenv("MT5_PASSWORD")
                    # try keyring
                    if not password and keyring:
                        try:
                            service = f"{APP_NAME}_mt5"
                            # Ensure account is a string for keyring lookup
                            account_str = str(account)
                            password = keyring.get_password(service, account_str) or keyring.get_password(service, "__default__")
                        except Exception:
                            password = None

                if password:
                    try:
                        try:
                            acct_int = int(account)
                        except Exception:
                            acct_int = account
                        login_ok = mt5.login(acct_int, password, server) if server else mt5.login(acct_int, password)
                        if not login_ok:
                            raise MarketDataError(f"MT5 login failed: {mt5.last_error()}")
                    except MarketDataError:
                        raise
                    except Exception as exc:
                        raise MarketDataError(f"MT5 login failed: {exc}")
                else:
                    logger = __import__('logging').getLogger(__name__)
                    logger.info("No MT5 password provided for account %s; assuming terminal already logged in.", account)

    def ensure_symbol(self, symbol: str):
        symbol = (symbol or "").strip()
        if not symbol:
            raise MarketDataError("Selecciona un simbolo MT5 valido.")
        if not mt5.symbol_select(symbol, True):
            raise MarketDataError(f"MT5 no puede seleccionar el simbolo {symbol}.")

    def get_rates(self, symbol: str, timeframe: str, count: int = 240, path: str = "", account: Optional[str] = None, password: Optional[str] = None, server: Optional[str] = None) -> list[dict[str, Any]]:
        self.ensure_connected(path, account=account, password=password, server=server)
        self.ensure_symbol(symbol)
        tf = _timeframe_map().get(str(timeframe).upper())
        if tf is None:
            raise MarketDataError(f"Timeframe no soportado: {timeframe}")
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) < 60:
            raise MarketDataError(f"Historico insuficiente para {symbol} {timeframe}.")
        bars = []
        for row in rates:
            bars.append(
                {
                    "time": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tick_volume": float(row["tick_volume"]),
                    "spread": float(row["spread"]),
                    "real_volume": float(row["real_volume"]),
                }
            )
        return bars

    def get_tick(self, symbol: str, path: str = "", account: Optional[str] = None, password: Optional[str] = None, server: Optional[str] = None) -> dict[str, Any]:
        self.ensure_connected(path, account=account, password=password, server=server)
        self.ensure_symbol(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MarketDataError(f"No hay tick actual para {symbol}: {mt5.last_error()}")
        data = tick._asdict()
        bid = float(data.get("bid") or 0)
        ask = float(data.get("ask") or 0)
        last = float(data.get("last") or 0)
        mid = ((bid + ask) / 2) if bid and ask else (last or bid or ask)
        if mid <= 0:
            raise MarketDataError(f"Tick invalido para {symbol}.")
        return {
            "time": datetime.fromtimestamp(int(data.get("time") or 0), tz=timezone.utc).isoformat(),
            "bid": bid,
            "ask": ask,
            "last": last,
            "price": mid,
            "volume": float(data.get("volume_real") or data.get("volume") or 0),
        }

    def snapshot(self, settings: dict[str, Any], count: int = 240) -> dict[str, Any]:
        symbol = settings.get("symbol", "EURUSD")
        timeframe = settings.get("timeframe", "M1")
        path = settings.get("mt5_path", "")
        account = settings.get("mt5_account")
        password = settings.get("mt5_password")
        server = settings.get("mt5_server")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": self.get_rates(symbol, timeframe, count=count, path=path, account=account, password=password, server=server),
            "tick": self.get_tick(symbol, path=path, account=account, password=password, server=server),
        }
