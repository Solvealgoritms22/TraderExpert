from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider metadata: models, endpoints, branding
# ---------------------------------------------------------------------------

PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o4-mini"],
        "fields": ["api_key", "model"],
    },
    "azure": {
        "name": "Azure OpenAI",
        "base_url": "",  # user-provided endpoint
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        "fields": ["api_key", "model", "endpoint", "api_version"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "fields": ["api_key", "model"],
    },
    "claude": {
        "name": "Claude (Anthropic)",
        "base_url": "https://api.anthropic.com/v1/messages",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-20241022"],
        "fields": ["api_key", "model"],
    },
    "gemini": {
        "name": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "fields": ["api_key", "model"],
    },
    "grok": {
        "name": "Grok (xAI)",
        "base_url": "https://api.x.ai/v1/chat/completions",
        "models": ["grok-3", "grok-3-mini", "grok-3-fast"],
        "fields": ["api_key", "model"],
    },
}


class AIClient:
    """Unified AI client that supports multiple providers."""

    MAX_REQUESTS_PER_MINUTE = 20

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        model: str = "",
        endpoint: str = "",
        api_version: str = "",
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model or self._default_model()
        self.endpoint = endpoint
        self.api_version = api_version or "2025-01-01-preview"

        # Session with retry
        self.session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503],
            allowed_methods=["POST"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        # Rate limiting
        self._request_timestamps: list[float] = []

    def _default_model(self) -> str:
        info = PROVIDERS.get(self.provider, {})
        models = info.get("models", [])
        return models[0] if models else "gpt-4o"

    @property
    def configured(self) -> bool:
        if not self.api_key:
            return False
        if self.provider == "azure" and not self.endpoint:
            return False
        return True

    def _check_rate_limit(self):
        now = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60]
        if len(self._request_timestamps) >= self.MAX_REQUESTS_PER_MINUTE:
            raise RuntimeError(
                f"Rate limit local alcanzado ({self.MAX_REQUESTS_PER_MINUTE} req/min). Esperando..."
            )
        self._request_timestamps.append(now)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError(f"API Key no configurada para {self.provider}.")
        self._check_rate_limit()

        dispatch = {
            "openai": self._call_openai_compatible,
            "azure": self._call_azure,
            "deepseek": self._call_openai_compatible,
            "grok": self._call_openai_compatible,
            "claude": self._call_claude,
            "gemini": self._call_gemini,
        }
        handler = dispatch.get(self.provider)
        if handler is None:
            raise RuntimeError(f"Proveedor desconocido: {self.provider}")
        return handler(messages)

    def test_connection(self) -> dict[str, Any]:
        """Quick connectivity test. Returns {success, message, model}."""
        try:
            if not self.configured:
                return {"success": False, "message": "API Key no configurada."}
            result = self.complete_json([
                {"role": "system", "content": "Reply with valid JSON: {\"status\": \"ok\"}"},
                {"role": "user", "content": "ping"},
            ])
            return {
                "success": True,
                "message": f"Conexión exitosa con {PROVIDERS.get(self.provider, {}).get('name', self.provider)}",
                "model": self.model,
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)[:300]}

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    def _call_openai_compatible(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """OpenAI, DeepSeek, and Grok all use the OpenAI-compatible API."""
        info = PROVIDERS.get(self.provider, {})
        url = info.get("base_url", "")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": config.MAX_RESPONSE_TOKENS,
            "temperature": config.AI_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }
        return self._post_and_parse_openai(url, headers, payload)

    def _call_azure(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        url = f"{self.endpoint}?api-version={self.api_version}"
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "messages": messages,
            "max_tokens": config.MAX_RESPONSE_TOKENS,
            "temperature": config.AI_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }
        return self._post_and_parse_openai(url, headers, payload)

    def _post_and_parse_openai(
        self, url: str, headers: dict, payload: dict
    ) -> dict[str, Any]:
        response = self.session.post(
            url, headers=headers, json=payload, timeout=config.REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            detail = response.text[:300]
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(
                f"Error de {self.provider} ({response.status_code}): {detail}"
            )
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def _call_claude(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Anthropic Messages API (different from OpenAI)."""
        system_text = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})

        # Ensure there's at least one user message
        if not user_messages:
            user_messages = [{"role": "user", "content": "Analyze and return JSON."}]

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": config.MAX_RESPONSE_TOKENS,
            "temperature": config.AI_TEMPERATURE,
            "system": system_text.strip(),
            "messages": user_messages,
        }
        url = PROVIDERS["claude"]["base_url"]
        response = self.session.post(
            url, headers=headers, json=payload, timeout=config.REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            detail = response.text[:300]
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(
                f"Error de Claude ({response.status_code}): {detail}"
            )
        data = response.json()
        content_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block["text"]
        return json.loads(content_text)

    def _call_gemini(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Google Gemini API (different format)."""
        system_text = ""
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Analyze and return JSON."}]}]

        url = f"{PROVIDERS['gemini']['base_url']}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": config.AI_TEMPERATURE,
                "maxOutputTokens": config.MAX_RESPONSE_TOKENS,
            },
        }
        if system_text.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_text.strip()}]
            }

        response = self.session.post(
            url, headers=headers, json=payload, timeout=config.REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            detail = response.text[:300]
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(
                f"Error de Gemini ({response.status_code}): {detail}"
            )
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
