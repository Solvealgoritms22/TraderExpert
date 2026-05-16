# TraderExpert RAG: Contexto macro, tecnico y geopolitico

Cobertura: Forex, Indices, Commodities, Crypto, Acciones, M1, M2, M5, M15, M30, H1.
Uso: reglas para mejorar la decision UP / DOWN / WAIT sin prometer certeza.
Fecha de preparacion: 2026-05-16.

## Principio rector

- El modelo debe usar el contexto externo como filtro de riesgo, no como garantia direccional.
- Si el contexto macro/geopolitico esta incompleto, no actualizado, contradictorio o no autorizado para consulta automatica, aumentar incertidumbre y favorecer WAIT.
- Para horizontes cortos, el precio actual, spread, volatilidad y proximidad a eventos macro pesan mas que narrativas largas.
- No usar una sola fuente o indicador para decidir UP/DOWN. Requerir confluencia entre precio, tendencia, momentum, volatilidad, calendario y riesgo externo.

## Indicadores tecnicos

### RSI

Fuente: Fidelity, Relative Strength Index.
Resumen util:
- RSI mide momentum en escala 0-100.
- Tradicionalmente, RSI sobre 70 indica sobrecompra y bajo 30 indica sobreventa.
- En tendencias fuertes, RSI puede permanecer sobrecomprado o sobrevendido durante periodos largos.
- Regla TraderExpert: RSI extremo no es senal contraria automatica. Usarlo como moderador de confianza.
- UP con RSI > 70: reducir confianza salvo que tendencia, ruptura y volumen confirmen continuidad.
- DOWN con RSI < 30: reducir confianza salvo que tendencia bajista y momentum confirmen continuidad.

### MACD

Fuente: Fidelity, MACD.
Resumen util:
- El cruce MACD/senal puede apoyar cambios de momentum.
- En rangos laterales, MACD suele generar whipsaws por cruces repetidos.
- Divergencia precio/MACD gana valor cuando confirma el cruce.
- Regla TraderExpert: si ATR bajo/rango lateral y MACD cruza sin ruptura de precio, no elevar confianza; favorecer WAIT.

### ATR

Fuente: Fidelity, Average True Range.
Resumen util:
- ATR mide volatilidad, no direccion.
- ATR creciente implica barras con rango mayor y puede aparecer tanto en ventas como en compras.
- ATR bajo suele asociarse a rango lateral/consolidacion.
- Regla TraderExpert: ATR alto en horizonte corto aumenta riesgo de ruido; ATR bajo sin ruptura valida favorece WAIT.
- Si ATR aumenta junto con ruptura clara y cierre fuerte, puede aumentar confianza, pero solo en direccion confirmada por tendencia.

## Eventos macro y calendario economico

### Politica monetaria

Fuentes: Federal Reserve, ECB.
Resumen util:
- La Fed busca maximo empleo, precios estables y tasas moderadas de largo plazo.
- La Fed ajusta la postura monetaria principalmente mediante el rango objetivo de la tasa federal.
- La Fed indica que sus decisiones se basan en objetivos, perspectiva de mediano plazo y balance de riesgos.
- La ECB publica decisiones de politica monetaria y evalua inflacion, riesgos, datos entrantes, dinamica subyacente y transmision monetaria.

Reglas TraderExpert:
- Antes de FOMC, ECB, BoE, BoJ, CPI, NFP o GDP, reducir confianza por riesgo de whipsaw.
- Despues de un evento de alto impacto, esperar confirmacion de direccion con cierre de vela y spread normalizado.
- Para pares con USD, eventos de Fed, CPI, empleo y GDP de EEUU pesan alto.
- Para EUR, ECB e inflacion eurozona pesan alto.
- Para GBP, BoE, empleo, CPI y GDP UK pesan alto.
- Para JPY, BoJ, rendimientos y aversion al riesgo pesan alto.

### CPI, GDP, empleo

Fuentes: BLS CPI, BEA GDP, Investing Economic Calendar.
Resumen util:
- CPI mide cambio promedio de precios pagados por consumidores urbanos.
- GDP es una medida amplia de actividad economica; cambios en GDP son indicadores populares de salud economica.
- Calendarios economicos organizan hora, moneda, evento, impacto, actual, forecast y previous.
- Eventos de mayor impacto incluyen decisiones de tasas, NFP, GDP, CPI y desempleo.

Reglas TraderExpert:
- Si hay evento de 3 estrellas/alto impacto cercano para la moneda del activo, favorecer WAIT hasta que pase el evento y el spread se estabilice.
- Actual vs Forecast importa mas que Actual aislado. La sorpresa mueve mercado cuando difiere de expectativas.
- Resultado mejor de lo esperado no siempre implica direccion lineal; depende de regimen: inflacion alta puede fortalecer moneda por expectativa de tasas, pero debilitar indices por tasas mas altas.

