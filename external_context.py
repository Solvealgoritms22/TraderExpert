from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests
import xml.etree.ElementTree as ET

import config

import concurrent.futures

logger = logging.getLogger(__name__)


class ExternalContextService:
    """Collects permitted external context without scraping restricted pages."""

    WORLD_MONITOR_BASE = "https://api.worldmonitor.app"

    def __init__(self):
        self.session = requests.Session()

    @staticmethod
    def _asset_terms(settings: dict[str, Any]) -> list[str]:
        symbol = str(settings.get("symbol") or "").upper()
        market_type = str(settings.get("market_type") or "")
        terms = [symbol, market_type]
        if "XAU" in symbol or "GOLD" in symbol:
            terms.extend(["gold", "metals", "commodities"])
        if "XAG" in symbol or "SILVER" in symbol:
            terms.extend(["silver", "metals", "commodities"])
        if "USD" in symbol:
            terms.extend(["dollar", "United States", "Fed"])
        if "EUR" in symbol:
            terms.extend(["euro", "ECB", "Europe"])
        if "GBP" in symbol:
            terms.extend(["pound", "BoE", "United Kingdom"])
        if "JPY" in symbol:
            terms.extend(["yen", "BoJ", "Japan"])
        if "OIL" in symbol or "WTI" in symbol or "BRENT" in symbol:
            terms.extend(["oil", "energy", "supply"])
        return [term for term in terms if term]

    def collect(self, settings: dict[str, Any]) -> dict[str, Any]:
        collected_at = datetime.now(timezone.utc).isoformat()
        context = {
            "collected_at": collected_at,
            "sources": [],
            "items": [],
            "warnings": [],
            "links": {
                "liveuamap": config.LIVEUAMAP_URL,
                "investing_calendar": config.INVESTING_CALENDAR_URL,
                "worldmonitor": "https://www.worldmonitor.app/",
            },
        }
        self._add_world_monitor(context, settings)
        self._add_configured_calendar_api(context, settings)
        self._add_rss_news(context, settings)
        if not any(item.get("source") == "liveuamap" for item in context["items"]):
            context["warnings"].append(
                "Liveuamap no se consulta automaticamente: no se encontro API oficial configurada; usar enlace manual."
            )
        if not any(item.get("source") == "investing_calendar" for item in context["items"]):
            context["warnings"].append(
                "Investing Calendar no se scrapea; configura ECONOMIC_CALENDAR_API_URL o revisa el enlace manual."
            )
        return context

    def _world_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if config.WORLD_MONITOR_API_KEY:
            headers["X-WorldMonitor-Key"] = config.WORLD_MONITOR_API_KEY
        return headers

    def _get_world_monitor(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.WORLD_MONITOR_BASE}{path}"
        response = self.session.get(
            url,
            headers=self._world_headers(),
            params=params or {},
            timeout=config.EXTERNAL_CONTEXT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def _append_items_from_payload(self, context: dict[str, Any], source: str, payload: Any, limit: int):
        candidates = []
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    candidates.extend(value)
            if not candidates:
                candidates = [payload]
        for item in candidates[:limit]:
            if not isinstance(item, dict):
                continue
            title = (
                item.get("title")
                or item.get("headline")
                or item.get("name")
                or item.get("event")
                or item.get("summary")
                or item.get("region")
                or source
            )
            summary = item.get("summary") or item.get("description") or item.get("body") or item.get("level") or ""
            severity = item.get("severity") or item.get("impact") or item.get("score") or item.get("importance")
            context["items"].append(
                {
                    "source": source,
                    "title": str(title)[:240],
                    "summary": str(summary)[:600],
                    "severity": severity,
                    "raw": self._compact_raw(item),
                }
            )

    @staticmethod
    def _compact_raw(item: dict[str, Any]) -> dict[str, Any]:
        compact = {}
        for key, value in item.items():
            if key.lower() in {"title", "headline", "summary", "description", "region", "level", "score", "impact", "time", "date", "country", "currency"}:
                compact[key] = value
            if len(compact) >= 12:
                break
        return compact

    def _add_world_monitor(self, context: dict[str, Any], settings: dict[str, Any]):
        endpoints = [
            ("/api/news/v1/list-feed-digest", {"limit": config.EXTERNAL_CONTEXT_MAX_ITEMS}, "worldmonitor_news"),
            ("/api/conflict/v1/list-acled-events", {"limit": config.EXTERNAL_CONTEXT_MAX_ITEMS}, "worldmonitor_conflict"),
            ("/api/market/v1/get-fear-greed-index", {}, "worldmonitor_fear_greed"),
            ("/api/supply-chain/v1/get-shipping-stress", {}, "worldmonitor_supply_chain"),
        ]
        added_source = False
        for path, params, source in endpoints:
            try:
                payload = self._get_world_monitor(path, params)
                self._append_items_from_payload(context, source, payload, config.EXTERNAL_CONTEXT_MAX_ITEMS)
                added_source = True
            except Exception as exc:
                logger.debug("WorldMonitor endpoint fallo %s: %s", path, exc)
                context["warnings"].append(f"WorldMonitor {source} no disponible: {str(exc)[:160]}")
        if added_source:
            context["sources"].append("worldmonitor_api")
        elif not config.WORLD_MONITOR_API_KEY:
            context["warnings"].append("WORLD_MONITOR_API_KEY no configurada; WorldMonitor puede rechazar endpoints privados.")

    def _add_configured_calendar_api(self, context: dict[str, Any], settings: dict[str, Any]):
        if not config.ECONOMIC_CALENDAR_API_URL:
            return
        try:
            params = {
                "symbol": settings.get("symbol", ""),
                "market_type": settings.get("market_type", ""),
                "limit": config.EXTERNAL_CONTEXT_MAX_ITEMS,
            }
            response = self.session.get(
                config.ECONOMIC_CALENDAR_API_URL,
                params=params,
                timeout=config.EXTERNAL_CONTEXT_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            self._append_items_from_payload(
                context,
                "investing_calendar",
                response.json(),
                config.EXTERNAL_CONTEXT_MAX_ITEMS,
            )
            context["sources"].append("economic_calendar_api")
        except Exception as exc:
            context["warnings"].append(f"ECONOMIC_CALENDAR_API_URL fallo: {str(exc)[:160]}")

    def _fetch_feed(self, url: str, source_name: str, terms: list[str]) -> list[dict[str, Any]]:
        try:
            # Low timeout to prevent slow RSS servers from blocking the system
            response = self.session.get(url, timeout=3)
            if response.status_code != 200:
                return []
            
            root = ET.fromstring(response.content)
            items = root.findall(".//item")
            
            results = []
            count = 0
            for item in items:
                if count >= 3:
                    break
                    
                title = item.find("title").text if item.find("title") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""
                
                content_lower = (title + " " + desc).lower()
                if any(term.lower() in content_lower for term in terms):
                    results.append({
                        "source": source_name,
                        "title": title[:200],
                        "summary": desc[:500],
                        "severity": "info",
                        "raw": {"link": item.find("link").text if item.find("link") is not None else ""}
                    })
                    count += 1
            return results
        except Exception as e:
            logger.debug("Error al procesar RSS %s: %s", source_name, e)
            return []

    def _add_rss_news(self, context: dict[str, Any], settings: dict[str, Any]):
        """Fetches news from public RSS feeds (Free and Fresh)."""
        feeds = [
            ("https://www.forexlive.com/feed/", "ForexLive"),
            ("https://finance.yahoo.com/news/rssindex", "YahooFinance"),
            ("https://mx.investing.com/rss/news.rss", "Investing_ES"),
            ("https://www.forexfactory.com/news/rss", "ForexFactory")
        ]
        
        terms = self._asset_terms(settings)
        added = False
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(feeds)) as executor:
            futures = {executor.submit(self._fetch_feed, url, name, terms): name for url, name in feeds}
            for future in concurrent.futures.as_completed(futures):
                try:
                    feed_results = future.result()
                    if feed_results:
                        context["items"].extend(feed_results)
                        added = True
                except Exception as exc:
                    logger.debug("Error en tarea paralela de RSS: %s", exc)
        
        if added:
            context["sources"].append("rss_news_feeds")
