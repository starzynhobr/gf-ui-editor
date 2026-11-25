"""Compare the real Qt canvas and the Vite CanvasView in WebView2.

Run from the repository with PYTHONPATH=src and npm install already done in web/.
The default source is the disposable game copy created by harness/run.ps1.
Each execution gets its own settings, WebView2 profile and image output.
"""

from __future__ import annotations

import argparse
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import struct
import tempfile
from time import monotonic, sleep
import traceback

from PIL import Image, ImageChops


FILES = ("BasicChar", "Storage", "MailList", "Menu")
PREVIEW_SIZE = (1024, 768)
PIXEL_TOLERANCE = 12
MAX_TEXTURE_DIFFERENCE = 0.01
MAX_PREVIEW_DIFFERENCE = 0.025


def isolate(out: Path) -> None:
    home = out / "home"
    (home / "Documents").mkdir(parents=True)
    os.environ.update(
        HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "AppData"),
        LOCALAPPDATA=str(home / "LocalAppData"), QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="1",
    )
    import PySide6.QtCore as QtCore

    QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, str(out / "settings"))

    class IsolatedQSettings(QtCore.QSettings):
        def __init__(self, *args, **kwargs):
            if args and isinstance(args[0], str) and not (len(args) > 1 and isinstance(args[1], QtCore.QSettings.Format)):
                super().__init__(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, *args, **kwargs)
            else:
                super().__init__(*args, **kwargs)

    QtCore.QSettings = IsolatedQSettings
    assert "HKEY" not in IsolatedQSettings("Local", "GF UI Editor").fileName()


def classic(out: Path, game: Path) -> list[dict]:
    from PySide6.QtCore import QPoint, QRectF, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gf_ui_editor import app as editor
    from gf_ui_editor.canvas_document import describe_document

    editor.DEFAULT_UI_DIRECTORY = game / "UI"
    assert out in editor.PROJECTS_ROOT.parents
    app = QApplication.instance() or QApplication([])

    def fail_dialog(*args):
        raise RuntimeError(str(args[1:]))

    QMessageBox.critical = staticmethod(fail_dialog)
    window = editor.EditorWindow()
    window.resize(1540, 1060)
    window.show()
    window.set_background_mode("none")
    window.game_drawn_action.setChecked(False)
    window.outlines_action.setChecked(False)
    window.labels_action.setChecked(False)
    view = window.view
    view.setFixedSize(1240, 920)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    cases = []
    try:
        for name in FILES:
            path = game / "UI" / f"{name}.xml"
            window.open_document(path)
            until = monotonic() + 20
            while window._textures_pending and monotonic() < until:
                app.processEvents()
                sleep(0.025)
            if window._textures_pending:
                raise TimeoutError(f"Qt textures: {name}")
            variants = [(False, False), (True, False)]
            if name == "BasicChar":
                variants.append((True, True))
            for preview, background in variants:
                window.set_text_mode("game" if preview else "off")
                window.set_game_resolution(PREVIEW_SIZE if preview else None)
                window.set_background_mode("builtin" if background else "none")
                doc = describe_document(path, PREVIEW_SIZE)
                x, y, width, height = doc["preview"]["screen"] if preview else doc["bounds"]
                width, height = min(1210, int(width) + 40), min(890, int(height) + 40)
                view.resetTransform()
                view.setSceneRect(QRectF(x - 5000, y - 5000, width + 10000, height + 10000))
                view.centerOn(x - 20 + view.viewport().width() / 2, y - 20 + view.viewport().height() / 2)
                app.processEvents()
                origin = view.mapToScene(QPoint(0, 0))
                key = f"{name}-{'preview' if preview else 'textures'}"
                if background:
                    key += "-background"
                shot = view.viewport().grab()
                if not shot.copy(0, 0, width, height).save(str(out / f"{key}-qt.png")):
                    raise RuntimeError(f"Qt screenshot failed: {key}")
                cases.append({
                    "key": key, "path": str(path), "preview": preview, "background": background,
                    "frame": (round(origin.x()), round(origin.y()), width, height),
                    "missing_qt": sorted(name.lower() for name in window.texture_cache.missing),
                })
    finally:
        window.close()
    return cases


def dds_samples(directory: Path) -> list[Path]:
    """Every root DDS, plus one example of each additional pixel layout in subdirectories."""
    files = sorted(directory.glob("*.dds"))

    def layout(path: Path) -> bytes:
        with path.open("rb") as handle:
            return handle.read(108)[80:108]

    layouts = {layout(path) for path in files}
    for path in directory.rglob("*.dds"):
        if path.parent == directory:
            continue
        header = layout(path)
        if len(header) == struct.calcsize("<I4sIIIII") and header not in layouts:
            layouts.add(header)
            files.append(path)
    return files


