from __future__ import annotations

import ctypes
import logging
import threading
import time
from pathlib import Path

import pystray
import webview
from PIL import Image, ImageDraw

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
                pystray.MenuItem("Analizar ahora", lambda icon=None, item=None: self.app.run_analysis_now()),
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
        self.engine = PredictionEngine()
        self.balance = BalanceService(self.settings, self.history, self.mt5)
        self.window = MainWindow(self)
        self.tray = TrayController(self)
        self.engine_running = False
        self._loop_thread = None
        self._lock = threading.Lock()
        self._last_signal = None
        self._shutting_down = False

    def start(self):
        set_windows_app_id()
        self.window.create()
        webview.start(
            self._on_webview_ready, 
            debug=False, 
            icon=str(resource_path("traderexpert.ico"))
        )

    def _on_webview_ready(self):
        self.tray.start()

    def route_after_splash(self):
        self.settings.set("splash_seen", True)
        if not self.settings.get("is_configured"):
            return self.open_config()
        return self.open_main()

    def open_config(self):
        full_settings = self.settings.settings.copy()
        full_settings["mt5_password"] = self.settings.get_mt5_password()
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
            self.settings.save_settings(clean)
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

    def run_analysis_now(self):
        if not self.settings.get("is_configured"):
            return {"success": False, "message": "Completa la configuracion inicial."}
        with self._lock:
            try:
                self.balance.evaluate_due_signals()
                snapshot = self.mt5.snapshot(self.settings.settings)
                snapshot["external_context"] = self.external_context.collect(self.settings.settings)
                signal = self.engine.analyze(snapshot, self.settings.settings)
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

    def summary(self):
        return SignalHistory.summarize(self.history.list_entries(), self.settings.get("virtual_balance", 0.0))

    def state_payload(self):
        signals = self.history.list_entries()
        latest = self._last_signal or (signals[0] if signals else {})
        return {
            "settings": self.settings.settings,
            "signals": signals,
            "summary": self.summary(),
            "latest_signal": latest,
            "engine_running": self.engine_running,
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
