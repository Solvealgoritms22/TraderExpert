from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_paths import data_path

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SignalHistory:
    def __init__(self, filename="signals.json", max_entries=300):
        self.filepath = data_path(filename)
        self.max_entries = max_entries

    def _read(self) -> list[dict[str, Any]]:
        if not self.filepath.exists():
            return []
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("No se pudo cargar historial de senales: %s", exc)
            return []

    def _write(self, entries: list[dict[str, Any]]):
        temp_path = self.filepath.with_suffix(f"{self.filepath.suffix}.tmp")
        temp_path.write_text(json.dumps(entries[: self.max_entries], indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(self.filepath)

    def add(self, signal: dict[str, Any]) -> dict[str, Any]:
        entries = self._read()
        signal = dict(signal)
        signal.setdefault("id", utc_now().strftime("%Y%m%d%H%M%S%f"))
        entries = [signal] + [entry for entry in entries if entry.get("id") != signal["id"]]
        self._write(entries)
        return signal

    def update(self, signal_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        entries = self._read()
        updated = None
        for entry in entries:
            if entry.get("id") == signal_id:
                entry.update(values)
                updated = entry
                break
        if updated:
            self._write(entries)
        return updated

    def list_entries(self) -> list[dict[str, Any]]:
        return self._read()

    def clear(self):
        if self.filepath.exists():
            self.filepath.unlink()

    def pending(self) -> list[dict[str, Any]]:
        return [entry for entry in self._read() if entry.get("status") == "OPEN"]

    @staticmethod
    def summarize(entries: list[dict[str, Any]], balance: float) -> dict[str, Any]:
        return {
            "balance": round(float(balance), 2),
            "wins": sum(1 for entry in entries if entry.get("status") == "WIN"),
            "losses": sum(1 for entry in entries if entry.get("status") == "LOSS"),
            "ties": sum(1 for entry in entries if entry.get("status") == "TIE"),
            "open": sum(1 for entry in entries if entry.get("status") == "OPEN"),
            "waits": sum(1 for entry in entries if entry.get("direction") == "WAIT"),
            "total": len(entries),
        }