def web(out: Path, page: Path, cases: list[dict], samples: list[Path], large_xml: Path) -> tuple[list[str], dict]:
    import webview
    from gf_ui_editor.web_shell import WebApi

    api = WebApi("pt_BR", False)
    window = webview.create_window("GF UI canvas comparison", page.as_uri(), js_api=api, width=1320, height=1000)
    api._attach(window)
    api._attach_canvas_assets()
    failures = []
    hashes = []
    checks = {}

    def wait_for_js(expression: str, label: str):
        window.evaluate_js(
            f"window.canvasCompareResult = null; {expression}.then("
            "value => {window.canvasCompareResult = {value}}, "
            "error => {window.canvasCompareResult = {error: String(error)}}); true"
        )
        end = monotonic() + 30
        while monotonic() < end:
            result = window.evaluate_js("window.canvasCompareResult")
            if result:
                if "error" in result:
                    raise RuntimeError(result["error"])
                return result["value"]
            sleep(0.1)
        raise TimeoutError(label)

    def capture() -> None:
        try:
            if not window.events.loaded.wait(30):
                raise TimeoutError("WebView2 did not load the harness")
            for case in cases:
                args = json.dumps([case["path"], case["preview"], case["background"]])
                result = wait_for_js(f"canvasCompare.open(...{args})", case["key"])
                case["missing_web"] = result["missing"]
                url = window.evaluate_js(f"canvasCompare.capture(...{json.dumps(case['frame'])})")
                encoded = url.split(",", 1)[1]
                (out / f"{case['key']}-web.png").write_bytes(base64.b64decode(encoded))
            bases = {folder: api.asset_base(str(folder / "fixture.xml")) for folder in {file.parent for file in samples}}
            files = [(bases[file.parent], file.name) for file in samples]
            hashes.extend(wait_for_js(f"canvasCompare.ddsHashes({json.dumps(files)})", "DDS decoder"))
            start = monotonic()
            large = wait_for_js(f"canvasCompare.open({json.dumps(str(large_xml))}, false, false)", large_xml.name)
            checks["large_xml"] = dict(
                file=large_xml.name, **large, open_ms=round((monotonic() - start) * 1000),
                pan_draw_p95_ms=window.evaluate_js("canvasCompare.panDrawTime()"),
            )

            fixture = out / "live-texture"
            fixture.mkdir()
            xml = fixture / "Fixture.xml"
            xml.write_text(
                '<Root_Node><BaseWndProperty WindowID="1" WindowHeight="96" WindowWidth="96">'
                '<BackGroundMap BGmap="Sample.dds"><NorUV NorUVLeft="0" NorUVTop="0" '
                'NorUVWidth="16" NorUVHeight="16"/></BackGroundMap></BaseWndProperty></Root_Node>',
                encoding="ascii",
            )
            dds = fixture / "Sample.dds"
            Image.new("RGBA", (16, 16), "red").save(dds)
            wait_for_js(f"canvasCompare.open({json.dumps(str(xml))}, false, false)", "texture fixture")
            checks["controls"] = wait_for_js("canvasCompare.checkControls()", "canvas controls")
            before = window.evaluate_js("canvasCompare.pixel(4, 4)")
            if before != [255, 0, 0, 255]:
                raise RuntimeError(f"Texture fixture did not load: {before}")
            replacement = fixture / "replacement.dds"
            Image.new("RGBA", (16, 16), "blue").save(replacement)
            replacement.replace(dds)
            deadline = monotonic() + 8
            while monotonic() < deadline:
                if window.evaluate_js("canvasCompare.pixel(4, 4)") == [0, 0, 255, 255]:
                    checks["texture_invalidation"] = True
                    break
                sleep(0.15)
            else:
                raise TimeoutError("DDS change was not redrawn")
        except Exception:
            failures.append(traceback.format_exc())
        finally:
            window.destroy()

    webview.start(capture, gui="edgechromium", storage_path=str(out / "webview"), private_mode=False)
    if failures:
        raise RuntimeError(failures[0])
    return hashes, checks


def compare(out: Path, case: dict) -> bool:
    key = case["key"]
    qt = Image.open(out / f"{key}-qt.png").convert("RGB")
    web_image = Image.open(out / f"{key}-web.png").convert("RGB")
    assert qt.size == web_image.size, key
    delta = ImageChops.difference(qt, web_image)
    red, green, blue = delta.split()
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    fraction = sum(maximum.histogram()[PIXEL_TOLERANCE + 1:]) / (qt.width * qt.height)
    combined = Image.new("RGB", (qt.width * 3, qt.height))
    combined.paste(qt, (0, 0))
    combined.paste(web_image, (qt.width, 0))
    combined.paste(delta.point(lambda value: min(255, value * 4)), (qt.width * 2, 0))
    combined.save(out / f"{key}-comparison.png")
    threshold = MAX_PREVIEW_DIFFERENCE if case["preview"] else MAX_TEXTURE_DIFFERENCE
    ok = fraction <= threshold and set(case["missing_web"]) == set(case["missing_qt"])
    case.update(fraction=fraction, threshold=threshold, passed=ok)
    print(f"{key}: {'PASS' if ok else 'FAIL'} ({fraction:.3%}, limit {threshold:.1%})", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path(tempfile.gettempdir()) / "gf-ui-harness-codex")
    work = parser.parse_args().work.resolve()
    game = work / "pristine"
    if not all((game / "UI" / f"{name}.xml").is_file() for name in FILES):
        parser.error("Run harness/run.ps1 to create the pristine game copy first.")
    out = Path(tempfile.mkdtemp(prefix="canvas-compare-", dir=work))
    print(out, flush=True)
    isolate(out)
    source = Path(__file__).resolve().parent
    build = out / "build"
    subprocess.run(["node", str(source / "canvas_compare.mjs"), str(build)], check=True)
    cases = classic(out, game)
    from gf_ui_editor.texture_cache import open_dds_rgba
    samples = dds_samples(game / "UI")
    large_xml = max((game / "UI").glob("*.xml"), key=lambda path: path.stat().st_size)
    hashes, checks = web(out, build / "harness" / "canvas_compare.html", cases, samples, large_xml)
    differing = [str(path.relative_to(game / "UI"))
                 for path, decoded in zip(samples, hashes, strict=True)
                 if sha256(open_dds_rgba(path).tobytes()).hexdigest() != decoded]
    print(f"DDS: {len(samples) - len(differing)}/{len(samples)} match Pillow RGBA", flush=True)
    results = [compare(out, case) for case in cases]
    report = {"dds": {"files": len(samples), "differing": differing}, "comparisons": cases, "checks": checks}
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if all(results) and not differing else 1


if __name__ == "__main__":
    raise SystemExit(main())