## Geopolitica y commodities

Fuentes: Liveuamap, WorldMonitor API.
Resumen util:
- Liveuamap cubre reportes de seguridad y conflicto por regiones.
- WorldMonitor documenta APIs REST para conflictos, noticias, mercado, supply chain, sanciones, transporte, energia y otros dominios.
- WorldMonitor usa endpoints versionados `/api/<service>/v1/<rpc-name>` y autenticacion `X-WorldMonitor-Key`.

Reglas TraderExpert:
- Conflicto en Medio Oriente, rutas maritimas, sanciones o energia puede impactar petroleo, oro, gas, indices y divisas refugio.
- Riesgo geopolitico alto suele aumentar demanda de refugio: oro, USD, CHF, JPY pueden reaccionar, pero no asumir direccion sin precio confirmando.
- En commodities, shocks de oferta pueden dominar indicadores tecnicos durante ventanas cortas.
- Si WorldMonitor no esta configurado o Liveuamap solo esta disponible como enlace manual, agregar risk_flag de contexto incompleto y favorecer WAIT si la tecnica no es fuerte.

## Riesgo de mercado y fraude

Fuentes: CFTC, SEC.
Resumen util:
- CFTC advierte que la mayoria de traders minoristas de forex pierden dinero y que resultados pasados no garantizan resultados futuros.
- CFTC advierte que bots/senales pueden ajustarse al pasado sin saber si las condiciones futuras persistiran.
- SEC advierte que forex puede ser muy riesgoso, el apalancamiento magnifica ganancias y perdidas, y el spread bid-ask es un costo.

Reglas TraderExpert:
- La app debe mantenerse como simulador. No sugerir depositos, brokers, apalancamiento ni operaciones reales.
- Si spread es amplio, datos son escasos o MT5 no entrega tick reciente, no emitir UP/DOWN.
- No presentar confianza como probabilidad garantizada. Usar `confidence` como calidad relativa de confluencia.

## Matriz de decision conservadora

Emitir UP solo si:
- Precio actual por encima de SMA20 y preferiblemente SMA20 > SMA50.
- Momentum positivo: MACD por encima de senal o mejorando.
- RSI no contradice gravemente la entrada, o la tendencia justifica RSI alto.
- ATR no indica ruido extremo incompatible con el horizonte.
- No hay evento macro de alto impacto inmediato sin confirmacion posterior.
- Contexto externo no contradice la direccion.

Emitir DOWN solo si:
- Precio actual bajo SMA20 y preferiblemente SMA20 < SMA50.
- Momentum negativo: MACD bajo senal o deteriorando.
- RSI no contradice gravemente la entrada, o la tendencia justifica RSI bajo.
- ATR no indica ruido extremo incompatible con el horizonte.
- No hay evento macro de alto impacto inmediato sin confirmacion posterior.
- Contexto externo no contradice la direccion.

Emitir WAIT si:
- Tendencia y momentum no coinciden.
- Precio esta en rango o cerca de soporte/resistencia sin ruptura.
- Spread o volatilidad son anormales.
- Evento macro/geopolitico relevante esta cerca.
- Datos externos faltan y la senal tecnica no supera claramente el umbral.
- La respuesta del modelo y la heuristica local discrepan.

## Fuentes usadas para este RAG

- Fidelity RSI: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI
- Fidelity MACD: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd
- Fidelity ATR: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
- Federal Reserve Monetary Policy: https://www.federalreserve.gov/monetarypolicy/2024-07-mpr-summary.htm
- BLS CPI: https://www.bls.gov/cpi/home.htm
- BEA GDP: https://www.bea.gov/data/gdp/gross-domestic-product
- Investing Economic Calendar: https://www.investing.com/economic-calendar
- ForexLive News Feed: https://www.forexlive.com/
- ForexFactory News: https://www.forexfactory.com/
- Yahoo Finance Market News: https://finance.yahoo.com/
- WorldMonitor API Reference: https://www.worldmonitor.app/docs/api-reference
- Liveuamap: https://liveuamap.com/
- CFTC Forex Frauds: https://www.cftc.gov/LearnAndProtect/forexfrauds
- SEC Foreign Currency Transactions: https://www.sec.gov/answers/forcurr.htm

## Priorización de Noticias (RSS)

1. **Breaking News (ForexLive/ForexFactory)**: Impacto inmediato. Si hay una noticia de "High Impact" o "Red Star", la IA debe priorizar la cautela sobre cualquier patrón técnico.
2. **Sentimiento de Mercado (Investing/Yahoo)**: Se usa para convalidar la tendencia de largo plazo (H1+).
3. **Filtro de Relevancia**: Las noticias proporcionadas en el campo `external_context` ya están filtradas por símbolo. Úsalas como factor determinante para la `confidence`.
