from __future__ import annotations

import base64
import json
import logging
import re
import threading
from pathlib import Path

import webview

from ai_client import PROVIDERS as AI_PROVIDERS
from app_metadata import APP_VERSION
from app_paths import resource_path

logger = logging.getLogger(__name__)
webview.settings["ALLOW_FILE_URLS"] = True


from localization import LOCALIZATION_DICT


class MainWindow:
    def __init__(self, app):
        self._app = app
        self.window = None
        self._base_uri = resource_path("").as_uri() + "/"
        self._eval_lock = threading.RLock()

    def create(self):
        try:
            screen = webview.screens[0]
            width, height = 980, 720
            x = max(0, (screen.width - width) // 2)
            y = max(0, (screen.height - height) // 2)
        except Exception:
            # Fallback if screens info not available
            width, height, x, y = 980, 720, None, None

        self.window = webview.create_window(
            "TraderExpert",
            html=self._splash_html(),
            width=width,
            height=height,
            x=x,
            y=y,
            frameless=True,
            easy_drag=True,
            js_api=WebAPI(self._app, self),
            background_color="#111313",
        )
        return self.window

    def load_splash(self):
        self._load(self._splash_html())

    def load_config(self, settings: dict):
        self._load(self._config_html(settings))

    def load_main(self, payload: dict):
        self._load(self._main_html(payload))

    def push_state(self, payload: dict):
        data = json.dumps(payload, ensure_ascii=False)
        self.eval_js(f"window.renderState && window.renderState({data});")

    def show_error(self, message: str):
        self.eval_js(f"window.showToast && window.showToast({json.dumps(message)}, true);")

    def eval_js(self, script: str):
        if not self.window:
            return
        with self._eval_lock:
            try:
                self.window.evaluate_js(script)
            except Exception as exc:
                logger.debug("No se pudo evaluar JS: %s", exc)

    def _load(self, html: str):
        if not self.window:
            return
        self.window.load_html(html, base_uri=self._base_uri)

    def _get_file_base64(self, path):
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.warning("No se pudo leer el archivo para base64: %s - %s", path, e)
            return ""

    def _read_text_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning("No se pudo leer el archivo de texto: %s - %s", path, e)
            return ""
    def _font_face_rule_data(self, family, filename, weight=900, style="normal"):
        path = resource_path(f"webfonts/{filename}")
        encoded = self._get_file_base64(path)
        if not encoded:
            return ""
        fmt = "woff2" if filename.endswith(".woff2") else "truetype"
        weight_line = f"font-weight:{weight};" if weight else ""
        return (
            f'@font-face {{'
            f'font-family:"{family}";'
            f'font-style:{style};'
            f'{weight_line}'
            f'font-display:block;'
            f'src:url(data:font/{fmt};base64,{encoded}) format("{fmt}");'
            f'}}'
        )

    def _build_icon_css(self):
        styles_path = resource_path("styles")
        all_css = self._read_text_file(styles_path / "all.css") or ""
        try:
            source_text = Path(__file__).read_text(encoding="utf-8")
        except Exception:
            source_text = ""

        icon_names = set(re.findall(r'fa-(?!duotone|solid|spin|fade)([a-z0-9-]+)', source_text))
        # common fallback icons used in the UI
        fallback = {"minus", "xmark", "check", "play", "pause", "bolt", "gear", "hand", "arrow-up", "arrow-down"}
        icon_names.update(fallback)
        icon_names = sorted(icon_names)

        icon_rules = []
        for icon_name in icon_names:
            before_pattern = re.compile(
                rf"[^{{}}]*\.fa-{re.escape(icon_name)}:before[^{{}}]*{{\s*content:\s*\"([^\"]+)\"\s*}}"
            )
            before_match = before_pattern.search(all_css)
            if before_match:
                icon_rules.append(f'.fa-{icon_name}:before {{ content:"{before_match.group(1)}"; }}')

        return "\n".join(
            [
                self._font_face_rule_data("Font Awesome 6 Pro", "fa-solid-900.woff2", 900),
                """
.fa, .fa-solid {
    -moz-osx-font-smoothing:grayscale;
    -webkit-font-smoothing:antialiased;
    display:inline-block;
    font-family:"Font Awesome 6 Pro";
    font-style:normal;
    font-weight:900;
    line-height:1;
    text-rendering:auto;
}
""",
                "\n".join(icon_rules),
            ]
        )

    def _font_face_rule(self, family, filename, weight=900, style="normal"):
        url = resource_path(f"webfonts/{filename}").as_uri()
        fmt = "woff2" if filename.endswith(".woff2") else "truetype"
        return (
            f'@font-face {{'
            f'font-family:"{family}";'
            f'font-style:{style};'
            f'font-weight:{weight};'
            f'font-display:block;'
            f'src:url("{url}") format("{fmt}");'
            f'}}'
        )

    def _logo_url(self):
        # Using Base64 is the most reliable way to display local images in WebView2
        logo_path = resource_path("traderexpert.png")
        encoded = self._get_file_base64(logo_path)
        if encoded:
            return f"data:image/png;base64,{encoded}"
        return ""

    def _head(self) -> str:
        all_css_path = resource_path("styles/all.css")
        all_css_url = all_css_path.as_uri()

        # Debug: log base and sample URIs to help diagnose missing assets
        logger.info("base_uri=%s", self._base_uri)
        logger.info("all_css_url=%s", all_css_url)
        try:
            sample_font_uri = resource_path("webfonts/fa-sharp-solid-900.woff2").as_uri()
            logger.info("sample_font_uri=%s", sample_font_uri)
        except Exception:
            logger.info("sample_font_uri not found yet")

        # Build minimal icon CSS (fonts embedded as data URIs) and inline animate.min.css
        icon_css = self._build_icon_css()
        animate_css = self._read_text_file(resource_path("styles") / "animate.min.css")
        css_block = "<style>\n" + icon_css + "\n" + (animate_css or "") + "\n</style>\n"

        style_block = (
            css_block +
            "<style>\n" +
            """
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800&display=swap');
:root {
    --bg: #0f1111;
    --panel: #161818;
    --panel-2: #1c1e1e;
    --input: #0a0c0c;
    --border: #24282a;
    --border-strong: #32383b;
    --text: #d1d5db;
    --strong: #ffffff;
    --muted: #9ca3af;
    --dim: #6b7280;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --blue: #4a6e82;
    --accent: #4a6e82;
    --accent-hover: #5d8aa8;
    --radius: 12px;
}
* { box-sizing: border-box; letter-spacing: -0.01em; outline: none; }
body {
    margin: 0;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: var(--bg);
    color: var(--text);
    font-family: 'Montserrat', system-ui, sans-serif;
    border: 1px solid var(--border);
}
/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: var(--dim); }

i.fa-solid, .fa-solid { font-family: "Font Awesome 6 Pro" !important; font-weight: 900 !important; }

button, input, select {
    font-family: inherit;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--input);
    color: var(--text);
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
button { cursor: pointer; min-height: 42px; padding: 0 20px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 10px; font-size: 13px; }
button:hover:not(:disabled) { background: var(--panel-2); border-color: var(--border-strong); color: var(--strong); transform: translateY(-1px); }
button:active:not(:disabled) { transform: translateY(0); }
button.primary { background: var(--accent); color: white; border: none; font-weight: 700; }
button.primary:hover:not(:disabled) { background: var(--accent-hover); color: white; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3); }
button.danger { color: var(--danger); }
button.danger:hover:not(:disabled) { background: rgba(239, 68, 68, 0.1); border-color: var(--danger); }
button:disabled { opacity: .4; cursor: not-allowed; }

input, select { height: 44px; padding: 0 14px; width: 100%; border-color: var(--border); background: var(--input); color: var(--strong); }
input[type="date"] { color-scheme: dark; font-weight: 600; cursor: pointer; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1); }
input::placeholder { color: var(--dim); }

header {
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    padding: 0 16px;
    background: rgba(15, 17, 17, 0.8);
    backdrop-filter: blur(10px);
    -webkit-app-region: drag;
    z-index: 100;
}
header * { -webkit-app-region: no-drag; }
.title { display: flex; align-items: center; gap: 12px; font-size: 13px; font-weight: 700; color: var(--strong); }
.window-actions { display: flex; gap: 6px; }
.icon-btn { width: 34px; height: 34px; min-height: 34px; padding: 0; border: none; background: transparent; color: var(--muted); }
.icon-btn:hover { background: rgba(255,255,255,0.08); color: var(--strong); transform: none; }

.screen { height: calc(100vh - 52px); overflow: hidden; display: flex; flex-direction: column; }
.content { flex: 1; overflow-y: auto; padding: 32px; }

/* Stepper */
.stepper { display: flex; justify-content: space-between; margin-bottom: 40px; position: relative; padding: 0 60px; }
.stepper::before { content: ''; position: absolute; top: 16px; left: 60px; right: 60px; height: 2px; background: var(--border-strong); z-index: 0; }
.step { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; gap: 10px; cursor: pointer; transition: all 0.2s ease; }
.step:hover .step-circle { border-color: var(--accent); color: var(--strong); transform: scale(1.05); }
.step.active:hover .step-circle { transform: none; }
.step-circle { width: 34px; height: 34px; border-radius: 50%; background: var(--panel); border: 2px solid var(--border-strong); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; transition: all 0.3s ease; color: var(--muted); }
.step.active .step-circle { background: var(--accent); border-color: var(--accent); color: white; box-shadow: 0 0 15px rgba(59, 130, 246, 0.4); }
.step.completed .step-circle { background: var(--accent); border-color: var(--accent); color: white; }
.step-label { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.step.active .step-label { color: var(--strong); }

.grid { display: grid; gap: 24px; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; position: relative; overflow: hidden; transition: transform 0.2s ease; }
.card:hover { transform: translateY(-2px); border-color: var(--border-strong); }
.card::after { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: linear-gradient(90deg, transparent, var(--accent), transparent); opacity: 0.8; box-shadow: 0 0 12px var(--accent); }
.card-label { font-size: 10px; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 12px; display: block; }
.card-value { color: var(--strong); font-size: 24px; font-weight: 800; }

.side-panel { display: flex; flex-direction: column; gap: 16px; }
.side-panel .card { flex: 1; display: flex; flex-direction: column; justify-content: center; min-height: 100px; }

.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 32px; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.toolbar button {
    height: 36px;
    min-height: 36px;
    padding: 0 16px;
    font-size: 12px;
    border-radius: var(--radius);
}
.toolbar .icon-btn {
    width: 36px;
    height: 36px;
    min-height: 36px;
    padding: 0;
}
.btn-group {
    display: inline-flex;
    background: var(--input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    padding: 2px;
    align-items: center;
    gap: 2px;
    height: 36px;
}
.btn-group .icon-btn {
    width: 30px;
    height: 30px;
    min-height: 30px;
    border-radius: calc(var(--radius) - 4px);
    border: none;
    background: transparent;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
}
.btn-group .icon-btn:hover {
    background: var(--panel-2);
    color: var(--strong);
}
.btn-group .icon-btn i {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-top: 1px;
}

.signal-stage { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 24px; }
.signal-panel {
    background: linear-gradient(145deg, #181a1a, #0f1111);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    min-height: 420px;
    position: relative;
    overflow: hidden;
}
.scanning-ring {
    position: absolute;
    width: 300px;
    height: 300px;
    border: 2px solid var(--accent);
    border-radius: 50%;
    opacity: 0;
    pointer-events: none;
}
.scanning .scanning-ring {
    animation: scan-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
.scanning .scanning-ring:nth-child(2) {
    animation-delay: 1s;
}
@keyframes scan-pulse {
    0% { transform: scale(0.8); opacity: 0; border-width: 8px; }
    50% { opacity: 0.4; }
    100% { transform: scale(1.6); opacity: 0; border-width: 1px; }
}

#signal-content {
    transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 2;
}

.scanning #signal-content {
    opacity: 0;
    transform: scale(0.85);
    filter: blur(8px);
    pointer-events: none;
}

.scanning-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 14px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.2em;
    text-transform: uppercase;
    opacity: 0;
    transition: opacity 0.4s ease;
    z-index: 3;
    pointer-events: none;
}

.scanning .scanning-label {
    opacity: 1;
    animation: text-pulse 1.5s infinite;
}

@keyframes text-pulse {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
}

.signal-icon { font-size: 120px; margin-bottom: 24px; transition: all 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.signal-icon.up { color: var(--success); filter: drop-shadow(0 0 25px rgba(16, 185, 129, 0.3)); transform: scale(1.1); }
.signal-icon.down { color: var(--danger); filter: drop-shadow(0 0 25px rgba(239, 68, 68, 0.3)); transform: scale(1.1); }
.signal-icon.wait { color: var(--warning); filter: drop-shadow(0 0 25px rgba(245, 158, 11, 0.2)); }
.signal-label { font-size: 52px; font-weight: 900; color: var(--strong); letter-spacing: -0.02em; }
.signal-meta { margin-top: 20px; font-size: 15px; color: #b1b5bb; line-height: 1.7; max-width: 440px; }

.history { margin-top: 32px; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.history-head { display: grid; grid-template-columns: 130px 110px 80px 80px 60px 1fr 80px; padding: 14px 20px; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border); font-size: 10px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.history-row { display: grid; grid-template-columns: 130px 110px 80px 80px 60px 1fr 80px; padding: 14px 20px; border-bottom: 1px solid var(--border); align-items: center; font-size: 12px; animation: slideIn 0.3s ease-out forwards; }
.history-row:last-child { border-bottom: none; }
@keyframes slideIn { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }

.pill { padding: 5px 12px; border-radius: 8px; font-size: 10px; font-weight: 800; text-transform: uppercase; }
.pill.up, .pill.WIN { background: rgba(16, 185, 129, 0.12); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.25); }
.pill.down, .pill.LOSS { background: rgba(239, 68, 68, 0.12); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.25); }
.pill.wait { background: rgba(245, 158, 11, 0.1); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.2); }

/* Custom Tooltip */
#tooltip {
    position: fixed;
    background: #1c1e1e;
    color: var(--strong);
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    font-size: 11px;
    line-height: 1.5;
    max-width: 300px;
    z-index: 10000;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    white-space: pre-line;
}
#tooltip.visible { opacity: 1; }

#chart-tooltip {
    position: fixed;
    background: #1c1e1e;
    border: 1px solid var(--border-strong);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 15px 35px rgba(0,0,0,0.6);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 10000;
    width: 320px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}
#chart-tooltip.visible { opacity: 1; }
#chart-tooltip canvas {
    background: #0f1111;
    border-radius: 6px;
    border: 1px solid rgba(255,255,255,0.03);
    width: 100%;
    height: 140px;
}

.toast { position: fixed; right: 32px; bottom: 32px; background: var(--panel-2); border: 1px solid var(--border-strong); padding: 16px 24px; border-radius: 14px; box-shadow: 0 15px 35px rgba(0,0,0,0.5); transform: translateY(120px); opacity: 0; transition: all 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 1000; font-weight: 500; }
.toast.open { transform: translateY(0); opacity: 1; }

.pagination { display: flex; align-items: center; justify-content: center; gap: 20px; padding: 20px; border-top: 1px solid var(--border); background: rgba(255,255,255,0.01); }
.pagination-info { font-size: 12px; color: var(--muted); font-weight: 600; }
.language-selector { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 8px; }
.lang-option { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--input); border: 1px solid var(--border); border-radius: 10px; cursor: pointer; transition: all 0.2s ease; }
.lang-option img { width: 22px; height: 16px; object-fit: cover; border-radius: 2px; box-shadow: 0 2px 4px rgba(0,0,0,0.3); }
.lang-option span { font-size: 13px; font-weight: 500; }
.lang-option:hover { border-color: var(--border-strong); background: var(--panel-2); transform: translateY(-1px); }
.lang-option.active { border-color: var(--accent); background: rgba(74, 110, 130, 0.1); color: var(--strong); box-shadow: 0 0 0 1px var(--accent); }

.form-section { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; display: grid; gap: 16px; align-content: start; }
.form-section h2 { margin: 0 0 8px; font-size: 17px; color: var(--strong); font-weight: 700; }
.field label { display: block; color: #b1b5bb; font-size: 11px; font-weight: 700; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }

.actions { display: flex; justify-content: flex-end; gap: 12px; padding: 20px 32px 28px; border-top: 1px solid var(--border); background: var(--bg); }

.muted { color: #8a8f94; }
.strong { color: var(--strong); }

.splash { height: 100vh; display: flex; align-items: center; justify-content: center; text-align: center; background: radial-gradient(circle at center, #1a1c1c 0%, #0f1111 100%); }
.splash-logo { width: 140px; height: 140px; margin-bottom: 24px; }

.step-content { display: none; }
.step-content.active { display: grid; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

select option { background: var(--panel); color: var(--text); padding: 10px; }

#action-btn.active:hover { background: #ff5f7e; box-shadow: 0 0 15px rgba(239, 68, 68, 0.3); }

/* Modal */
.modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); display: none; align-items: center; justify-content: center; z-index: 2000; animation: fadeIn 0.3s ease; }
.modal { background: var(--panel); border: 1px solid var(--border-strong); border-radius: 20px; width: 400px; padding: 32px; box-shadow: 0 25px 50px rgba(0,0,0,0.6); transform: scale(0.9); transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.modal-overlay.open { display: flex; }
.modal-overlay.open .modal { transform: scale(1); }
.modal-title { font-size: 20px; font-weight: 800; color: var(--strong); margin-bottom: 12px; display: flex; align-items: center; gap: 12px; }
.modal-text { font-size: 14px; color: var(--muted); line-height: 1.6; margin-bottom: 24px; }
.modal-actions { display: flex; gap: 12px; justify-content: flex-end; }
.modal-btn { padding: 10px 20px; border-radius: 10px; font-weight: 700; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; }
.modal-btn.cancel { background: transparent; border-color: var(--border); color: var(--muted); }
.modal-btn.confirm { background: var(--accent); color: white; }
.modal-btn.confirm.danger { background: var(--danger); }
.modal-btn:hover { transform: translateY(-2px); filter: brightness(1.1); }

/* Empty State */
.empty-history { grid-column: 1 / -1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; text-align: center; color: var(--muted); }
.empty-history i { font-size: 48px; color: rgba(255,255,255,0.05); margin-bottom: 20px; }
.empty-history h3 { color: var(--strong); font-size: 16px; margin: 0 0 8px; font-weight: 700; }
.empty-history p { font-size: 13px; max-width: 300px; margin: 0; line-height: 1.6; }

/* Asset Flags/Icons */
.asset-render { display: flex; align-items: center; gap: 10px; }
.flag-pair { display: flex; align-items: center; position: relative; width: 42px; height: 24px; }
.flag { width: 24px; height: 24px; border-radius: 50%; object-fit: cover; border: 2px solid var(--panel); position: absolute; }
.flag:nth-child(1) { left: 0; z-index: 2; }
.flag:nth-child(2) { left: 18px; z-index: 1; opacity: 0.8; }
.asset-icon { font-size: 20px; color: var(--accent); width: 24px; text-align: center; }
.asset-text { font-size: 14px; font-weight: 700; color: var(--strong); }
.asset-tf { font-size: 11px; color: var(--muted); margin-left: 4px; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }

/* Chart Type Selector */
.chart-type-selector {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 8px;
}
.chart-option {
    background: var(--input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    text-align: center;
    position: relative;
    overflow: hidden;
}
.chart-option img {
    height: 48px;
    width: auto;
    max-width: 48px;
    object-fit: contain;
    filter: drop-shadow(0 4px 8px rgba(0,0,0,0.2));
    transition: transform 0.3s ease;
}
.chart-option span {
    font-size: 13px;
    font-weight: 700;
    color: var(--muted);
    transition: color 0.2s ease;
}
.chart-option:hover {
    border-color: var(--border-strong);
    background: var(--panel-2);
    transform: translateY(-2px);
}
.chart-option:hover img {
    transform: scale(1.1);
}
.chart-option.active {
    border-color: var(--accent);
    background: rgba(74, 110, 130, 0.08);
    box-shadow: 0 0 0 1px var(--accent), 0 8px 20px rgba(59, 130, 246, 0.15);
}
.chart-option.active span {
    color: var(--strong);
}
.chart-option.active img {
    transform: scale(1.05);
}

/* RAG Toggle Selector */
.rag-toggle-selector {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 8px;
}
.rag-option {
    background: var(--input);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 20px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
}
.rag-option i {
    font-size: 16px;
    transition: transform 0.2s ease, color 0.2s ease;
}
.rag-option span {
    font-size: 13px;
    font-weight: 700;
    color: var(--muted);
    transition: color 0.2s ease;
}
.rag-option:hover {
    border-color: var(--border-strong);
    background: var(--panel-2);
}
.rag-option:hover i {
    transform: scale(1.15);
}
/* Activado Style */
.rag-option[data-value="true"]:hover i {
    color: var(--success);
}
.rag-option[data-value="true"].active {
    border-color: var(--success);
    background: rgba(16, 185, 129, 0.08);
    box-shadow: 0 0 0 1px var(--success), 0 4px 12px rgba(16, 185, 129, 0.15);
}
.rag-option[data-value="true"].active i {
    color: var(--success);
    transform: scale(1.05);
}
.rag-option[data-value="true"].active span {
    color: var(--strong);
}

/* Desactivado Style */
.rag-option[data-value="false"]:hover i {
    color: var(--danger);
}
.rag-option[data-value="false"].active {
    border-color: var(--danger);
    background: rgba(239, 68, 68, 0.08);
    box-shadow: 0 0 0 1px var(--danger), 0 4px 12px rgba(239, 68, 68, 0.15);
}
.rag-option[data-value="false"].active i {
    color: var(--danger);
    transform: scale(1.05);
}
.rag-option[data-value="false"].active span {
    color: var(--strong);
}
""" + "</style>"
        )

        return f'<base href="{self._base_uri}">\n' + \
               '<meta charset="UTF-8">\n' + \
               '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' + \
               style_block

    def _chrome(self, title: str) -> str:
        logo = self._logo_url()
        return f"""
<header>
    <div class="title">
        <img src="{logo}" style="height:26px; width:26px; object-fit:contain; background:transparent;" alt="Logo">
        <span>{title}</span>
    </div>
    <div class="window-actions">
        <button class="icon-btn" onclick="pywebview.api.minimize()" data-t-aria="minimize_aria" aria-label="Minimizar"><i class="fa-solid fa-minus"></i></button>
        <button class="icon-btn" onclick="pywebview.api.toggle_fullscreen()" data-t-aria="fullscreen_aria" aria-label="Pantalla Completa"><i class="fa-solid fa-expand"></i></button>
        <button class="icon-btn danger" onclick="pywebview.api.quit()" data-t-aria="quit_aria" aria-label="Salir"><i class="fa-solid fa-xmark"></i></button>
    </div>
</header>
<div id="tooltip" class="tooltip"></div>
"""

    def _splash_html(self) -> str:
        logo = self._logo_url()
        return f"""
<!DOCTYPE html>
<html lang="es">
<head>{self._head()}</head>
<body>
<main class="splash">
    <section>
        <img src="{logo}" class="splash-logo" alt="Logo">
        <h1 style="margin:0; font-size:42px; font-weight:900; letter-spacing:-0.03em;">Trader<span style="color:var(--accent)">Expert</span></h1>
        <p style="margin-top:8px; color:var(--muted); font-size:14px; font-weight:500;">IA de Predicción de Mercados Financieros</p>
        <div style="width:200px; height:3px; background:var(--panel); border-radius:10px; margin:40px auto 0; overflow:hidden; position:relative;">
            <div style="position:absolute; top:0; left:0; height:100%; width:50%; background:var(--accent); border-radius:10px; animation: load-anim 1.5s infinite ease-in-out;"></div>
        </div>
        <style>
            @keyframes load-anim {{
                0% {{ transform: translateX(-100%); }}
                100% {{ transform: translateX(200%); }}
            }}
        </style>
    </section>
</main>
<script>
setTimeout(() => pywebview.api.route_after_splash().catch(() => {{}}), 2000);
</script>
</body>
</html>
"""

    def _config_html(self, settings: dict) -> str:
        s = json.dumps(settings, ensure_ascii=False)
        loc_json = json.dumps(LOCALIZATION_DICT, ensure_ascii=False)
        providers_json = json.dumps(AI_PROVIDERS, ensure_ascii=False)

        candles_path = resource_path("images/icon_candles.png")
        line_path = resource_path("images/icon_line.png")
        bars_path = resource_path("images/icon_bars.png")

        candles_base64 = ""
        line_base64 = ""
        bars_base64 = ""

        encoded_candles = self._get_file_base64(candles_path)
        if encoded_candles:
            candles_base64 = f"data:image/png;base64,{encoded_candles}"

        encoded_line = self._get_file_base64(line_path)
        if encoded_line:
            line_base64 = f"data:image/png;base64,{encoded_line}"

        encoded_bars = self._get_file_base64(bars_path)
        if encoded_bars:
            bars_base64 = f"data:image/png;base64,{encoded_bars}"

        openai_path = resource_path("images/openai.svg")
        azure_path = resource_path("images/azure.svg")
        grok_path = resource_path("images/grok.svg")
        deepseek_path = resource_path("images/deepseek.svg")
        claude_path = resource_path("images/claude.svg")
        gemini_path = resource_path("images/gemini.svg")

        openai_base64 = ""
        azure_base64 = ""
        grok_base64 = ""
        deepseek_base64 = ""
        claude_base64 = ""
        gemini_base64 = ""

        encoded_openai = self._get_file_base64(openai_path)
        if encoded_openai:
            openai_base64 = f"data:image/svg+xml;base64,{encoded_openai}"

        encoded_azure = self._get_file_base64(azure_path)
        if encoded_azure:
            azure_base64 = f"data:image/svg+xml;base64,{encoded_azure}"

        encoded_grok = self._get_file_base64(grok_path)
        if encoded_grok:
            grok_base64 = f"data:image/svg+xml;base64,{encoded_grok}"

        encoded_deepseek = self._get_file_base64(deepseek_path)
        if encoded_deepseek:
            deepseek_base64 = f"data:image/svg+xml;base64,{encoded_deepseek}"

        encoded_claude = self._get_file_base64(claude_path)
        if encoded_claude:
            claude_base64 = f"data:image/svg+xml;base64,{encoded_claude}"

        encoded_gemini = self._get_file_base64(gemini_path)
        if encoded_gemini:
            gemini_base64 = f"data:image/svg+xml;base64,{encoded_gemini}"

        return f"""
<!DOCTYPE html>
<html lang="es">
<head>{self._head()}</head>
<body>
{self._chrome("TraderExpert v" + APP_VERSION)}
<main class="screen">
    <section class="content">
        <div class="toolbar">
            <div>
                <div class="card-label" data-t="settings">Configuracion</div>
                <h1 style="margin:4px 0 0;color:var(--strong);font-size:22px;" data-t="config_title">Personaliza tu experiencia</h1>
            </div>
        </div>

        <div class="stepper">
            <div class="step active" id="step-1-ind" onclick="goToStep(1)"><div class="step-circle">1</div><div class="step-label" data-t="step1_title">Conexion</div></div>
            <div class="step" id="step-2-ind" onclick="goToStep(2)"><div class="step-circle">2</div><div class="step-label" data-t="step2_title">Mercado</div></div>
            <div class="step" id="step-3-ind" onclick="goToStep(3)"><div class="step-circle">3</div><div class="step-label" data-t="step3_title">Simulacion</div></div>
            <div class="step" id="step-4-ind" onclick="goToStep(4)"><div class="step-circle">4</div><div class="step-label" data-t="step4_title">Estrategia</div></div>
            <div class="step" id="step-5-ind" onclick="goToStep(5)"><div class="step-circle">5</div><div class="step-label" data-t="step5_title">IA</div></div>
        </div>

        <form id="config-form">
            <!-- STEP 1: CONEXION -->
            <div class="step-content active" id="step-1">
                <section class="form-section">
                    <h2 data-t="step1_header">Terminal MT5</h2>
                    <div class="field"><label data-t="field_mt5_path">Ruta MT5 (Opcional)</label><input name="mt5_path" placeholder="C:\\Program Files\\MetaTrader 5\\terminal64.exe"></div>
                    <div class="field"><label data-t="field_mt5_account">Cuenta</label><input name="mt5_account" placeholder="5043420806"></div>
                    <div class="field"><label data-t="field_mt5_password">Contraseña</label><input type="password" name="mt5_password" placeholder="••••••••"></div>
                    <div class="field"><label data-t="field_mt5_server">Servidor</label><input name="mt5_server" placeholder="MetaQuotes-Demo"></div>
                </section>
            </div>

            <!-- STEP 2: MERCADO -->
            <div class="step-content" id="step-2">
                <section class="form-section">
                    <h2 data-t="step2_header">Configuracion de Mercado</h2>
                    <div class="field"><label data-t="field_market_type">Tipo de mercado</label>
                        <select name="market_type" onchange="updateSymbolsByMarketType()">
                            <option value="Forex" data-t="market_forex">🌐 Forex</option>
                            <option value="Indices" data-t="market_indices">📊 Indices</option>
                            <option value="Commodities" data-t="market_commodities">🥇 Commodities</option>
                            <option value="Crypto" data-t="market_crypto">₿ Crypto</option>
                            <option value="Acciones" data-t="market_acciones">🏢 Acciones</option>
                        </select>
                    </div>
                    <div class="field">
                        <label data-t="field_active_symbol">Activo (Símbolo)</label>
                        <div style="display:flex; align-items:center; gap:12px;">
                            <select name="symbol" onchange="updateAssetPreview(this.value)" style="flex:1;">
                                <option value="EURUSD">EURUSD</option>
                            </select>
                            <div id="asset-preview" style="background:var(--panel-2); padding:0 16px; border-radius:var(--radius); border:1px solid var(--border); min-width:140px; height:44px; display:flex; align-items:center; justify-content:center;">-</div>
                        </div>
                    </div>
                    <div class="field"><label data-t="field_timeframe">Temporalidad</label>
                        <select name="timeframe">
                            <option>M1</option><option>M2</option><option>M5</option><option>M15</option><option>M30</option><option>H1</option>
                        </select>
                    </div>
                    <div class="field">
                        <label data-t="field_chart_type">Tipo de Gráfico</label>
                        <input type="hidden" name="chart_type" id="chart-type-input">
                        <div class="chart-type-selector">
                            <div class="chart-option" data-value="candles" onclick="selectChartType('candles')">
                                <img src="{candles_base64}" alt="Velas">
                                <span data-t="chart_candles">Velas</span>
                            </div>
                            <div class="chart-option" data-value="line" onclick="selectChartType('line')">
                                <img src="{line_base64}" alt="Línea">
                                <span data-t="chart_line">Línea</span>
                            </div>
                            <div class="chart-option" data-value="bars" onclick="selectChartType('bars')">
                                <img src="{bars_base64}" alt="Barras">
                                <span data-t="chart_bars">Barras</span>
                            </div>
                        </div>
                    </div>
                </section>
            </div>

            <!-- STEP 3: SIMULACION -->
            <div class="step-content" id="step-3">
                <section class="form-section">
                    <h2 data-t="step3_header">Parámetros y Sonido</h2>
                    <div class="grid" style="grid-template-columns: 1fr 1fr;">
                        <div class="field"><label data-t="field_virtual_balance">Capital Virtual</label><input type="number" name="virtual_balance" step="0.01"></div>
                        <div class="field"><label data-t="field_stake_amount">Monto por Señal</label><input type="number" name="stake_amount" step="0.01"></div>
                    </div>
                    <div class="grid" style="grid-template-columns: 1fr 1fr;">
                        <div class="field">
                            <label data-t="field_payout_percent">Payout %</label>
                            <div style="display:flex; align-items:center; gap:12px; margin-top:8px; background:var(--panel); border:1px solid var(--border); border-radius:var(--radius); padding:4px 12px; height:44px;">
                                <input type="range" name="payout_percent" min="10" max="100" step="1" style="flex:1; accent-color:var(--accent); cursor:pointer; background:transparent; height:6px;" oninput="document.getElementById('payout-val').textContent = this.value + '%'">
                                <span id="payout-val" style="font-size:13px; font-weight:800; color:var(--strong); min-width:45px; text-align:right;">80%</span>
                            </div>
                        </div>
                        <div class="field">
                            <label data-t="field_confidence_threshold">Confianza Mínima</label>
                            <div style="display:flex; align-items:center; gap:12px; margin-top:8px; background:var(--panel); border:1px solid var(--border); border-radius:var(--radius); padding:4px 12px; height:44px;">
                                <input type="range" name="confidence_threshold" min="0.50" max="0.95" step="0.01" style="flex:1; accent-color:var(--accent); cursor:pointer; background:transparent; height:6px;" oninput="document.getElementById('confidence-val').textContent = Math.round(this.value * 100) + '%'">
                                <span id="confidence-val" style="font-size:13px; font-weight:800; color:var(--strong); min-width:45px; text-align:right;">65%</span>
                            </div>
                        </div>
                    </div>
                    <div class="grid" style="grid-template-columns: 1fr 1fr;">
                        <div class="field"><label data-t="field_prediction_horizon">Horizonte Predicción (min)</label><input type="number" name="prediction_horizon_minutes" min="1"></div>
                        <div class="field"><label data-t="field_analysis_interval">Intervalo Análisis (min)</label><input type="number" name="analysis_interval_minutes" min="1"></div>
                    </div>
                    <div class="field"><label data-t="field_enable_sounds">Sonidos de Alerta</label>
                        <select name="enable_sounds">
                            <option value="true" data-t="sounds_enabled">🔊 Activado</option>
                            <option value="false" data-t="sounds_disabled">🔇 Desactivado</option>
                        </select>
                    </div>

                    <hr style="border:none; border-top:1px solid var(--border); margin:16px 0;">

                    <div class="field">
                        <label data-t="trading_mode_label">Modo de Operación</label>
                        <select name="trading_mode" id="trading-mode-select" onchange="toggleTradingMode()">
                            <option value="simulation" data-t="mode_simulation">🎮 Simulación</option>
                            <option value="real" data-t="mode_real">💰 Cuenta Real</option>
                        </select>
                    </div>
                    <div id="real-mode-warning" style="display:none; background: rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3); border-radius:var(--radius); padding:12px; margin:8px 0;">
                        <div style="display:flex; align-items:center; gap:8px; color:#EF4444; font-size:12px; font-weight:600;">
                            <i class="fa-solid fa-triangle-exclamation"></i>
                            <span data-t="real_mode_warning">⚠️ Operar en modo real implica riesgo de pérdida de capital</span>
                        </div>
                    </div>
                    <div id="real-mode-fields" style="display:none;">
                        <div class="grid" style="grid-template-columns: 1fr 1fr 1fr;">
                            <div class="field"><label data-t="field_lot_size">Volumen (Lotes)</label><input type="number" name="lot_size" step="0.01" min="0.01" max="100"></div>
                            <div class="field"><label data-t="field_sl_multiplier">SL (ATR ×)</label><input type="number" name="auto_sl_atr_multiplier" step="0.1" min="0.5" max="5.0"></div>
                            <div class="field"><label data-t="field_tp_ratio">TP Ratio (R:R)</label><input type="number" name="auto_tp_ratio" step="0.1" min="1.0" max="5.0"></div>
                        </div>
                    </div>
                </section>
            </div>
            <!-- STEP 4: ESTRATEGIA / RAG -->
            <div class="step-content" id="step-4">
                <section class="form-section">
                    <h2 data-t="step4_header">Estrategia e Inteligencia (RAG)</h2>
                    <div class="field">
                        <label data-t="field_strategy_prompt">Instrucciones de Estrategia (Prompt)</label>
                        <textarea name="strategy_prompt" style="width:100%; height:120px; padding:12px; border-radius:var(--radius); border:1px solid var(--border); background:var(--panel); color:var(--strong); font-family:inherit; resize:vertical;"></textarea>
                    </div>
                    <div class="field">
                        <label data-t="field_rag_directory">Carpeta de Conocimiento (RAG)</label>
                        <input name="rag_directory" placeholder="Ej: rag_knowledge">
                    </div>
                    <div class="field">
                        <label data-t="field_lang_response">Idioma de la App</label>
                        <input type="hidden" name="language" id="lang-input">
                        <div class="language-selector">
                            <div class="lang-option" data-lang="es" onclick="setLanguage('es')">
                                <img src="https://flagcdn.com/w40/es.png"><span>Español</span>
                            </div>
                            <div class="lang-option" data-lang="en" onclick="setLanguage('en')">
                                <img src="https://flagcdn.com/w40/us.png"><span>English</span>
                            </div>
                            <div class="lang-option" data-lang="pt" onclick="setLanguage('pt')">
                                <img src="https://flagcdn.com/w40/br.png"><span>Português</span>
                            </div>
                            <div class="lang-option" data-lang="fr" onclick="setLanguage('fr')">
                                <img src="https://flagcdn.com/w40/fr.png"><span>Français</span>
                            </div>
                            <div class="lang-option" data-lang="de" onclick="setLanguage('de')">
                                <img src="https://flagcdn.com/w40/de.png"><span>Deutsch</span>
                            </div>
                        </div>
                    </div>
                    <div class="field">
                        <label data-t="field_enable_rag">Uso de RAG / Entrenamiento</label>
                        <input type="hidden" name="enable_rag" id="enable-rag-input">
                        <div class="rag-toggle-selector">
                            <div class="rag-option" data-value="true" onclick="selectRagOption('true')">
                                <i class="fa-solid fa-circle-check"></i>
                                <span data-t="rag_enabled">Activado</span>
                            </div>
                            <div class="rag-option" data-value="false" onclick="selectRagOption('false')">
                                <i class="fa-solid fa-circle-xmark"></i>
                                <span data-t="rag_disabled">Desactivado</span>
                            </div>
                        </div>
                    </div>
                </section>
            </div>

            <!-- STEP 5: AI PROVIDER -->
            <div class="step-content" id="step-5">
                <section class="form-section">
                    <h2 data-t="step5_header">Proveedor de IA</h2>
                    <input type="hidden" name="ai_provider" id="ai-provider-input">
                    <div class="provider-grid" id="provider-grid"></div>

                    <div id="ai-fields" style="margin-top:16px; display: flex; flex-direction: column; gap: 16px;"></div>

                    <div style="margin-top:12px;">
                        <button type="button" id="test-ai-btn" onclick="testAIConnection()" style="display:inline-flex; align-items:center; gap:8px; padding:10px 20px; background:var(--panel-2); border:1px solid var(--border); border-radius:var(--radius); color:var(--text); cursor:pointer; font-weight:600; font-size:12px; transition:all 0.2s ease;">
                            <i class="fa-solid fa-plug"></i>
                            <span data-t="btn_test_connection">Probar Conexion</span>
                        </button>
                        <span id="test-result" style="margin-left:12px; font-size:12px; font-weight:600;"></span>
                    </div>
                </section>
            </div>
        </form>
    </section>
    <section class="actions">
        <button onclick="pywebview.api.open_main()">
            <i class="fa-solid fa-house"></i>
            <span data-t="back_home">Volver al Inicio</span>
        </button>
        <div style="flex:1;"></div>
        <button id="prev-btn" style="display:none;" onclick="changeStep(-1)">
            <i class="fa-solid fa-chevron-left"></i>
            <span data-t="prev">Anterior</span>
        </button>
        <button id="next-btn" class="primary" onclick="changeStep(1)">
            <span data-t="next">Siguiente</span>
            <i class="fa-solid fa-chevron-right"></i>
        </button>
        <button id="save-btn" class="primary" style="display:none;" onclick="saveConfig()">
            <i class="fa-solid fa-check"></i>
            <span data-t="save">Guardar e Iniciar</span>
        </button>
    </section>
</main>
<div class="toast" id="toast"></div>
<script>
const LOCALIZATION = {loc_json};
const initial = {s};
let currentStep = 1;
const form = document.getElementById('config-form');

function translateConfigPage(lang) {{
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    
    // Translate standard texts
    document.querySelectorAll('[data-t]').forEach(el => {{
        const key = el.getAttribute('data-t');
        if (dict[key]) {{
            el.textContent = dict[key];
        }}
    }});
    
    // Translate input placeholders if dict has them
    document.querySelectorAll('[data-t-placeholder]').forEach(el => {{
        const key = el.getAttribute('data-t-placeholder');
        if (dict[key]) {{
            el.setAttribute('placeholder', dict[key]);
        }}
    }});

    // Translate chrome actions
    document.querySelectorAll('[data-t-aria]').forEach(el => {{
        const key = el.getAttribute('data-t-aria');
        if (dict[key]) {{
            el.setAttribute('aria-label', dict[key]);
        }}
    }});
}}

function fill() {{
    for (const [key, value] of Object.entries(initial)) {{
        const field = form.elements[key];
        if (field) {{
            if (typeof value === 'boolean') field.value = String(value);
            else field.value = value ?? '';
            // Trigger input event to update range display indicators
            field.dispatchEvent(new Event('input'));
            if (key === 'language') setLanguage(value || 'es');
            if (key === 'chart_type') selectChartType(value || 'candles');
            if (key === 'enable_rag') selectRagOption(value);
        }}
    }}
    updateSymbolsByMarketType();
    updateAssetPreview(initial.symbol);
    toggleTradingMode();
    loadMT5Symbols();
}}

function setLanguage(lang) {{
    document.getElementById('lang-input').value = lang;
    document.querySelectorAll('.lang-option').forEach(opt => {{
        opt.classList.toggle('active', opt.dataset.lang === lang);
    }});
    translateConfigPage(lang);
}}

function updateAssetPreview(val) {{
    const preview = document.getElementById('asset-preview');
    if (preview) preview.innerHTML = renderAssetHTML(val);
}}

function renderAssetHTML(symbol, timeframe = "", compact = false) {{
    if (!symbol) return '<span style="color:var(--muted); font-size:11px;">-</span>';
    symbol = symbol.toUpperCase();
    
    const size = compact ? 14 : 24;
    const fontSize = compact ? '10px' : '14px';
    const gap = compact ? '4px' : '10px';
    const pairWidth = compact ? '24px' : '42px';
    const flagShift = compact ? 10 : 18;

    const map = {{
        'EUR': 'eu', 'USD': 'us', 'GBP': 'gb', 'JPY': 'jp', 'AUD': 'au', 'CAD': 'ca', 'CHF': 'ch', 'NZD': 'nz',
        'CNY': 'cn', 'MXN': 'mx', 'BRL': 'br', 'HKD': 'hk', 'SGD': 'sg'
    }};

    if (symbol.length === 6) {{
        const c1 = symbol.substring(0, 3);
        const c2 = symbol.substring(3, 6);
        if (map[c1] && map[c2]) {{
            return `
                <div class="asset-render" style="gap:${{gap}};">
                    <div class="flag-pair" style="width:${{pairWidth}}; height:${{size}}px;">
                        <img src="https://flagcdn.com/w80/${{map[c1]}}.png" class="flag" style="width:${{size}}px; height:${{size}}px; border-width: 1px;">
                        <img src="https://flagcdn.com/w80/${{map[c2]}}.png" class="flag" style="width:${{size}}px; height:${{size}}px; left:${{flagShift}}px; border-width: 1px;">
                    </div>
                    <div class="asset-text" style="font-size:${{fontSize}}; opacity: 0.9;">${{symbol}}</div>
                </div>
            `;
        }}
    }}
    let icon = 'fa-chart-line';
    if (symbol.includes('BTC')) icon = 'fa-brands fa-bitcoin';
    else if (symbol.includes('ETH')) icon = 'fa-brands fa-ethereum';
    else if (symbol.includes('XAU') || symbol.includes('GOLD')) icon = 'fa-coins';
    else if (symbol.includes('US30') || symbol.includes('NAS') || symbol.includes('SPX')) icon = 'fa-arrow-trend-up';

    return `
        <div class="asset-render" style="gap:${{gap}};">
            <i class="fa-solid ${{icon}}" style="font-size:${{compact ? '12px' : '20px'}}; color:var(--accent); width:${{size}}px; text-align:center;"></i>
            <div class="asset-text" style="font-size:${{fontSize}}; opacity: 0.9;">${{symbol}}</div>
        </div>
    `;
}}

function selectChartType(value) {{
    const input = document.getElementById('chart-type-input');
    if (input) input.value = value;
    
    document.querySelectorAll('.chart-option').forEach(opt => {{
        opt.classList.toggle('active', opt.dataset.value === value || opt.getAttribute('data-value') === value);
    }});
}}

function selectRagOption(value) {{
    const valStr = String(value).toLowerCase();
    const input = document.getElementById('enable-rag-input');
    if (input) input.value = valStr;
    
    document.querySelectorAll('.rag-option').forEach(opt => {{
        const optVal = String(opt.dataset.value || opt.getAttribute('data-value')).toLowerCase();
        opt.classList.toggle('active', optVal === valStr);
    }});
}}

function goToStep(next) {{
    if (next < 1 || next > 5) return;
    
    document.getElementById(`step-${{currentStep}}`).classList.remove('active');
    document.getElementById(`step-${{currentStep}}-ind`).classList.remove('active');
    
    // Update completed states for all steps
    for (let i = 1; i <= 5; i++) {{
        const ind = document.getElementById(`step-${{i}}-ind`);
        if (ind) {{
            if (i < next) {{
                ind.classList.add('completed');
            }} else {{
                ind.classList.remove('completed');
            }}
        }}
    }}
    
    currentStep = next;
    document.getElementById(`step-${{currentStep}}`).classList.add('active');
    document.getElementById(`step-${{currentStep}}-ind`).classList.add('active');
    
    document.getElementById('prev-btn').style.display = currentStep > 1 ? 'inline-flex' : 'none';
    document.getElementById('next-btn').style.display = currentStep < 5 ? 'inline-flex' : 'none';
    document.getElementById('save-btn').style.display = currentStep === 5 ? 'inline-flex' : 'none';
}}

function changeStep(delta) {{
    goToStep(currentStep + delta);
}}

function values() {{
    const data = Object.fromEntries(new FormData(form).entries());
    const numerics = ['virtual_balance','stake_amount','payout_percent','confidence_threshold','lot_size','auto_sl_atr_multiplier','auto_tp_ratio'];
    numerics.forEach(k => data[k] = Number(data[k]));
    data.enable_sounds = data.enable_sounds === 'true';
    data.enable_rag = data.enable_rag === 'true';
    data.is_configured = true;
    return data;
}}

const DEFAULT_SYMBOLS_BY_MARKET = {{
    "Forex": [
        {{ name: "EURUSD", desc: "Euro / US Dollar" }},
        {{ name: "GBPUSD", desc: "Great Britain Pound / US Dollar" }},
        {{ name: "USDJPY", desc: "US Dollar / Japanese Yen" }},
        {{ name: "AUDUSD", desc: "Australian Dollar / US Dollar" }},
        {{ name: "USDCAD", desc: "US Dollar / Canadian Dollar" }},
        {{ name: "USDCHF", desc: "US Dollar / Swiss Franc" }},
        {{ name: "NZDUSD", desc: "New Zealand Dollar / US Dollar" }},
        {{ name: "EURGBP", desc: "Euro / Great Britain Pound" }},
        {{ name: "EURJPY", desc: "Euro / Japanese Yen" }},
        {{ name: "GBPJPY", desc: "Great Britain Pound / Japanese Yen" }},
        {{ name: "EURCHF", desc: "Euro / Swiss Franc" }},
        {{ name: "CHFJPY", desc: "Swiss Franc / Japanese Yen" }},
        {{ name: "AUDJPY", desc: "Australian Dollar / Japanese Yen" }},
        {{ name: "GBPCAD", desc: "Great Britain Pound / Canadian Dollar" }}
    ],
    "Indices": [
        {{ name: "US30", desc: "Dow Jones Industrial Average" }},
        {{ name: "NAS100", desc: "Nasdaq 100" }},
        {{ name: "SPX500", desc: "S&P 500 Index" }},
        {{ name: "GER40", desc: "DAX 40 Index" }},
        {{ name: "UK100", desc: "FTSE 100 Index" }},
        {{ name: "JPN225", desc: "Nikkei 225" }}
    ],
    "Commodities": [
        {{ name: "XAUUSD", desc: "Gold / US Dollar" }},
        {{ name: "XAGUSD", desc: "Silver / US Dollar" }},
        {{ name: "USOUSD", desc: "WTI Crude Oil / US Dollar" }},
        {{ name: "UKOUSD", desc: "Brent Crude Oil / US Dollar" }}
    ],
    "Crypto": [
        {{ name: "BTCUSD", desc: "Bitcoin / US Dollar" }},
        {{ name: "ETHUSD", desc: "Ethereum / US Dollar" }},
        {{ name: "SOLUSD", desc: "Solana / US Dollar" }},
        {{ name: "XRPUSD", desc: "Ripple / US Dollar" }},
        {{ name: "ADAUSD", desc: "Cardano / US Dollar" }}
    ],
    "Acciones": [
        {{ name: "AAPL", desc: "Apple Inc." }},
        {{ name: "MSFT", desc: "Microsoft Corp." }},
        {{ name: "GOOGL", desc: "Alphabet Inc." }},
        {{ name: "AMZN", desc: "Amazon.com Inc." }},
        {{ name: "TSLA", desc: "Tesla Inc." }},
        {{ name: "NVDA", desc: "NVIDIA Corp." }}
    ]
}};

function updateSymbolsByMarketType() {{
    const marketSelect = document.querySelector('[name="market_type"]');
    const symbolSelect = document.querySelector('[name="symbol"]');
    if (!marketSelect || !symbolSelect) return;
    
    const market = marketSelect.value || "Forex";
    const symbols = DEFAULT_SYMBOLS_BY_MARKET[market] || DEFAULT_SYMBOLS_BY_MARKET["Forex"];
    
    const currentVal = symbolSelect.value || initial.symbol || "";
    
    symbolSelect.innerHTML = "";
    symbols.forEach(s => {{
        const opt = document.createElement("option");
        opt.value = s.name;
        opt.textContent = `${{s.name}} — ${{s.desc}}`;
        opt.selected = s.name === currentVal;
        symbolSelect.appendChild(opt);
    }});
    
    updateAssetPreview(symbolSelect.value);
}}

function toggleTradingMode() {{
    const mode = document.getElementById('trading-mode-select').value;
    document.getElementById('real-mode-warning').style.display = mode === 'real' ? 'block' : 'none';
    document.getElementById('real-mode-fields').style.display = mode === 'real' ? 'block' : 'none';
    // Show/hide simulation-only fields
    const simFields = document.querySelectorAll('[name="virtual_balance"], [name="stake_amount"], [name="payout_percent"]');
    simFields.forEach(f => {{
        const field = f.closest('.field');
        if (field) field.style.display = mode === 'real' ? 'none' : '';
    }});
}}

async function loadMT5Symbols() {{
    try {{
        const result = await pywebview.api.get_mt5_symbols();
        if (!result.success || !result.symbols.length) return;
        const select = document.querySelector('[name="symbol"]');
        if (!select || select.tagName !== 'SELECT') return;
        const currentVal = select.value || initial.symbol || '';
        select.innerHTML = '';
        // Group by path
        const groups = {{}};
        result.symbols.forEach(s => {{
            const parts = s.path.split('\\\\');
            const group = parts.length > 1 ? parts[0] : 'Other';
            if (!groups[group]) groups[group] = [];
            groups[group].push(s);
        }});
        for (const [group, symbols] of Object.entries(groups)) {{
            const optgroup = document.createElement('optgroup');
            optgroup.label = group;
            symbols.forEach(s => {{
                const opt = document.createElement('option');
                opt.value = s.name;
                opt.textContent = `${{s.name}} — ${{s.description}}`;
                opt.selected = s.name === currentVal;
                optgroup.appendChild(opt);
            }});
            select.appendChild(optgroup);
        }}
    }} catch (e) {{
        // Silently fail - MT5 might not be connected
    }}
}}

function showToast(message, error=false) {{
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast open' + (error ? ' error' : '');
    setTimeout(() => toast.className = 'toast', 3000);
}}

async function saveConfig() {{
    const btn = document.getElementById('save-btn');
    btn.disabled = true;
    try {{
        const result = await pywebview.api.save_config(values());
        if (!result.success) throw new Error(result.message);
        await pywebview.api.open_main();
    }} catch (e) {{
        showToast(e.message || String(e), true);
    }} finally {{
        btn.disabled = false;
    }}
}}

// ---- AI Provider Logic ----
const AI_PROVIDERS = {providers_json};
const PROVIDER_BRAND = {{
    openai:   {{ color: '#10A37F', logo: '{openai_base64}',   label: 'OpenAI',   lightBg: true }},
    azure:    {{ color: '#0078D4', logo: '{azure_base64}',   label: 'Azure OpenAI' }},
    deepseek: {{ color: '#4D6BFE', logo: '{deepseek_base64}', label: 'DeepSeek' }},
    claude:   {{ color: '#D97706', logo: '{claude_base64}',   label: 'Claude',   lightBg: true }},
    gemini:   {{ color: '#4285F4', logo: '{gemini_base64}',   label: 'Gemini' }},
    grok:     {{ color: '#E5E7EB', logo: '{grok_base64}',     label: 'Grok',     lightBg: true }},
}};

function renderProviderCards() {{
    const grid = document.getElementById('provider-grid');
    if (!grid) return;
    grid.innerHTML = '';
    for (const [key, info] of Object.entries(AI_PROVIDERS)) {{
        const brand = PROVIDER_BRAND[key] || {{ color: '#888', icon: 'fa-microchip', label: key }};
        const card = document.createElement('div');
        card.className = 'provider-card';
        card.dataset.provider = key;
        card.onclick = () => selectProvider(key);
        
        let iconContent = '';
        let iconBg = '';
        if (brand.logo) {{
            iconContent = `<img src="${{brand.logo}}" style="width: 24px; height: 24px; object-fit: contain;">`;
            if (brand.lightBg) {{
                iconBg = 'background: #f8fafc; border: 1px solid var(--border);';
            }} else {{
                iconBg = `background: ${{brand.color}}15;`;
            }}
        }} else {{
            iconContent = `<i class="fa-solid ${{brand.icon}}"></i>`;
            iconBg = `background: ${{brand.color}}20; color: ${{brand.color}};`;
        }}

        card.innerHTML = `
            <div class="provider-icon" style="${{iconBg}}">
                ${{iconContent}}
            </div>
            <div class="provider-name">${{info.name}}</div>
            <div class="provider-check"><i class="fa-solid fa-circle-check"></i></div>
        `;
        grid.appendChild(card);
    }}
}}

function selectProvider(key) {{
    document.getElementById('ai-provider-input').value = key;
    document.querySelectorAll('.provider-card').forEach(c => {{
        c.classList.toggle('selected', c.dataset.provider === key);
    }});
    renderAIFields(key);
    // Clear test result
    document.getElementById('test-result').textContent = '';
}}

function renderAIFields(provider) {{
    const container = document.getElementById('ai-fields');
    if (!container) return;
    const lang = document.getElementById('lang-input')?.value || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    const info = AI_PROVIDERS[provider] || {{}};
    const fields = info.fields || [];
    
    let html = '';
    
    if (fields.includes('api_key')) {{
        html += `
            <div class="field">
                <label data-t="field_ai_api_key">${{dict.field_ai_api_key || 'API Key'}}</label>
                <div style="position:relative;">
                    <input type="password" name="ai_api_key" id="ai-key-input" 
                           placeholder="${{dict.ai_key_placeholder || 'sk-... o tu API Key'}}" 
                           autocomplete="off"
                           style="padding-right:40px;">
                    <button type="button" onclick="toggleKeyVisibility()" 
                            style="position:absolute; right:8px; top:50%; transform:translateY(-50%); background:none; border:none; color:var(--muted); cursor:pointer; padding:4px;">
                        <i class="fa-solid fa-eye" id="key-toggle-icon"></i>
                    </button>
                </div>
            </div>
        `;
    }}
    
    if (fields.includes('endpoint')) {{
        html += `
            <div class="field">
                <label data-t="field_ai_endpoint">${{dict.field_ai_endpoint || 'Endpoint (URL)'}}</label>
                <input name="ai_endpoint" placeholder="${{dict.ai_endpoint_placeholder || 'https://tu-recurso.openai.azure.com/...'}}" autocomplete="off">
            </div>
        `;
    }}
    
    if (fields.includes('api_version')) {{
        html += `
            <div class="field">
                <label data-t="field_ai_api_version">${{dict.field_ai_api_version || 'Version API'}}</label>
                <input name="ai_api_version" value="2025-01-01-preview" autocomplete="off">
            </div>
        `;
    }}
    
    if (fields.includes('model')) {{
        const models = info.models || [];
        const options = models.map(m => `<option value="${{m}}">${{m}}</option>`).join('');
        html += `
            <div class="field">
                <label data-t="field_ai_model">${{dict.field_ai_model || 'Modelo'}}</label>
                <select name="ai_model">${{options}}</select>
            </div>
        `;
    }}
    
    container.innerHTML = html;
    
    // Restore saved API key from keyring for the selected provider
    const savedKeys = initial.ai_api_keys || {{}};
    const keyForProvider = savedKeys[provider] || (initial.ai_provider === provider ? (initial.ai_api_key || '') : '');
    if (keyForProvider && container.querySelector('[name="ai_api_key"]')) {{
        container.querySelector('[name="ai_api_key"]').value = keyForProvider;
    }}
    
    // Restore saved values for the active provider
    if (initial.ai_provider === provider) {{
        if (initial.ai_endpoint && container.querySelector('[name="ai_endpoint"]')) {{
            container.querySelector('[name="ai_endpoint"]').value = initial.ai_endpoint;
        }}
        if (initial.ai_api_version && container.querySelector('[name="ai_api_version"]')) {{
            container.querySelector('[name="ai_api_version"]').value = initial.ai_api_version;
        }}
        if (initial.ai_model && container.querySelector('[name="ai_model"]')) {{
            container.querySelector('[name="ai_model"]').value = initial.ai_model;
        }}
    }}
}}

function toggleKeyVisibility() {{
    const input = document.getElementById('ai-key-input');
    const icon = document.getElementById('key-toggle-icon');
    if (input.type === 'password') {{
        input.type = 'text';
        icon.className = 'fa-solid fa-eye-slash';
    }} else {{
        input.type = 'password';
        icon.className = 'fa-solid fa-eye';
    }}
}}

async function testAIConnection() {{
    const btn = document.getElementById('test-ai-btn');
    const result = document.getElementById('test-result');
    const lang = document.getElementById('lang-input')?.value || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    
    btn.disabled = true;
    result.textContent = dict.testing || 'Probando...';
    result.style.color = 'var(--muted)';
    
    try {{
        // Save current values first so backend can test with them
        const data = values();
        await pywebview.api.save_config(data);
        const res = await pywebview.api.test_ai_connection();
        if (res.success) {{
            result.textContent = (dict.test_success || '✅ Conexion exitosa') + (res.model ? ` (${{res.model}})` : '');
            result.style.color = '#10B981';
        }} else {{
            result.textContent = (dict.test_fail || '❌ Error') + ': ' + (res.message || 'Unknown');
            result.style.color = '#EF4444';
        }}
    }} catch (e) {{
        result.textContent = (dict.test_fail || '❌ Error') + ': ' + String(e.message || e);
        result.style.color = '#EF4444';
    }} finally {{
        btn.disabled = false;
    }}
}}

// Initialize provider cards
renderProviderCards();
selectProvider(initial.ai_provider || 'openai');

fill();
</script>
<style>
.provider-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
}}
.provider-card {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 16px 8px;
    background: var(--panel);
    border: 2px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    transition: all 0.25s ease;
    position: relative;
}}
.provider-card:hover {{
    border-color: var(--accent);
    background: var(--panel-2);
    transform: translateY(-2px);
}}
.provider-card.selected {{
    border-color: var(--accent);
    background: rgba(139, 92, 246, 0.08);
    box-shadow: 0 0 20px rgba(139, 92, 246, 0.15);
}}
.provider-icon {{
    width: 44px;
    height: 44px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    transition: transform 0.2s ease;
}}
.provider-card:hover .provider-icon {{
    transform: scale(1.1);
}}
.provider-name {{
    font-size: 11px;
    font-weight: 700;
    color: var(--strong);
    text-align: center;
    letter-spacing: 0.02em;
}}
.provider-check {{
    position: absolute;
    top: 8px;
    right: 8px;
    font-size: 14px;
    color: var(--accent);
    opacity: 0;
    transition: opacity 0.2s ease;
}}
.provider-card.selected .provider-check {{
    opacity: 1;
}}
</style>
</body>
</html>
"""

    def _main_html(self, payload: dict) -> str:
        data = json.dumps(payload, ensure_ascii=False)
        loc_json = json.dumps(LOCALIZATION_DICT, ensure_ascii=False)
        return f"""
<!DOCTYPE html>
<html lang="es">
<head>{self._head()}</head>
<body>
{self._chrome("TraderExpert v" + APP_VERSION)}
<main class="screen">
    <section class="content">
        <header class="toolbar">
            <div class="toolbar-left">
                <!-- Sleek Primary Actions -->
                <button id="action-btn" class="primary" onclick="toggleEngine()">
                    <i class="fa-solid fa-play"></i>
                    <span data-t="btn_start">Iniciar</span>
                </button>
                <button id="analyze-btn" onclick="runAnalysisNow()" data-tip-key="tip_analyze" data-tip="Realizar análisis inmediato" onmouseover="showTip(this, event)" onmouseout="hideTip()">
                    <i class="fa-solid fa-bolt"></i>
                    <span data-t="analyze">Analizar</span>
                </button>
                
                <div style="width:1px; height:20px; background:var(--border); margin:0 4px;"></div>
                
                <!-- Sleek Pill-shaped Utility Button Group -->
                <div class="btn-group">
                    <button class="icon-btn" onclick="confirmResetBalance()" data-tip-key="tip_reset" data-tip="Restablecer balance virtual" onmouseover="showTip(this, event)" onmouseout="hideTip()">
                        <i class="fa-solid fa-rotate-left"></i>
                    </button>
                    <button class="icon-btn" onclick="confirmClearHistory()" data-tip-key="tip_clear" data-tip="Limpiar historial de señales" onmouseover="showTip(this, event)" onmouseout="hideTip()">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                    <button class="icon-btn" onclick="exportData()" data-tip-key="tip_export" data-tip="Exportar historial a CSV" onmouseover="showTip(this, event)" onmouseout="hideTip()">
                        <i class="fa-solid fa-download"></i>
                    </button>
                </div>
            </div>
            <div class="toolbar-right">
                <!-- Next Analysis Timer Badge -->
                <div id="timer-badge" style="display:none; align-items:center; gap:8px; background:rgba(74, 110, 130, 0.08); padding:6px 12px; border-radius:var(--radius); border:1px solid rgba(74, 110, 130, 0.3); font-size:11px; font-weight:700; transition: all 0.3s ease; height: 36px;" data-tip-key="next_analysis" data-tip="Siguiente análisis" onmouseover="showTip(this, event)" onmouseout="hideTip()">
                    <i class="fa-solid fa-clock" id="timer-badge-icon" style="font-size:12px; color:var(--accent);"></i>
                    <span id="timer-badge-text" style="color:var(--text); font-family: monospace; font-size: 12px; font-weight:700; letter-spacing:0.05em;">--:--</span>
                </div>
                <!-- Sleek Compact Date Filter -->
                <div style="display:flex; align-items:center; gap:8px; background:var(--panel); padding:0 12px; border-radius:var(--radius); border:1px solid var(--border); height: 36px;">
                    <input type="date" id="filter-date" onchange="applyFilter()" style="height:34px; border:none; background:transparent; width:130px; font-size:11px; padding:0; line-height:34px;">
                </div>
                <!-- Compact Config Button -->
                <button onclick="pywebview.api.open_config()">
                    <i class="fa-solid fa-gear"></i>
                    <span data-t="settings">Configuracion</span>
                </button>
            </div>
        </header>
        <section class="cards" id="dashboard-cards-grid">
            <div class="card"><div class="card-label" id="balance-label" data-t="virtual_balance">Saldo virtual</div><div class="card-value" id="balance">$0.00</div></div>
            <div class="card" id="equity-card" style="display:none;"><div class="card-label" data-t="equity_label">Equity Real</div><div class="card-value" id="equity">$0.00</div></div>
            <div class="card"><div class="card-label" data-t="active_symbol">Activo</div><div class="card-value" id="active-asset">-</div></div>
            <div class="card"><div class="card-label" data-t="wins">Ganadas</div><div class="card-value" id="wins">0</div></div>
            <div class="card"><div class="card-label" data-t="losses">Perdidas</div><div class="card-value" id="losses">0</div></div>
        </section>
        <section class="signal-stage" style="margin-top:20px;">
            <div class="signal-panel" id="signal-container">
                <div class="scanning-ring"></div>
                <div class="scanning-ring"></div>
                <div class="scanning-label" data-t="scanning_market">Escaneando mercado...</div>
                <div id="signal-content">
                    <i id="signal-icon" class="signal-icon wait fa-solid fa-hand"></i>
                    <div class="signal-label" id="signal-label">ESPERAR</div>
                    <div class="signal-meta" id="signal-meta">Esperando inicio de sesion.</div>
                </div>
            </div>
            <aside class="side-panel">
                <div class="card"><div class="card-label" data-t="confidence">Confianza</div><div class="card-value" id="confidence">0%</div></div>
                <div class="card"><div class="card-label" data-t="engine_state">Estado del Motor</div><div class="card-value" id="engine-state" style="font-size:16px;">Detenido</div></div>
                <div class="card"><div class="card-label" data-t="detected_risks">Riesgos detectados</div><div class="strong" id="risks" style="margin-top:8px;font-size:13px;line-height:1.6;max-height:80px;overflow-y:auto;padding-right:4px;">-</div></div>
                <div class="card"><div class="card-label" data-t="external_context">Contexto externo</div><div class="strong" id="external-context" style="margin-top:8px;font-size:12px;max-height:120px;overflow-y:auto;padding-right:4px;">-</div></div>
            </aside>
        </section>
        <section class="history">
            <div class="history-head">
                <span data-t="history_date">Fecha</span>
                <span data-t="history_asset">Activo</span>
                <span data-t="history_signal">Senal</span>
                <span data-t="history_status">Estado</span>
                <span data-t="history_confidence">Conf.</span>
                <span data-t="history_reason">Razon del analisis</span>
                <span class="optional" data-t="history_delta">Delta</span>
            </div>
            <div id="history-body" style="max-height: 400px; min-height: 200px; overflow-y: auto;"></div>
            <div class="pagination">
                <button class="pagination-btn icon-btn" onclick="changePage(-1)" id="prev-page"><i class="fa-solid fa-chevron-left"></i></button>
                <span class="pagination-info" id="page-info">Pagina 1 de 1</span>
                <button class="pagination-btn icon-btn" onclick="changePage(1)" id="next-page"><i class="fa-solid fa-chevron-right"></i></button>
            </div>
        </section>
    </section>
</main>
<div id="tooltip" class="tooltip"></div>
<div id="chart-tooltip">
    <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; font-weight:700; margin-bottom: 2px;">
        <span id="ct-symbol" style="color:var(--text);">-</span>
        <span id="ct-direction" class="pill" style="font-size:9px; padding:2px 8px; letter-spacing: 0.05em;">UP</span>
    </div>
    <canvas id="ct-canvas" width="296" height="140"></canvas>
    <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--muted); margin-top: 2px;">
        <span id="ct-entry-wrap">Entrada: <strong id="ct-entry" style="color:var(--strong);">-</strong></span>
        <span id="ct-exit-wrap">Salida: <strong id="ct-exit" style="color:var(--strong);">-</strong></span>
    </div>
</div>
<div class="modal-overlay" id="modal-overlay">
    <div class="modal">
        <div class="modal-title" id="modal-title"><i class="fa-solid fa-circle-question"></i> Confirmar</div>
        <div class="modal-text" id="modal-text">¿Estás seguro de realizar esta acción?</div>
        <div class="modal-actions">
            <button class="modal-btn cancel" id="modal-cancel-btn" onclick="closeModal()">Cancelar</button>
            <button class="modal-btn confirm" id="modal-confirm-btn">Confirmar</button>
        </div>
    </div>
</div>
<div class="toast" id="toast"></div>
<audio id="audio-win" src="https://assets.mixkit.co/active_storage/sfx/2013/2013-preview.mp3"></audio>
<audio id="audio-signal" src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"></audio>

<script>
const LOCALIZATION = {loc_json};
let state = {data};
let currentPage = 1;
const pageSize = 10;
let filterDate = '';

function translatePage(lang) {{
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    
    // Translate standard texts
    document.querySelectorAll('[data-t]').forEach(el => {{
        const key = el.getAttribute('data-t');
        if (dict[key]) {{
            el.textContent = dict[key];
        }}
    }});
    
    // Translate tooltips
    document.querySelectorAll('[data-tip-key]').forEach(el => {{
        const key = el.getAttribute('data-tip-key');
        if (dict[key]) {{
            el.setAttribute('data-tip', dict[key]);
        }}
    }});

    // Translate window action labels (aria)
    document.querySelectorAll('[data-t-aria]').forEach(el => {{
        const key = el.getAttribute('data-t-aria');
        if (dict[key]) {{
            el.setAttribute('aria-label', dict[key]);
        }}
    }});
}}

function playSound(type) {{
    if (!state.settings?.enable_sounds) return;
    const el = document.getElementById('audio-' + type);
    if (el) {{ el.currentTime = 0; el.play().catch(() => {{}}); }}
}}

function toggleEngine() {{
    if (state.engine_running) stopEngine();
    else startEngine();
}}

async function runAnalysisNow() {{
    if (!state.engine_running) {{
        const lang = state.settings?.language || 'es';
        const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
        showToast(dict['toast_engine_stopped'] || 'El motor está detenido. Inícialo antes de analizar.', true);
        return;
    }}
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    const btn = document.getElementById('analyze-btn');
    const container = document.getElementById('signal-container');
    btn.disabled = true;
    container.classList.add('scanning');
    document.getElementById('signal-label').textContent = dict['scanning_market'] || 'ESCANEANDO...';
    
    try {{
        const result = await pywebview.api.run_analysis_now();
        if (!result.success) showToast(result.message, true);
    }} catch (e) {{
        showToast(dict['toast_connection_error'] || "Error de conexión", true);
    }} finally {{
        btn.disabled = false;
    }}
}}

async function startEngine() {{
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    const btn = document.getElementById('action-btn');
    btn.disabled = true;
    const result = await pywebview.api.start_engine();
    if (!result.success) showToast(result.message, true);
    btn.disabled = false;
}}

async function stopEngine() {{
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    const btn = document.getElementById('action-btn');
    btn.disabled = true;
    const result = await pywebview.api.stop_engine();
    if (!result.success) showToast(result.message, true);
    btn.disabled = false;
}}

async function exportData() {{
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    const res = await pywebview.api.export_csv();
    if (res.success) {{
        const blob = new Blob([res.csv], {{ type: 'text/csv' }});
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'TraderExpert_Historial.csv';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        showToast(dict['toast_export_success'] || "Historial exportado con éxito");
    }} else {{
        showToast(res.message || dict['toast_export_error'] || "Error al exportar", true);
    }}
}}

function applyFilter() {{
    filterDate = document.getElementById('filter-date').value;
    currentPage = 1;
    renderState(window.lastState);
}}

function changePage(delta) {{
    currentPage += delta;
    renderState(window.lastState);
}}

function renderState(next) {{
    if (!next) return;
    document.getElementById('signal-container').classList.remove('scanning');
    window.lastState = next;
    const oldSignals = state.signals || [];
    state = next;
    
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];

    if ((state.signals || []).length > oldSignals.length) {{
        playSound('signal');
    }}

    // Apply localization dictionary
    translatePage(lang);

    // Update MT5 Connection Badge
    const mt5Badge = document.getElementById('mt5-badge');
    const mt5Dot = document.getElementById('mt5-indicator-dot');
    const mt5Text = document.getElementById('mt5-indicator-text');
    if (mt5Badge && mt5Dot && mt5Text) {{
        if (state.mt5_connected) {{
            mt5Dot.style.color = '#10B981';
            mt5Text.textContent = 'MT5';
            mt5Text.style.color = 'var(--text)';
            mt5Badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
            mt5Badge.style.background = 'rgba(16, 185, 129, 0.08)';
        }} else {{
            mt5Dot.style.color = '#EF4444';
            mt5Text.textContent = (dict['mt5_not_connected'] || 'MT5 Sin Conexión');
            mt5Text.style.color = 'var(--muted)';
            mt5Badge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
            mt5Badge.style.background = 'rgba(239, 68, 68, 0.05)';
        }}
    }}

    // Hide timers immediately if the engine is stopped
    if (!state.engine_running) {{
        const tb = document.getElementById('timer-badge');
        if (tb) tb.style.display = 'none';
    }}

    // Filtering
    let signals = (state.signals || []).sort((a,b) => new Date(b.created_at) - new Date(a.created_at));
    if (filterDate) {{
        signals = signals.filter(s => s.created_at.startsWith(filterDate));
    }}

    // Recalculate Metrics for filtered view
    const filteredWins = signals.filter(s => s.status === 'WIN').length;
    const filteredLosses = signals.filter(s => s.status === 'LOSS').length;
    
    document.getElementById('wins').textContent = filteredWins;
    document.getElementById('losses').textContent = filteredLosses;
    
    const summary = state.summary || {{}};
    const tradingMode = state.settings?.trading_mode || 'simulation';
    const balanceLabel = document.getElementById('balance-label');
    const equityCard = document.getElementById('equity-card');

    if (tradingMode === 'real') {{
        if (balanceLabel) balanceLabel.textContent = dict['real_balance'] || 'Saldo Real';
        if (equityCard) equityCard.style.display = '';
        if (state.account_info) {{
            document.getElementById('balance').textContent = '$' + (state.account_info.balance || 0).toFixed(2);
            document.getElementById('equity').textContent = '$' + (state.account_info.equity || 0).toFixed(2);
            
            if (balanceLabel && state.account_info.server) {{
                const isDemo = state.account_info.trade_mode === 0;
                const modeStr = isDemo ? 'DEMO' : 'REAL';
                balanceLabel.innerHTML = `${{dict['real_balance'] || 'Saldo Real'}} <span style="font-size:10px; color:var(--muted); font-weight:normal; margin-left:6px;">(${{state.account_info.server}} - ${{modeStr}})</span>`;
            }}
        }} else {{
            document.getElementById('balance').textContent = '$ --';
            document.getElementById('equity').textContent = '$ --';
        }}
    }} else {{
        if (balanceLabel) balanceLabel.textContent = dict['virtual_balance'] || 'Saldo Virtual';
        if (equityCard) equityCard.style.display = 'none';
        document.getElementById('balance').textContent = '$' + (summary.balance || 0).toFixed(2);
    }}
    
    const assetEl = document.getElementById('active-asset');
    assetEl.innerHTML = renderAssetHTML(state.settings?.symbol, state.settings?.timeframe);

    const actionBtn = document.getElementById('action-btn');
    if (state.engine_running) {{
        actionBtn.classList.add('active');
        actionBtn.querySelector('i').className = 'fa-solid fa-pause';
        actionBtn.querySelector('span').textContent = dict['btn_pause'] || 'Pausar';
        document.getElementById('engine-state').textContent = dict['state_active'] || 'Activo';
        document.getElementById('engine-state').style.color = 'var(--success)';
    }} else {{
        actionBtn.classList.remove('active');
        actionBtn.querySelector('i').className = 'fa-solid fa-play';
        actionBtn.querySelector('span').textContent = dict['btn_start'] || 'Iniciar';
        document.getElementById('engine-state').textContent = dict['state_stopped'] || 'Detenido';
        document.getElementById('engine-state').style.color = 'var(--muted)';
    }}
    
    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) {{
        if (state.engine_running) {{
            analyzeBtn.disabled = false;
            analyzeBtn.style.opacity = '1';
            analyzeBtn.style.cursor = 'pointer';
            analyzeBtn.setAttribute('data-tip-key', 'tip_analyze');
            analyzeBtn.setAttribute('data-tip', dict['tip_analyze'] || 'Realizar análisis inmediato');
        }} else {{
            analyzeBtn.disabled = true;
            analyzeBtn.style.opacity = '0.4';
            analyzeBtn.style.cursor = 'not-allowed';
            analyzeBtn.setAttribute('data-tip-key', 'tip_analyze_disabled');
            analyzeBtn.setAttribute('data-tip', dict['tip_analyze_disabled'] || 'Inicia el motor para poder analizar');
        }}
    }}

    const latest = signals[0] || {{}};
    const [icon, cls, label] = signalClass(latest.direction, lang);
    const iconEl = document.getElementById('signal-icon');
    const contentEl = document.getElementById('signal-content');
    
    if (iconEl.className !== `signal-icon ${{cls}} fa-solid ${{icon}}`) {{
        contentEl.style.animation = 'none';
        contentEl.offsetHeight;
        contentEl.style.animation = 'fadeIn 0.5s ease-out';
    }}
    
    iconEl.className = `signal-icon ${{cls}} fa-solid ${{icon}}`;
    document.getElementById('signal-label').textContent = label;
    document.getElementById('confidence').textContent = Math.round((latest.confidence || 0) * 100) + '%';
    
    if (latest.reason) {{
        document.getElementById('signal-meta').textContent = latest.reason;
    }} else {{
        document.getElementById('signal-meta').textContent = dict['waiting_session'] || 'Esperando inicio de sesion.';
    }}
    
    document.getElementById('risks').textContent = (latest.risk_flags || []).join(', ') || dict['no_risks'] || 'Ninguno detectado';
    
    const ext = latest.external_context || {{}};
    const sourcesCount = (ext.sources || []).length;
    const itemsCount = (ext.items || []).length;
    
    if (sourcesCount > 0 || itemsCount > 0) {{
        const sourcesText = (ext.sources || []).map(s => '• ' + s).join('\\n');
        const itemsText = (ext.items || []).map(i => '• ' + (i.title || i)).slice(0, 5).join('\\n');
        const tooltipContent = `FUENTES CONECTADAS:\\n${{sourcesText}}\\n\\nÚLTIMOS EVENTOS:\\n${{itemsText}}${{itemsCount > 5 ? '\\n... y ' + (itemsCount - 5) + ' más' : ''}}`;

        document.getElementById('external-context').innerHTML = `
            <div style="display:flex; flex-direction:column; gap:4px; cursor:help;" 
                 data-tip="${{tooltipContent}}"
                 onmouseover="showTip(this, event)" 
                 onmouseout="hideTip()">
                <span style="color:var(--accent); font-weight:700;">${{sourcesCount}} ${{dict['connected_sources'] || 'fuentes conectadas'}}</span>
                <span class="muted">${{itemsCount}} ${{dict['events_processed'] || 'eventos/noticias procesados'}}</span>
            </div>
        `;
    }} else {{
        document.getElementById('external-context').innerHTML = `
            <div style="display:flex; align-items:center; gap:10px;">
                <span class="dim" style="font-style:italic;">${{dict['searching_events'] || 'Buscando eventos de mercado...'}}</span>
                <i class="fa-solid fa-spinner fa-spin" style="color:var(--accent); font-size:12px;"></i>
            </div>
        `;
    }}

    // Pagination
    const totalPages = Math.max(1, Math.ceil(signals.length / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;
    
    const startIdx = (currentPage - 1) * pageSize;
    const pageSignals = signals.slice(startIdx, startIdx + pageSize);
    
    const pageTemplate = dict['page_info'] || "Pagina {{page}} de {{total}}";
    document.getElementById('page-info').textContent = pageTemplate.replace('{{page}}', currentPage).replace('{{total}}', totalPages);
    document.getElementById('prev-page').disabled = currentPage === 1;
    document.getElementById('next-page').disabled = currentPage === totalPages;

    document.getElementById('history-body').innerHTML = pageSignals.map((item, idx) => {{
        const absoluteIdx = startIdx + idx;
        const d = new Date(item.created_at);
        const dateStr = d.toLocaleDateString([], {{day:'2-digit', month:'2-digit'}});
        const timeStr = d.toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit', second:'2-digit'}});
        
        let signalLabelStr = item.direction;
        if (item.direction === 'UP') signalLabelStr = dict['signal_buy'] || 'COMPRA';
        else if (item.direction === 'DOWN') signalLabelStr = dict['signal_sell'] || 'VENTA';
        else if (item.direction === 'WAIT') signalLabelStr = dict['signal_wait'] || 'ESPERAR';
        
        return `
        <div class="history-row">
            <span style="font-size:11px; white-space:nowrap; cursor:help;"
                  onmouseover="showChartTip(${{absoluteIdx}}, event)"
                  onmouseout="hideChartTip()"
                  onmousemove="moveChartTip(event)">
                <span style="color:var(--muted);">${{dateStr}}</span>
                <span style="color:var(--strong); font-weight:700; margin-left:4px;">${{timeStr}}</span>
            </span>
            <span style="cursor:help;"
                  onmouseover="showChartTip(${{absoluteIdx}}, event)"
                  onmouseout="hideChartTip()"
                  onmousemove="moveChartTip(event)">
                ${{renderAssetHTML(item.symbol || state.settings?.symbol, "", true)}}
            </span>
            <span><span class="pill ${{item.direction?.toLowerCase()}}">${{signalLabelStr}}</span></span>
            <span><span class="pill ${{item.status}}">${{item.status}}</span></span>
            <span>${{Math.round(item.confidence * 100)}}%</span>
            <span class="muted" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;padding-right:10px;" 
                  data-tip="${{item.reason || ''}}"
                  onmouseover="showTip(this, event)" onmouseout="hideTip()">${{item.reason}}</span>
            <span style="color:${{item.balance_delta >= 0 ? 'var(--success)' : 'var(--danger)'}}">${{item.balance_delta >= 0 ? '+' : ''}}${{item.balance_delta?.toFixed(2)}}</span>
        </div>
    `}}).join('') || `
        <div class="empty-history">
            <i class="fa-solid fa-folder-open"></i>
            <h3 data-t="no_signals_title">${{dict['no_signals_title'] || 'No hay señales registradas'}}</h3>
            <p data-t="no_signals_desc">${{dict['no_signals_desc'] || 'Las señales aparecerán aquí automáticamente una vez que inicies el análisis de mercado.'}}</p>
        </div>
    `;
}}

function escapeJs(str) {{
    return str.replace(/'/g, "\\'").replace(/\\n/g, "\\n");
}}

function showTip(el, e) {{
    const tip = document.getElementById('tooltip');
    const text = el.getAttribute('data-tip');
    if (!text || !tip) return;
    tip.textContent = text;
    tip.classList.add('visible');
    tip.style.left = (e.clientX + 15) + 'px';
    tip.style.top = (e.clientY + 15) + 'px';
}}
function hideTip() {{
    const tip = document.getElementById('tooltip');
    if (tip) tip.classList.remove('visible');
}}

function showChartTip(index, e) {{
    const tip = document.getElementById('chart-tooltip');
    const canvas = document.getElementById('ct-canvas');
    if (!tip || !canvas) return;

    const signals = (state.signals || []).sort((a,b) => new Date(b.created_at) - new Date(a.created_at));
    const sig = signals[index];
    if (!sig) return;

    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];

    document.getElementById('ct-symbol').textContent = `${{sig.symbol}} (${{sig.timeframe}})`;
    
    let directionLabelStr = sig.direction;
    if (sig.direction === 'UP') directionLabelStr = dict['signal_buy'] || 'COMPRA';
    else if (sig.direction === 'DOWN') directionLabelStr = dict['signal_sell'] || 'VENTA';
    else if (sig.direction === 'WAIT') directionLabelStr = dict['signal_wait'] || 'ESPERAR';

    const dirEl = document.getElementById('ct-direction');
    dirEl.textContent = directionLabelStr;
    dirEl.className = `pill ${{sig.direction?.toLowerCase()}}`;

    const entryLabelWrap = document.getElementById('ct-entry-wrap');
    if (entryLabelWrap) {{
        entryLabelWrap.innerHTML = `${{dict['tooltip_entry'] || 'Entrada'}}: <strong id="ct-entry" style="color:var(--strong);">${{sig.entry_price ? sig.entry_price.toFixed(5) : '-'}}</strong>`;
    }}
    
    const exitWrap = document.getElementById('ct-exit-wrap');
    if (sig.exit_price) {{
        exitWrap.style.display = 'block';
        exitWrap.innerHTML = `${{dict['tooltip_exit'] || 'Salida'}}: <strong id="ct-exit" style="color:var(--strong);">${{sig.exit_price.toFixed(5)}}</strong>`;
    }} else {{
        exitWrap.style.display = 'none';
    }}

    tip.classList.add('visible');
    
    // Position immediately
    let x = e.clientX + 15;
    let y = e.clientY + 15;
    const width = 320;
    const height = 210;
    if (x + width > window.innerWidth) {{
        x = e.clientX - width - 15;
    }}
    if (y + height > window.innerHeight) {{
        y = e.clientY - height - 15;
    }}
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';

    drawChart(canvas, sig, lang);
}}

function hideChartTip() {{
    const tip = document.getElementById('chart-tooltip');
    if (tip) tip.classList.remove('visible');
}}

function moveChartTip(e) {{
    const tip = document.getElementById('chart-tooltip');
    if (tip && tip.classList.contains('visible')) {{
        let x = e.clientX + 15;
        let y = e.clientY + 15;
        const width = 320;
        const height = 210;
        if (x + width > window.innerWidth) {{
            x = e.clientX - width - 15;
        }}
        if (y + height > window.innerHeight) {{
            y = e.clientY - height - 15;
        }}
        tip.style.left = x + 'px';
        tip.style.top = y + 'px';
    }}
}}

function drawChart(canvas, sig, lang) {{
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const bars = sig.history_bars || [];
    if (bars.length === 0) {{
        ctx.fillStyle = '#6B7280';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(dict['no_history_chart'] || 'Gráfico histórico no disponible', canvas.width / 2, canvas.height / 2);
        return;
    }}
    
    let prices = bars.flatMap(b => [b.high, b.low]);
    if (sig.entry_price) prices.push(sig.entry_price);
    if (sig.exit_price) prices.push(sig.exit_price);
    
    const maxPrice = Math.max(...prices);
    const minPrice = Math.min(...prices);
    
    const padTop = 15;
    const padBottom = 15;
    const chartHeight = canvas.height - padTop - padBottom;
    const priceRange = maxPrice - minPrice || 0.00001;
    
    function getPosVal(price) {{
        return padTop + chartHeight * (1 - (price - minPrice) / priceRange);
    }}
    
    // Draw background grid
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {{
        const y = padTop + (chartHeight / 4) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
    }}
    
    // Draw candlesticks
    const spacing = canvas.width / bars.length;
    const barWidth = Math.max(2, spacing - 2);
    
    bars.forEach((bar, idx) => {{
        const x = idx * spacing + spacing / 2;
        const yOpen = getPosVal(bar.open);
        const yClose = getPosVal(bar.close);
        const yHigh = getPosVal(bar.high);
        const yLow = getPosVal(bar.low);
        
        const isUp = bar.close >= bar.open;
        const color = isUp ? '#10B981' : '#EF4444';
        
        // Draw wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x, yHigh);
        ctx.lineTo(x, yLow);
        ctx.stroke();
        
        // Draw body
        ctx.fillStyle = color;
        const bodyHeight = Math.max(1.5, Math.abs(yClose - yOpen));
        ctx.fillRect(x - barWidth / 2, Math.min(yOpen, yClose), barWidth, bodyHeight);
    }});
    
    // Draw entry line
    if (sig.entry_price) {{
        const yEntry = getPosVal(sig.entry_price);
        ctx.strokeStyle = sig.direction === 'UP' ? 'rgba(16, 185, 129, 0.5)' : sig.direction === 'DOWN' ? 'rgba(239, 68, 68, 0.5)' : 'rgba(245, 158, 11, 0.5)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(0, yEntry);
        ctx.lineTo(canvas.width, yEntry);
        ctx.stroke();
        ctx.setLineDash([]);
        
        ctx.fillStyle = sig.direction === 'UP' ? '#10B981' : sig.direction === 'DOWN' ? '#EF4444' : '#F59E0B';
        ctx.font = 'bold 8px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(dict['tooltip_entry']?.toUpperCase() || 'ENTRADA', 6, yEntry - 3);
    }}
    
    // Draw exit line
    if (sig.exit_price) {{
        const yExit = getPosVal(sig.exit_price);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(0, yExit);
        ctx.lineTo(canvas.width, yExit);
        ctx.stroke();
        ctx.setLineDash([]);
        
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 8px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(dict['tooltip_exit']?.toUpperCase() || 'SALIDA', canvas.width - 6, yExit - 3);
    }}
}}
window.onmousemove = (e) => {{
    const tip = document.getElementById('tooltip');
    if (tip && tip.classList.contains('visible')) {{
        tip.style.left = (e.clientX + 15) + 'px';
        tip.style.top = (e.clientY + 15) + 'px';
    }}
}};

function renderAssetHTML(symbol, timeframe = "", compact = false) {{
    if (!symbol) return '<span style="color:var(--muted); font-size:11px;">-</span>';
    symbol = symbol.toUpperCase();
    
    const size = compact ? 12 : 24;
    const fontSize = compact ? '10px' : '14px';
    const gap = compact ? '4px' : '10px';
    const pairWidth = compact ? '22px' : '42px';
    const flagShift = compact ? 9 : 18;

    const map = {{
        'EUR': 'eu', 'USD': 'us', 'GBP': 'gb', 'JPY': 'jp', 'AUD': 'au', 'CAD': 'ca', 'CHF': 'ch', 'NZD': 'nz',
        'CNY': 'cn', 'MXN': 'mx', 'BRL': 'br', 'HKD': 'hk', 'SGD': 'sg'
    }};

    if (symbol.length === 6) {{
        const c1 = symbol.substring(0, 3);
        const c2 = symbol.substring(3, 6);
        if (map[c1] && map[c2]) {{
            return `
                <div class="asset-render" style="gap:${{gap}};">
                    <div class="flag-pair" style="width:${{pairWidth}}; height:${{size}}px;">
                        <img src="https://flagcdn.com/w80/${{map[c1]}}.png" class="flag" style="width:${{size}}px; height:${{size}}px; border-width: 1px;">
                        <img src="https://flagcdn.com/w80/${{map[c2]}}.png" class="flag" style="width:${{size}}px; height:${{size}}px; left:${{flagShift}}px; border-width: 1px;">
                    </div>
                    <div class="asset-text" style="font-size:${{fontSize}}; opacity: 0.9;">${{symbol}}</div>
                </div>
            `;
        }}
    }}
    let icon = 'fa-chart-line';
    if (symbol.includes('BTC')) icon = 'fa-brands fa-bitcoin';
    else if (symbol.includes('ETH')) icon = 'fa-brands fa-ethereum';
    else if (symbol.includes('XAU') || symbol.includes('GOLD')) icon = 'fa-coins';
    else if (symbol.includes('US30') || symbol.includes('NAS') || symbol.includes('SPX')) icon = 'fa-arrow-trend-up';

    return `
        <div class="asset-render" style="gap:${{gap}};">
            <i class="fa-solid ${{icon}}" style="font-size:${{compact ? '12px' : '20px'}}; color:var(--accent); width:${{size}}px; text-align:center;"></i>
            <div class="asset-text" style="font-size:${{fontSize}}; opacity: 0.9;">${{symbol}}</div>
        </div>
    `;
}}

function signalClass(dir, lang) {{
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    dir = String(dir || 'WAIT').toUpperCase();
    if (dir === 'UP') return ['fa-arrow-up', 'up', dict['signal_buy'] || 'COMPRA'];
    if (dir === 'DOWN') return ['fa-arrow-down', 'down', dict['signal_sell'] || 'VENTA'];
    return ['fa-hand', 'wait', dict['signal_wait'] || 'ESPERAR'];
}}

let modalCallback = null;
function openModal(title, text, confirmLabel, isDanger, callback) {{
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];

    document.getElementById('modal-title').innerHTML = `<i class="fa-solid ${{isDanger ? 'fa-triangle-exclamation' : 'fa-circle-question'}}"></i> ${{title}}`;
    document.getElementById('modal-text').textContent = text;
    
    const cancelBtn = document.getElementById('modal-cancel-btn');
    if (cancelBtn) cancelBtn.textContent = dict['modal_cancel'] || 'Cancelar';

    const btn = document.getElementById('modal-confirm-btn');
    btn.textContent = confirmLabel;
    btn.className = 'modal-btn confirm' + (isDanger ? ' danger' : '');
    modalCallback = callback;
    document.getElementById('modal-overlay').classList.add('open');
}}
function closeModal() {{
    document.getElementById('modal-overlay').classList.remove('open');
    modalCallback = null;
}}
document.getElementById('modal-confirm-btn').onclick = () => {{
    if (modalCallback) modalCallback();
    closeModal();
}};

function confirmResetBalance() {{
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    openModal(dict['modal_reset_title'] || 'Restablecer Balance', dict['modal_reset_text'] || '¿Deseas restablecer el balance virtual a su estado inicial? Esto no afectará tu historial.', dict['modal_reset_confirm'] || 'Restablecer', false, () => {{
        pywebview.api.reset_balance().then(res => {{
            if (res.success) showToast(dict['toast_balance_reset'] || 'Balance restablecido correctamente', false);
        }});
    }});
}}

function confirmClearHistory() {{
    const lang = state.settings?.language || 'es';
    const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
    openModal(dict['modal_clear_title'] || 'Limpiar Historial', dict['modal_clear_text'] || '¿Deseas eliminar todo el historial de señales? Esta acción no se puede deshacer.', dict['modal_clear_confirm'] || 'Eliminar Todo', true, () => {{
        pywebview.api.clear_history().then(res => {{
            if (res.success) showToast(dict['toast_history_cleared'] || 'Historial eliminado', false);
        }});
    }});
}}

function showToast(msg, err) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast open' + (err ? ' error' : '');
    if (err) playSound('error');
    setTimeout(() => t.className = 'toast', 4000);
}}

// Periodic status check (every 10 seconds)
setInterval(async () => {{
    try {{
        const res = await pywebview.api.get_market_status();
        
        // Update badges
        const lang = state.settings?.language || 'es';
        const dict = LOCALIZATION[lang] || LOCALIZATION['es'];

        const mt5Badge = document.getElementById('mt5-badge');
        const mt5Dot = document.getElementById('mt5-indicator-dot');
        const mt5Text = document.getElementById('mt5-indicator-text');
        if (mt5Badge && mt5Dot && mt5Text) {{
            if (res.mt5_connected) {{
                mt5Dot.style.color = '#10B981';
                mt5Text.textContent = 'MT5';
                mt5Text.style.color = 'var(--text)';
                mt5Badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                mt5Badge.style.background = 'rgba(16, 185, 129, 0.08)';
            }} else {{
                mt5Dot.style.color = '#EF4444';
                mt5Text.textContent = (dict['mt5_not_connected'] || 'MT5 Sin Conexión');
                mt5Text.style.color = 'var(--muted)';
                mt5Badge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                mt5Badge.style.background = 'rgba(239, 68, 68, 0.05)';
            }}
        }}

        // Real-time balance and equity if real trading mode is active
        if (state.settings?.trading_mode === 'real' && res.mt5_connected && res.account_info) {{
            document.getElementById('balance').textContent = '$' + (res.account_info.balance || 0).toFixed(2);
            document.getElementById('equity').textContent = '$' + (res.account_info.equity || 0).toFixed(2);
        }}
    }} catch(e) {{}}
}}, 10000);

// Dynamic 1-second countdown timer for next analysis
setInterval(() => {{
    if (!state.engine_running || !state.next_analysis_timestamp) {{
        const tb = document.getElementById('timer-badge');
        if (tb) tb.style.display = 'none';
        return;
    }}
    
    const now = Date.now() / 1000;
    const diff = state.next_analysis_timestamp - now;
    
    const timerBadge = document.getElementById('timer-badge');
    const timerText = document.getElementById('timer-badge-text');
    
    if (diff <= 0) {{
        const lang = state.settings?.language || 'es';
        const dict = LOCALIZATION[lang] || LOCALIZATION['es'];
        const textStr = dict['analyzing'] || 'Analizando...';
        if (timerBadge && timerText) {{
            timerBadge.style.display = 'inline-flex';
            timerText.textContent = textStr;
        }}
        return;
    }}
    
    // Format minutes:seconds
    const minutes = Math.floor(diff / 60);
    const seconds = Math.floor(diff % 60);
    const pad = (num) => String(num).padStart(2, '0');
    const timerStr = pad(minutes) + ':' + pad(seconds);
    
    // Update toolbar badge
    if (timerBadge && timerText) {{
        timerBadge.style.display = 'inline-flex';
        timerText.textContent = timerStr;
        
        // Premium dynamic alerts: if less than 30 seconds, pulse/alert border
        if (diff < 30) {{
            timerBadge.style.borderColor = 'rgba(239, 68, 68, 0.4)';
            timerBadge.style.background = 'rgba(239, 68, 68, 0.08)';
            const icon = document.getElementById('timer-badge-icon');
            if (icon) icon.style.color = '#EF4444';
        }} else {{
            timerBadge.style.borderColor = 'rgba(74, 110, 130, 0.3)';
            timerBadge.style.background = 'rgba(74, 110, 130, 0.08)';
            const icon = document.getElementById('timer-badge-icon');
            if (icon) icon.style.color = 'var(--accent)';
        }}
    }}
}}, 1000);

renderState(state);
</script>
</body>
</html>
"""


class WebAPI:
    def __init__(self, app, window: MainWindow):
        self._app = app
        self._window = window

    def route_after_splash(self):
        self._defer(self._app.route_after_splash)
        return {"success": True}

    def save_config(self, settings):
        return self._app.save_config(settings or {})

    def open_main(self):
        self._defer(self._app.open_main)
        return {"success": True}

    def open_config(self):
        self._defer(self._app.open_config)
        return {"success": True}

    def start_engine(self):
        return self._app.start_engine()

    def stop_engine(self):
        return self._app.stop_engine()

    def run_analysis_now(self):
        return self._app.run_analysis_now()

    def list_signals(self):
        return {"success": True, "signals": self._app.history.list_entries()}

    def get_balance_summary(self):
        return {"success": True, "summary": self._app.summary()}

    def minimize(self):
        if self._window.window:
            self._window.window.minimize()
        return {"success": True}

    def toggle_fullscreen(self):
        if self._window.window:
            self._window.window.toggle_fullscreen()
        return {"success": True}

    def reset_balance(self):
        initial_val = float(self._app.settings.get("initial_virtual_balance", 1000.0))
        self._app.settings.reset_virtual_balance(initial_val)
        self._defer(self._app.refresh_state)
        return {"success": True}

    def clear_history(self):
        self._app.history.clear()
        self._defer(self._app.refresh_state)
        return {"success": True}

    def export_csv(self):
        import csv
        import io
        entries = self._app.history.list_entries()
        output = io.StringIO()
        if not entries:
            return {"success": False, "message": "No hay datos para exportar."}
            
        writer = csv.DictWriter(output, fieldnames=["created_at", "symbol", "direction", "status", "confidence", "reason", "balance_delta"])
        writer.writeheader()
        for entry in entries:
            writer.writerow({
                "created_at": entry.get("created_at"),
                "symbol": entry.get("symbol"),
                "direction": entry.get("direction"),
                "status": entry.get("status"),
                "confidence": entry.get("confidence"),
                "reason": entry.get("reason"),
                "balance_delta": entry.get("balance_delta")
            })
        return {"success": True, "csv": output.getvalue()}

    def test_ai_connection(self):
        return self._app.test_ai_connection()

    def get_mt5_symbols(self):
        return self._app.get_mt5_symbols()

    def get_market_status(self):
        return self._app.get_market_status()

    def quit(self):
        self._defer(self._app.quit)
        return {"success": True}

    @staticmethod
    def _defer(callback, delay=0.25):
        timer = threading.Timer(delay, callback)
        timer.daemon = True
        timer.start()
