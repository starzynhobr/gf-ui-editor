"""Screenshots of the web interface for the project page on the site (1440x900, dark theme, pt-BR).

Usage: python harness/site_screenshots.py <output_dir> <game_copy> [<sandbox_dir>]

- Same sandbox as harness/web_smoke.py: HOME/USERPROFILE/APPDATA point into <sandbox_dir>
  (default: <output_dir>/../site-prints-sandbox) and QSettings goes to an INI there, before
  the editor is imported. The registry is never touched.
- The game copy is copied again to SITE_GAME_DIR (default C:\\Games\\Grand Fantasia Violet)
  so that any path that shows up is a neutral one. That folder must not exist or be empty;
  it is removed at the end. The real game is never touched.
- The window stays off screen and is captured with PrintWindow (harness/offscreen.py).
- Before every capture the page text is checked for the sandbox path and the Windows user
  name; a capture that would leak one of them fails the run.
- Needs the front build (`npm run build` in web/).
"""
from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

OUT = Path(sys.argv[1]).resolve()
PRISTINE = Path(sys.argv[2]).resolve()
SANDBOX = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else OUT.parent / "site-prints-sandbox"
GAME = Path(os.environ.get("SITE_GAME_DIR", r"C:\Games\Grand Fantasia Violet"))
SIZE = (1440, 900)
if not (PRISTINE / "UI").is_dir():
    raise SystemExit(f"Game copy not found in {PRISTINE}.")
MARKER = GAME / ".site-screenshots"  # a copy left by an earlier run may be wiped
if GAME.exists() and any(GAME.iterdir()) and not MARKER.exists():
    raise SystemExit(f"{GAME} is not empty; choose another SITE_GAME_DIR.")
RAW = SANDBOX / "raw"  # untouched captures and the log
for folder in (SANDBOX,):
    if folder.exists():
        shutil.rmtree(folder)
(SANDBOX / "home" / "Documents").mkdir(parents=True)
RAW.mkdir(parents=True)
OUT.mkdir(parents=True, exist_ok=True)
os.environ["USERPROFILE"] = os.environ["HOME"] = str(SANDBOX / "home")
os.environ["APPDATA"] = str(SANDBOX / "home" / "AppData")
GAME.mkdir(parents=True, exist_ok=True)
MARKER.touch()
subprocess.run(["robocopy", str(PRISTINE), str(GAME), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/MT:16"], check=False)

import PySide6.QtCore as QtCore  # noqa: E402

QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, str(SANDBOX / "settings"))


class _IsolatedQSettings(QtCore.QSettings):
    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], str) and not (len(args) > 1 and isinstance(args[1], QtCore.QSettings.Format)):
            super().__init__(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, *args, **kwargs)
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _IsolatedQSettings
assert "HKEY" not in _IsolatedQSettings("Local", "GF UI Editor").fileName()

from gf_ui_editor import app as app_module, project as project_module, remote_manifest, updater, web_shell  # noqa: E402

assert str(SANDBOX) in str(project_module.PROJECTS_ROOT), project_module.PROJECTS_ROOT
assert "HKEY" not in app_module.QSettings("Local", "GF UI Editor").fileName()
app_module.DEFAULT_UI_DIRECTORY = GAME / "UI"
remote_manifest.fetch = lambda *args, **kwargs: None


def _offline(url: str):
    raise OSError(f"offline: {url}")


updater._request = _offline
prefs = app_module.prefs
prefs.game_dir = str(GAME)
prefs.ui_mode = "web"  # 0.8.0 ships with the new interface as the default
prefs.text_mode = "game"
prefs.canvas_ids = False
prefs.set("web_theme", "dark")

PROJECT = "STZ-UI"
INSPECTOR_XML, INSPECTOR_ID = os.environ.get("SITE_INSPECTOR", "Inventory.xml:5002").split(":")
PALETTE_QUERY = os.environ.get("SITE_PALETTE", "")
from gf_ui_editor import __version__ as VERSION  # noqa: E402  (real bundled notes, spotlight included)
prefs.set("notes_seen_version", VERSION)


class ShotsApi(web_shell.WebApi):
    def whats_new_state(self) -> dict:
        return {"version": VERSION, "auto_open": False, "pill": False}


api = ShotsApi("pt_BR", False, prefs, app_module.DEFAULT_UI_DIRECTORY, None)
api._dialogs = lambda *args: None
import webview  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offscreen import capture_window, window_options  # noqa: E402

