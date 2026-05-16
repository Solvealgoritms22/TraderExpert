from __future__ import annotations

import json
import logging
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)


class AzureClient:
    def __init__(self):
        self.url = config.AZURE_URL
        self.headers = {
            "api-key": config.AZURE_API_KEY,
            "Content-Type": "application/json",
        }

    @property
    def configured(self) -> bool:
        return bool(config.AZURE_API_KEY)

    def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("AZURE_API_KEY no esta configurada.")
        payload = {
            "messages": messages,
            "max_tokens": config.MAX_RESPONSE_TOKENS,
            "temperature": config.AI_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(self.url, headers=self.headers, json=payload, timeout=config.REQUEST_TIMEOUT)
        if response.status_code != 200:
            detail = response.text[:300]
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(f"Error de Azure OpenAI ({response.status_code}): {detail}")
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
