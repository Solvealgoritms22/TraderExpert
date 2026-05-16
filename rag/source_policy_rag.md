# TraderExpert RAG: Politica de fuentes externas

Cobertura: Forex, Indices, Commodities, Crypto, Acciones, M1, M2, M5, M15, M30, H1.
Objetivo: definir como usar datos de Liveuamap, WorldMonitor e Investing sin depender de scraping fragil.

## WorldMonitor

- Usar WorldMonitor por API cuando `WORLD_MONITOR_API_KEY` este configurada.
- La documentacion indica endpoints REST versionados bajo `https://api.worldmonitor.app/api/<service>/v1/<rpc-name>`.
- Enviar `X-WorldMonitor-Key: wm_live_...` cuando exista clave.
- Priorizar estos dominios para trading:
  - news/feed digest: riesgo narrativo.
  - conflict/acled events: conflicto y protestas.
  - market/fear-greed: sentimiento.
  - supply-chain/shipping stress: energia, commodities, indices.
  - sanctions: riesgo geopolitico y comercio.
- Si la API falla, no inventar contexto. Agregar risk_flag y bajar confianza.

## Liveuamap

- Usar como OSINT manual/enlace si no hay API oficial o autorizada configurada.
- El contenido puede ser relevante para energia, oro, indices, USD, JPY y CHF cuando hay conflicto o seguridad regional.
- No hacer scraping agresivo ni depender de selectores HTML.
- Si el usuario reviso manualmente Liveuamap y agrega contexto en RAG o API autorizada, usarlo como riesgo cualitativo.

## RSS News Feeds (ForexLive, ForexFactory, YahooFinance)

- Estas son las fuentes primarias de tiempo real para el motor de TraderExpert.
- **ForexLive**: Máxima prioridad para sentimiento intradía y breaking news de divisas.
- **ForexFactory**: Fuente autorizada para el calendario económico y noticias de alto impacto (estrellas rojas).
- **Investing (ES)**: Provee análisis de mercado y sentimiento en español para confluencia regional.
- **YahooFinance**: Contexto general de mercado, índices y commodities.
- **Regla de Filtrado**: El motor filtra por términos de activos (EUR, USD, Gold, etc.). Solo usar noticias que pasen el filtro de relevancia.
- **Impacto**: Noticias de "Alto Impacto" o "Breaking News" en estas fuentes deben disparar cautela inmediata. Si hay contradicción técnica, forzar WAIT.

## Regla de integridad

- Si una fuente no esta disponible, decirlo en `risk_flags`.
- Si una fuente contradice precio/tecnica, favorecer WAIT.
- Si fuente externa es antigua o no tiene timestamp, usarla solo como contexto debil.
- Toda decision final debe seguir siendo: UP, DOWN o WAIT.
