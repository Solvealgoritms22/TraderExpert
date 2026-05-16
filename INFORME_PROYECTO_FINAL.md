# Informe de Proyecto Final: TraderExpert
## Actividad 8.4: Ingeniería de Software II

---

### 1. Resumen del Proyecto
**TraderExpert** es una aplicación de escritorio avanzada diseñada para actuar como un asistente de análisis financiero de grado institucional. Utiliza Inteligencia Artificial de última generación (GPT-4o vía Azure OpenAI) combinada con análisis técnico tradicional y procesamiento de contexto externo en tiempo real para generar señales de trading de alta precisión.

### 2. Objetivos del Sistema
- **Automatización del Análisis**: Eliminar el sesgo emocional mediante el uso de modelos de razonamiento lógico.
- **Convergencia de Datos**: Integrar indicadores técnicos (OHLCV) con eventos macroeconómicos y noticias globales.
- **Interfaz de Alta Fidelidad**: Proporcionar una experiencia de usuario (UX) profesional y fluida mediante tecnologías web modernas incrustadas.
- **Gestión de Riesgos**: Identificar proactivamente banderas rojas en el mercado antes de sugerir una operación.

### 3. Arquitectura del Software
El sistema sigue una arquitectura modular y desacoplada que facilita el mantenimiento y la escalabilidad:

- **Capa de Presentación (UI)**: Desarrollada con HTML5, CSS3 (Glassmorphism) y JavaScript. Se comunica de forma asíncrona con el backend a través de un puente de `pywebview`.
- **Capa de Lógica de Negocio (Core)**:
    - `PredictionEngine`: Coordina las llamadas a la API de OpenAI y procesa los prompts.
    - `ExternalContextService`: Servicio especializado en Web Scraping y RAG para obtener contexto de mercado.
    - `TechnicalAnalysis`: Módulo encargado del cálculo de indicadores técnicos (RSI, EMAs, Volume).
- **Capa de Datos y Seguridad**:
    - `SettingsManager`: Persistencia de preferencias del usuario.
    - `Windows Vault (Keyring)`: Almacén seguro para credenciales de MetaTrader 5.
- **Integración de Trading**: Cliente nativo para MetaTrader 5 que permite la lectura de datos de mercado en vivo.

### 4. Especificaciones Técnicas
| Componente | Tecnología Seleccionada |
| :--- | :--- |
| **Lenguaje de Programación** | Python 3.11+ |
| **Inteligencia Artificial** | Azure OpenAI Service (Modelo GPT-4o) |
| **Interfaz Gráfica** | Webview2 (Chrome Engine) |
| **Framework de Estilos** | CSS3 Vanilla (Custom Premium Design) |
| **API de Mercados** | Terminal MetaTrader 5 |
| **Seguridad de Datos** | Encriptación via OS Keyring |

### 5. Características Destacadas
1. **Razonamiento IA Multi-Estrategia**: El modelo está instruido en conceptos de Smart Money (SMC), ICT y VSA.
2. **Sistema de Contexto RAG**: Recuperación de información relevante de noticias y políticas de fuentes para fundamentar las decisiones.
3. **Internacionalización**: Soporte nativo para 5 idiomas (Español, Inglés, Portugués, Francés, Alemán).
4. **Dashboard Institucional**: Interfaz oscura de bajo contraste con micro-animaciones y estados de carga en tiempo real.
5. **Gestión de Historial**: Seguimiento detallado de señales con cálculo automático de Win/Loss y balance virtual.

### 6. Conclusiones y Metodología
El desarrollo se llevó a cabo siguiendo principios de desarrollo ágil, con un fuerte enfoque en la **Experiencia del Usuario (UX)**. La integración de LLMs (Large Language Models) en un flujo de trabajo financiero real demuestra la viabilidad de la IA generativa para tareas de análisis técnico complejo, siempre que se combine con datos estructurados y filtros de riesgo tradicionales.

---

**Materia**: Ingeniería de Software II
**Actividad**: 8.4 - Proyecto Final
**Estudiante**: [Tu Nombre Aquí]
**Fecha**: Mayo 2026
