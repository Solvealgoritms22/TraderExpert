from __future__ import annotations

import ctypes
import logging
import threading
import time
from pathlib import Path

import pystray
import webview
from PIL import Image, ImageDraw

from ai_client import AIClient
from app_metadata import APP_NAME
from app_paths import data_path, resource_path
from balance_service import BalanceService
from external_context import ExternalContextService
from main_window import MainWindow
from mt5_client import MT5Client, MarketDataError
from prediction_engine import PredictionEngine
from settings_manager import SettingsManager
from signal_history import SignalHistory


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(data_path("app.log"), encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def set_windows_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
    except Exception:
        pass


def set_window_icon_win32(title: str, ico_path: str):
    try:
        # Win32 constants
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        
        user32 = ctypes.windll.user32
        
        # Try finding the window multiple times in case it is still initializing
        for _ in range(15):
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                hicon = user32.LoadImageW(
                    None,
                    ico_path,
                    IMAGE_ICON,
                    0, 0,
                    LR_LOADFROMFILE
                )
                if hicon:
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
                    logger.info("Successfully set custom Win32 window icon.")
                    return True
            time.sleep(0.2)
    except Exception as e:
        logger.error("Error setting Win32 window icon: %s", e)
    return False


class TrayController:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self.thread = None

    def start(self):
        if self.icon:
            return
        self.icon = pystray.Icon(
            APP_NAME,
            self._create_icon(),
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem("Mostrar", lambda icon=None, item=None: self.app.open_main()),
                pystray.MenuItem("Analizar", lambda icon=None, item=None: self.app.run_analysis_now()),
                pystray.MenuItem("Iniciar motor", lambda icon=None, item=None: self.app.start_engine()),
                pystray.MenuItem("Detener motor", lambda icon=None, item=None: self.app.stop_engine()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", lambda icon=None, item=None: self.app.quit()),
            ),
        )
        self.thread = threading.Thread(target=self.icon.run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.icon:
            self.icon.stop()
            self.icon = None

    @staticmethod
    def _create_icon():
        icon_path = resource_path("traderexpert.png")
        if icon_path.exists():
            try:
                return Image.open(icon_path)
            except Exception:
                pass
        image = Image.new("RGBA", (64, 64), (17, 19, 19, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(31, 33, 33, 255), outline=(58, 65, 69, 255), width=2)
        draw.line((18, 42, 29, 31, 38, 36, 48, 20), fill=(110, 231, 183, 255), width=4)
        draw.polygon((45, 20, 49, 20, 49, 24), fill=(110, 231, 183, 255))
        return image


class TraderExpertApp:
    def __init__(self):
        self.settings = SettingsManager()
        self.history = SignalHistory()
        self.mt5 = MT5Client()
        self.external_context = ExternalContextService()
        self.ai_client = self._build_ai_client()
        self.engine = PredictionEngine(ai=self.ai_client)
        self.balance = BalanceService(self.settings, self.history, self.mt5)
        self.window = MainWindow(self)
        self.tray = TrayController(self)
        self.engine_running = False
        self._loop_thread = None
        self._lock = threading.Lock()
        self._last_signal = None
        self._shutting_down = False

    def _build_ai_client(self) -> AIClient:
        return AIClient(
            provider=self.settings.get("ai_provider", "openai"),
            api_key=self.settings.get_ai_api_key(),
            model=self.settings.get("ai_model", "gpt-4o"),
            endpoint=self.settings.get("ai_endpoint", ""),
            api_version=self.settings.get("ai_api_version", "2025-01-01-preview"),
        )

    def rebuild_ai_client(self):
        self.ai_client = self._build_ai_client()
        self.engine.ai = self.ai_client

    def start(self):
        set_windows_app_id()
        self.window.create()
        threading.Thread(target=self._connection_monitor_loop, daemon=True).start()
        webview.start(
            self._on_webview_ready, 
            debug=False, 
            icon=str(resource_path("traderexpert.ico"))
        )

    def _connection_monitor_loop(self):
        last_status = None
        while not self._shutting_down:
            if self.settings.get("is_configured"):
                try:
                    current_status = self.mt5.check_connection() if self.mt5.available else False
                    if current_status != last_status:
                        last_status = current_status
                        if self.window and self.window.window:
                            self.window.push_state(self.state_payload())
                except Exception:
                    pass
            time.sleep(5)

    def _on_webview_ready(self):
        self.tray.start()
        ico_path = str(resource_path("traderexpert.ico"))
        threading.Thread(target=set_window_icon_win32, args=("TraderExpert", ico_path), daemon=True).start()
        threading.Thread(target=self.connect_mt5_in_background, daemon=True).start()

    def connect_mt5_in_background(self):
        if self.settings.get("is_configured"):
            try:
                self.mt5.ensure_connected(
                    path=self.settings.get("mt5_path", ""),
                    account=self.settings.get("mt5_account", ""),
                    password=self.settings.get_mt5_password(),
                    server=self.settings.get("mt5_server", ""),
                )
                logger.info("MT5 background auto-connection established.")
                # Verify connection establishes with the trade server
                for _ in range(10):
                    if self.mt5.check_connection():
                        logger.info("MT5 background connection verified to trade server.")
                        break
                    time.sleep(1)
                self.window.push_state(self.state_payload())
            except Exception as exc:
                logger.warning("MT5 background auto-connection failed: %s", exc)

    def route_after_splash(self):
        self.settings.set("splash_seen", True)
        if not self.settings.get("is_configured"):
            return self.open_config()
        return self.open_main()

    def open_config(self):
        full_settings = self.settings.settings.copy()
        full_settings["mt5_password"] = self.settings.get_mt5_password()
        full_settings["ai_api_key"] = self.settings.get_ai_api_key()
        full_settings["ai_api_keys"] = self.settings.get_all_ai_api_keys()
        self.window.load_config(full_settings)
        return {"success": True}

    def open_main(self):
        self.window.load_main(self.state_payload())
        return {"success": True}

    def validate_config(self, values: dict):
        required = ["market_type", "symbol", "chart_type", "timeframe"]
        for key in required:
            if not str(values.get(key, "")).strip():
                raise ValueError(f"Campo requerido: {key}")
        if values.get("timeframe") not in {"M1", "M2", "M5", "M15", "M30", "H1"}:
            raise ValueError("Timeframe invalido.")
        for key in ["prediction_horizon_minutes", "analysis_interval_minutes"]:
            value = int(values.get(key) or 0)
            if value <= 0:
                raise ValueError(f"{key} debe ser mayor que cero.")
            values[key] = value
        for key in ["virtual_balance", "stake_amount", "payout_percent", "confidence_threshold"]:
            value = float(values.get(key) or 0)
            if value <= 0:
                raise ValueError(f"{key} debe ser mayor que cero.")
            values[key] = value
        if not 0.5 <= values["confidence_threshold"] <= 0.95:
            raise ValueError("El umbral de confianza debe estar entre 0.50 y 0.95.")
        if values["stake_amount"] > values["virtual_balance"]:
            raise ValueError("El monto por senal no puede superar el saldo virtual.")
        values["symbol"] = str(values["symbol"]).strip()
        values["is_configured"] = True
        return values

    def save_config(self, values: dict):
        try:
            clean = self.validate_config(dict(values))
            old_initial = float(self.settings.get("initial_virtual_balance", 0.0))
            new_balance = float(clean["virtual_balance"])
            if not self.settings.get("is_configured") or old_initial != new_balance:
                clean["initial_virtual_balance"] = new_balance
            # Handle AI API key securely via keyring
            ai_api_key = clean.pop("ai_api_key", None)
            if ai_api_key:
                self.settings.set_ai_api_key(ai_api_key)
            self.settings.save_settings(clean)
            # Rebuild AI client with new provider settings
            self.rebuild_ai_client()
            self.window.push_state(self.state_payload())
            # Try to initialize MT5 and login using the provided settings (non-blocking)
            try:
                self.mt5.ensure_connected(
                    path=clean.get("mt5_path", ""),
                    account=clean.get("mt5_account", ""),
                    password=self.settings.get_mt5_password(),
                    server=clean.get("mt5_server", ""),
                )
                logger.info("MT5 initialized/login attempt after saving settings.")
            except Exception as exc:
                logger.warning("MT5 login attempt failed after saving settings: %s", exc)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def start_engine(self):
        if not self.settings.get("is_configured"):
            return {"success": False, "message": "Completa la configuracion inicial."}
        if not self.mt5.check_connection():
            return {"success": False, "message": "Conecta MetaTrader 5 para iniciar el analisis."}
        symbol = self.settings.get("symbol", "")
        if symbol and not self.mt5.is_market_open(symbol):
            return {"success": False, "message": f"Mercado cerrado para {symbol}. Espera a que abra."}
        if self.settings.get("trading_mode") == "real":
            trade_check = self.mt5.can_trade()
            if not trade_check.get("can_trade"):
                return {"success": False, "message": trade_check.get("reason", "No se puede operar")}
        if self.engine_running:
            return {"success": True}
        self.engine_running = True
        self._loop_thread = threading.Thread(target=self._engine_loop, daemon=True)
        self._loop_thread.start()
        self.window.push_state(self.state_payload())
        return {"success": True}

    def stop_engine(self):
        self.engine_running = False
        self.window.push_state(self.state_payload())
        return {"success": True}

    def _engine_loop(self):
        while self.engine_running and not self._shutting_down:
            try:
                self.run_analysis_now()
            except Exception as exc:
                logger.warning("Analisis automatico fallo: %s", exc)
            wait_seconds = max(30, int(self.settings.get("analysis_interval_minutes", 5)) * 60)
            for _ in range(wait_seconds):
                if not self.engine_running or self._shutting_down:
                    break
                time.sleep(1)

    def _compute_atr(self, bars: list, period: int = 14) -> float:
        """Simple ATR calculation for SL/TP."""
        if len(bars) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(bars)):
            h = float(bars[i]["high"])
            l = float(bars[i]["low"])
            pc = float(bars[i - 1]["close"])
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        return sum(trs[-period:]) / period if trs else 0.0

    def run_analysis_now(self):
        if not self.settings.get("is_configured"):
            return {"success": False, "message": "Completa la configuracion inicial."}

        if not self.mt5.check_connection():
            self.engine_running = False
            self.window.push_state(self.state_payload())
            return {"success": False, "message": "MT5 desconectado. Motor detenido."}

        symbol = self.settings.get("symbol", "")
        if symbol and not self.mt5.is_market_open(symbol):
            return {"success": False, "message": f"Mercado cerrado para {symbol}."}

        with self._lock:
            self.balance.evaluate_due_signals()

        try:
            snapshot = self.mt5.snapshot(self.settings.settings)
            snapshot["external_context"] = self.external_context.collect(self.settings.settings)
            signal = self.engine.analyze(snapshot, self.settings.settings)

            # --- Real trading: place order if direction is UP/DOWN ---
            trading_mode = self.settings.get("trading_mode", "simulation")
            if trading_mode == "real" and signal["direction"] in ("UP", "DOWN"):
                trade_check = self.mt5.can_trade()
                if trade_check.get("can_trade"):
                    volume = float(self.settings.get("lot_size", 0.01))
                    # Compute SL/TP from ATR
                    atr = self._compute_atr(snapshot["bars"])
                    entry_price = float(signal.get("entry_price", 0))
                    sl_distance = atr * float(self.settings.get("auto_sl_atr_multiplier", 1.5))
                    tp_distance = sl_distance * float(self.settings.get("auto_tp_ratio", 2.0))

                    if signal["direction"] == "UP":
                        sl = round(entry_price - sl_distance, 5) if sl_distance > 0 else 0.0
                        tp = round(entry_price + tp_distance, 5) if tp_distance > 0 else 0.0
                    else:
                        sl = round(entry_price + sl_distance, 5) if sl_distance > 0 else 0.0
                        tp = round(entry_price - tp_distance, 5) if tp_distance > 0 else 0.0

                    order = self.mt5.place_market_order(
                        symbol=signal["symbol"],
                        direction=signal["direction"],
                        volume=volume,
                        sl=sl,
                        tp=tp,
                        comment=f"TE_{signal['id'][:8]}",
                    )
                    if order.get("success"):
                        signal["mt5_ticket"] = order["ticket"]
                        signal["mt5_open_price"] = order["price"]
                        signal["mt5_volume"] = order["volume"]
                        signal["mt5_sl"] = sl
                        signal["mt5_tp"] = tp
                        logger.info("Real order placed: ticket=%d for signal %s", order["ticket"], signal["id"][:8])
                    else:
                        signal["risk_flags"] = signal.get("risk_flags", []) + [f"order_failed: {order.get('message', '')}"]
                        logger.warning("Real order failed: %s", order.get("message"))
                else:
                    signal["risk_flags"] = signal.get("risk_flags", []) + [f"cannot_trade: {trade_check.get('reason', '')}"]

            with self._lock:
                signal = self.history.add(signal)
                self._last_signal = signal
                self.window.push_state(self.state_payload())

            return {"success": True, "signal": signal}
        except MarketDataError as exc:
            self.window.show_error(str(exc))
            return {"success": False, "message": str(exc)}
        except Exception as exc:
            logger.exception("No se pudo analizar mercado")
            self.window.show_error(str(exc))
            return {"success": False, "message": str(exc)}

    def state_payload(self):
        signals = self.history.list_entries()
        latest = self._last_signal or (signals[0] if signals else {})
        mt5_connected = self.mt5.check_connection() if self.mt5.available else False
        symbol = self.settings.get("symbol", "")
        payload = {
            "settings": self.settings.settings,
            "signals": signals,
            "summary": SignalHistory.summarize(signals, self.settings.get("virtual_balance", 0.0)),
            "latest_signal": latest,
            "engine_running": self.engine_running,
            "mt5_connected": mt5_connected,
            "market_open": self.mt5.is_market_open(symbol) if mt5_connected and symbol else False,
        }
        # Real mode: include account info and open positions
        if self.settings.get("trading_mode") == "real" and mt5_connected:
            payload["account_info"] = self.mt5.get_account_info()
            payload["open_positions"] = self.mt5.get_open_positions()
        return payload

    def test_ai_connection(self):
        return self.ai_client.test_connection()

    def get_mt5_symbols(self):
        """Return available MT5 symbols for dynamic UI."""
        if not self.mt5.check_connection():
            return {"success": False, "symbols": []}
        return {"success": True, "symbols": self.mt5.get_available_symbols()}

    def get_market_status(self):
        """Return MT5 connection and market open status."""
        mt5_connected = self.mt5.check_connection() if self.mt5.available else False
        symbol = self.settings.get("symbol", "")
        trade_check = self.mt5.can_trade() if mt5_connected else {"can_trade": False, "reason": "MT5 no conectado"}
        return {
            "mt5_connected": mt5_connected,
            "market_open": self.mt5.is_market_open(symbol) if mt5_connected and symbol else False,
            "can_trade": trade_check.get("can_trade", False),
            "trade_reason": trade_check.get("reason", ""),
            "account_info": self.mt5.get_account_info() if mt5_connected else {},
        }

    def refresh_state(self):
        self.window.push_state(self.state_payload())

    def quit(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self.engine_running = False
        try:
            self.mt5.shutdown()
            self.tray.stop()
        finally:
            if self.window.window:
                self.window.window.destroy()


if __name__ == "__main__":
    TraderExpertApp().start()
