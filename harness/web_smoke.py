"""Teste de ponta a ponta da interface web: a janela pywebview real numa caixa de areia.

Uso: python harness/web_smoke.py <pasta_saida> <copia_do_jogo>
(a cópia do jogo é a `pristine` que o harness/run.ps1 cria, ex.: %TEMP%\\gf-ui-harness\\pristine)

- Igual ao run_flows.py: HOME/USERPROFILE/APPDATA apontam para a saída e o QSettings vai
  para um INI dentro dela, antes de importar o editor. A cópia do jogo é copiada de novo
  para <saida>/game; o jogo real nunca é tocado.
- Precisa do build do front (`npm run build` em web/).
- Diálogos nativos de pasta/arquivo são respondidos por roteiro (ANSWERS), como no run_flows.
- Fluxo: tela inicial → Novo projeto (cópia do jogo) → lista de arquivos → abrir XML →
  editar o arquivo no disco → F5 (confirmação da primeira vez) → conferir o que foi gravado
  no jogo → tela inicial de novo → trocar o idioma.
- Saída: log.json (passos e verificações) e shots/*.png (capturas da janela).
  Termina com código 0 se todas as verificações passaram.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
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
if not (PRISTINE / "UI").is_dir():
    raise SystemExit(f"Cópia do jogo não encontrada em {PRISTINE} (rode harness/run.ps1 uma vez).")
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "home" / "Documents").mkdir(parents=True)
(OUT / "shots").mkdir()
os.environ["USERPROFILE"] = os.environ["HOME"] = str(OUT / "home")
os.environ["APPDATA"] = str(OUT / "home" / "AppData")
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
assert "HKEY" not in _IsolatedQSettings("Local", "GF UI Editor").fileName()

from gf_ui_editor import app as app_module, project as project_module, remote_manifest, web_shell  # noqa: E402

assert str(OUT) in str(project_module.PROJECTS_ROOT), project_module.PROJECTS_ROOT
assert "HKEY" not in app_module.QSettings("Local", "GF UI Editor").fileName()
app_module.DEFAULT_UI_DIRECTORY = GAME / "UI"
remote_manifest.fetch = lambda *args, **kwargs: None  # sem rede: o resultado não depende do manifesto
app_module.prefs.game_dir = str(GAME)  # o Novo projeto já abre com a cópia do jogo

LOG: list[dict] = []
FAILED: list[str] = []
ANSWERS: list = []  # respostas dos diálogos nativos (pasta/arquivo), em ordem


def log(kind: str, **data) -> None:
    entry = {"kind": kind, **data}
    LOG.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def check(name: str, condition: bool, **detail) -> None:
    log("check", name=name, ok=bool(condition), **detail)
    if not condition:
        FAILED.append(name)


def answer(kind, directory, file_types, save_name):
    value = ANSWERS.pop(0) if ANSWERS else None
    log("dialog", which=kind, answer=str(value))
    return value


# ---- janela -----------------------------------------------------------------------------
api = web_shell.WebApi("pt_BR", False, app_module.prefs, app_module.DEFAULT_UI_DIRECTORY, None)
api._dialogs = answer
import webview  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offscreen import capture_window, window_options  # noqa: E402

window = webview.create_window(
    web_shell.APP_TITLE, web_shell._start_url(False), js_api=api, width=1440, height=900, min_size=(1024, 680),
    background_color="#111318", **window_options(),
)
api._attach(window)

HELPERS = r"""
window.__smoke = window.__smoke || {
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


def js(code: str):
    window.evaluate_js(HELPERS)
    return window.evaluate_js(code)


def wait(code: str, timeout: float = 20.0, what: str = ""):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = js(code)
        except Exception:  # noqa: BLE001 - a página pode estar recarregando
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
        return ctypes.windll.user32.FindWindowW(None, web_shell.APP_TITLE)


def shot(name: str) -> None:
    """Captura a janela (fora da tela e sem foco; ver harness/offscreen.py)."""
    time.sleep(0.35)
    path = OUT / "shots" / f"{name}.png"
    if not capture_window(_hwnd(), path):
        FAILED.append(f"captura {name}")
    log("shot", name=name, path=str(path))


# ---- roteiro ----------------------------------------------------------------------------
def scenario() -> None:
    project_root = project_module.PROJECTS_ROOT / "Smoke-Test"

    # 1. Tela inicial sem projetos.
    check("home aparece", bool(wait("!!__smoke.q('[data-testid=home]')", 30, "tela inicial")))
    text = js("__smoke.text('[data-testid=home]')") or ""
    check("home sem projeto convida a começar", "Comece um projeto de UI" in text, text=text[:200])
    check("home sem projetos", "Nenhum projeto ainda" in text)
    check("seção Como funciona", "COMO FUNCIONA" in text.upper())
    shot("01-home-vazia")

    # 2. Novo projeto a partir da UI da cópia do jogo.
    js("__smoke.clickText('Novo projeto', '[data-testid=home]')")
    check("diálogo Novo projeto", bool(wait("!!__smoke.q('input[name=project-name]')", 10, "diálogo novo projeto")))
    wait("__smoke.q('select[name=project-source]') && __smoke.q('select[name=project-source]').options.length > 2", 10, "origens")
    source = js("__smoke.q('select[name=project-source]').value")
    check("origem padrão = pasta UI do jogo", os.path.normcase(str(source)) == os.path.normcase(str(GAME / "UI")), source=source)
    dialog_text = js("__smoke.text('[role=dialog]')") or ""
    check("pasta do jogo preenchida", str(GAME) in (js("Array.from(document.querySelectorAll('[role=dialog] input')).map(i => i.value).join('|')") or ""))
    js("__smoke.setValue('input[name=project-name]', 'Smoke Test')")
    time.sleep(0.4)
    dialog_text = js("__smoke.text('[role=dialog]')") or ""
    check("destino com o nome do projeto", "UICustom/Smoke-Test" in (js("__smoke.q('[role=dialog] select:not([name])').innerText") or ""))
    shot("02-novo-projeto")
    js("__smoke.click('[data-testid=create-project]')")
    check("lista de arquivos depois de criar", bool(wait("!!__smoke.q('[data-testid=files-panel] [data-file]')", 180, "lista de arquivos")))
    check("projeto criado no disco", (project_root / "project.db").is_file() and (project_root / "ui" / "BasicChar.xml").is_file())
    count = len(list((project_root / "ui").rglob("*.xml")))
    status = js("__smoke.text('[data-testid=status-message]')") or ""
    check("status: projeto criado", "Projeto criado com" in status, status=status)
    top = js("__smoke.text('[data-testid=topbar]')") or ""
    check("barra superior mostra o projeto", "Smoke Test" in top, top=top)
    all_title = js("__smoke.text('[data-section=all]')") or ""
    check("seção TODOS com o total de XMLs", f"TODOS · {count}" in all_title.upper(), title=all_title[:40], xml=count)
    shot("03-projeto-aberto")

    # 3. Filtrar e abrir um XML (o caminho vai para o CanvasView).
    js("__smoke.setValue('[data-testid=files-panel] input', 'basicchar')")
    filtered = wait(
        "(() => { const rows = __smoke.all('[data-section=all] [data-file]').map((r) => r.dataset.file);"
        " return rows.length > 0 && rows.every((name) => name.toLowerCase().includes('basicchar')) && rows })()",
        5, "filtro",
    )
    check("filtro só deixa os XMLs com o texto", bool(filtered) and "BasicChar.xml" in filtered, rows=filtered)
    js("__smoke.click('[data-section=all] [data-file=\"BasicChar.xml\"]')")
    crumb = wait("__smoke.text('[data-testid=breadcrumb]')", 5, "breadcrumb")
    check("XML aberto na barra", crumb is not None and "BasicChar.xml" in crumb, crumb=crumb)
    drawn = wait("!!__smoke.q('[data-testid=center] canvas')", 20, "canvas desenhado")
    center = js("__smoke.text('[data-testid=center]')") or ""
    check("canvas desenha o XML", bool(drawn) and "Error" not in center, center=center[:200])
    time.sleep(1.5)  # texturas carregando no worker
    check("último XML lembrado", app_module.prefs.last_file("Smoke-Test") == "BasicChar.xml")
    js("__smoke.setValue('[data-testid=files-panel] input', '')")
    shot("04-xml-aberto")

    # 4. Ctrl+2 (Texturas) e Ctrl+3 (Elementos: em breve), depois volta ao XML.
    js("__smoke.key('2', { ctrlKey: true })")
    check("Ctrl+2 mostra Texturas", bool(wait("(__smoke.text('[data-testid=files-panel]') || '').includes('Texturas')", 5, "texturas")))
    js("__smoke.key('3', { ctrlKey: true })")
    check("Ctrl+3 mostra Elementos (em breve)", bool(wait("!!__smoke.q('[data-testid=coming-soon]')", 5, "elementos")))
    js("__smoke.key('1', { ctrlKey: true })")
    wait("!!__smoke.q('[data-testid=files-panel] [data-file]')", 5, "volta aos XMLs")

    # 5. Edita o XML no disco (como o Notepad++ faria) e espera o contador do F5.
    target = project_root / "ui" / "BasicChar.xml"
    original = target.read_bytes()
    edited = original.replace(b"<", b"\r\n<", 1) if not original.startswith(b"\r\n") else original + b"\r\n"
    target.write_bytes(edited)
    pending = wait("__smoke.text('[data-testid=publish-count]')", 12, "contador do F5")
    check("contador do F5 = 1", (pending or "").strip() == "1", pending=pending)
    check("chip de não publicados", "ainda não publicados" in (js("__smoke.text('[data-testid=statusbar]')") or ""))
    check("seção Alterados aparece", bool(wait("!!__smoke.q('[data-section=changed] [data-file]')", 8, "alterados")))
    shot("05-pendente")

    # 6. F5: confirmação da primeira vez, progresso, resultado.
    js("__smoke.key('F5')")
    confirm = wait("(__smoke.text('[role=dialog]') || '').includes('Isto vai')", 8, "confirmação do F5")
    check("confirmação da primeira vez", bool(confirm))
    check("confirmação cita a pasta UICustom", str(GAME / "UICustom" / "Smoke-Test") in (js("__smoke.text('[role=dialog]')") or ""))
    shot("06-confirmar-envio")
    js("__smoke.clickText('Sim', '[role=dialog]')")
    status = wait("(__smoke.text('[data-testid=status-message]') || '').includes('Publicado') && __smoke.text('[data-testid=status-message]')", 60, "publicado")
    check("status: publicado 1 arquivo", status is not None and "Publicado: 1 arquivo" in status, status=status)
    check("jogo recebeu o XML na pasta UI", (GAME / "UI" / "BasicChar.xml").read_bytes() == edited)
    check("UICustom/Smoke-Test recebeu o XML", (GAME / "UICustom" / "Smoke-Test" / "BasicChar.xml").read_bytes() == edited)
    launcher = (GAME / "Launcher.ini").read_text(encoding="latin-1")
    check("Launcher.ini seleciona a UI", "custom:Smoke-Test" in launcher)
    check("confirmação lembrada", app_module.prefs.publish_confirmed is True)
    wait("!__smoke.q('[data-testid=publish-count]')", 8, "contador zerado")
    check("contador do F5 zerado", not js("!!__smoke.q('[data-testid=publish-count]')"))
    shot("07-enviado")

    # 7. F5 de novo: sem confirmação, nada mudou.
    js("__smoke.key('F5')")
    status = wait("(__smoke.text('[data-testid=status-message]') || '').includes('Nada mudou') && __smoke.text('[data-testid=status-message]')", 60, "nada mudou")
    check("segundo F5 sem pergunta e sem mudanças", status is not None and not js("!!__smoke.q('[role=dialog]')"))

    # 8. Tela inicial com o projeto (continuar, tamanho calculado em segundo plano).
    js("__smoke.click('[data-testid=topbar] button')")
    wait("!!__smoke.q('[data-testid=home-project-row]')", 10, "linha do projeto")
    size = wait("(() => { const r = __smoke.q('[data-testid=home-project-row]'); return r && /\\d+ (KB|MB|GB)/.test(r.innerText) && r.innerText })()", 30, "tamanho do projeto")
    check("tamanho do projeto aparece", bool(size), row=size)
    home_text = js("__smoke.text('[data-testid=home]')") or ""
    check("cartão Continuar", "CONTINUAR DE ONDE PAROU" in home_text.upper() and "Smoke Test" in home_text)
    check("XML fechado ao voltar para a tela inicial", not js("!!__smoke.q('[data-testid=breadcrumb]')"))
    shot("08-home-com-projeto")

    # 9. Menu ⋯ da linha e Gerenciar.
    js("__smoke.click('[data-testid=home-project-row] button[aria-label]')")
    menu = wait("__smoke.text('[role=menu]')", 5, "menu da linha") or ""
    check("menu ⋯ tem Duplicar, Renomear e Excluir", all(word in menu for word in ("Duplicar", "Renomear", "Excluir")), menu=menu)
    shot("09-menu-projeto")
    js("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    js("window.dispatchEvent(new MouseEvent('mousedown'))")

    # 10. Continuar reabre o último XML.
    js("__smoke.clickText('Continuar', '[data-testid=home]')")
    crumb = wait("__smoke.text('[data-testid=breadcrumb]')", 8, "continuar")
    check("Continuar reabre o último XML", crumb is not None and "BasicChar.xml" in crumb)

    # 11. Idioma: inglês pelas configurações.
    js("__smoke.click('[data-testid=side-rail] button[aria-label=\"Configurações\"]')")
    wait("!!__smoke.q('[role=menu]')", 5, "menu configurações")
    js("__smoke.clickText('Idioma', '[role=menu]')")
    wait("__smoke.all('[role=menu]').length > 1", 5, "submenu idioma")
    js(
        "(() => { const menus = __smoke.all('[role=menu]'); const items = menus[menus.length - 1].querySelectorAll('[role=menuitem]');"
        " const item = Array.from(items).find((b) => b.innerText.includes('English')); if (item) item.click(); return !!item })()"
    )
    check("idioma trocado para inglês", bool(wait("(__smoke.text('[data-testid=topbar]') || '').includes('Send to game')", 5, "inglês")))
    check("idioma salvo nas preferências", app_module.prefs.language == "en_US")
    shot("10-ingles")

    # 12. Comportamentos de navegador desligados.
    blocked = js(
        "(() => { const e = new KeyboardEvent('keydown', { key: 'r', ctrlKey: true, cancelable: true, bubbles: true });"
        " window.dispatchEvent(e); const w = new WheelEvent('wheel', { ctrlKey: true, cancelable: true, bubbles: true });"
        " document.body.dispatchEvent(w); const m = new MouseEvent('contextmenu', { cancelable: true, bubbles: true });"
        " document.body.dispatchEvent(m); return [e.defaultPrevented, w.defaultPrevented, m.defaultPrevented] })()"
    )
    check("Ctrl+R, Ctrl+roda e menu de contexto bloqueados", blocked == [True, True, True], blocked=blocked)


def driver() -> None:
    try:
        scenario()
    except Exception:  # noqa: BLE001
        log("error", traceback=traceback.format_exc())
        FAILED.append("exceção no roteiro")
    finally:
        (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
        window.destroy()


webview.start(driver, gui="edgechromium", private_mode=True, storage_path=str(OUT / "webview"))
log("summary", failed=FAILED, checks=sum(1 for entry in LOG if entry["kind"] == "check"))
(OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(1 if FAILED else 0)
