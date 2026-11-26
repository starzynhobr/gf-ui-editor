"""Exercita recuperação e timeout com Qt e WebView2 reais, em uma caixa de areia.

Uso: python harness/ui_startup_smoke.py
Requer o build da web (npm run build em web/).
"""

from __future__ import annotations

import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace


def child(out: Path, scenario: str, arguments: list[str]) -> None:
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(out / "home")
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = str(out / "appdata")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["GF_HARNESS_VISIBLE"] = "0"

    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    import webview

    from gf_ui_editor import app, single_instance, web_shell, webview_runtime
    from offscreen import window_options

    assert webview_runtime.webview2_version(), "WebView2 indisponível"
    settings_path = str(out / "settings.ini")
    app.QSettings = lambda *_: QSettings(settings_path, QSettings.Format.IniFormat)
    app.DEFAULT_UI_DIRECTORY = out / "missing" / "UI"
    if scenario == "timeout":
        app.prefs.ui_mode = "web"
    elif scenario == "healthy":
        app.__version__ = "0.8.0"
        app.prefs.remove("ui_mode")
        app.prefs.remove("web_starting")
    app.prefs.auto_update_check = False

    address = single_instance.default_address() + "-" + out.name
    acquire, send_open = single_instance.acquire, single_instance.send_open
    single_instance.acquire = lambda: acquire(address)
    single_instance.send_open = lambda path: send_open(path, address)

    create_window, start = webview.create_window, webview.start
    if scenario != "healthy":
        web_shell.WEB_DIST = out / "blank"
    opened = []

    def create(*args, **kwargs):
        window = create_window(*args, **kwargs, **window_options())
        opened.append(window)
        window.events.shown += lambda: print("WEB-SHOWN", flush=True)
        return window

    confirmed = threading.Event()
    loaded = threading.Event()

    def close_after_ready():
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if loaded.is_set() and not app.prefs.get("web_starting"):
                confirmed.set()
                break
            time.sleep(0.05)
        opened[0].destroy()

    webview.create_window = create
    if scenario == "healthy":
        def start_healthy(**kwargs):
            opened[0].events.loaded += loaded.set
            start(close_after_ready, **kwargs)

        webview.start = start_healthy

    from gf_ui_editor.whats_new import notes_need_showing

    notes_pending = notes_need_showing(app.prefs, app.__version__)
    dialogs = []

    def dismiss_warning():
        widget = QApplication.activeModalWidget()
        if isinstance(widget, app.WhatsNewDialog):
            dialogs.append("notes")
            widget.accept()
        elif isinstance(widget, QMessageBox):
            dialogs.append(widget.text())
            widget.accept()
            QApplication.instance().quit()

    show = app.EditorWindow.show

    def show_classic(window):
        assert not window._offer_web_banner, "faixa visível durante a recuperação"
        window.move(-12000, -12000)
        show(window)
        timer = QTimer(window)
        timer.timeout.connect(dismiss_warning)
        timer.start(50)

    app.EditorWindow.show = show_classic
    started = time.monotonic()

    fallback = []

    def spawn(command, *, env):
        assert command[1:] == ["-m", "gf_ui_editor", "--ui", "classic", "--web-start-failed"]
        fallback.extend(command[3:])

    app.subprocess = SimpleNamespace(Popen=spawn)
    assert app.main(["--ui", "web"] if scenario == "forced" else arguments) == 0
    assert app.prefs.ui_mode == "web"
    if scenario == "healthy":
        assert opened and confirmed.is_set() and not app.prefs.get("web_starting")
        assert app.prefs.get("ui_default_migrated")
        return
    assert app.prefs.get("web_starting")
    if scenario == "timeout":
        assert opened and time.monotonic() - started >= web_shell.WEB_START_TIMEOUT
        assert fallback
        subprocess.run([sys.executable, __file__, str(out), "fallback", *fallback], timeout=18, check=True)
        return
    assert not opened and dialogs == (["notes"] if notes_pending else []) + [
        "A interface nova não abriu da última vez. Abrimos a clássica; "
        "você pode tentar a nova de novo em Configurações → Interface."
    ]
    assert app.prefs.get("notes_seen_version") == app.__version__
    print("CLASSIC-WARNING", flush=True)


def main() -> None:
    if len(sys.argv) >= 3:
        child(Path(sys.argv[1]), sys.argv[2], sys.argv[3:])
        return

    with tempfile.TemporaryDirectory(prefix="gf-ui-startup-") as folder:
        out = Path(folder)
        (out / "blank").mkdir()
        (out / "blank" / "index.html").write_text("<body>Sem confirmação da casca</body>", encoding="utf-8")
        command = [sys.executable, __file__, str(out)]

        def run(scenario: str) -> None:
            subprocess.run([*command, scenario], timeout=55, check=True)
            print(f"{scenario}: OK", flush=True)

        run("timeout")
        run("recover")
        with subprocess.Popen([*command, "forced"], stdout=subprocess.PIPE, text=True) as process:
            lines: Queue[str] = Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            try:
                assert lines.get(timeout=15).strip() == "WEB-SHOWN"
            finally:
                process.kill()
                process.wait(timeout=10)
        print("forced: WebView2 interrompido antes da confirmação", flush=True)
        run("recover")
        run("healthy")


if __name__ == "__main__":
    main()