window = webview.create_window(
    web_shell.APP_TITLE, web_shell._start_url(False), js_api=api, width=SIZE[0], height=SIZE[1], min_size=(1024, 680),
    background_color="#111318", **window_options(),
)
api._attach(window)

HELPERS = r"""
window.__s = window.__s || {
  q: (s) => document.querySelector(s),
  all: (s) => Array.from(document.querySelectorAll(s)),
  text: (s) => { const e = s ? document.querySelector(s) : document.body; return e ? e.innerText : null },
  click: (s) => { const e = document.querySelector(s); if (!e) return false; e.click(); return true },
  clickText: (text, scope) => {
    const root = scope ? document.querySelector(scope) : document;
    const el = Array.from(root.querySelectorAll('button, [role=button], [role=menuitem]')).find((b) => b.innerText.trim().includes(text));
    if (!el) return false; el.click(); return true
  },
  setValue: (s, v) => {
    const e = document.querySelector(s); if (!e) return false;
    const proto = e.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, v);
    e.dispatchEvent(new Event(e.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); return true
  },
  key: (key, opts) => { window.dispatchEvent(new KeyboardEvent('keydown', Object.assign({ key, bubbles: true }, opts || {}))); return true },
};
true
"""
# Toasts and the hover tip are transient: never in a site capture.
# The sandbox game copy is not the official UI, so the "UI oficial: não guardada" chip is hidden too.
CLEAN_CSS = "[data-sonner-toaster], .gf-tooltip { display: none !important; } [data-testid=official-chip] { visibility: hidden !important; }"
LOG: list[dict] = []
FAILED: list[str] = []
_USER = getpass.getuser()
SECRETS = [str(SANDBOX), str(SANDBOX).replace("\\", "/"), "\\Users\\", "/Users/", f"\\{_USER}\\", f"/{_USER}/", "AppData"]


def log(kind: str, **data) -> None:
    entry = {"kind": kind, **data}
    LOG.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def js(code: str):
    window.evaluate_js(HELPERS)
    return window.evaluate_js(code)


def wait(code: str, timeout: float = 20.0, what: str = ""):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = js(code)
        except Exception:  # noqa: BLE001 - the page may be reloading
            value = None
        if value:
            return value
        time.sleep(0.15)
    log("timeout", what=what or code)
    FAILED.append(f"timeout: {what or code}")
    return None


def _hwnd() -> int:
    try:
        return int(window.native.Handle.ToInt64())
    except Exception:  # noqa: BLE001
        import ctypes
        return ctypes.windll.user32.FindWindowW(None, web_shell.APP_TITLE)


def _fit_client() -> None:
    """Resizes the window so the page (client area) is exactly 1440x900 CSS px."""
    for _ in range(3):
        inner = js("[window.innerWidth, window.innerHeight]") or [0, 0]
        if list(inner) == list(SIZE):
            return
        width, height = window.width + SIZE[0] - inner[0], window.height + SIZE[1] - inner[1]
        window.resize(width, height)
        time.sleep(0.6)
    log("size", inner=js("[window.innerWidth, window.innerHeight]"))


def _leaks() -> list[str]:
    text = js("document.body.innerText + ' ' + Array.from(document.querySelectorAll('input, textarea')).map((e) => e.value).join(' ')") or ""
    lowered = text.lower()
    return [secret for secret in SECRETS if secret.lower() in lowered]


def shot(name: str, settle: float = 0.6) -> Path:
    js("(() => { if (!document.getElementById('site-clean')) { const s = document.createElement('style'); s.id = 'site-clean';"
       f" s.textContent = {json.dumps(CLEAN_CSS)}; document.head.append(s) }} return true }})()")
    time.sleep(settle)
    leaks = _leaks()
    if leaks:
        FAILED.append(f"{name}: personal data on screen")
        log("leak", name=name, found=leaks)
    raw = RAW / f"{name}.png"
    if not capture_window(_hwnd(), raw):
        FAILED.append(f"capture {name}")
        return raw
    from PIL import Image

    image = Image.open(raw).convert("RGB")
    if image.size != SIZE:  # DPI scaling: capture is larger, reduce with Lanczos
        image = image.resize(SIZE, Image.Resampling.LANCZOS)
    path = OUT / f"{name}.png"
    image.save(path, optimize=True)
    log("shot", name=name, raw=list(Image.open(raw).size), path=str(path))
    return path


