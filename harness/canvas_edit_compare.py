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
import zlib

from canvas_compare import isolate
from offscreen import capture_window, window_options


RESOLUTION = (1024, 768)
FILES = ("MailList.xml", "Storage.xml")
ATLAS_INDEX = 4  # MailList WindowID 2050, with all four button states.
ATLAS_NORMAL = (539, 81, 69, 16)
ATLAS_FOCUS = (539, 93, 60, 20)


def fixtures(out, game, light=False):
    from gf_ui_editor.project import Project, convert_to_light
    from gf_ui_editor.game_texts import TEXT_INDEX
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
    game_fixture = out / "game"
    index = game_fixture / TEXT_INDEX
    index.parent.mkdir(parents=True)
    index.write_text("637|Original harness label|\n", encoding="ascii")
    projects = tuple(Project.create(name, source, game_fixture, out / "projects", include_assets=True) for name in ("qt", "web"))
    if light:
        rows = []
        for path in source.iterdir():
            data = path.read_bytes()
            rows.append(f"UI/{path.name}|{len(data)}|{zlib.crc32(data):08X}|0|0|")
        (game_fixture / "GameDataFileList.txt").write_text("\n".join(rows), encoding="ascii")
        for project in projects:
            convert_to_light(project)
            assert not any(project.ui_dir.iterdir())
    return projects


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

        assert QThreadPool.globalInstance().waitForDone(5000)
        window._apply_loaded_textures()
        window.select_element(ATLAS_INDEX)
        window.open_selected_atlas()
        atlas = window.atlas_dialog
        assert atlas is not None
        atlas.edit_button.click()
        atlas.resize_element.setChecked(True)
        for state, values in (("NorUV", ATLAS_NORMAL), ("FocusUV", ATLAS_FOCUS)):
            atlas.state_combo.setCurrentIndex(atlas.state_combo.findData(state))
            for field, value in zip((atlas.left_spin, atlas.top_spin, atlas.width_spin, atlas.height_spin), values):
                field.setValue(value)
        atlas.apply_button.click()
        snapshot("atlas")
        window.undo_stack.undo()
        snapshot("atlas-undo")
        window.undo_stack.redo()
        snapshot("atlas-redo")
        atlas.close()
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
        diagnostic = js("""({
            error: canvasEdit.state().error || document.querySelector('.gf-atlas-dialog [role=alert]')?.textContent,
            crop: [...document.querySelectorAll('.gf-atlas-fields input')].map(field => field.value),
            editing: document.querySelector('.gf-atlas-surface')?.dataset.editing,
            cut: (() => { const box = document.querySelector('.gf-atlas-cut')?.getBoundingClientRect(); return box && [box.x, box.y, box.width, box.height] })(),
            hit: (() => { const box = document.querySelector('.gf-atlas-cut')?.getBoundingClientRect(); return box && document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2)?.className })(),
        })""")
        raise TimeoutError(f"{label}: {diagnostic}")

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

    def drag_at(x, y, dx=0, dy=0, *, modifiers=0, button="left", clicks=1):
        buttons = {"left": 1, "middle": 4}[button]
        cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, buttons=buttons,
            clickCount=clicks, modifiers=modifiers)
        if dx or dy:
            cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x + dx, y=y + dy,
                buttons=buttons, modifiers=modifiers)
        cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x + dx, y=y + dy,
            button=button, buttons=0, clickCount=clicks, modifiers=modifiers)

    def stable(expression, frames=3):
        """Value of `expression` once it stays the same for `frames` animation frames.

        The atlas view settles after mounting (ResizeObserver -> fit) and React paints a pan on a
        later frame than the pointer event, so a single read can see a view that is still moving.
        """
        return async_js(f"""new Promise((resolve, reject) => {{
            let last = null, same = 0, count = 0
            const tick = () => {{
                const value = JSON.stringify({expression})
                same = value === last ? same + 1 : 0
                last = value
                if (same >= {frames}) return resolve(JSON.parse(value))
                if (++count > 600) return reject(new Error('still moving: ' + value))
                requestAnimationFrame(tick)
            }}
            requestAnimationFrame(tick)
        }})""")

    def gesture(x, y, dx=0, dy=0, *, modifiers=0, clicks=1):
        x, y = js(f"canvasEdit.point({x},{y})")
        drag_at(x, y, dx, dy, modifiers=modifiers, clicks=clicks)

    def atlas_gesture(start, end):
        (x, y), (end_x, end_y) = stable(
            f"[canvasEdit.atlasPoint({start[0]}, {start[1]}), canvasEdit.atlasPoint({end[0]}, {end[1]})]"
        )
        drag_at(x, y, end_x - x, end_y - y)

    def click_atlas(caption):
        assert js(f"""[...document.querySelectorAll('.gf-atlas-dialog button')].some(button => {{
            if (button.textContent.trim() !== {json.dumps(caption)} || button.disabled) return false
            button.click()
            return true
        }})"""), caption

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
            wait("!!window.canvasEdit", "harness ready")
            js(f"canvasEdit.previewTexture({json.dumps(str(project.ui_dir / 'main.dds'))}); true")
            wait("!!document.querySelector('.gf-atlas-surface > canvas[style]') && document.querySelector('.gf-atlas-surface > canvas').offsetTop > 0", "texture preview without XML")
            assert not js("!!document.querySelector('[data-testid=atlas-edit], .gf-atlas-fields')")
            x, y = stable("canvasEdit.atlasPoint(512, 512)")
            drag_at(x, y, 22, 17, button="middle")
            wait(f"JSON.stringify(canvasEdit.atlasPoint(512, 512)) !== JSON.stringify({json.dumps([x, y])})", "atlas pan")
            pan_x, pan_y = stable("canvasEdit.atlasPoint(512, 512)")
            assert (round(pan_x - x), round(pan_y - y)) == (22, 17), (x, y, pan_x, pan_y)
            scale = js("canvasEdit.atlasPoint(513, 512)[0] - canvasEdit.atlasPoint(512, 512)[0]")
            cdp("Input.dispatchMouseEvent", type="mouseWheel", x=pan_x, y=pan_y, deltaX=0, deltaY=-120)
            wait(f"canvasEdit.atlasPoint(513, 512)[0] - canvasEdit.atlasPoint(512, 512)[0] > {scale}", "atlas zoom")
            js("document.querySelector('.gf-atlas-close').click(); true")
            results["texture-preview-zoom-pan"] = True

            async_js(f"canvasEdit.open({json.dumps(str(paths[0]))}, false)")
            snapshot("mail-open")
            js("window.addEventListener('gf:element-dblclick', event => window.elementDoubleClick = event.detail); true")
            gesture(45, 35)
            gesture(45, 35, clicks=2)
            assert js("window.elementDoubleClick") == {"index": 2, "windowId": "2010"}
            results["element-doubleclick"] = True
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

            js("""const mode = document.querySelector('select[aria-label="Texto"]');
                mode.value = 'game'; mode.dispatchEvent(new Event('change', {bubbles: true})); true""")
            assert js("canvasEdit.state().doc.elements[2].texts.game.value") == "Original harness label"
            assert async_js("pywebview.api.texts_save('T_TextIndex.ini', '637', ['Updated harness label'])") == {"saved": True}
            wait("canvasEdit.state().doc.elements[2].texts.game.value === 'Updated harness label'", "live game text")
            assert js("canvasEdit.state().dirty && canvasEdit.state().canUndo")
            assert js("canvasEdit.state().doc.elements[10].geometry") == expected["nudge"][10]
            results["live-text-preserves-dirty-xml"] = True

            # Simula a casca: o evento vem depois que o manifesto foi atualizado.
            layer_select = "document.querySelector('select[aria-label=Camadas]')"
            assert js(f"{layer_select}.dataset.active") == "false"
            layer_path = json.dumps(str(paths[0]))
            layer_name = json.dumps(paths[1].name)
            for action, active in (("add", "true"), ("remove", "false")):
                assert async_js(f"pywebview.api.canvas_change_layers({layer_path}, '{action}', {layer_name})") is None
                js("window.dispatchEvent(new CustomEvent('gf:layers-changed')); true")
                wait(f"{layer_select}.dataset.active === '{active}'", f"external layer {action}")
                assert js("canvasEdit.state().dirty && canvasEdit.state().canUndo")
                assert js("canvasEdit.state().doc.elements[10].geometry") == expected["nudge"][10]
            results["layer-event-preserves-dirty-xml"] = True

            js(f"canvasEdit.openAtlas({ATLAS_INDEX}); true")
            wait("document.querySelectorAll('[data-testid=atlas-state-card] select option:not([disabled])').length === 4 && !!document.querySelector('.gf-atlas-cut')", "atlas states")
            click_atlas("Editar posição")
            wait("document.querySelector('.gf-atlas-surface').dataset.editing === 'true'", "atlas edit mode")
            atlas_gesture((550, 87), (553, 89))
            wait("document.querySelector('.gf-atlas-fields input').value === '539'", "move normal crop")
            previous_x = js("canvasEdit.atlasPoint(603, 99)[0]")
            click_atlas("Centralizar")
            wait(f"canvasEdit.atlasPoint(603, 99)[0] < {previous_x}", "recenter normal crop")
            view_x, view_y = js("""(() => {
                const box = document.querySelector('.gf-atlas-surface').getBoundingClientRect()
                return [box.x + box.width / 2, box.y + box.height / 2]
            })()""")
            cdp("Input.dispatchMouseEvent", type="mouseWheel", x=view_x, y=view_y, deltaX=0, deltaY=120)
            wait("Number(document.querySelector('.gf-atlas-magnification').textContent.slice(0, -1)) <= 1000", "zoom out from crop")
            # Land just inside the last pixel so the ceiling yields the intended end.
            x, y, edge = js("""(() => {
                const box = document.querySelector('.gf-atlas-cut [data-edge=se]').getBoundingClientRect()
                const x = box.x + box.width / 2, y = box.y + box.height / 2
                return [x, y, document.elementFromPoint(x,y)?.dataset.edge]
            })()""")
            assert edge == "se", (x, y, edge)
            end_x, end_y = js("canvasEdit.atlasPoint(607.8, 96.8)")
            drag_at(x, y, end_x - x, end_y - y)
            wait("document.querySelectorAll('.gf-atlas-fields input')[2].value === '69'", "resize normal crop")
            js("document.querySelector('.gf-atlas-resize input').click(); true")
            assert js("""(() => {
                const select = document.querySelector('[data-testid=atlas-state-card] select')
                Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'FocusUV')
                select.dispatchEvent(new Event('change', { bubbles: true }))
                return true
            })()""")
            wait("""(() => {
                const cut = document.querySelector('.gf-atlas-cut').getBoundingClientRect();
                const view = document.querySelector('.gf-atlas-surface').getBoundingClientRect();
                return document.querySelector('[data-testid=atlas-state-card] select').value === 'FocusUV' &&
                    Math.abs(cut.left + cut.width / 2 - view.left - view.width / 2) < 1 &&
                    Math.abs(cut.top + cut.height / 2 - view.top - view.height / 2) < 1;
            })()""", "focus state centered")
            atlas_gesture((539.2, 93.2), (598.8, 112.8))
            wait("document.querySelectorAll('.gf-atlas-fields input')[1].value === '93'", "draw focus crop")
            async_js("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))")
            assert capture_window(window.native.Handle.ToInt64(), out / "mail-atlas.png")
            click_atlas("Aplicar")
            snapshot("atlas")
            uv = f"canvasEdit.state().doc.elements[{ATLAS_INDEX}]"
            assert js(f"{uv}.uv") == list(ATLAS_NORMAL)
            assert js(f"{uv}.button_uvs.FocusUV") == list(ATLAS_FOCUS)
            js("document.querySelector('.gf-atlas-close').click(); true")
            async_js("canvasEdit.undo()")
            snapshot("atlas-undo")
            assert js(f"{uv}.uv") == [536, 79, 64, 18]
            assert js(f"{uv}.button_uvs.FocusUV") == [536, 98, 64, 18]
            async_js("canvasEdit.redo()")
            snapshot("atlas-redo")
            assert js(f"{uv}.uv") == list(ATLAS_NORMAL)
            assert js(f"{uv}.button_uvs.FocusUV") == list(ATLAS_FOCUS)
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
    parser.add_argument("--light", action="store_true", help="Run both canvases with converted project fixtures.")
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
    qt_project, web_project = fixtures(out, game, args.light)
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
