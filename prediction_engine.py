from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import config
from azure_client import AzureClient
from rag_manager import RAGManager
from signal_history import utc_now
from technical_analysis import compute_features


class PredictionEngine:
    def __init__(self, ai: AzureClient | None = None, rag: RAGManager | None = None):
        self.ai = ai or AzureClient()
        self.rag = rag or RAGManager()

    @staticmethod
    def _normalize_ai_response(value: dict[str, Any]) -> dict[str, Any]:
        direction = str(value.get("direction", "WAIT")).upper()
        if direction not in {"UP", "DOWN", "WAIT"}:
            direction = "WAIT"
        try:
            confidence = float(value.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        risk_flags = value.get("risk_flags", [])
        if isinstance(risk_flags, str):
            risk_flags = [risk_flags]
        if not isinstance(risk_flags, list):
            risk_flags = []
        return {
            "direction": direction,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": str(value.get("reason") or "Sin razon detallada."),
            "risk_flags": [str(flag) for flag in risk_flags][:8],
            "expiry_minutes": value.get("expiry_minutes"),
        }

    def _fallback_prediction(self, features: dict[str, Any]) -> dict[str, Any]:
        return {
            "direction": features.get("local_direction", "WAIT"),
            "confidence": float(features.get("local_confidence", 0.0)),
            "reason": "Fallback local: decision basada en tendencia, medias, MACD, RSI y volatilidad.",
            "risk_flags": ["ai_unavailable"],
            "expiry_minutes": None,
        }

    def analyze(self, snapshot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        bars = snapshot["bars"]
        features = compute_features(bars)
        threshold = float(settings.get("confidence_threshold", 0.72))
        horizon = int(settings.get("prediction_horizon_minutes", 5))
        
        rag_context = ""
        if settings.get("enable_rag", True):
            rag_context = self.rag.load_context(
                [settings.get("market_type", ""), settings.get("timeframe", ""), settings.get("symbol", "")],
                max_chars=12000,
                custom_dir=settings.get("rag_directory")
            )
        compact_bars = bars[-80:]
        base_prompt = config.SYSTEM_PROMPT
        user_strategy = settings.get("strategy_prompt", "")
        
        lang = settings.get("language", "es")
        lang_map = {
            "es": "Responde detalladamente en ESPAÑOL.",
            "en": "Respond in detail in ENGLISH.",
            "pt": "Responda detalhadamente em PORTUGUÊS.",
            "fr": "Répondez en détail en FRANÇAIS.",
            "de": "Antworten Sie detailliert auf DEUTSCH."
        }
        lang_instruction = lang_map.get(lang, lang_map["es"])
        
        full_system_prompt = f"{base_prompt}\n\nREGLAS DE ESTRATEGIA ADICIONALES:\n{user_strategy}" if user_strategy else base_prompt
        full_system_prompt = f"{full_system_prompt}\n\n{lang_instruction}"

        messages = [
            {"role": "system", "content": full_system_prompt},
            {
                "role": "user",
                "content": (
                    "Analiza esta configuracion y devuelve solo JSON.\n"
                    f"Settings: {json.dumps(settings, ensure_ascii=False)}\n"
                    f"Features: {json.dumps(features, ensure_ascii=False)}\n"
                    f"Tick: {json.dumps(snapshot.get('tick', {}), ensure_ascii=False)}\n"
                    f"External context: {json.dumps(snapshot.get('external_context', {}), ensure_ascii=False)}\n"
                    f"Recent OHLC: {json.dumps(compact_bars, ensure_ascii=False)}\n"
                    "Contexto externo permitido: usa solo los datos entregados arriba. "
                    "Si las fuentes externas advierten falta de API, trata ese vacio como incertidumbre.\n"
                    f"RAG local:\n{rag_context}"
                ),
            },
        ]
        try:
            raw = self.ai.complete_json(messages)
            prediction = self._normalize_ai_response(raw)
        except Exception as exc:
            prediction = self._fallback_prediction(features)
            prediction["risk_flags"].append(str(exc)[:180])

        local_direction = features.get("local_direction", "WAIT")
        if prediction["direction"] in {"UP", "DOWN"} and local_direction in {"UP", "DOWN"}:
            if prediction["direction"] != local_direction:
                prediction["risk_flags"].append("ai_local_conflict")
                prediction["confidence"] = min(prediction["confidence"], 0.55)

        if prediction["confidence"] < threshold or prediction["direction"] not in {"UP", "DOWN"}:
            direction = "WAIT"
            status = "WAIT"
        else:
            direction = prediction["direction"]
            status = "OPEN"

        now = utc_now()
        entry_price = float(snapshot.get("tick", {}).get("price") or features["close"])
        signal = {
            "id": now.strftime("%Y%m%d%H%M%S%f"),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=horizon)).isoformat() if direction != "WAIT" else "",
            "market_type": settings.get("market_type"),
            "symbol": settings.get("symbol"),
            "timeframe": settings.get("timeframe"),
            "horizon_minutes": horizon,
            "direction": direction,
            "confidence": round(float(prediction["confidence"]), 3),
            "reason": prediction["reason"],
            "risk_flags": prediction["risk_flags"],
            "external_context": snapshot.get("external_context", {}),
            "entry_price": entry_price if direction != "WAIT" else None,
            "exit_price": None,
            "status": status,
            "balance_delta": 0.0,
            "stake_amount": float(settings.get("stake_amount", 0.0)),
            "payout_percent": float(settings.get("payout_percent", 0.0)),
            "features": features,
        }
        if direction == "WAIT" and not signal["risk_flags"]:
            signal["risk_flags"] = ["confidence_below_threshold"]
        return signal