def choose(label: str, value: str) -> None:
    selector = json.dumps(f'.gf-canvas-toolbar select[aria-label="{label}"]')
    js(f"__s.setValue({selector}, {json.dumps(value)})")


def open_xml(name: str) -> None:
    js("__s.key('1', { ctrlKey: true })")
    wait("!!__s.q('[data-testid=files-panel] [data-file]')", 10, "file list")
    js(f"__s.setValue('[data-testid=files-panel] input', {json.dumps(name.split('.')[0])})")
    wait(f"!!__s.q('[data-section=all] [data-file=\"{name}\"]')", 10, f"{name} listed")
    js(f"__s.click('[data-section=all] [data-file=\"{name}\"]')")
    wait(f"(__s.text('[data-testid=breadcrumb]') || '').includes({json.dumps(name)})", 10, f"{name} open")
    wait("!!__s.q('[data-testid=center] canvas')", 20, "canvas")
    js("__s.setValue('[data-testid=files-panel] input', '')")
    time.sleep(2.0)  # textures decode in the worker
    resolution = MODE["resolution"]
    current = "(__s.q('.gf-canvas-toolbar select[aria-label=\"Tela\"]') || {}).value"
    # The toolbar may re-apply the previous screen once the XML loads: check again after it settles.
    for _ in range(4):
        if js(current) == resolution:
            break
        wait("!__s.q('.gf-canvas-toolbar select[aria-label=\"Tela\"]').disabled", 8, "toolbar ready")
        choose("Tela", resolution)
        time.sleep(1.5)
    else:
        FAILED.append(f"game screen {resolution} for {name}")
    js("__s.click('[data-testid=canvas-fit]')")
    time.sleep(0.6)


def select_element(window_id: str) -> None:
    js("__s.key('3', { ctrlKey: true })")
    wait("!!__s.q('[data-testid=tree-row]')", 10, "element tree")
    js("__s.setValue('[data-testid=element-tree] input', '')")
    index = js(
        "(() => { const r = __s.all('[data-testid=tree-row]').find((row) => row.innerText.split(/\\s+/).includes(%s));"
        " return r ? r.dataset.index : null })()" % json.dumps(window_id)
    )
    if index is None:
        FAILED.append(f"element {window_id} not found")
        return
    js(f"__s.click('[data-testid=tree-row][data-index=\"{index}\"]')")
    wait("!!__s.q('input[name=geometry-x]')", 5, "properties panel")
    time.sleep(0.5)


def clear_selection() -> None:
    js("__s.key('Escape')")
    time.sleep(0.3)


def palette(query: str = "") -> None:
    js("__s.key('k', { ctrlKey: true })")
    wait("!!__s.q('[data-testid=command-input]')", 5, "palette")
    if query:
        js(f"__s.setValue('[data-testid=command-input]', {json.dumps(query)})")
    time.sleep(0.8)


def close_palette() -> None:
    js("__s.q('[data-testid=command-input]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))")
    wait("!__s.q('[data-testid=command-palette]')", 5, "palette closed")


def open_settings() -> None:
    js("__s.click('[data-testid=side-rail] button[aria-label=\"Configurações\"]')")
    wait("!!__s.q('[role=menu]')", 5, "gear menu")
    js("__s.clickText('Configurações…', '[role=menu]')")
    wait("!!__s.q('[data-testid=settings]')", 5, "settings")


def close_settings() -> None:
    js("__s.click('[data-testid=settings-close]')")
    wait("!__s.q('[data-testid=settings]')", 5, "settings closed")


def set_theme(key: str) -> None:
    open_settings()
    wait("!!__s.q('[data-setting=web_theme]')", 5, "theme picker")
    js(f"__s.click('[data-setting=web_theme] [data-value={key}]')")
    close_settings()
    wait(f"document.documentElement.dataset.theme === '{key}'", 5, f"theme {key}")
    time.sleep(0.6)


# ---- script -----------------------------------------------------------------------------

def create_project() -> None:
    wait("!!__s.q('[data-testid=home]')", 30, "home")
    js("__s.clickText('Novo projeto', '[data-testid=home]')")
    wait("!!__s.q('input[name=project-name]')", 10, "new project dialog")
    wait("__s.q('select[name=project-source]') && __s.q('select[name=project-source]').options.length > 2", 10, "sources")
    js(f"__s.setValue('input[name=project-name]', {json.dumps(PROJECT)})")
    time.sleep(0.5)
    js("__s.click('[data-testid=create-project]')")
    wait("!!__s.q('[data-testid=files-panel] [data-file]')", 240, "project created")
    time.sleep(1.0)


