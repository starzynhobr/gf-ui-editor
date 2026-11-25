"""Harness "mesma entrada, mesma saída": roda fluxos reais do editor numa caixa de areia.

Uso: python harness/run_flows.py <pasta_saida> <copia_do_jogo>
(normalmente via harness/run.ps1, que roda a versão de referência e a atual e compara).

- O código testado vem do PYTHONPATH (o `src` da árvore que se quer testar).
- HOME/USERPROFILE/APPDATA apontam para a saída antes de importar o editor: projetos,
  bancos e preferências ficam na caixa de areia. O QSettings("Local", "GF UI Editor")
  iria direto ao Registro; aqui ele é desviado para um INI (como no tests/conftest.py).
- A cópia do jogo é copiada de novo para a saída; o jogo real nunca é tocado.
- Diálogos são respondidos por roteiro (ANSWERS); toda pergunta/aviso vai para o log.
- Saída: log.json (passos e mensagens), outputs.json (sha1 dos arquivos gravados) e
  shots/*.png. O compare.py diz o que difere entre duas saídas.

Fluxo novo: escreva uma função e chame run("nome", funcao), sem mudar a ordem dos
existentes (o compare.py compara os logs em ordem).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

OUT = Path(sys.argv[1]).resolve()
PRISTINE = Path(sys.argv[2]).resolve()
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "home" / "Documents").mkdir(parents=True)
(OUT / "shots").mkdir()
os.environ["USERPROFILE"] = os.environ["HOME"] = str(OUT / "home")
os.environ["APPDATA"] = str(OUT / "home" / "AppData")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
GAME = OUT / "game"
subprocess.run(["robocopy", str(PRISTINE), str(GAME), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/MT:16"], check=False)

import PySide6.QtCore as QtCore  # noqa: E402

QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, str(OUT / "settings"))


class _IsolatedQSettings(QtCore.QSettings):
    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], str) and not (len(args) > 1 and isinstance(args[1], QtCore.QSettings.Format)):
            super().__init__(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, *args, **kwargs)
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _IsolatedQSettings
QSettings = _IsolatedQSettings
assert "HKEY" not in QSettings("Local", "GF UI Editor").fileName()

from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMenu, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

import gf_ui_editor  # noqa: E402
from gf_ui_editor import app as app_module, text_data  # noqa: E402

assert str(OUT) in str(app_module.PROJECTS_ROOT), app_module.PROJECTS_ROOT
assert "HKEY" not in app_module.QSettings("Local", "GF UI Editor").fileName()
app_module.DEFAULT_UI_DIRECTORY = GAME / "UI"

LOG: list[dict] = []
ANSWERS: list = []  # respostas para getText/getItem/getMultiLineText/QMenu, em ordem
STEP = {"name": "init"}


def log(kind, **data):
    entry = {"step": STEP["name"], "kind": kind, **data}
    LOG.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def _box(kind):
    def show(parent, title, text, *args, **kwargs):
        log(kind, title=str(title), text=str(text))
        return QMessageBox.StandardButton.Ok
    return show


def _question(parent, title, text, *args, **kwargs):
    log("question", title=str(title), text=str(text))
    return QMessageBox.StandardButton.Yes


def _answer(kind, *args, **kwargs):
    if not ANSWERS:
        log("unexpected_input", which=kind, args=[str(a) for a in args[1:3]])
        return "", False
    value = ANSWERS.pop(0)
    log("input", which=kind, value=str(value))
    return value, True


QMessageBox.information = staticmethod(_box("information"))
QMessageBox.warning = staticmethod(_box("warning"))
QMessageBox.critical = staticmethod(_box("critical"))
QMessageBox.question = staticmethod(_question)
QInputDialog.getText = staticmethod(lambda *a, **k: _answer("getText", *a, **k))
QInputDialog.getItem = staticmethod(lambda *a, **k: _answer("getItem", *a, **k))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: _answer("getMultiLineText", *a, **k))


def _menu_exec(self, *args, **kwargs):
    wanted = ANSWERS.pop(0) if ANSWERS else None
    for action in self.actions():
        if wanted and action.text().startswith(wanted):
            log("menu", chose=action.text())
            return action
    log("unexpected_menu", wanted=str(wanted), options=[a.text() for a in self.actions()])
    return None


class _ScriptedMenu(QMenu):
    def exec(self, *args, **kwargs):  # noqa: A003
        return _menu_exec(self)


app_module.QMenu = _ScriptedMenu


def _dialog_exec(self):
    log("dialog", cls=type(self).__name__, title=self.windowTitle())
    return QDialog.DialogCode.Accepted


QDialog.exec = _dialog_exec


def _box_exec(self):
    log("messagebox", title=self.windowTitle(), text=self.text())
    buttons = self.buttons()
    yes = self.button(QMessageBox.StandardButton.Yes) or self.button(QMessageBox.StandardButton.Ok)
    if yes is not None:
        self._e2e_clicked = yes
    return QMessageBox.StandardButton.Yes if yes is not None else 0


QMessageBox.exec = _box_exec
import faulthandler  # noqa: E402

_STACKS = open(OUT / "stacks.txt", "w")


def _watchdog():
    faulthandler.dump_traceback_later(150, exit=True, file=_STACKS)  # rearmado a cada passo


def _new_project_exec(self):
    self.name_edit.setText("E2E")
    self.source_dir = GAME / "UI"
    self.game_dir = GAME
    self.publish_folder = ""
    self.loose_files = []
    log("dialog", cls="NewProjectDialog")
    return QDialog.DialogCode.Accepted


app_module.NewProjectDialog.exec = _new_project_exec


def pump(seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(window, name):
    pump(0.2)
    window.grab().save(str(OUT / "shots" / f"{name}.png"))


def step(name):
    _watchdog()
    STEP["name"] = name
    log("step")


def run(name, fn):
    step(name)
    try:
        fn()
        log("ok")
    except Exception as exc:  # noqa: BLE001
        log("error", error=repr(exc), tb=traceback.format_exc())


window = app_module.EditorWindow()
window.resize(1600, 950)
window.show()
pump(1)
shot(window, "01_home_vazia")
state: dict = {}


def create_project():
    assert window.new_project()
    pump(1)
    state["project"] = window.project
    log("info", root=str(window.project.root), files=len(window.project.base_hashes))


run("criar_projeto", create_project)
project = state.get("project")
if project is None:
    raise SystemExit("sem projeto")
ui = project.ui_dir


def open_basicchar():
    window.open_document(ui / "BasicChar.xml")
    pump(1)
    shot(window, "02_basicchar")
    log("info", elements=len(window.document.elements))


run("abrir_xml", open_basicchar)


def text_modes():
    for mode in app_module.TEXT_MODES:
        window.set_text_mode(mode)
        pump(0.3)
        texts = sorted(
            str(getattr(item, "game_text", "") or "") for item in getattr(window, "element_items", {}).values()
        ) if hasattr(window, "element_items") else []
        log("info", mode=mode, game_text_for=[window._game_text_for(e) for e in window.document.elements[:40]])
        shot(window, f"03_texto_{mode}")
    window.set_text_mode("off")


run("modos_de_texto", text_modes)


def filter_tree():
    for query in ("hp", "Button", "zzzz"):
        window.filter_tree(query)
        pump(0.2)
        tree = window.tree
        visible = []

        def walk(item):
            for i in range(item.childCount()):
                child = item.child(i)
                if not child.isHidden():
                    visible.append(child.text(0))
                walk(child)

        walk(tree.invisibleRootItem())
        log("info", query=query, visible=visible)
    shot(window, "04_filtro")
    window.filter_tree("")


run("filtro_arvore", filter_tree)


def move_and_save():
    textured = [e.index for e in window.document.elements if e.texture_name and window.document.texture_editable(e.index)]
    state["textured"] = textured
    index = textured[1]
    window.select_element(index)
    window.move_selected(5, 3)
    window._confirm_diff_preview = lambda: True
    window.save_document()
    pump(0.5)
    log("info", moved=window.document.elements[index].window_id)


run("mover_e_salvar", move_and_save)


def change_texture():
    index = state["textured"][2]
    window.select_element(index)
    current = window.document.elements[index].texture_name
    names = app_module.textures.ui_texture_names(window.texture_cache.ui_directory) if hasattr(app_module, "textures") else None
    other = next(n for n in sorted((p.name for p in ui.iterdir() if p.suffix.lower() in (".dds", ".tga")), key=str.lower) if n != current)
    ANSWERS.extend(["Usar outro", other])
    window.change_selected_texture()
    pump(0.3)
    ANSWERS.extend(["Criar cópia", "e2e_copia.dds"])
    window.select_element(state["textured"][3])
    window.change_selected_texture()
    pump(0.3)
    window.save_document()
    pump(0.5)
    shot(window, "05_textura_trocada")


run("trocar_textura", change_texture)


def new_image():
    window.select_element(0)
    names = sorted((p.name for p in ui.iterdir() if p.suffix.lower() in (".dds", ".tga")), key=str.lower)
    ANSWERS.append(names[0])
    window.new_image()
    pump(1)
    for widget in QApplication.topLevelWidgets():
        if type(widget).__name__ == "AtlasDialog" and widget.isVisible():
            widget.grab().save(str(OUT / "shots" / "06_atlas_nova_imagem.png"))
            widget.close()
    window.save_document()
    pump(0.5)
    shot(window, "06_nova_imagem")


run("nova_imagem", new_image)


def edit_text_and_publish():
    path = GAME / "data" / "Translate" / "T_TextIndex.ini"
    record = text_data.TextFile.load(path).records[5]
    edits = {"T_TextIndex.ini": {record.record_id: text_data.TextEdit([record.fields[0] + " E2E"] + record.fields[1:], list(record.fields))}}
    text_data.save_edits(project.root, edits)
    log("info", text_id=record.record_id, before=record.fields[0])
    window.test_in_game()
    pump(1)
    shot(window, "07_publicado")


run("f5_com_texto", edit_text_and_publish)


def rename_texture():
    used = window.document.elements[state["textured"][4]].texture_name
    state["renamed_from"] = used
    ANSWERS.append("e2e_renomeada.dds")
    window.rename_project_file(ui / used)
    pump(0.5)
    users = app_module.file_list.xml_using_texture(project, "e2e_renomeada.dds") if hasattr(app_module, "file_list") else []
    log("info", old=used, users_now=[p.name for p in users])


run("renomear_textura", rename_texture)


def delete_files():
    window.delete_project_file(ui / "e2e_renomeada.dds")
    pump(0.3)
    window.delete_project_file(ui / "Radar.xml")
    pump(0.3)


run("apagar", delete_files)


def restore():
    path = ui / "BasicChar.xml"
    backups, original = window._history_entries(path)
    log("info", backups=len(backups), has_original=original is not None)
    window.restore_file(path, original or backups[-1])
    pump(0.5)
    shot(window, "08_restaurado")


run("restaurar", restore)


def version_and_home():
    ANSWERS.append("versao e2e")
    window.save_project_version(project)
    pump(0.5)
    window.show_home()
    pump(3)
    shot(window, "09_home_com_projeto")


run("versao_e_home", version_and_home)


def game_error():
    ANSWERS.append("Error: BasicChar.cpp ID=ZZZ_NAO_EXISTE")
    window.resolve_game_error()
    pump(0.5)


run("erro_do_jogo", game_error)


def updates():
    window.check_for_updates(manual=True)
    pump(8)


run("verificar_atualizacoes", updates)


# ---- resultado: conteúdo dos arquivos gravados (sem nomes com data/hora) ----
def digest(folder: Path, skip=()) -> dict[str, str]:
    result = {}
    if not folder.exists():
        return result
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if path.is_file() and not any(part in rel for part in skip):
            result[rel] = hashlib.sha1(path.read_bytes()).hexdigest()
    return result


outputs = {
    "project_ui": digest(ui),
    "game_ui": digest(GAME / "UI"),
    "uicustom": digest(GAME / "UICustom"),
    "translate": digest(GAME / "data" / "Translate"),
    "launcher_ini": hashlib.sha1((GAME / "Launcher.ini").read_bytes()).hexdigest(),
    "text_edits": {k: {i: e.fields for i, e in v.items()} for k, v in text_data.load_edits(project.root).items()},
    "history_count": sum(1 for p in project.history_dir.rglob("*") if p.is_file()),
}
(OUT / "outputs.json").write_text(json.dumps(outputs, indent=1, ensure_ascii=False), encoding="utf-8")
(OUT / "log.json").write_text(json.dumps(LOG, indent=1, ensure_ascii=False), encoding="utf-8")
print("version", gf_ui_editor.__version__, "errors", sum(1 for e in LOG if e["kind"] == "error"))
window.close()
