# TraderExpert

App de escritorio para simulacion de direccion de precio con MetaTrader 5 y Azure OpenAI.

## Uso

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Configura `AZURE_API_KEY` en `.env` para usar el modelo. Sin clave, la app usa una heuristica tecnica local conservadora.

## Contexto externo

La app no hace scraping directo de Investing.com. Para mejorar el contexto:

```env
AZURE_API_KEY=...
WORLD_MONITOR_API_KEY=wm_live_...
ECONOMIC_CALENDAR_API_URL=https://tu-proveedor-autorizado.example/calendar
LIVEUAMAP_URL=https://liveuamap.com/
INVESTING_CALENDAR_URL=https://www.investing.com/economic-calendar
```

- WorldMonitor se consulta por API cuando hay clave.
- Liveuamap queda como fuente OSINT manual/enlace salvo que configures un API autorizado propio.
- Investing Calendar queda como enlace/manual review o por `ECONOMIC_CALENDAR_API_URL` si tienes un proveedor autorizado.

## Seguridad

- No ejecuta operaciones reales.
- El saldo es virtual.
- No hace scraping directo de Investing.com.
- Muestra `ESPERAR` cuando la confianza no supera el umbral configurado.

## Almacenamiento de credenciales MT5

La contraseña de la cuenta MT5 no se guarda en texto plano en `settings.json`. Si introduces la contraseña desde la aplicación, se almacena de forma segura en el gestor de credenciales del sistema (Windows Credential Manager) usando la librería `keyring`.

Requisitos:
- `keyring` (se agregó a `requirements.txt`).

Notas:
- Si `keyring` no está disponible, la aplicación registra una advertencia y no guardará la contraseña de forma segura.
- También puedes proporcionar credenciales mediante variables de entorno `MT5_ACCOUNT`, `MT5_PASSWORD` y `MT5_SERVER`.
