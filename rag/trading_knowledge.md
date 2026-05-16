# TraderExpert RAG Base

## Conservatismo

- Una senal solo debe emitirse cuando precio, tendencia, momentum y contexto no se contradicen de forma material.
- Si el mercado esta lateral, con baja liquidez, vela extrema reciente o cerca de soporte/resistencia fuerte, prioriza WAIT.
- Una prediccion con confianza menor al umbral configurado debe terminar en WAIT.
- El objetivo es simulacion y entrenamiento; no ejecutar ordenes reales.

## Criterios tecnicos

- UP necesita preferiblemente precio sobre SMA20, SMA20 sobre SMA50, MACD positivo o mejorando y pendiente reciente positiva.
- DOWN necesita preferiblemente precio bajo SMA20, SMA20 bajo SMA50, MACD negativo o deteriorando y pendiente reciente negativa.
- RSI mayor a 70 reduce calidad de compra por riesgo de agotamiento.
- RSI menor a 30 reduce calidad de venta por riesgo de rebote.
- ATR y volatilidad alta reducen confianza si el horizonte es corto.

## Riesgo de contexto

- Noticias macro, conflicto geopolitico, eventos de calendario economico y gaps de liquidez pueden invalidar patrones tecnicos.
- Si no hay fuente permitida actualizada para contexto externo, declara esa incertidumbre en risk_flags.
