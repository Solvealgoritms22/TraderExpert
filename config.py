import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional during lightweight tests
    def load_dotenv(*args, **kwargs):
        return False

from app_paths import data_path, executable_dir, resource_path


if getattr(sys, "frozen", False):
    _env_candidates = (data_path(".env"), executable_dir() / ".env", resource_path(".env"))
else:
    _env_candidates = (executable_dir() / ".env", data_path(".env"), resource_path(".env"))

for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path, override=False)


def _env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_float(name: str, default: float, min_value: float | None = None, max_value: float | None = None) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


AZURE_ENDPOINT = os.getenv(
    "AZURE_ENDPOINT",
    "https://aievaluacioncne2.cognitiveservices.azure.com/openai/deployments/gpt-4o/chat/completions",
)
AZURE_API_KEY = os.getenv("AZURE_API_KEY", "")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2025-01-01-preview")
AZURE_URL = f"{AZURE_ENDPOINT}?api-version={AZURE_API_VERSION}"

REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 60, min_value=10, max_value=180)
MAX_RESPONSE_TOKENS = _env_int("MAX_RESPONSE_TOKENS", 1200, min_value=256, max_value=4096)
AI_TEMPERATURE = _env_float("AI_TEMPERATURE", 0.1, min_value=0.0, max_value=1.0)
WORLD_MONITOR_API_KEY = os.getenv("WORLD_MONITOR_API_KEY", "").strip()
EXTERNAL_CONTEXT_TIMEOUT = _env_int("EXTERNAL_CONTEXT_TIMEOUT", 12, min_value=3, max_value=45)
EXTERNAL_CONTEXT_MAX_ITEMS = _env_int("EXTERNAL_CONTEXT_MAX_ITEMS", 8, min_value=1, max_value=30)
LIVEUAMAP_URL = os.getenv("LIVEUAMAP_URL", "https://liveuamap.com/").strip()
INVESTING_CALENDAR_URL = os.getenv(
    "INVESTING_CALENDAR_URL",
    "https://www.investing.com/economic-calendar",
).strip()
ECONOMIC_CALENDAR_API_URL = os.getenv("ECONOMIC_CALENDAR_API_URL", "").strip()

WINDOW_WIDTH = 980
WINDOW_HEIGHT = 720
WINDOW_TITLE = "TraderExpert"

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    (
        "Eres un ANALISTA DE RIESGO ELITE. Tu prioridad es la HONESTIDAD y la CONVERGENCIA de datos. "
        "Si los indicadores técnicos contradicen el contexto externo (noticias/sentimiento), DEBES penalizar la confianza y preferir WAIT. "
        "No intentes adivinar; si no hay claridad institucional (SMC/VSA), no sugieras entrada. "
        "Devuelve siempre JSON válido con: direction (UP, DOWN, WAIT), confidence (0-1), reason, risk_flags, expiry_minutes."
    ),
)
