from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    # pyrefly: ignore [missing-import]
    import keyring
except Exception:
    keyring = None
from app_metadata import APP_NAME

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover - depends on Windows terminal install
    mt5 = None


class MarketDataError(RuntimeError):
    pass


TIMEFRAME_NAMES = ("M1", "M2", "M5", "M15", "M30", "H1")

MAGIC_NUMBER = 20250516  # Unique ID for TraderExpert orders


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
            raise MarketDataError(f"No se pudo conectar a MT5")

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

    def check_connection(self) -> bool:
        if mt5 is None:
            self.connected = False
            return False
        try:
            info = mt5.terminal_info()
            if info is None:
                self.connected = False
                return False
            is_conn = bool(info.connected)
            self.connected = is_conn
            return is_conn
        except Exception:
            self.connected = False
            return False

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

    # ------------------------------------------------------------------
    # Account Info
    # ------------------------------------------------------------------

    def get_account_info(self) -> dict[str, Any]:
        """Get real-time account balance, equity, margin, etc."""
        if mt5 is None or not self.connected:
            return {}
        try:
            info = mt5.account_info()
            if info is None:
                return {}
            return {
                "balance": float(info.balance),
                "equity": float(info.equity),
                "margin": float(info.margin),
                "free_margin": float(info.margin_free),
                "profit": float(info.profit),
                "leverage": int(info.leverage),
                "currency": str(info.currency),
                "server": str(info.server),
                "login": int(info.login),
                "trade_mode": int(info.trade_mode),  # 0=demo, 2=real
            }
        except Exception as exc:
            logger.warning("Error getting account info: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Symbol Discovery
    # ------------------------------------------------------------------

    def get_available_symbols(self) -> list[dict[str, Any]]:
        """List all visible symbols available from the broker."""
        if mt5 is None or not self.connected:
            return []
        try:
            symbols = mt5.symbols_get()
            if not symbols:
                return []
            result = []
            for s in symbols:
                if not s.visible:
                    continue
                result.append({
                    "name": s.name,
                    "path": s.path,
                    "description": s.description,
                    "trade_mode": int(s.trade_mode),
                    "spread": int(s.spread),
                    "digits": int(s.digits),
                    "volume_min": float(s.volume_min),
                    "volume_max": float(s.volume_max),
                    "volume_step": float(s.volume_step),
                })
            return result
        except Exception as exc:
            logger.warning("Error listing symbols: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Market Status
    # ------------------------------------------------------------------

    def is_market_open(self, symbol: str) -> bool:
        """Check if the market is open for trading a specific symbol."""
        if mt5 is None or not self.connected:
            return False
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return False
            # trade_mode: 0=disabled, 4=full access
            return info.trade_mode == 4
        except Exception:
            return False

    def can_trade(self) -> dict[str, Any]:
        """Check if algorithmic trading is enabled and terminal is connected."""
        if mt5 is None:
            return {"can_trade": False, "reason": "MetaTrader5 no instalado"}
        try:
            info = mt5.terminal_info()
            if info is None:
                return {"can_trade": False, "reason": "MT5 no conectado"}
            if not info.connected:
                return {"can_trade": False, "reason": "MT5 sin conexion al servidor de trading"}
            if not info.trade_allowed:
                return {"can_trade": False, "reason": "Habilita 'Allow algo trading' en MT5 (Tools > Options > Expert Advisors)"}
            return {"can_trade": True, "reason": ""}
        except Exception as exc:
            return {"can_trade": False, "reason": str(exc)[:200]}

    # ------------------------------------------------------------------
    # Order Execution
    # ------------------------------------------------------------------

    def place_market_order(self, symbol: str, direction: str, volume: float,
                           sl: float = 0.0, tp: float = 0.0, comment: str = "") -> dict[str, Any]:
        """Place a market order (BUY or SELL)."""
        if mt5 is None or not self.connected:
            return {"success": False, "message": "MT5 no conectado"}

        self.ensure_symbol(symbol)
        order_type = mt5.ORDER_TYPE_BUY if direction == "UP" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "message": f"No se puede obtener precio para {symbol}"}

        price = tick.ask if direction == "UP" else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": comment or "TraderExpert",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl > 0:
            request["sl"] = sl
        if tp > 0:
            request["tp"] = tp

        logger.info("Sending order: %s %s %.2f lots @ %.5f (SL=%.5f, TP=%.5f)",
                     direction, symbol, volume, price, sl, tp)
        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "message": f"order_send returned None: {mt5.last_error()}"}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning("Order failed: %s (retcode=%d)", result.comment, result.retcode)
            return {"success": False, "message": f"Orden rechazada: {result.comment} (code {result.retcode})"}

        logger.info("Order executed: ticket=%d, price=%.5f, volume=%.2f", result.order, result.price, result.volume)
        return {
            "success": True,
            "ticket": int(result.order),
            "price": float(result.price),
            "volume": float(result.volume),
        }

    def close_position(self, ticket: int) -> dict[str, Any]:
        """Close an open position by its ticket number."""
        if mt5 is None or not self.connected:
            return {"success": False, "message": "MT5 no conectado"}

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"success": False, "message": f"Posicion {ticket} no encontrada (ya cerrada?)"}

        pos = positions[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return {"success": False, "message": f"No se puede obtener precio para {pos.symbol}"}

        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": "TraderExpert Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        logger.info("Closing position: ticket=%d, %s %.2f lots @ %.5f",
                     ticket, pos.symbol, pos.volume, price)
        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "message": f"close order_send returned None: {mt5.last_error()}"}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"success": False, "message": f"Cierre rechazado: {result.comment} (code {result.retcode})"}

        logger.info("Position closed: ticket=%d, price=%.5f", ticket, result.price)
        return {"success": True, "price": float(result.price), "profit": float(pos.profit)}

    def get_open_positions(self) -> list[dict[str, Any]]:
        """Get all open positions placed by TraderExpert."""
        if mt5 is None or not self.connected:
            return []
        try:
            positions = mt5.positions_get()
            if not positions:
                return []
            return [
                {
                    "ticket": int(p.ticket),
                    "symbol": str(p.symbol),
                    "volume": float(p.volume),
                    "type": "BUY" if p.type == 0 else "SELL",
                    "price_open": float(p.price_open),
                    "price_current": float(p.price_current),
                    "profit": float(p.profit),
                    "sl": float(p.sl),
                    "tp": float(p.tp),
                    "time": int(p.time),
                    "magic": int(p.magic),
                    "comment": str(p.comment),
                }
                for p in positions
                if p.magic == MAGIC_NUMBER
            ]
        except Exception as exc:
            logger.warning("Error listing positions: %s", exc)
            return []