def save_official_ui() -> None:
    """Stores the official UI (no "não guardada" banner or chip); dismisses the banner if it can't."""
    deadline = time.time() + 10
    while not js("!!__s.q('[data-testid=reference-banner]')"):
        if time.time() > deadline:
            return
        time.sleep(0.2)
    js("__s.clickText('Guardar UI oficial', '[data-testid=reference-banner]')")
    if wait("!!__s.q('[data-testid=official-save]')", 5, "official dialog"):
        js("__s.click('[data-testid=official-save]')")
        deadline = time.time() + 30  # a game copy that isn't the official UI never gets there
        while time.time() < deadline and "Pronto" not in (js("__s.text('[data-testid=official-save]')") or ""):
            time.sleep(0.3)
        log("official", saved="Pronto" in (js("__s.text('[data-testid=official-save]')") or ""))
        js("__s.clickText('Fechar', '[role=dialog]')")
        wait("!__s.q('[data-testid=official-dialog]')", 5, "official dialog closed")
    if js("!!__s.q('[data-testid=reference-banner]')"):
        js("__s.q('[data-testid=reference-banner] button[aria-label]').click()")
    wait("!__s.q('[data-testid=reference-banner]')", 5, "banner gone")


def canvas_mode(resolution: str, background: str = "builtin") -> None:
    """Game screen for the next XML: "off" or one of the toolbar presets (e.g. "1280x720")."""
    MODE["resolution"] = resolution
    prefs.background_mode = background


MODE = {"resolution": "game"}


