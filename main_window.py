from __future__ import annotations

import base64
import json
import logging
import threading
import re
from pathlib import Path

import webview

from app_metadata import APP_VERSION
from app_paths import resource_path

logger = logging.getLogger(__name__)
webview.settings["ALLOW_FILE_URLS"] = True


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
.step { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; gap: 10px; }
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
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 12px; }

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
        <button class="icon-btn" onclick="pywebview.api.minimize()" aria-label="Minimizar"><i class="fa-solid fa-minus"></i></button>
        <button class="icon-btn" onclick="pywebview.api.toggle_fullscreen()" aria-label="Pantalla Completa"><i class="fa-solid fa-expand"></i></button>
        <button class="icon-btn danger" onclick="pywebview.api.quit()" aria-label="Salir"><i class="fa-solid fa-xmark"></i></button>
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
                <div class="card-label">Configuracion</div>
                <h1 style="margin:4px 0 0;color:var(--strong);font-size:22px;">Personaliza tu experiencia</h1>
            </div>
        </div>

        <div class="stepper">
            <div class="step active" id="step-1-ind"><div class="step-circle">1</div><div class="step-label">Conexion</div></div>
            <div class="step" id="step-2-ind"><div class="step-circle">2</div><div class="step-label">Mercado</div></div>
            <div class="step" id="step-3-ind"><div class="step-circle">3</div><div class="step-label">Simulacion</div></div>
            <div class="step" id="step-4-ind"><div class="step-circle">4</div><div class="step-label">Estrategia</div></div>
        </div>

        <form id="config-form">
            <!-- STEP 1: CONEXION -->
            <div class="step-content active" id="step-1">
                <section class="form-section">
                    <h2>Terminal MT5</h2>
                    <div class="field"><label>Ruta MT5 (Opcional)</label><input name="mt5_path" placeholder="C:\\Program Files\\MetaTrader 5\\terminal64.exe"></div>
                    <div class="field"><label>Cuenta</label><input name="mt5_account" placeholder="5043420806"></div>
                    <div class="field"><label>Contraseña</label><input type="password" name="mt5_password" placeholder="••••••••"></div>
                    <div class="field"><label>Servidor</label><input name="mt5_server" placeholder="MetaQuotes-Demo"></div>
                </section>
            </div>

            <!-- STEP 2: MERCADO -->
            <div class="step-content" id="step-2">
                <section class="form-section">
                    <h2>Configuracion de Mercado</h2>
                    <div class="field"><label>Tipo de mercado</label>
                        <select name="market_type">
                            <option value="Forex">🌐 Forex</option>
                            <option value="Indices">📊 Indices</option>
                            <option value="Commodities">🥇 Commodities</option>
                            <option value="Crypto">₿ Crypto</option>
                            <option value="Acciones">🏢 Acciones</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>Activo (Símbolo)</label>
                        <div style="display:flex; align-items:center; gap:12px;">
                            <input name="symbol" list="symbols" placeholder="EURUSD" oninput="updateAssetPreview(this.value)" style="flex:1;">
                            <div id="asset-preview" style="background:var(--panel-2); padding:0 16px; border-radius:var(--radius); border:1px solid var(--border); min-width:140px; height:44px; display:flex; align-items:center; justify-content:center;">-</div>
                        </div>
                    </div>
                    <datalist id="symbols">
                        <option value="EURUSD"><option value="GBPUSD"><option value="USDJPY"><option value="XAUUSD">
                        <option value="US500"><option value="NAS100"><option value="BTCUSD">
                    </datalist>
                    <div class="field"><label>Temporalidad</label>
                        <select name="timeframe">
                            <option>M1</option><option>M2</option><option>M5</option><option>M15</option><option>M30</option><option>H1</option>
                        </select>
                    </div>
                    <div class="field"><label>Tipo de Gráfico</label>
                        <select name="chart_type">
                            <option value="candles">🕯️ Velas</option>
                            <option value="line">📈 Línea</option>
                            <option value="bars">📊 Barras</option>
                        </select>
                    </div>
                </section>
            </div>

            <!-- STEP 3: SIMULACION -->
            <div class="step-content" id="step-3">
                <section class="form-section">
                    <h2>Parámetros y Sonido</h2>
                    <div class="grid" style="grid-template-columns: 1fr 1fr;">
                        <div class="field"><label>Capital Virtual</label><input type="number" name="virtual_balance" step="0.01"></div>
                        <div class="field"><label>Monto por Señal</label><input type="number" name="stake_amount" step="0.01"></div>
                    </div>
                    <div class="grid" style="grid-template-columns: 1fr 1fr;">
                        <div class="field"><label>Payout %</label><input type="number" name="payout_percent" step="0.01"></div>
                        <div class="field"><label>Confianza Mínima</label><input type="number" name="confidence_threshold" step="0.01" min="0.5" max="0.99"></div>
                    </div>
                    <div class="grid" style="grid-template-columns: 1fr 1fr;">
                        <div class="field"><label>Horizonte Predicción (min)</label><input type="number" name="prediction_horizon_minutes" min="1"></div>
                        <div class="field"><label>Intervalo Análisis (min)</label><input type="number" name="analysis_interval_minutes" min="1"></div>
                    </div>
                    <div class="field"><label>Sonidos de Alerta</label>
                        <select name="enable_sounds">
                            <option value="true">🔊 Activado</option>
                            <option value="false">🔇 Desactivado</option>
                        </select>
                    </div>
                </section>
            </div>
            <!-- STEP 4: ESTRATEGIA / RAG -->
            <div class="step-content" id="step-4">
                <section class="form-section">
                    <h2>Estrategia e Inteligencia (RAG)</h2>
                    <div class="field">
                        <label>Instrucciones de Estrategia (Prompt)</label>
                        <textarea name="strategy_prompt" style="width:100%; height:120px; padding:12px; border-radius:var(--radius); border:1px solid var(--border); background:var(--panel); color:var(--strong); font-family:inherit; resize:vertical;"></textarea>
                    </div>
                    <div class="field">
                        <label>Carpeta de Conocimiento (RAG)</label>
                        <input name="rag_directory" placeholder="Ej: rag_knowledge">
                    </div>
                    <div class="field">
                        <label>Idioma de Respuesta (IA)</label>
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
                        <label>Uso de RAG / Entrenamiento</label>
                        <select name="enable_rag">
                            <option value="true">✅ Activado</option>
                            <option value="false">❌ Desactivado</option>
                        </select>
                    </div>
                </section>
            </div>
        </form>
    </section>
    <section class="actions">
        <button onclick="pywebview.api.open_main()">
            <i class="fa-solid fa-house"></i>
            <span>Volver al Inicio</span>
        </button>
        <div style="flex:1;"></div>
        <button id="prev-btn" style="display:none;" onclick="changeStep(-1)">
            <i class="fa-solid fa-chevron-left"></i>
            <span>Anterior</span>
        </button>
        <button id="next-btn" class="primary" onclick="changeStep(1)">
            <span>Siguiente</span>
            <i class="fa-solid fa-chevron-right"></i>
        </button>
        <button id="save-btn" class="primary" style="display:none;" onclick="saveConfig()">
            <i class="fa-solid fa-check"></i>
            <span>Guardar e Iniciar</span>
        </button>
    </section>
