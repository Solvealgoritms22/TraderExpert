<p align="center">
  <img src="traderexpert.png" alt="TraderExpert Logo" width="160" height="160" />
</p>

<h1 align="center">TraderExpert</h1>

<p align="center">
  <strong>El nexo definitivo entre análisis institucional con IA Multimodelo y ejecución algorítmica nativa en tiempo real.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Version-v2.1.0-4A6E82?style=for-the-badge&logoColor=white" alt="Version 2.1.0" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Platform Windows" />
  <img src="https://img.shields.io/badge/Execution-MetaTrader_5-007FFF?style=for-the-badge&logo=metatrader&logoColor=white" alt="MetaTrader 5 Native" />
</p>

---

## 🌐 Resumen del Sistema

**TraderExpert** es una aplicación de escritorio diseñada para traders institucionales y algorítmicos. Integra indicadores técnicos puros de volumen y acción de precio con el análisis cognitivo de múltiples modelos avanzados de Inteligencia Artificial (OpenAI, DeepSeek, Gemini, Claude, Grok y Azure OpenAI). 

La plataforma recopila información en tiempo real del terminal **MetaTrader 5**, consulta fuentes OSINT externas para verificar riesgos macroeconómicos y geopolíticos, alimenta un motor RAG con directrices de riesgo corporativas y ejecuta operaciones directamente en la cuenta de corretaje (Demo o Real) con salvaguardas automáticas contra desconexiones y mercados cerrados.

---

## 🛠️ Stack Tecnológico

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python_3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  </a>
  <a href="https://openai.com/">
    <img src="https://img.shields.io/badge/AI_Providers-OpenAI_%7C_DeepSeek_%7C_Gemini_%7C_Claude-8E44AD?style=for-the-badge&logo=openai&logoColor=white" alt="AI Providers" />
  </a>
  <a href="https://www.metatrader5.com/">
    <img src="https://img.shields.io/badge/MetaTrader_5-Broker_Integration-007FFF?style=for-the-badge&logo=metatrader&logoColor=white" alt="MetaTrader 5" />
  </a>
  <br/>
  <a href="https://pywebview.flowrl.com/">
    <img src="https://img.shields.io/badge/UI_Engine-Pywebview-2C3E50?style=for-the-badge&logo=html5&logoColor=white" alt="Pywebview" />
  </a>
  <a href="https://sqlite.org/">
    <img src="https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  </a>
  <a href="https://github.com/jaraco/keyring">
    <img src="https://img.shields.io/badge/Security-OS_Keyring-E74C3C?style=for-the-badge&logo=keycdn&logoColor=white" alt="OS Keyring" />
  </a>
</p>

---

## 📐 Arquitectura & Flujo de Operación

El siguiente diagrama detalla cómo fluyen los datos a través del sistema, desde la recolección inicial del mercado hasta la toma de decisiones cognitivas de la IA y su posterior ejecución física.

```mermaid
graph TD
    A[Terminal MetaTrader 5] -->|Tick / Precios / Cuenta| B(TraderExpert Backend)
    C[OSINT & Geopolítica: Liveuamap/Economic Calendar] -->|Contexto Global| B
    D[Base de Conocimiento RAG Local] -->|Reglas de Estrategia| B
    
    B -->|Ingesta de Datos unificados| E{Motor de Decisión IA}
    
    E -->|API Key Segura via Keyring| F[OpenAI / Gemini / Claude / DeepSeek / Grok]
    F -->|Análisis de Riesgo & Dirección JSON| E
    
    E -->|Filtro de Confianza Mínima| G{Verificación de Modos}
    
    G -->|Modo Simulación| H[Settle Virtual en SQLite: Ajuste Balance de Prueba]
    G -->|Modo Real| I[Disparo MT5 Order_Send: Gestión StopLoss y TakeProfit Físicos]
    
    I -->|Monitoreo en Vivo| A
```

---

## 💎 Características Clave

### 1. Conectividad Nativa MetaTrader 5 (MT5)
- **Modos Flexibles**: Permite alternar instantáneamente entre el **Modo Simulación** (operaciones virtuales almacenadas en la base de datos local) y el **Modo Real** (órdenes físicas y liquidación a través del terminal MT5).
- **Sincronización en Tiempo Real**: El panel principal recupera balances de cuenta, equidades vivas, nombre del servidor del bróker e insignias de estado (DEMO / REAL) directamente desde el terminal.
- **Protección de Mercado**: Impide el análisis cognitivo y las ejecuciones automáticas si la terminal MT5 se desconecta o si el mercado de activos está cerrado.
- **Liquidación Automatizada**: Cierre de posiciones inmediato a precio de mercado sobre los tickets correspondientes al cumplirse el horizonte de predicción.

