"""Compare real canvas edits and XML bytes in Qt and WebView2.

Usage: python harness/canvas_edit_compare.py <new-output-directory> <game-copy>
Run with PYTHONPATH=src and npm install already done in web/.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from time import monotonic, sleep
import traceback

from canvas_compare import isolate
from offscreen import capture_window, window_options


RESOLUTION = (1024, 768)
FILES = ("MailList.xml", "Storage.xml")


def fixtures(out, game):
    from gf_ui_editor.project import Project
    from gf_ui_editor.xml_document import UIDocument

    source = out / "fixture"
    source.mkdir()
    ui = game / "UI"
    for name in FILES:
        shutil.copy2(ui / name, source / name)
        for element in UIDocument.load(ui / name).elements:
            if element.texture_name:
                texture = ui / element.texture_name
                if texture.is_file() and texture.parent == ui:
                    shutil.copy2(texture, source / texture.name)
    return tuple(Project.create(name, source, None, out / "projects", include_assets=True) for name in ("qt", "web"))


def classic(project):
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QThreadPool
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gf_ui_editor import app as editor

    app = QApplication.instance() or QApplication([])
    editor.DEFAULT_UI_DIRECTORY = project.ui_dir
    editor.prefs.game_resolution = "off"

    def fail_dialog(*args):
        raise RuntimeError(str(args[1:]))

    QMessageBox.critical = staticmethod(fail_dialog)
    window = editor.EditorWindow()
    window.resize(1500, 1000)
    window.show()
    window.project = project
    window._confirm_diff_preview = lambda: True
    view = window.view
    left = Qt.MouseButton.LeftButton
    no_button = Qt.MouseButton.NoButton
    none = Qt.KeyboardModifier.NoModifier
    shift = Qt.KeyboardModifier.ShiftModifier
    ctrl = Qt.KeyboardModifier.ControlModifier

    def stage(name, preview):
        window.open_document(project.ui_dir / name)
        window.set_game_resolution(RESOLUTION if preview else None)
        view.resetTransform()
        view.setSceneRect(QRectF(-5000, -5000, 10000, 10000))
        view.centerOn(140, 150)
        app.processEvents()

    def pos(x, y):
        point = view.mapFromScene(QPointF(x, y))
        assert view.viewport().rect().contains(point), point
        return point

    def gesture(x, y, dx=0, dy=0, *, modifiers=none):
        start = pos(x, y)
        QTest.mousePress(view.viewport(), left, modifiers, start)
        if dx or dy:
            end = start + QPoint(dx, dy)
            move = QMouseEvent(QEvent.Type.MouseMove, QPointF(end), QPointF(view.viewport().mapToGlobal(end)),
                               no_button, left, modifiers)
            app.sendEvent(view.viewport(), move)
        else:
            end = start
        QTest.mouseRelease(view.viewport(), left, modifiers, end)
        app.processEvents()

    groups = {}

    def snapshot(key):
        groups[key] = [list(element.geometry) for element in window.document.elements]

    def handle(index):
        location = window.items[index].resize_handle.scenePos()
        return location.x(), location.y()

    try:
        stage(FILES[0], False)
        snapshot("mail-open")
        gesture(48, 95)
        assert window.items[9].isSelected()
        gesture(48, 95, 13, -4, modifiers=shift)
        snapshot("move-axis")
        assert groups["move-axis"][9] == [49, 78, 32, 32]
        gesture(*handle(9), 8, 6)
        snapshot("resize")
        assert groups["resize"][9] == [49, 78, 40, 38]
        gesture(48, 136, modifiers=ctrl)
        assert {index for index, item in window.items.items() if item.isSelected()} == {9, 10}
        gesture(*handle(10), 19, 7, modifiers=shift)
        snapshot("group")
        assert groups["group"][9:11] != groups["resize"][9:11]
        window.undo_stack.undo()
        snapshot("undo-group")
        assert groups["undo-group"] == groups["resize"]
        window.undo_stack.redo()
        snapshot("redo-group")
        QTest.keyClick(view, Qt.Key.Key_Right)
        QTest.keyClick(view, Qt.Key.Key_Down, shift)
        snapshot("nudge")
        window.save_document()
        assert not window.document.is_dirty

        stage(FILES[1], True)
        window.select_element(0)
        gesture(*handle(0), -12, -6)
        snapshot("anchored-resize")
        gesture(62, 11, 60, 6)
        snapshot("anchored-move")
        window.save_document()
        assert not window.document.is_dirty
        assert groups["anchored-resize"][0][2:] == [306, 243]
        assert groups["anchored-move"][0][2:] == [1, 1]
        return groups
    finally:
        window.hide()
        window.deleteLater()
        QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents()


def web(out, page, project, expected):
    import webview
    from gf_ui_editor.web_shell import WebApi

    api = WebApi("pt_BR", False, default_ui_directory=project.ui_dir)
    api.open_project(str(project.root))
    window = webview.create_window(
        "GF UI canvas editing comparison", page.as_uri(), js_api=api,
        width=1320, height=1000, **window_options(),
    )
    api._attach(window)
    results = {}
    failures = []

    def js(expression):
        return window.evaluate_js(expression)

    def wait(expression, label):
        deadline = monotonic() + 20
        while monotonic() < deadline:
            value = js(expression)
            if value:
                return value
            sleep(0.05)
        raise TimeoutError(f"{label}: {js('canvasEdit.state().error')}")

    def async_js(expression):
        js(f"""window.editResult = null; {expression}.then(
          value => {{window.editResult = {{value: value ?? null}}}},
          error => {{window.editResult = {{error: String(error)}}}}); true""")
        result = wait("window.editResult", expression)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result.get("value")

    def cdp(method, **arguments):
        from System import Action

        pending = []
        native = window.native
        native.Invoke(Action(lambda: pending.append(native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(
            method, json.dumps(arguments),
        ))))
        if not pending[0].Wait(5000):
            raise TimeoutError(method)

    def gesture(x, y, dx=0, dy=0, *, modifiers=0):
        x, y = js(f"canvasEdit.point({x},{y})")
        cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1,
            clickCount=1, modifiers=modifiers)
        if dx or dy:
            cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x + dx, y=y + dy,
                buttons=1, modifiers=modifiers)
        cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x + dx, y=y + dy,
            button="left", buttons=0, clickCount=1, modifiers=modifiers)

    def snapshot(key):
        geometries = "canvasEdit.state().doc.elements.map(e => e.geometry)"
        try:
            wait(f"JSON.stringify({geometries}) === JSON.stringify({json.dumps(expected[key])})", key)
        except TimeoutError as error:
            actual = js(geometries)
            differences = [
                (index, before, after) for index, (before, after) in enumerate(zip(expected[key], actual))
                if before != after
            ]
            raise AssertionError(f"{key}: expected vs. actual {differences}") from error
        results[key] = True

    def handle(index):
        x, y, width, height = js(f"canvasEdit.state().doc.elements[{index}].geometry")
        return x + width, y + height

    def draw():
        try:
            if not window.events.loaded.wait(30):
                raise TimeoutError("WebView2 did not load")
            paths = [project.ui_dir / name for name in FILES]
            async_js(f"canvasEdit.open({json.dumps(str(paths[0]))}, false)")
            snapshot("mail-open")
            gesture(48, 95)
            wait("canvasEdit.state().selection[0] === 9", "click selection")
            gesture(48, 95, 13, -4, modifiers=8)
            snapshot("move-axis")
            gesture(*handle(9), 8, 6)
            snapshot("resize")
            gesture(48, 136, modifiers=2)
            wait("canvasEdit.state().selection.join(',') === '9,10'", "Control selection")
            gesture(*handle(10), 19, 7, modifiers=8)
            snapshot("group")
            async_js("canvasEdit.undo()")
            snapshot("undo-group")
            async_js("canvasEdit.redo()")
            snapshot("redo-group")
            for key, code, modifiers in (("ArrowRight", 39, 0), ("ArrowDown", 40, 8)):
                cdp("Input.dispatchKeyEvent", type="keyDown", key=key, code=key,
                    windowsVirtualKeyCode=code, modifiers=modifiers)
                cdp("Input.dispatchKeyEvent", type="keyUp", key=key, code=key,
                    windowsVirtualKeyCode=code, modifiers=modifiers)
            snapshot("nudge")
            assert capture_window(window.native.Handle.ToInt64(), out / "mail-group.png")
            assert async_js("canvasEdit.previewSave()")
            async_js("canvasEdit.save()")
            assert not js("canvasEdit.state().dirty || canvasEdit.state().canUndo")

            async_js(f"canvasEdit.open({json.dumps(str(paths[1]))}, true)")
            js("canvasEdit.select([0]); true")
            wait("canvasEdit.state().selection[0] === 0", "root selection")
            x, y, _, _ = js("canvasEdit.state().doc.preview.frame")
            gesture(x, y, -12, -6)
            snapshot("anchored-resize")
            gesture(62, 11, 60, 6)
            snapshot("anchored-move")
            assert capture_window(window.native.Handle.ToInt64(), out / "storage-root.png")
            async_js("canvasEdit.save()")
            assert not js("canvasEdit.state().dirty || canvasEdit.state().canUndo")

            # Reopen a disposable copy for the external-change and visibility checks.
            external = out / "External.xml"
            shutil.copy2(paths[0], external)
            async_js(f"canvasEdit.open({json.dumps(str(external))}, false)")
            x, y, _, _ = js("canvasEdit.state().doc.elements[10].geometry")
            hx, hy, _, _ = js("canvasEdit.state().doc.elements[9].geometry")
            js("canvasEdit.setHidden([9], true); true")
            gesture(hx + 6, hy + 6)
            assert 9 not in js("canvasEdit.state().selection")
            js("canvasEdit.setHidden([9], false); canvasEdit.select([]); true")
            gesture(hx + 6, hy + 6)
            wait("canvasEdit.state().selection[0] === 9", "unhidden control")
            gesture(x + 8, y + 6, modifiers=8)
            wait("canvasEdit.state().selection.join(',') === '9,10'", "Shift selection")
            js("canvasEdit.setHidden([9], true); canvasEdit.setLocked([10], true); canvasEdit.setIsolated(10); true")
            gesture(x + 8, y + 6, 12, 6)
            assert not js("canvasEdit.state().dirty")
            js("canvasEdit.setLocked([10], false); true")
            gesture(x + 8, y + 6, 12, 6)
            wait("canvasEdit.state().dirty", "unlocked isolated control")
            async_js("canvasEdit.undo()")
            assert not js("canvasEdit.state().dirty")
            async_js("canvasEdit.redo()")
            assert js("canvasEdit.state().dirty")
            js("window.confirmCalls = 0; window.confirm = () => ++window.confirmCalls > 1; true")
            data = external.read_bytes()
            external.write_bytes(data + b"\n")
            wait("window.confirmCalls === 1", "external edit prompt")
            assert js("canvasEdit.state().dirty")
            external.write_bytes(data + b"\n\n")
            wait("window.confirmCalls === 2 && !canvasEdit.state().dirty", "external edit accepted")
            changed = data.replace(b'WindowLeft="37"', b'WindowLeft="39"', 1)
            assert changed != data
            external.write_bytes(changed)
            wait(f"canvasEdit.state().doc.elements[10].geometry[0] === {x + 2}", "clean external reload")
            gesture(-10, y - 10, x + 25, 20)
            wait("canvasEdit.state().selection.includes(10)", "marquee selection")
            results["external-reload-and-visibility"] = True
        except Exception:
            failures.append(traceback.format_exc())
        finally:
            window.destroy()

    webview.start(draw, gui="edgechromium", storage_path=str(out / "webview"), private_mode=False)
    if failures:
        raise RuntimeError(failures[0])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("game_copy", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    game = args.game_copy.resolve(strict=True)
    if not (game / "UI").is_dir() or not all((game / "UI" / name).is_file() for name in FILES):
        raise SystemExit(f"Missing UI fixtures in {game}")
    out.mkdir(parents=True, exist_ok=False)
    isolate(out)
    here = Path(__file__).resolve().parent
    build = out / "web-build"
    subprocess.run(["node", str(here / "canvas_compare.mjs"), str(build)], check=True)
    qt_project, web_project = fixtures(out, game)
    steps = web(out, build / "harness" / "canvas_compare.html", web_project, classic(qt_project))

    summary = {"steps": steps, "files": {}}
    for name in FILES:
        qt = (qt_project.ui_dir / name).read_bytes()
        current = (web_project.ui_dir / name).read_bytes()
        original = (game / "UI" / name).read_bytes()
        assert qt == current and qt != original, name
        for project in (qt_project, web_project):
            history = project.history(project.ui_dir / name)
            assert len(history) == 1 and history[0].read_bytes() == original
        summary["files"][name] = {"bytes": len(qt), "sha256": sha256(qt).hexdigest(), "exact_match": True}
    result = json.dumps(summary, indent=2)
    (out / "log.json").write_text(result, encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