</main>
<div class="toast" id="toast"></div>
<script>
const initial = {s};
let currentStep = 1;
const form = document.getElementById('config-form');

function fill() {{
    for (const [key, value] of Object.entries(initial)) {{
        const field = form.elements[key];
        if (field) {{
            if (typeof value === 'boolean') field.value = String(value);
            else field.value = value ?? '';
            if (key === 'language') setLanguage(value || 'es');
        }}
    }}
    updateAssetPreview(initial.symbol);
}}

function setLanguage(lang) {{
    document.getElementById('lang-input').value = lang;
    document.querySelectorAll('.lang-option').forEach(opt => {{
        opt.classList.toggle('active', opt.dataset.lang === lang);
    }});
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

function changeStep(delta) {{
    const next = currentStep + delta;
    if (next < 1 || next > 4) return;
    
    document.getElementById(`step-${{currentStep}}`).classList.remove('active');
    document.getElementById(`step-${{currentStep}}-ind`).classList.remove('active');
    if (delta > 0) document.getElementById(`step-${{currentStep}}-ind`).classList.add('completed');
    
    currentStep = next;
    document.getElementById(`step-${{currentStep}}`).classList.add('active');
    document.getElementById(`step-${{currentStep}}-ind`).classList.add('active');
    
    document.getElementById('prev-btn').style.display = currentStep > 1 ? 'inline-flex' : 'none';
    document.getElementById('next-btn').style.display = currentStep < 4 ? 'inline-flex' : 'none';
    document.getElementById('save-btn').style.display = currentStep === 4 ? 'inline-flex' : 'none';
}}

function values() {{
    const data = Object.fromEntries(new FormData(form).entries());
    const numerics = ['virtual_balance','stake_amount','payout_percent','confidence_threshold'];
    numerics.forEach(k => data[k] = Number(data[k]));
    data.enable_sounds = data.enable_sounds === 'true';
    data.enable_rag = data.enable_rag === 'true';
    data.is_configured = true;
    return data;
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
fill();
</script>
</body>
</html>
"""

    def _main_html(self, payload: dict) -> str:
        data = json.dumps(payload, ensure_ascii=False)
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
                <button id="action-btn" class="primary" onclick="toggleEngine()">
                    <i class="fa-solid fa-play"></i>
                    <span>Iniciar</span>
                </button>
                <button id="analyze-btn" onclick="runAnalysisNow()">
                    <i class="fa-solid fa-bolt"></i>
                    <span>Analizar ahora</span>
                </button>
                <div style="width:1px; height:24px; background:var(--border); margin:0 8px;"></div>
                <button class="icon-btn" onclick="confirmResetBalance()" onmouseenter="showTooltip(event, 'Restablecer balance virtual')" onmouseleave="hideTooltip()">
                    <i class="fa-solid fa-rotate-left"></i>
                </button>
                <button class="icon-btn" onclick="confirmClearHistory()" onmouseenter="showTooltip(event, 'Limpiar historial de señales')" onmouseleave="hideTooltip()">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
                <button class="icon-btn" onclick="exportData()" onmouseenter="showTooltip(event, 'Exportar historial a CSV')" onmouseleave="hideTooltip()">
                    <i class="fa-solid fa-download"></i>
                </button>
            </div>
            <div class="toolbar-right">
                <div style="display:flex; align-items:center; gap:8px; background:var(--panel); padding:4px 16px; border-radius:var(--radius); border:1px solid var(--border);">
                    <input type="date" id="filter-date" onchange="applyFilter()" style="height:32px; border:none; background:transparent; width:130px; font-size:12px; padding:0;">
                </div>
                <button onclick="pywebview.api.open_config()">
                    <i class="fa-solid fa-gear"></i>
                    <span>Configuracion</span>
                </button>
            </div>
        </header>
        <section class="cards">
            <div class="card"><div class="card-label">Saldo virtual</div><div class="card-value" id="balance">$0.00</div></div>
            <div class="card"><div class="card-label">Activo</div><div class="card-value" id="active-asset">-</div></div>
            <div class="card"><div class="card-label">Ganadas</div><div class="card-value" id="wins">0</div></div>
            <div class="card"><div class="card-label">Perdidas</div><div class="card-value" id="losses">0</div></div>
        </section>
        <section class="signal-stage" style="margin-top:20px;">
            <div class="signal-panel" id="signal-container">
                <div class="scanning-ring"></div>
                <div class="scanning-ring"></div>
                <div class="scanning-label">Escaneando mercado...</div>
                <div id="signal-content">
                    <i id="signal-icon" class="signal-icon wait fa-solid fa-hand"></i>
                    <div class="signal-label" id="signal-label">ESPERAR</div>
                    <div class="signal-meta" id="signal-meta">Esperando inicio de sesion.</div>
                </div>
            </div>
            <aside class="side-panel">
                <div class="card"><div class="card-label">Confianza</div><div class="card-value" id="confidence">0%</div></div>
                <div class="card"><div class="card-label">Estado del Motor</div><div class="card-value" id="engine-state" style="font-size:16px;">Detenido</div></div>
                <div class="card"><div class="card-label">Riesgos detectados</div><div class="strong" id="risks" style="margin-top:8px;font-size:13px;line-height:1.6;max-height:80px;overflow-y:auto;padding-right:4px;">-</div></div>
                <div class="card"><div class="card-label">Contexto externo</div><div class="strong" id="external-context" style="margin-top:8px;font-size:12px;max-height:120px;overflow-y:auto;padding-right:4px;">-</div></div>
            </aside>
        </section>
        <section class="history">
            <div class="history-head"><span>Fecha</span><span>Activo</span><span>Senal</span><span>Estado</span><span>Conf.</span><span>Razon del analisis</span><span class="optional">Delta</span></div>
            <div id="history-body" style="max-height: 400px; min-height: 200px; overflow-y: auto;"></div>
            <div class="pagination">
                <button class="pagination-btn icon-btn" onclick="changePage(-1)" id="prev-page"><i class="fa-solid fa-chevron-left"></i></button>
                <span class="pagination-info" id="page-info">Pagina 1 de 1</span>
                <button class="pagination-btn icon-btn" onclick="changePage(1)" id="next-page"><i class="fa-solid fa-chevron-right"></i></button>
            </div>
        </section>
    </section>
</main>
<div id="tooltip"></div>
<div class="modal-overlay" id="modal-overlay">
    <div class="modal">
        <div class="modal-title" id="modal-title"><i class="fa-solid fa-circle-question"></i> Confirmar</div>
        <div class="modal-text" id="modal-text">¿Estás seguro de realizar esta acción?</div>
        <div class="modal-actions">
            <button class="modal-btn cancel" onclick="closeModal()">Cancelar</button>
            <button class="modal-btn confirm" id="modal-confirm-btn">Confirmar</button>
        </div>
    </div>
</div>
<div class="toast" id="toast"></div>
<audio id="audio-win" src="https://assets.mixkit.co/active_storage/sfx/2013/2013-preview.mp3"></audio>
<audio id="audio-signal" src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"></audio>

<script>
let state = {data};
let currentPage = 1;
const pageSize = 10;
let filterDate = '';

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
    const btn = document.getElementById('analyze-btn');
    const container = document.getElementById('signal-container');
    btn.disabled = true;
    container.classList.add('scanning');
    document.getElementById('signal-label').textContent = 'ESCANEANDO...';
    
    try {{
        const result = await pywebview.api.run_analysis_now();
        if (!result.success) showToast(result.message, true);
    }} catch (e) {{
        showToast("Error de conexión", true);
    }} finally {{
        btn.disabled = false;
        // Scanning class will be removed by renderState when signals update
    }}
}}

async function startEngine() {{
    const btn = document.getElementById('action-btn');
    btn.disabled = true;
    const result = await pywebview.api.start_engine();
    if (!result.success) showToast(result.message, true);
    btn.disabled = false;
}}

async function stopEngine() {{
    const btn = document.getElementById('action-btn');
    btn.disabled = true;
    const result = await pywebview.api.stop_engine();
    if (!result.success) showToast(result.message, true);
    btn.disabled = false;
}}

async function exportData() {{
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
        showToast("Historial exportado con éxito");
    }} else {{
        showToast(res.message || "Error al exportar", true);
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
    
    if ((state.signals || []).length > oldSignals.length) {{
        playSound('signal');
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
    document.getElementById('balance').textContent = '$' + (summary.balance || 0).toFixed(2);
    
    const assetEl = document.getElementById('active-asset');
    assetEl.innerHTML = renderAssetHTML(state.settings?.symbol, state.settings?.timeframe);

    const actionBtn = document.getElementById('action-btn');
    if (state.engine_running) {{
        actionBtn.classList.add('active');
        actionBtn.querySelector('i').className = 'fa-solid fa-pause';
        actionBtn.querySelector('span').textContent = 'Pausar';
        document.getElementById('engine-state').textContent = 'Activo';
        document.getElementById('engine-state').style.color = 'var(--success)';
    }} else {{
        actionBtn.classList.remove('active');
        actionBtn.querySelector('i').className = 'fa-solid fa-play';
        actionBtn.querySelector('span').textContent = 'Iniciar';
        document.getElementById('engine-state').textContent = 'Detenido';
        document.getElementById('engine-state').style.color = 'var(--muted)';
    }}

    const latest = signals[0] || {{}};
    const [icon, cls, label] = signalClass(latest.direction);
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
    document.getElementById('signal-meta').textContent = latest.reason || 'Esperando analisis.';
    document.getElementById('risks').textContent = (latest.risk_flags || []).join(', ') || 'Ninguno detectado';
    
    const ext = latest.external_context || {{}};
    const sourcesCount = (ext.sources || []).length;
    const itemsCount = (ext.items || []).length;
    
    if (sourcesCount > 0 || itemsCount > 0) {{
        const sourcesText = (ext.sources || []).map(s => '• ' + s).join('\\n');
        const itemsText = (ext.items || []).map(i => '• ' + (i.title || i)).slice(0, 5).join('\\n');
        const tooltipContent = `FUENTES CONECTADAS:\\n${{sourcesText}}\\n\\nÚLTIMOS EVENTOS:\\n${{itemsText}}${{itemsCount > 5 ? '\\n... y ' + (itemsCount - 5) + ' más' : ''}}`;
        const safeTooltip = tooltipContent.replace(/'/g, "\\'").replace(/\n/g, "\\\\n");

        document.getElementById('external-context').innerHTML = `
            <div style="display:flex; flex-direction:column; gap:4px; cursor:help;" 
                 onmouseover="showTooltip(event, '${{safeTooltip}}')" 
                 onmouseout="hideTooltip()">
                <span style="color:var(--accent); font-weight:700;">${{sourcesCount}} fuentes conectadas</span>
                <span class="muted">${{itemsCount}} eventos/noticias procesados</span>
            </div>
        `;
    }} else {{
        document.getElementById('external-context').innerHTML = `
            <div style="display:flex; align-items:center; gap:10px;">
                <span class="dim" style="font-style:italic;">Buscando eventos de mercado...</span>
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
    
    document.getElementById('page-info').textContent = `Pagina ${{currentPage}} de ${{totalPages}}`;
    document.getElementById('prev-page').disabled = currentPage === 1;
    document.getElementById('next-page').disabled = currentPage === totalPages;

    document.getElementById('history-body').innerHTML = pageSignals.map(item => {{
        const d = new Date(item.created_at);
        const dateStr = d.toLocaleDateString([], {{day:'2-digit', month:'2-digit'}});
        const timeStr = d.toLocaleTimeString([], {{hour:'2-digit', minute:'2-digit', second:'2-digit'}});
        return `
        <div class="history-row">
            <span style="font-size:11px; white-space:nowrap;">
                <span style="color:var(--muted);">${{dateStr}}</span>
                <span style="color:var(--strong); font-weight:700; margin-left:4px;">${{timeStr}}</span>
            </span>
            <span>${{renderAssetHTML(item.symbol || state.settings?.symbol, "", true)}}</span>
            <span><span class="pill ${{item.direction?.toLowerCase()}}">${{item.direction}}</span></span>
            <span><span class="pill ${{item.status}}">${{item.status}}</span></span>
            <span>${{Math.round(item.confidence * 100)}}%</span>
            <span class="muted" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;padding-right:10px;" onmouseover="showTooltip(event, '${{escapeJs(item.reason || '')}}')" onmouseout="hideTooltip()">${{item.reason}}</span>
            <span style="color:${{item.balance_delta >= 0 ? 'var(--success)' : 'var(--danger)'}}">${{item.balance_delta >= 0 ? '+' : ''}}${{item.balance_delta?.toFixed(2)}}</span>
        </div>
    `}}).join('') || `
        <div class="empty-history">
            <i class="fa-solid fa-folder-open"></i>
            <h3>No hay señales registradas</h3>
            <p>Las señales aparecerán aquí automáticamente una vez que inicies el análisis de mercado.</p>
        </div>
    `;
}}

function escapeJs(str) {{
    return str.replace(/'/g, "\\'").replace(/\n/g, "\\\\n");
}}

function showTooltip(e, text) {{
    const el = document.getElementById('tooltip');
    if (!text || !el) return;
    el.textContent = text;
    el.classList.add('visible');
    const x = e.clientX + 15;
    const y = e.clientY + 15;
    el.style.left = x + 'px';
    el.style.top = y + 'px';
}}
function hideTooltip() {{
    const el = document.getElementById('tooltip');
    if (el) el.classList.remove('visible');
}}
window.onmousemove = (e) => {{
    const el = document.getElementById('tooltip');
    if (el && el.classList.contains('visible')) {{
        el.style.left = (e.clientX + 15) + 'px';
        el.style.top = (e.clientY + 15) + 'px';
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

function signalClass(dir) {{
    dir = String(dir || 'WAIT').toUpperCase();
    if (dir === 'UP') return ['fa-arrow-up', 'up', 'COMPRA'];
    if (dir === 'DOWN') return ['fa-arrow-down', 'down', 'VENTA'];
    return ['fa-hand', 'wait', 'ESPERAR'];
}}

let modalCallback = null;
function openModal(title, text, confirmLabel, isDanger, callback) {{
    document.getElementById('modal-title').innerHTML = `<i class="fa-solid ${{isDanger ? 'fa-triangle-exclamation' : 'fa-circle-question'}}"></i> ${{title}}`;
    document.getElementById('modal-text').textContent = text;
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
    openModal('Restablecer Balance', '¿Deseas restablecer el balance virtual a su estado inicial? Esto no afectará tu historial.', 'Restablecer', false, () => {{
        pywebview.api.reset_balance().then(res => {{
            if (res.success) showToast('Balance restablecido correctamente', false);
        }});
    }});
}}

function confirmClearHistory() {{
    openModal('Limpiar Historial', '¿Deseas eliminar todo el historial de señales? Esta acción no se puede deshacer.', 'Eliminar Todo', true, () => {{
        pywebview.api.clear_history().then(res => {{
            if (res.success) showToast('Historial eliminado', false);
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

    def quit(self):
        self._defer(self._app.quit)
        return {"success": True}

    @staticmethod
    def _defer(callback):
        timer = threading.Timer(0.05, callback)
        timer.daemon = True
        timer.start()
