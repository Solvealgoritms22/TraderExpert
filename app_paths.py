import os
import sys
from pathlib import Path

from app_metadata import APP_NAME


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        path = Path(base) / APP_NAME if base else Path.home() / f".{APP_NAME.lower()}"
    else:
        path = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_path(filename: str) -> Path:
    return user_data_dir() / filename