### 2. Puerta de Enlace IA Multimodelo con Credenciales Seguras
- **Soporte Global**: Compatible con OpenAI (GPT-4o), Claude 3.5 Sonnet, DeepSeek R1, Gemini 1.5 Pro, Grok 2 y Azure OpenAI.
- **Formularios Dinámicos Modernos**: La interfaz de configuración presenta tarjetas e inputs interactivos específicos para cada proveedor, incluyendo multiselección de modelos nativos y visualización elegante.
- **Seguridad Absoluta (Keyring)**: Las claves de API de los proveedores de IA y la contraseña del terminal MT5 se almacenan de forma cifrada en el **Windows Credential Manager** utilizando la biblioteca nativa `keyring`, previniendo fugas en archivos de texto plano.

### 3. Motor RAG & OSINT Enriquecido
- **Estrategia RAG**: Carga de documentos de texto locales en una carpeta de conocimiento para contextualizar a la IA bajo reglas operativas de tu propia mesa de dinero.
- **Validación OSINT**: Recopilación automatizada de eventos geopolíticos en tiempo real y calendarios macroeconómicos para penalizar confianza ante volatilidad inminente.

---

## 📸 Capturas de Pantalla (Visual Overview)

### 1. Panel de Control (Dashboard Principal)
Visualización integral del saldo (simulado o real), equidad, estado del motor de decisión ("ESPERAR"), confianza algorítmica, riesgos geopolíticos/OSINT detectados e insignias dinámicas de conexión del bróker MT5 y estado de mercado.
<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Dashboard Principal TraderExpert" width="90%" />
</p>

### 2. Configuración - Conexión Broker MT5 (Paso 1)
Acceso y enlace seguro al terminal MetaTrader 5 con credenciales encriptadas en el almacén seguro del sistema operativo (Windows Credential Manager).
<p align="center">
  <img src="docs/screenshots/config_connection.png" alt="Configuración de Conexión MT5" width="90%" />
</p>

### 3. Configuración - Parámetros de Estrategia & RAG (Paso 4)
Definición de prompts institucionales de estrategia, habilitación de base de conocimiento RAG local y selección instantánea del idioma de respuesta de la IA.
<p align="center">
  <img src="docs/screenshots/config_rag.png" alt="Configuración Estrategia RAG" width="90%" />
</p>

### 4. Gráfico e Historial Integrado con Tooltips Interactivos
Visualización histórica de análisis con mini-gráficos de velas en tooltips flotantes que muestran dinámicamente los niveles exactos de entrada y salida calculados.
<p align="center">
  <img src="docs/screenshots/chart_tooltip.png" alt="Gráfico e Historial" width="90%" />
</p>

---

## 🚀 Instalación y Despliegue

### Requisitos Previos
- **Windows 10 / 11**
- **Python 3.11** o superior instalado en el PATH.
- **Terminal MetaTrader 5** instalado y con la opción "Permitir Trading Algorítmico" habilitada en la pestaña *Herramientas > Opciones > Asesores Expertos*.

### Proceso de Configuración

1. **Clonar el Repositorio e Inicializar el Entorno**:
   ```bash
   # Clonar el proyecto
   git clone https://github.com/tu-usuario/traderexpert.git
   cd TraderExpert

   # Crear y activar entorno virtual
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. **Instalar Dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecutar la Aplicación**:
   ```bash
   python main.py
   ```

---

## 🔒 Variables de Entorno & Configuración Avanzada

Si prefieres omitir la configuración gráfica por defecto o proveer claves directamente desde entornos de desarrollo continuos (CI/CD), puedes configurar un archivo `.env` en la raíz del proyecto:

```env
# Claves de IA (Opcionales si se configuran desde la UI con Keyring)
OPENAI_API_KEY=sk-proj-...
AZURE_API_KEY=...
DEEPSEEK_API_KEY=...
CLAUDE_API_KEY=...
GEMINI_API_KEY=...

# Fuentes de Datos OSINT y Eventos Macro
WORLD_MONITOR_API_KEY=wm_live_...
ECONOMIC_CALENDAR_API_URL=https://tu-proveedor-autorizado.example/calendar
LIVEUAMAP_URL=https://liveuamap.com/
INVESTING_CALENDAR_URL=https://www.investing.com/economic-calendar
```

---

## 📄 Licencia y Descargo de Responsabilidad

Este software ha sido diseñado con propósitos educativos y de asistencia operativa de trading institucional. La operación en mercados financieros reales conlleva altos riesgos de pérdida de capital. Los autores y desarrolladores de **TraderExpert** no se hacen responsables de pérdidas financieras directas o indirectas resultantes del uso del software en **Modo Real**. Use y configure sus salvaguardas (StopLoss / Lotes mínimos) con total discreción.
