import json
import logging
import shutil
from pathlib import Path

from app_paths import data_path

logger = logging.getLogger(__name__)
try:
    # pyrefly: ignore [missing-import]
    import keyring
except Exception:
    keyring = None
from app_metadata import APP_NAME


class SettingsManager:
    def __init__(self, filename="settings.json"):
        self.filepath = data_path(filename)
        self._migrate_legacy_file(filename)
        self.defaults = {
            "market_type": "Forex",
            "symbol": "EURUSD",
            "chart_type": "candles",
            "timeframe": "M1",
            "prediction_horizon_minutes": 5,
            "analysis_interval_minutes": 5,
            "virtual_balance": 1000.0,
            "initial_virtual_balance": 1000.0,
            "stake_amount": 10.0,
            "payout_percent": 80.0,
            "confidence_threshold": 0.72,
            "mt5_path": "",
            "mt5_account": "",
            "mt5_password": "",
            "mt5_server": "",
            "is_configured": False,
            "splash_seen": False,
            "enable_sounds": True,
            "strategy_prompt": "ACTÚA COMO UN ANALISTA DE ELITE. TU CONOCIMIENTO INCLUYE:\n1. SMC/ICT: Identifica Order Blocks, Liquidez (BSL/SSL), Fair Value Gaps (FVG) y Breakers.\n2. VSA: Analiza la relación precio-volumen para detectar trampas profesionales.\n3. CONVERGENCIA: Solo valida señales donde el análisis técnico coincida con el contexto externo (Noticias/Sentimiento).\n4. HONESTIDAD: Si los datos son contradictorios o la volatilidad es errática, tu respuesta DEBE SER 'WAIT'.\n5. GESTIÓN: Prioriza la preservación de capital sobre la ganancia. No busques trades donde no hay claridad institucional.",
            "rag_directory": "rag_knowledge",
            "enable_rag": True,
            "language": "es",
        }
        self.settings = self.load_settings()
        self._cached_password = None

    def _migrate_legacy_file(self, filename):
        legacy_path = Path(filename)
        if self.filepath.exists() or not legacy_path.exists():
            return
        try:
            shutil.copy2(legacy_path, self.filepath)
        except Exception as exc:
            logger.warning("No se pudo migrar configuracion local: %s", exc)

    def load_settings(self):
        if not self.filepath.exists():
            return self.defaults.copy()
        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
            merged = self.defaults.copy()
            if isinstance(data, dict):
                merged.update(data)
            return merged
        except Exception as exc:
            logger.warning("No se pudo cargar settings: %s", exc)
            return self.defaults.copy()

    def save_settings(self, values=None):
        password_to_store = None
        if values:
            # Extract password if provided so it is not written to disk
            if "mt5_password" in values:
                password_to_store = values.pop("mt5_password")
            self.settings.update(values)

        # If a password was provided and keyring is available, save it securely
        if password_to_store is not None:
            try:
                if keyring:
                    service = f"{APP_NAME}_mt5"
                    # Ensure account is a string for keyring
                    account = str(self.settings.get("mt5_account", "") or "__default__")
                    keyring.set_password(service, account, password_to_store)
                    self._cached_password = password_to_store
                else:
                    logger.warning("Keyring no disponible: la contraseña no se guardará de forma segura.")
            except Exception as exc:
                logger.warning("No se pudo guardar contraseña en keyring: %s", exc)

        # Ensure password is not persisted in the settings file
        self.settings.pop("mt5_password", None)
        temp_path = self.filepath.with_suffix(f"{self.filepath.suffix}.tmp")
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(self.settings, file, indent=2, ensure_ascii=False)
        temp_path.replace(self.filepath)

    def get(self, key, default=None):
        return self.settings.get(key, self.defaults.get(key) if default is None else default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

    def reset_virtual_balance(self, amount: float):
        amount = float(amount)
        self.settings["virtual_balance"] = amount
        self.settings["initial_virtual_balance"] = amount
        self.save_settings()

    def get_mt5_password(self):
        if self._cached_password:
            return self._cached_password
        
        if keyring:
            try:
                service = f"{APP_NAME}_mt5"
                account = str(self.settings.get("mt5_account", "") or "__default__")
                pwd = keyring.get_password(service, account)
                if pwd:
                    self._cached_password = pwd
                    return pwd
            except Exception as exc:
                logger.warning("Error al recuperar password de keyring: %s", exc)
        return ""
