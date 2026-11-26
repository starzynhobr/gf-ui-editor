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
    wait(
        "(__smoke.text('[data-testid=home-projects]') || '').includes('Nenhum projeto ainda')"
        " || !!__smoke.q('[data-testid=home-project-row]')",
        20, "carregamento dos projetos",
    )
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
    check("Ctrl+3 mostra a árvore de elementos", bool(wait("!!__smoke.q('[data-testid=element-tree]')", 5, "elementos")))
    js("__smoke.key('1', { ctrlKey: true })")
    wait("!!__smoke.q('[data-testid=files-panel] [data-file]')", 5, "volta aos XMLs")

    # 5. Edita o XML no disco (como o Notepad++ faria) e espera o contador do F5.
    target = project_root / "ui" / "BasicChar.xml"
    original = target.read_bytes()
    edited = original + b"\r\n"  # espaço depois da raiz: muda o arquivo e o XML continua válido
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
    check("menu ⋯ tem Versões, Puxar e Limpar", all(word in menu for word in ("Versões do projeto", "Puxar da pasta do jogo", "Limpar projeto")), menu=menu)
    shot("09-menu-projeto")
    js("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    js("window.dispatchEvent(new MouseEvent('mousedown'))")

    # 9b. Bloco 3: Salvar versão pelo cartão Continuar e lista de versões.
    check("cartão tem Salvar versão, Versões e Puxar", all(
        js(f"!!__smoke.q('[data-testid={name}]')") for name in ("home-save-version", "home-versions", "home-pull")
    ))
    versions_before = len(list((project_root / ".versions").glob("*.zip")))
    js("__smoke.click('[data-testid=home-save-version]')")
    if wait("!!__smoke.q('[role=dialog] input')", 5, "nome da versão"):
        js("__smoke.setValue('[role=dialog] input', 'smoke')")
        js("__smoke.clickText('OK', '[role=dialog]')")
    saved = wait(
        f"(() => {{ const s = __smoke.text('[data-testid=status-message]'); return s && s.includes('Versão salva') && s }})()",
        20, "versão salva",
    )
    versions_after = len(list((project_root / ".versions").glob("*.zip")))
    check("Salvar versão grava o .zip", bool(saved) and versions_after == versions_before + 1, before=versions_before, after=versions_after)
    js("__smoke.click('[data-testid=home-versions]')")
    listed = wait("(() => { const d = __smoke.text('[role=dialog]'); return d && d.includes('smoke') && d })()", 8, "lista de versões")
    check("Versões lista a versão salva", bool(listed), dialog=(listed or "")[:200])
    shot("09b-versoes")
    js("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    wait("!__smoke.q('[role=dialog]')", 5, "fecha versões")

    # 10. Continuar reabre o último XML.
    js("__smoke.clickText('Continuar', '[data-testid=home]')")
    crumb = wait("__smoke.text('[data-testid=breadcrumb]')", 8, "continuar")
    check("Continuar reabre o último XML", crumb is not None and "BasicChar.xml" in crumb)
    check("chip da UI oficial no rodapé", bool(wait("!!__smoke.q('[data-testid=official-chip]')", 8, "chip UI oficial")))

    # 10b. Bloco 2: árvore, painel, menu de arquivos, salvar e descartar.
    block2(project_root)

    # 10c. Textos (Ctrl+4): buscar, abrir, editar, salvar e enviar com F5.
    texts_flow(project_root)

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


def block2(project_root: Path) -> None:
    from gf_ui_editor.xml_document import UIDocument

    xml = project_root / "ui" / "BasicChar.xml"
    document = UIDocument.load(xml)
    child = document.elements[1]
    before_edit = xml.read_bytes()

    # Árvore de elementos (Ctrl+3): uma linha por elemento, hierarquia, filtro.
    js("__smoke.key('3', { ctrlKey: true })")
    count = wait("__smoke.all('[data-testid=tree-row]').length", 15, "árvore de elementos")
    check("árvore com uma linha por elemento", count == len(document.elements), rows=count, elements=len(document.elements))
    nested = js("__smoke.all('[data-testid=tree-row] [style*=\"padding-left\"]').some((e) => parseInt(e.style.paddingLeft) > 0)")
    check("árvore mostra a hierarquia (recuo dos filhos)", bool(nested))
    js(f"__smoke.setValue('[data-testid=element-tree] input', '{child.window_id}')")
    filtered = wait(
        f"(() => {{ const rows = __smoke.all('[data-testid=tree-row]'); return rows.length > 0 && rows.length < {len(document.elements)}"
        f" && rows.some((r) => r.dataset.index === '{child.index}') && rows.length }})()",
        5, "filtro da árvore",
    )
    check("filtro da árvore pelo WindowID", bool(filtered), rows=filtered)
    js("__smoke.setValue('[data-testid=element-tree] input', '')")
    wait(f"__smoke.all('[data-testid=tree-row]').length === {len(document.elements)}", 5, "filtro limpo")

    # Painel: sem seleção, depois o elemento clicado na árvore.
    panel = js("__smoke.text('[data-testid=properties-panel]')") or ""
    check("painel sem seleção", "Nenhum elemento selecionado" in panel, panel=panel[:80])
    js(f"__smoke.click('[data-testid=tree-row][data-index=\"{child.index}\"]')")
    x_value = wait("(__smoke.q('input[name=geometry-x]') || {}).value", 5, "painel com o elemento")
    check("painel mostra a posição do XML", x_value == str(child.x), x=x_value, expected=child.x)
    check("linha selecionada na árvore", js(f"__smoke.q('[data-testid=tree-row][data-index=\"{child.index}\"]').getAttribute('aria-selected')") == "true")
    panel = js("__smoke.text('[data-testid=properties-panel]')") or ""
    check("painel tem identificação, textura e aparência", all(word in panel for word in ("IDENTIFICAÇÃO", "TEXTURA", "APARÊNCIA", child.window_id)))
    js(f"__smoke.q('[data-testid=tree-row][data-index=\"{child.index}\"] [data-state=locked]').click()")
    check("travar desliga os campos do painel", bool(wait("__smoke.q('input[name=geometry-x]').disabled", 3, "travado")))
    js(f"__smoke.q('[data-testid=tree-row][data-index=\"{child.index}\"] [data-state=locked]').click()")
    js("__smoke.q('[data-testid=tree-header]').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 200, clientY: 200 }))")
    menu = wait("__smoke.text('[role=menu]')", 3, "menu de colunas") or ""
    check("menu de colunas com WindowID e ParentNode", "WindowID" in menu and "ParentNode" in menu, menu=menu)
    js("window.dispatchEvent(new MouseEvent('mousedown'))")
    shot("11-arvore-e-painel")

    if js("window.__gfDoc && window.__gfDoc.editing()"):
        edit_and_save(xml, child)
    else:
        log("skip", what="editar, salvar e descartar: o store do documento (doc/store.ts) ainda não está implementado")
        js(f"__smoke.setValue('input[name=geometry-x]', '{child.x + 3}')")
        js("__smoke.q('input[name=geometry-x]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
        status = wait("(__smoke.text('[data-testid=status-message]') || '').includes('Edição indisponível')", 5, "aviso sem store")
        check("sem o store, editar avisa e não grava", bool(status) and xml.read_bytes() == before_edit)

    # Menu de contexto da lista de arquivos: renomear e apagar um XML que não está aberto.
    js("__smoke.key('1', { ctrlKey: true })")
    wait("!!__smoke.q('[data-section=all] [data-file]')", 5, "lista de arquivos")
    js("__smoke.setValue('[data-testid=files-panel] input', 'AddressBook')")
    wait("!!__smoke.q('[data-section=all] [data-file=\"AddressBook.xml\"]')", 5, "AddressBook na lista")
    js("__smoke.q('[data-section=all] [data-file=\"AddressBook.xml\"]').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 150, clientY: 300 }))")
    menu = wait("__smoke.text('[role=menu]')", 5, "menu do arquivo") or ""
    check("menu do arquivo tem Renomear, Apagar e Restaurar", all(word in menu for word in ("Renomear", "Apagar", "Restaurar versão anterior")), menu=menu)
    shot("12-menu-arquivo")
    js("__smoke.clickText('Renomear', '[role=menu]')")
    wait("!!__smoke.q('[role=dialog] input')", 5, "nome novo")
    js("__smoke.setValue('[role=dialog] input', 'AddressBook2')")
    js("__smoke.clickText('OK', '[role=dialog]')")
    renamed = project_root / "ui" / "AddressBook2.xml"
    deadline = time.time() + 5
    while time.time() < deadline and not renamed.is_file():
        time.sleep(0.1)
    check("renomear grava no projeto", renamed.is_file() and not (project_root / "ui" / "AddressBook.xml").exists())
    js("__smoke.setValue('[data-testid=files-panel] input', 'AddressBook2')")
    wait("!!__smoke.q('[data-section=all] [data-file=\"AddressBook2.xml\"]')", 5, "AddressBook2 na lista")
    js("__smoke.q('[data-section=all] [data-file=\"AddressBook2.xml\"]').dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 150, clientY: 300 }))")
    wait("!!__smoke.q('[role=menu]')", 5, "menu do arquivo renomeado")
    js("__smoke.clickText('Apagar', '[role=menu]')")
    wait("(__smoke.text('[role=dialog]') || '').includes('AddressBook2.xml')", 5, "confirmar apagar")
    js("__smoke.clickText('Sim', '[role=dialog]')")
    deadline = time.time() + 5
    while time.time() < deadline and renamed.exists():
        time.sleep(0.1)
    check("apagar tira o arquivo do projeto", not renamed.exists())
    js("__smoke.setValue('[data-testid=files-panel] input', '')")


def edit_and_save(xml: Path, child) -> None:
    """Passos que dependem do store do documento (doc/store.ts implementado pelo canvas)."""
    before = xml.read_bytes()
    new_x = child.x + 3
    js(f"__smoke.setValue('input[name=geometry-x]', '{new_x}')")
    js("__smoke.q('input[name=geometry-x]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
    check("editar X marca o XML como alterado", bool(wait("!!__smoke.q('[data-testid=dirty-marker]')", 5, "alterado")))
    check("Salvar habilitado", js("!__smoke.q('[data-testid=save]').disabled") is True)
    js("__smoke.key('z', { ctrlKey: true })")
    check("Ctrl+Z desfaz", bool(wait("!__smoke.q('[data-testid=dirty-marker]')", 5, "desfeito")))
    js("__smoke.key('y', { ctrlKey: true })")
    check("Ctrl+Y refaz", bool(wait("!!__smoke.q('[data-testid=dirty-marker]')", 5, "refeito")))
    js("__smoke.key('s', { ctrlKey: true })")
    diff = wait("__smoke.text('[data-testid=diff]')", 8, "diff antes de salvar") or ""
    check("Ctrl+S mostra o diff antes de gravar", "WindowLeft" in diff and xml.read_bytes() == before, diff=diff[:300])
    shot("13-diff-salvar")
    js("__smoke.click('[data-testid=diff-confirm]')")
    check("salvar grava o X novo", bool(wait("!__smoke.q('[data-testid=dirty-marker]')", 8, "salvo")))
    check("XML no disco com o X novo", f'WindowLeft="{new_x}"'.encode() in xml.read_bytes())

    # Descartar ao trocar de XML.
    saved = xml.read_bytes()
    js(f"__smoke.setValue('input[name=geometry-x]', '{new_x + 5}')")
    js("__smoke.q('input[name=geometry-x]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
    wait("!!__smoke.q('[data-testid=dirty-marker]')", 5, "alterado de novo")
    js("__smoke.click('[data-testid=topbar] button')")  # casinha
    asked = wait("(__smoke.text('[role=dialog]') || '').includes('alterações não salvas')", 5, "descartar ao ir para a tela inicial")
    check("tela inicial pergunta Descartar alterações?", bool(asked))
    shot("14-descartar")
    js("__smoke.clickText('Cancelar', '[role=dialog]')")
    check("Cancelar mantém o XML aberto", bool(wait("!__smoke.q('[data-testid=home]') && !!__smoke.q('[data-testid=dirty-marker]')", 3, "cancelado")))
    js("__smoke.click('[data-testid=topbar] button')")
    wait("!!__smoke.q('[role=dialog]')", 5, "pergunta de novo")
    js("__smoke.clickText('Descartar', '[role=dialog]')")
    check("Descartar vai para a tela inicial sem gravar", bool(wait("!!__smoke.q('[data-testid=home]')", 5, "home")) and xml.read_bytes() == saved)
    js("__smoke.clickText('Continuar', '[data-testid=home]')")
    wait("__smoke.text('[data-testid=breadcrumb]')", 8, "volta ao XML")


def _pick_text_record():
    """Um texto do T_TextIndex.ini da cópia do jogo que só aparece uma vez (busca sem ambiguidade)."""
    from gf_ui_editor.text_data import TRANSLATE_DIR, TextFile

    text_file = TextFile.load(GAME / TRANSLATE_DIR / "T_TextIndex.ini")
    lowered = text_file.text.lower()
    for record in text_file.records:
        value = record.fields[0] if record.fields else ""
        if 12 <= len(value) <= 40 and value.isascii() and value.replace(" ", "").isalpha() and lowered.count(value.lower()) == 1:
            return text_file, record
    raise RuntimeError("nenhum texto único no T_TextIndex.ini da cópia do jogo")


def texts_flow(project_root: Path) -> None:
    from gf_ui_editor import text_data
    from gf_ui_editor.text_data import TRANSLATE_DIR, TextFile

    text_file, record = _pick_text_record()
    new_text = "Smoke " + record.fields[0]
    js("__smoke.key('4', { ctrlKey: true })")
    check("Ctrl+4 mostra a tela de Textos", bool(wait("!!__smoke.q('[data-testid=texts-page]')", 5, "textos")))
    summary = wait("__smoke.text('[data-testid=texts-summary]')", 10, "resumo dos textos") or ""
    check("resumo sem busca", "Digite para buscar" in summary, summary=summary)
    js(f"__smoke.setValue('input[name=texts-search]', {json.dumps(record.fields[0])})")
    row = f"[data-testid=text-row][data-id=\"{record.record_id}\"]"
    found = wait(f"!!__smoke.q('{row}')", 30, "resultado da busca de texto")
    check("busca acha o texto", bool(found), text=record.fields[0], id=record.record_id)
    summary = js("__smoke.text('[data-testid=texts-summary]')") or ""
    check("resumo com o total", "resultado" in summary, summary=summary)
    shot("15-textos-busca")
    js(f"__smoke.click('{row}')")
    check("editor flutuante abre", bool(wait("!!__smoke.q('[data-testid=text-editor] textarea')", 5, "editor de texto")))
    editor = js("__smoke.text('[data-testid=text-editor]')") or ""
    check("editor mostra arquivo, ID e a dica do |", f"T_TextIndex.ini · ID {record.record_id}" in editor and '"|"' in editor, editor=editor[:200])
    js("(() => { const area = __smoke.q('[data-testid=text-editor] textarea'); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;"
       f" set.call(area, {json.dumps(new_text)}); area.dispatchEvent(new Event('input', {{ bubbles: true }})); return true }})()")
    shot("16-textos-editor")
    js("__smoke.click('[data-testid=text-save]')")
    check("editor fecha ao salvar", bool(wait("!__smoke.q('[data-testid=text-editor]')", 8, "salvar texto")))
    edits = text_data.load_edits(project_root)
    saved = edits.get("T_TextIndex.ini", {}).get(record.record_id)
    check("project.db guarda a edição", saved is not None and saved.fields[0] == new_text and saved.original[0] == record.fields[0])
    check("jogo só muda ao enviar", TextFile.load(GAME / TRANSLATE_DIR / "T_TextIndex.ini").by_id[record.record_id].fields == record.fields)
    js("__smoke.setValue('input[name=texts-search]', '')")
    marked = wait(f"(__smoke.q('{row}') || {{}}).dataset && __smoke.q('{row}').dataset.state", 8, "marcador de editado")
    check("sem busca, o texto editado aparece com ●", marked == "edited" and "●" in (js(f"__smoke.text('{row}')") or ""), state=marked)

    js("__smoke.key('F5')")
    status = wait("(__smoke.text('[data-testid=status-message]') || '').includes('Textos:') && __smoke.text('[data-testid=status-message]')", 60, "F5 com textos")
    check("F5 envia o texto para data/Translate", status is not None and "Textos: 1 arquivo" in status, status=status)
    sent = TextFile.load(GAME / TRANSLATE_DIR / "T_TextIndex.ini").by_id[record.record_id].fields[0]
    check("data/Translate da cópia do jogo com o texto novo", sent == new_text, sent=sent)
    shot("17-textos-enviados")
    js("__smoke.key('1', { ctrlKey: true })")


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