def scenario() -> None:
    _fit_client()
    create_project()
    save_official_ui()

    # 1. Game texts on the Guild window (no game screen, like the classic capture).
    canvas_mode("off")
    open_xml("Fellowship_family.xml")
    js("__s.key('3', { ctrlKey: true })")
    time.sleep(1.0)
    shot("textos-do-jogo")

    # 2. Texts tab: search across data/Translate.
    js("__s.key('4', { ctrlKey: true })")
    wait("!!__s.q('[data-testid=texts-page]')", 5, "texts page")
    js("__s.setValue('input[name=texts-search]', 'Guild')")
    wait("!!__s.q('[data-testid=text-row]')", 30, "text results")
    time.sleep(1.0)
    shot("aba-textos")
    js("__s.setValue('input[name=texts-search]', '')")

    # 3. HUD layers over the game background.
    canvas_mode("1280x720")
    open_xml("Menu.xml")
    choose("Camadas", "default")
    wait("!!__s.q('[data-section=layers] [data-file]')", 15, "HUD layers")
    time.sleep(2.5)
    js("__s.click('[data-testid=canvas-fit]')")
    time.sleep(1.0)
    shot("camadas-hud")
    choose("Camadas", "clear")
    wait("!__s.q('[data-section=layers]')", 8, "layers cleared")

    # 4. Element tree + properties panel, a selected element.
    canvas_mode("off")
    open_xml(INSPECTOR_XML)
    select_element(INSPECTOR_ID)
    shot("elementos-inspector")

    # 5. DDS atlas from the properties panel, whole atlas in view.
    if js("(() => { const b = __s.q('[data-testid=open-atlas]'); return !!b && !b.disabled })()"):
        js("__s.click('[data-testid=open-atlas]')")
        wait("!!__s.q('[data-testid=atlas-surface]')", 10, "atlas")
        time.sleep(1.0)
        js("__s.clickText('Atlas inteiro', '[data-testid=atlas-side]')")
        time.sleep(1.5)
        shot("atlas-dds")
        js("__s.click('.gf-atlas-close')")
        wait("!__s.q('[data-testid=atlas-surface]')", 5, "atlas closed")
    else:
        FAILED.append("atlas button disabled")

    # 6. XML code next to the canvas (Ctrl+U) on the Guild window.
    open_xml("Fellowship_family.xml")
    select_element("5400")  # "Deixar", on the left: stays in view next to the code panel
    js("__s.key('u', { ctrlKey: true })")
    wait("!!__s.q('[data-testid=source-panel] .cm-content')", 8, "source panel")
    time.sleep(0.8)
    js("__s.click('[data-testid=canvas-fit]')")
    shot("codigo-xml", 1.0)
    js("__s.key('u', { ctrlKey: true })")
    wait("!__s.q('[data-testid=source-panel]')", 5, "source closed")

    # 7. Ctrl+K over the canvas.
    palette(PALETTE_QUERY)
    shot("busca-ctrl-k")
    close_palette()

    # 8. Themes: the same screen in the 5 themes, cut into vertical strips side by side.
    select_element("5100")
    strips = []
    for key in THEMES:
        set_theme(key)
        strips.append(shot(f"tema-{key}", 0.8))
    set_theme("dark")
    montage(strips, OUT / "temas.png")
    open_settings()
    time.sleep(0.6)
    shot("configuracoes-geral")
    close_settings()

    # 9. Export to several resolutions.
    clear_selection()
    js("__s.click('[data-testid=export-menu]')")
    wait("!!__s.q('[role=menu]')", 5, "export menu")
    js("__s.clickText('Exportar para várias resoluções', '[role=menu]')")
    wait("__s.all('[data-testid^=resolution-card-]').length >= 2", 30, "resolution previews")
    time.sleep(3.0)
    shot("varias-resolucoes")
    js("__s.key('Escape')")
    js("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    wait("!__s.q('[data-testid^=resolution-card-]')", 5, "resolutions closed")

    # 10. What's new with the "Interface nova" card.
    js("__s.click('[data-testid=side-rail] button[aria-label=\"Configurações\"]')")
    wait("!!__s.q('[role=menu]')", 5, "gear menu")
    js("__s.clickText('Novidades', '[role=menu]')")
    wait("!!__s.q('[data-testid=notes-spotlight]')", 8, "Interface nova card")
    time.sleep(1.2)
    shot("novidades")
    js("__s.key('Escape')")
    wait("!__s.q('[data-testid=whats-new]')", 5, "whats new closed")

    # 11. Home with the project (Continuar card).
    js("__s.click('[data-testid=topbar] button')")
    wait("!!__s.q('[data-testid=home-project-row]')", 10, "home with project")
    wait("(() => { const r = __s.q('[data-testid=home-project-row] [data-size]'); return r && /\\d/.test(r.dataset.size) })()", 30, "project size")
    time.sleep(1.5)
    shot("tela-inicial")


THEMES = {"dark": "Escuro", "midnight": "Meia-noite", "light": "Claro", "cappuccino": "Cappuccino", "rosa": "Rosa"}


def montage(paths: list[Path], target: Path) -> None:
    """Same screen in each theme, cut into equal vertical strips side by side, each with its name."""
    from PIL import Image, ImageDraw, ImageFont

    images = [Image.open(path).convert("RGB") for path in paths]
    width, height = images[0].size
    result = Image.new("RGB", (width, height))
    step = width / len(images)
    for index, image in enumerate(images):
        left, right = round(index * step), round((index + 1) * step)
        result.paste(image.crop((left, 0, right, height)), (left, 0))
    draw = ImageDraw.Draw(result)
    for index in range(1, len(images)):
        x = round(index * step)
        draw.line([(x, 0), (x, height)], fill=(0, 0, 0), width=2)
    try:
        font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuisb.ttf"), 20)
    except OSError:
        font = ImageFont.load_default()
    for index, name in enumerate(THEMES.values()):
        center = round((index + 0.5) * step)
        box = draw.textbbox((0, 0), name, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        top = height - 96
        draw.rounded_rectangle((center - w / 2 - 16, top - 10, center + w / 2 + 16, top + h + 14), 18,
                               fill=(124, 77, 255), outline=(255, 255, 255), width=2)
        draw.text((center - w / 2 - box[0], top - box[1] + 2), name, font=font, fill=(255, 255, 255))
    result.save(target, optimize=True)
    log("montage", path=str(target))


FINISHED = threading.Event()


def driver() -> None:
    try:
        scenario()
    except Exception:  # noqa: BLE001
        log("error", traceback=traceback.format_exc())
        FAILED.append("exception")
    finally:
        (RAW / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
        FINISHED.set()
        window.destroy()


try:
    webview.start(driver, gui="edgechromium", private_mode=True, storage_path=str(SANDBOX / "webview"))
finally:
    for _ in range(10):  # background scans may still hold a file for a moment
        shutil.rmtree(GAME, ignore_errors=True)
        if not GAME.exists():
            break
        time.sleep(1.0)
if not FINISHED.is_set():
    FAILED.append("window closed before the script finished")
log("summary", failed=FAILED)
sys.exit(1 if FAILED else 0)
