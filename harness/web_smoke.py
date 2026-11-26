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
# Sem rede de verdade: o manifesto e o GitHub respondem pelo que o roteiro puser aqui.
MANIFEST: list = [None]
remote_manifest.fetch = lambda *args, **kwargs: MANIFEST[0]
NET: dict[str, bytes] = {}  # URL -> resposta simulada; URL ausente = sem conexão


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data, self._offset = data, 0
        self.headers = {"Content-Length": str(len(data))}

    def read(self, size: int = -1) -> bytes:
        end = len(self._data) if size is None or size < 0 else self._offset + size
        chunk, self._offset = self._data[self._offset:end], min(end, len(self._data))
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_request(url: str):
    if url not in NET:
        raise OSError(f"rede desligada no smoke: {url}")
    return _FakeResponse(NET[url])


from gf_ui_editor import updater  # noqa: E402

updater._request = _fake_request
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

def _theme(label: str) -> None:
    # Engrenagem enxuta: o tema fica em Configurações → Geral.
    key = {"Escuro": "dark", "Meia-noite": "midnight", "Claro": "light", "Cappuccino": "cappuccino", "Rosa": "rosa"}[label]
    _open_settings()
    wait("!!__smoke.q('[data-setting=web_theme]')", 5, "seção Geral carregada")
    js(f"__smoke.click('[data-setting=web_theme] [data-value={key}]')")
    _close_settings()


def polish() -> None:
    check("divisores dos painéis", bool(js("!!__smoke.q('[data-testid=resize-left]')")))
    js("__smoke.key('1', { ctrlKey: true })")
    wait("!!__smoke.q('[data-section=all] [data-testid=layer-check]')", 8, "checkbox de camada")
    layer_file = js(
        "(() => { const on = new Set(__smoke.all('[data-section=layers] [data-file]').map((r) => r.dataset.file));"
        " const row = __smoke.all('[data-section=all] [data-file]').find((r) => !on.has(r.dataset.file) && r.dataset.file.endsWith('.xml'));"
        " return row ? row.dataset.file : null })()"
    )
    toggle = (
        "(() => { const row = __smoke.all('[data-section=all] [data-file]').find((r) => r.dataset.file === %s);"
        " if (row) row.querySelector('[data-testid=layer-check]').click(); return !!row })()" % json.dumps(layer_file)
    )
    js(toggle)
    in_layers = "__smoke.all('[data-section=layers] [data-file]').some((r) => r.dataset.file === %s)" % json.dumps(layer_file)
    check("marcar camada pela lista", bool(layer_file) and bool(wait(in_layers, 8, "camada marcada")), file=layer_file)
    js(toggle)
    check("desmarcar camada pela lista", bool(wait("!" + in_layers, 8, "camada desmarcada")))
    # Alça entre seções: arrastar muito para baixo não tira nada da tela e só mexe nas duas vizinhas.
    js("(() => { const row = __smoke.all('[data-section=all] [data-file]').find((r) => r.dataset.file.endsWith('.xml')); row.querySelector('[data-testid=layer-check]').click() })()")
    wait("!!__smoke.q('[data-testid^=resize-]')", 8, "alça entre seções")
    result = js(
        "(() => { const h = __smoke.q('[data-testid^=resize-]'); const box = h.closest('[data-testid=files-panel]').getBoundingClientRect();"
        " const r = h.getBoundingClientRect(); const y = r.top + 2;"
        " h.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientY: y }));"
        " window.dispatchEvent(new MouseEvent('mousemove', { clientY: y + 2000 }));"
        " window.dispatchEvent(new MouseEvent('mouseup', { clientY: y + 2000 }));"
        " const secs = __smoke.all('[data-section]').map((s) => s.getBoundingClientRect());"
        " return secs.every((s) => s.bottom <= box.bottom + 1 && s.height >= 40) })()"
    )
    time.sleep(0.3)
    check("alça entre seções não tira seção da tela", bool(result))
    js("__smoke.click('[data-testid=stz-pill]')")
    card = wait("__smoke.text('[data-testid=stz-card]')", 5, "cartão STZ") or ""
    time.sleep(0.6)  # animação de entrada
    check("cartão STZ Labs com quem ajudou", "QUEM AJUDOU A CONSTRUIR" in card.upper() and "Discord" in card, card=card[:160])
    shot("15b-stz-labs")
    js("document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))")
    check("cartão STZ fecha ao clicar fora", bool(wait("!__smoke.q('[data-testid=stz-card]')", 3, "fecha cartão")))
    for label, key in (("Claro", "light"), ("Meia-noite", "midnight")):
        _theme(label)
        changed = wait(f"document.documentElement.dataset.theme === '{key}'", 5, f"tema {key}")
        time.sleep(0.5)
        check(f"tema {label}", bool(changed))
        shot(f"15c-tema-{key}")
    check("tema salvo nas preferências", app_module.prefs.get("web_theme") == "midnight")
    _theme("Escuro")
    wait("document.documentElement.dataset.theme === 'dark'", 5, "tema escuro")

THEMES = (("Escuro", "dark"), ("Claro", "light"), ("Meia-noite", "midnight"))


def _set_theme(label: str, key: str) -> bool:
    _theme(label)
    changed = wait(f"document.documentElement.dataset.theme === '{key}'", 5, f"tema {key}")
    time.sleep(0.4)  # a troca de tema anima as cores
    return bool(changed)


def _close_how_to() -> bool:
    js("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    return bool(wait("!__smoke.q('[data-testid=how-to]')", 5, "fecha Como usar"))


def how_to_flow() -> None:
    """F1 abre o "Como usar" (show_how_to da clássica); também pela engrenagem e pelo Ctrl+K. Captura nos 3 temas."""
    prevented = js("(() => { const e = new KeyboardEvent('keydown', { key: 'F1', bubbles: true, cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented })()")
    text = wait("__smoke.text('[data-testid=how-to]')", 5, "Como usar pelo F1") or ""
    check("F1 abre o Como usar", bool(text) and bool(prevented), prevented=prevented)
    steps = js("__smoke.all('[data-testid=how-to-step]').length")
    check("Como usar com os cinco passos da clássica", steps == 5 and "Do projeto ao jogo em cinco passos" in text
          and all(step in text for step in ("Crie um projeto", "Edite e salve", "Envie para o jogo com F5", "Entenda o preview", "Compartilhe")),
          steps=steps)
    shortcuts = js("__smoke.text('[data-testid=how-to-shortcuts]')") or ""
    check("Como usar com o vídeo e os atalhos", bool(wait("!!__smoke.q('[data-testid=how-to-video]')", 5, "link do vídeo"))
          and all(key in shortcuts for key in ("Ctrl+Shift+N", "Ctrl+Shift+O", "F5")), shortcuts=shortcuts)
    entered = js("getComputedStyle(__smoke.q('[role=dialog]')).animationName")
    check("Como usar com animação de entrada", entered == "dialog-in", animation=entered)
    time.sleep(0.6)  # passos entram em sequência
    shot("19a-como-usar-dark")
    check("Esc fecha o Como usar", _close_how_to())

    # Engrenagem: logo depois de Configurações…
    js("__smoke.click('[data-testid=side-rail] button[aria-label=\"Configurações\"]')")
    wait("!!__smoke.q('[role=menu]')", 5, "menu da engrenagem")
    items = js("__smoke.all('[role=menu] [role=menuitem]').map((b) => b.innerText.trim())") or []
    check("engrenagem tem Como usar depois de Configurações…", len(items) > 1 and items[1].startswith("Como usar"), items=items)
    js("__smoke.clickText('Como usar', '[role=menu]')")
    check("Como usar pela engrenagem", bool(wait("!!__smoke.q('[data-testid=how-to]')", 5, "Como usar pela engrenagem")))
    _close_how_to()

    # Ctrl+K.
    js("__smoke.key('k', { ctrlKey: true })")
    wait("!!__smoke.q('[data-testid=command-input]')", 5, "paleta")
    js("__smoke.setValue('[data-testid=command-input]', 'como usar')")
    wait("((__smoke.q('[cmdk-item][data-selected=true]') || {}).innerText || '').includes('Como usar')", 5, "comando Como usar")
    js("__smoke.q('[data-testid=command-input]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))")
    check("Como usar pelo Ctrl+K", bool(wait("!__smoke.q('[data-testid=command-palette]') && !!__smoke.q('[data-testid=how-to]')", 5, "Como usar pela paleta")))
    _close_how_to()

    for label, key in THEMES[1:]:
        _set_theme(label, key)
        js("__smoke.key('F1')")
        wait("!!__smoke.q('[data-testid=how-to]')", 5, f"Como usar no tema {key}")
        time.sleep(0.7)
        colors = js("(() => { const d = __smoke.q('[role=dialog]'); const h = d.querySelector('h2'); return [getComputedStyle(d).backgroundColor, getComputedStyle(h).color] })()") or []
        check(f"Como usar no tema {label} segue o tema", len(colors) == 2 and colors[0] != colors[1], colors=colors)
        shot(f"19b-como-usar-{key}")
        _close_how_to()
        if os.environ.get("GF_SMOKE_TOUR"):
            theme_tour(key)
    _set_theme("Escuro", "dark")


def theme_tour(key: str) -> None:
    """Só com GF_SMOKE_TOUR=1: capturas das telas novas no tema (conferência visual, sem verificações)."""
    js("__smoke.key('k', { ctrlKey: true })")
    wait("!!__smoke.q('[data-testid=command-input]')", 5, "paleta")
    time.sleep(0.4)
    shot(f"tour-{key}-paleta")
    js("__smoke.q('[data-testid=command-input]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))")
    wait("!__smoke.q('[data-testid=command-palette]')", 5, "fecha paleta")
    _open_settings()
    time.sleep(0.4)
    shot(f"tour-{key}-configuracoes")
    _settings_section("updates")
    time.sleep(0.3)
    shot(f"tour-{key}-configuracoes-atualizacoes")
    _close_settings()
    js("__smoke.key('3', { ctrlKey: true })")
    wait("!!__smoke.q('[data-testid=tree-row]')", 5, "árvore")
    js("__smoke.click('[data-testid=tree-row][data-index=\"1\"]')")
    time.sleep(0.3)
    js("__smoke.key('u', { ctrlKey: true })")
    wait("!!__smoke.q('[data-testid=source-panel] .cm-content')", 5, "código")
    time.sleep(0.5)
    shot(f"tour-{key}-codigo")
    js("__smoke.key('u', { ctrlKey: true })")
    wait("!__smoke.q('[data-testid=source-panel]')", 5, "fecha código")
    if js("(() => { const b = __smoke.q('[data-testid=open-atlas]'); return !!b && !b.disabled })()"):
        js("__smoke.click('[data-testid=open-atlas]')")
        wait("!!__smoke.q('[data-testid=atlas-surface]')", 10, "atlas")
        time.sleep(1.0)
        shot(f"tour-{key}-atlas")
        js("__smoke.click('.gf-atlas-close')")
        wait("!__smoke.q('[data-testid=atlas-surface]')", 5, "fecha atlas")
    js("__smoke.key('4', { ctrlKey: true })")
    time.sleep(0.5)
    shot(f"tour-{key}-textos")
    js("__smoke.key('1', { ctrlKey: true })")
    time.sleep(0.3)
    # Divisor dos painéis e alça entre seções com o destaque de "arrastando".
    js("(() => { __smoke.q('[data-testid=resize-left]').classList.add('is-dragging');"
       " const r = __smoke.q('.gf-row-resize'); if (r) r.classList.add('is-dragging'); return true })()")
    time.sleep(0.3)
    shot(f"tour-{key}-divisores")
    js("(() => { __smoke.all('.is-dragging').forEach((e) => e.classList.remove('is-dragging')); return true })()")


def _hex_rgb(value: str) -> tuple[float, ...] | None:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:  # o build minifica #ffffff para #fff
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        return None
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _contrast(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        rgb = _hex_rgb(color)
        if rgb is None:
            return -1
        r, g, b = ((c / 12.92) if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    a, b = luminance(first), luminance(second)
    if a < 0 or b < 0:
        return 0.0
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# Pares (texto, fundo, mínimo) conferidos nos temas novos: WCAG AA (4.5) para texto,
# 3 para ícones, texto secundário curto e cores de estado.
CONTRAST_PAIRS = (
    ("text", "panel", 4.5), ("text", "window", 4.5), ("text", "card", 4.5), ("text", "menu", 4.5),
    ("bright", "chrome", 4.5), ("muted", "panel", 3.0), ("muted", "card", 3.0), ("icon", "chrome", 3.0),
    ("accent-text", "panel", 4.5), ("accent-text", "accent-soft", 4.5), ("on-accent", "accent", 4.5),
    ("gold", "panel", 3.0), ("warning", "warning-bg", 4.5), ("danger", "panel", 3.0), ("success", "panel", 3.0),
    ("text", "selected", 4.5),
)


def _theme_contrast(key: str) -> None:
    names = sorted({name for pair in CONTRAST_PAIRS for name in pair[:2]})
    values = js("(() => { const s = getComputedStyle(document.documentElement); return Object.fromEntries(%s.map((n) => [n, s.getPropertyValue('--color-' + n).trim()])) })()" % json.dumps(names)) or {}
    low = {f"{a}/{b}": round(_contrast(values.get(a, ""), values.get(b, "")), 2) for a, b, minimum in CONTRAST_PAIRS
           if _contrast(values.get(a, ""), values.get(b, "")) < minimum}
    check(f"contraste legível no tema {key}", bool(values) and not low, low=low)


def _texture_peek(key: str) -> None:
    """Ctrl+2, mouse parado numa textura: o cartão aparece ao lado com miniatura, tamanho e formato."""
    js("__smoke.key('2', { ctrlKey: true })")
    wait("__smoke.all('[data-section=all] [data-file]').some((r) => r.dataset.file.toLowerCase().endsWith('.dds'))", 8, "lista de texturas")
    hover = (
        "(() => { const rows = __smoke.all('[data-section=all] [data-file]').filter((r) => r.dataset.file.toLowerCase().endsWith('.dds'));"
        " const row = rows[%d]; if (!row) return null; const r = row.getBoundingClientRect();"
        " row.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: r.left + 30, clientY: r.top + 8 })); return row.dataset.file })()"
    )
    name = js(hover % 3)
    time.sleep(0.15)
    early = js("!!__smoke.q('[data-testid=texture-peek]')")
    card = wait("(() => { const f = __smoke.text('[data-testid=texture-peek-format]'); return f && __smoke.q('[data-testid=texture-peek] canvas') && f })()", 10, "cartão da textura")
    size = js("__smoke.text('[data-testid=texture-peek-size]')") or ""
    check(f"prévia da textura aparece depois do atraso ({key})", bool(name) and not early and bool(card) and "px" in size,
          file=name, format=card, size=size)
    placed = js("(() => { const c = __smoke.q('[data-testid=texture-peek]'); if (!c) return false; const b = c.getBoundingClientRect();"
                " const p = __smoke.q('[data-testid=files-panel]').getBoundingClientRect(); return b.left >= p.right && b.right <= innerWidth })()")
    check(f"cartão ao lado da lista ({key})", bool(placed))
    time.sleep(0.5)
    shot(f"21-{key}-textura-hover")
    # Segue a linha de baixo e some ao sair da lista.
    other = js(hover % 4) or ""
    short = other.replace("/", "\\").split("\\")[-1]
    followed = wait("(__smoke.text('[data-testid=texture-peek-name]') || '') === %s" % json.dumps(short), 3, "cartão segue a linha")
    check(f"cartão segue a linha sob o mouse ({key})", bool(followed), file=other)
    js("(() => { const list = __smoke.q('[data-section=all] [data-file]').parentElement.parentElement;"
       " list.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body })); return true })()")
    check(f"cartão some ao sair da lista ({key})", bool(wait("!__smoke.q('[data-testid=texture-peek]')", 3, "cartão some")))
    js("__smoke.key('1', { ctrlKey: true })")
    wait("__smoke.all('[data-section=all] [data-file]').some((r) => r.dataset.file.toLowerCase().endsWith('.xml'))", 5, "volta aos XMLs")


def new_themes_flow() -> None:
    """Cappuccino e Rosa: contraste dos tokens e capturas da tela inicial, canvas com painel,
    atlas, Ver código, Ctrl+K, Configurações, tooltip/toast e a prévia flutuante das texturas."""
    for label, key in (("Cappuccino", "cappuccino"), ("Rosa", "rosa")):
        check(f"tema {label}", _set_theme(label, key))
        _theme_contrast(key)
        # Canvas com o painel de propriedades (Elementos, um controle selecionado) e um tooltip.
        js("__smoke.key('3', { ctrlKey: true })")
        wait("!!__smoke.q('[data-testid=tree-row]')", 5, "árvore")
        js("__smoke.click('[data-testid=tree-row][data-index=\"1\"]')")
        time.sleep(0.6)
        js("(() => { const b = __smoke.q('[data-testid=side-rail] button[title], [data-testid=side-rail] button[data-gf-title]');"
           " if (b) b.dispatchEvent(new PointerEvent('pointerover', { bubbles: true })); return !!b })()")
        tip = wait("!!__smoke.q('.gf-tooltip')", 3, "tooltip")
        check(f"tooltip no tema {label}", bool(tip))
        # Toast (sonner): réplica com a mesma classe para conferir as cores do tema.
        js("(() => { const t = document.createElement('div'); t.className = 'gf-toast'; t.dataset.smokeToast = '1';"
           " t.textContent = 'Aberto no Notepad++. Depois de salvar lá, aperte Ctrl+R aqui para ver a mudança.';"
           " Object.assign(t.style, { position: 'fixed', right: '24px', bottom: '48px', padding: '14px 16px', borderRadius: '8px', width: '340px', fontSize: '13px', zIndex: 200 });"
           " document.body.append(t); return true })()")
        shot(f"20-{key}-canvas-painel")
        js("(() => { __smoke.all('[data-smoke-toast]').forEach((e) => e.remove()); window.dispatchEvent(new PointerEvent('pointerdown')); return true })()")
        # Ver código.
        js("__smoke.key('u', { ctrlKey: true })")
        if wait("!!__smoke.q('[data-testid=source-panel] .cm-content')", 5, "código"):
            time.sleep(0.5)
            shot(f"20-{key}-codigo")
        js("__smoke.key('u', { ctrlKey: true })")
        wait("!__smoke.q('[data-testid=source-panel]')", 5, "fecha código")
        # Atlas.
        if js("(() => { const b = __smoke.q('[data-testid=open-atlas]'); return !!b && !b.disabled })()"):
            js("__smoke.click('[data-testid=open-atlas]')")
            check(f"atlas abre no tema {label}", bool(wait("!!__smoke.q('[data-testid=atlas-surface]')", 10, "atlas")))
            time.sleep(1.0)
            shot(f"20-{key}-atlas")
            js("__smoke.click('.gf-atlas-close')")
            wait("!__smoke.q('[data-testid=atlas-surface]')", 5, "fecha atlas")
        # Ctrl+K.
        js("__smoke.key('k', { ctrlKey: true })")
        wait("!!__smoke.q('[data-testid=command-input]')", 5, "paleta")
        js("__smoke.setValue('[data-testid=command-input]', 'tema')")
        listed = wait("(() => { const t = __smoke.text('[data-testid=command-palette]') || ''; return t.includes('Cappuccino') && t.includes('Rosa') })()", 5, "temas na paleta")
        check(f"Ctrl+K lista Cappuccino e Rosa ({label})", bool(listed))
        time.sleep(0.3)
        shot(f"20-{key}-paleta")
        js("__smoke.q('[data-testid=command-input]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))")
        wait("!__smoke.q('[data-testid=command-palette]')", 5, "fecha paleta")
        # Configurações (o seletor de tema com os cinco temas e os ícones).
        _open_settings()
        wait("!!__smoke.q('[data-setting=web_theme]')", 5, "seção Geral")
        options = js("__smoke.all('[data-setting=web_theme] [data-value]').map((b) => [b.dataset.value, !!b.querySelector('svg')])") or []
        check(f"seletor com os cinco temas e ícones ({label})",
              [o[0] for o in options] == ["dark", "midnight", "light", "cappuccino", "rosa"] and all(o[1] for o in options), options=options)
        fits = js("(() => { const s = __smoke.q('[data-setting=web_theme]'); const d = s.closest('[role=dialog]') || document.body;"
                  " return s.getBoundingClientRect().right <= d.getBoundingClientRect().right + 1 })()")
        check(f"seletor de tema cabe em Configurações ({label})", bool(fits))
        time.sleep(0.3)
        shot(f"20-{key}-configuracoes")
        _close_settings()
        # Prévia flutuante das texturas.
        _texture_peek(key)
        # Tela inicial (e volta pelo Continuar).
        js("__smoke.click('[data-testid=topbar] button')")
        wait("!!__smoke.q('[data-testid=home-project-row]')", 10, "tela inicial")
        time.sleep(0.6)
        shot(f"20-{key}-home")
        js("__smoke.clickText('Continuar', '[data-testid=home]')")
        wait("!!__smoke.q('[data-testid=breadcrumb]')", 8, "continuar")
        time.sleep(0.5)
    check("tema Rosa salvo nas preferências", app_module.prefs.get("web_theme") == "rosa")
    _set_theme("Escuro", "dark")


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
    canvas_toolbar()

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

    # 10d. Polimento: pílula STZ Labs, temas, divisores dos painéis.
    polish()

    # 10d2. Como usar (F1), nos 3 temas.
    how_to_flow()

    # 10d3. Temas Cappuccino e Rosa (capturas nas telas principais) e a prévia das texturas.
    new_themes_flow()

    # 10e. Bloco 4: Configurações, atualizador e manifesto remoto.
    settings_flow()
    hidden_buttons_flow()
    updates_flow()
    manifest_flow()
    standalone_flow(project_root)

    # 10f. Notas de versão (acordeão, filtro, linha do tempo), fontes e o cartão STZ nas duas vistas.
    release_notes_flow()
    fonts_flow()
    stz_helpers_flow()

    # 11. Idioma: inglês pela tela de Configurações (a engrenagem só tem Configurações,
    # Como usar, Novidades, Verificar atualizações e Sobre).
    js("__smoke.click('[data-testid=side-rail] button[aria-label=\"Configurações\"]')")
    wait("!!__smoke.q('[role=menu]')", 5, "menu configurações")
    gear = js("__smoke.all('[role=menu] [role=menuitem]').map((b) => b.innerText.trim())") or []
    check("engrenagem enxuta", len(gear) == 5 and gear[0] == "Configurações…" and gear[1].startswith("Como usar")
          and not any("Idioma" in item or "Tema" in item for item in gear), items=gear)
    js("document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))")
    wait("!__smoke.q('[role=menu]')", 3, "fecha engrenagem")
    _open_settings()
    js("__smoke.setValue('select[name=language]', 'en_US')")
    wait("(__smoke.text('[data-testid=topbar]') || '').includes('Send to game')", 5, "inglês")
    _close_settings()
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


def standalone_flow(project_root: Path) -> None:
    from System import Action

    loose = OUT / "standalone"
    loose.mkdir()
    xml = loose / "SmokeStandalone.xml"
    second = loose / "SecondStandalone.xml"
    texture = loose / "SmokeStandalone.dds"
    shutil.copyfile(next((GAME / "UI").glob("*.dds")), texture)
    original = (
        b'<Root_Node><BaseWndProperty WindowID="1" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="80">'
        b'<BackGroundMap BGmap="SmokeStandalone.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="8" NorUVHeight="9"/>'
        b'</BackGroundMap></BaseWndProperty></Root_Node>'
    )
    xml.write_bytes(original)
    second.write_bytes(b"<Standalone/>")
    ignored = loose / "notes.txt"
    ignored.write_bytes(b"text")
    position = js("(() => { const box = __smoke.q('[data-testid=center]').getBoundingClientRect();"
                  "return { x: Math.round(box.left + 100), y: Math.round(box.top + 100) } })()")
    data = {"items": [], "files": [str(second), str(ignored), str(xml)], "dragOperationsMask": 1}
    native = window.native
    for kind in ("dragEnter", "dragOver", "drop"):
        pending = []
        params = json.dumps({"type": kind, **position, "data": data})
        native.Invoke(Action(lambda: pending.append(native.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(
            "Input.dispatchDragEvent", params,
        ))))
        if not pending[0].Wait(5000):
            raise TimeoutError(f"WebView2 drop: {kind}")

    bar = '[data-testid=standalone-bar]'
    check("drop nativo abre todos os XMLs e mantém o projeto", bool(wait(
        f"!!__smoke.q('{bar}') && __smoke.all('[data-standalone-file]').length === 2"
        " && __gfDoc.state().path?.endsWith('SmokeStandalone.xml')", 12, "drop XMLs avulsos",
    )) and api.shell_state()["project"]["root"] == str(project_root))
    js("window.dropTexture = null; pywebview.api.asset_base(__gfDoc.state().path).then("
       "base => fetch(base + 'SmokeStandalone.dds')).then(response => response.arrayBuffer()).then("
       "data => window.dropTexture = new TextDecoder().decode(data.slice(0, 4))); true")
    check("WebView2 serve a textura ao canvas e ao atlas", bool(wait(
        "window.dropTexture === 'DDS '", 8, "textura avulsa do disco",
    )))
    js("__smoke.key('3', { ctrlKey: true })")
    wait("__smoke.click('[data-testid=tree-row][data-index=\"0\"]')", 5, "selecionar controle avulso")
    wait("!!__smoke.q('input[name=geometry-x]')", 5, "geometria avulsa")
    js("__smoke.setValue('input[name=geometry-x]', '37');"
       "__smoke.q('input[name=geometry-x]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
    wait("__gfDoc.state().dirty", 5, "XML avulso editado")
    js(f"__smoke.clickText('Salvar no lugar', '{bar}')")
    diff = wait("__smoke.text('[data-testid=diff]')", 5, "diff avulso") or ""
    check("Salvar no lugar mostra o diff antes da gravação", 'WindowLeft="37"' in diff and xml.read_bytes() == original)
    js("__smoke.click('[data-testid=diff-confirm]')")
    wait("!__gfDoc.state().dirty", 5, "avulso salvo")
    backup = list(loose.glob("SmokeStandalone.before-gf-ui-editor-*.xml"))
    check("XML avulso salvo com backup exato ao lado", len(backup) == 1 and backup[0].read_bytes() == original
          and b'WindowLeft="37"' in xml.read_bytes())
    js(f"__smoke.clickText('Importar para o projeto', '{bar}')")
    wait("!!__smoke.q('[role=dialog] input[type=checkbox]:checked')", 5, "importar com texturas")
    js("__smoke.clickText('Importar', '[role=dialog]')")
    target = project_root / "ui" / xml.name
    check("Importar mantém o documento ativo no workspace do projeto", bool(wait(
        f"!__smoke.q('{bar}') && __gfDoc.state().path === {json.dumps(str(target))}", 8, "documento promovido",
    )))
    check("Importar copia XML editado e a textura que faltava", target.read_bytes() == xml.read_bytes()
          and (target.parent / texture.name).read_bytes() == texture.read_bytes())
    js("__smoke.key('1', { ctrlKey: true })")
    check("lista retém o outro avulso após a importação", bool(wait(
        "__smoke.all('[data-standalone-file]').length === 1"
        " && __smoke.q('[data-standalone-file]').textContent === 'SecondStandalone.xml'", 5, "lista avulsa",
    )))


def _open_settings() -> bool:
    js("__smoke.click('[data-testid=side-rail] button[aria-label=\"Configurações\"]')")
    wait("!!__smoke.q('[role=menu]')", 5, "menu da engrenagem")
    js("__smoke.clickText('Configurações…', '[role=menu]')")
    return bool(wait("!!__smoke.q('[data-testid=settings]')", 5, "tela de Configurações"))


def _close_settings() -> None:
    js("__smoke.click('[data-testid=settings-close]')")
    wait("!__smoke.q('[data-testid=settings]')", 5, "fechar Configurações")


def _settings_section(key: str) -> bool:
    js(f"__smoke.click('[data-testid=settings] [data-section={key}]')")
    return bool(wait(f"!!__smoke.q('[data-testid=settings-{key}]')", 5, f"seção {key}"))


def _dialog_with(text: str) -> str:
    return f"(() => {{ const d = __smoke.all('[role=dialog]').find((e) => e.innerText.includes({json.dumps(text)})); return d ? d.innerText : null }})()"


def settings_flow() -> None:
    check("engrenagem abre as Configurações", _open_settings())
    time.sleep(0.5)  # animação de entrada
    shot("16a-configuracoes-geral")
    check("seção Geral com idioma e tema", bool(js("!!__smoke.q('select[name=language]') && !!__smoke.q('[data-setting=web_theme]')")))

    check("seção Envio", _settings_section("publish"))
    before = app_module.prefs.publish_on_save
    js("__smoke.click('[data-setting=publish_on_save]')")
    check("switch grava Enviar ao salvar", bool(wait(
        f"__smoke.q('[data-setting=publish_on_save]').getAttribute('aria-checked') === '{str(not before).lower()}'", 5, "switch envio",
    )) and app_module.prefs.publish_on_save is (not before))
    time.sleep(0.3)
    shot("16b-configuracoes-envio")
    js("__smoke.click('[data-setting=publish_on_save]')")
    wait(f"__smoke.q('[data-setting=publish_on_save]').getAttribute('aria-checked') === '{str(before).lower()}'", 5, "switch de volta")
    time.sleep(0.2)
    check("Enviar ao salvar volta ao que era", app_module.prefs.publish_on_save is before)

    check("seção Editor", _settings_section("editor"))
    js("__smoke.setValue('select[name=navigation_style]', 'paintnet')")
    check("estilo de navegação salvo", bool(wait("__smoke.q('select[name=navigation_style]').value === 'paintnet'", 5, "navegação"))
          and app_module.prefs.navigation_style == "paintnet")
    js("__smoke.setValue('select[name=navigation_style]', 'corel')")
    wait("__smoke.q('select[name=navigation_style]').value === 'corel'", 5, "navegação corel")

    check("seção Tela", _settings_section("screen"))
    js("__smoke.setValue('select[name=game_resolution]', '1280x720')")
    on_canvas = wait("__smoke.q('select[aria-label=Tela]')?.value === '1280x720'", 8, "resolução 1280x720 no canvas")
    check("resolução pelas Configurações vale no canvas", bool(on_canvas) and app_module.prefs.game_resolution == "1280x720",
          canvas=js("__smoke.q('select[aria-label=Tela]')?.value ?? null"), saved=app_module.prefs.game_resolution)
    shot("16c-configuracoes-tela")
    js("__smoke.setValue('select[name=game_resolution]', 'game')")
    wait("__smoke.q('select[aria-label=Tela]')?.value === 'game'", 8, "resolução do jogo de volta")
    check("resolução volta a seguir o jogo", app_module.prefs.game_resolution == "game")
    _close_settings()


def hidden_buttons_flow() -> None:
    """Configurações sem botões apagados: o que não tem o que fazer não aparece."""
    _open_settings()
    disabled = []
    for section in ("general", "editor", "screen", "publish", "updates"):
        _settings_section(section)
        time.sleep(0.25)
        disabled += js(
            "__smoke.all('[data-testid=settings] button:disabled').map((b) => b.innerText.trim() || b.getAttribute('aria-label'))"
        ) or []
    check("Configurações sem botões apagados", disabled == [], disabled=disabled)
    _settings_section("general")
    time.sleep(0.3)
    row = js("__smoke.text('[data-testid=settings-review-skipped]')") or ""
    check("sem versão pulada, só o texto", "Nenhuma versão pulada" in row
          and not js("!!__smoke.q('[data-testid=settings-review-skipped] button')"), row=row)
    notices = js("__smoke.text('[data-testid=settings-review-notices]')") or ""
    check("sem avisos vistos, só o texto", not js("!!__smoke.q('[data-testid=settings-review-notices] button')"), row=notices)
    shot("25-configuracoes-sem-botoes-apagados")
    _close_settings()


WHATS_NEW = "[data-testid=whats-new]"


def release_notes_flow() -> None:
    _open_settings()
    _settings_section("updates")
    js("__smoke.clickText('Novidades desta versão', '[data-testid=settings-updates]')")
    check("Novidades abre", bool(wait(f"!!__smoke.q('{WHATS_NEW} [data-testid=release-notes]')", 8, "Novidades")))
    time.sleep(0.6)
    chips = js(f"__smoke.all('{WHATS_NEW} [data-filter]').map((c) => [c.dataset.filter, c.innerText.trim()])") or []
    check("chips de categoria com contagem", len(chips) >= 2 and chips[0][0] == "all", chips=chips)
    check("destaques no topo", (js(f"__smoke.all('{WHATS_NEW} .gf-notes-highlight').length") or 0) >= 3)
    closed = js(f"__smoke.all('{WHATS_NEW} .gf-notes-item-head[aria-expanded=false]').length") or 0
    check("lista recolhida (só títulos)", closed > 3 and not js(f"!!__smoke.q('{WHATS_NEW} .gf-notes-item-text')"), closed=closed)
    js(f"__smoke.q('{WHATS_NEW} .gf-notes-item-head').click()")
    check("clicar no título abre a descrição", bool(wait(f"!!__smoke.q('{WHATS_NEW} .gf-notes-item-text')", 3, "item aberto")))
    time.sleep(0.4)
    shot("22a-novidades-acordeao")
    js(f"__smoke.click('{WHATS_NEW} [data-testid=notes-toggle-all]')")
    time.sleep(0.5)
    opened = js(f"__smoke.all('{WHATS_NEW} .gf-notes-item-head[aria-expanded=true]').length") or 0
    check("Expandir tudo", opened == closed, opened=opened, total=closed)
    js(f"__smoke.click('{WHATS_NEW} [data-testid=notes-toggle-all]')")
    time.sleep(0.3)
    js(f"__smoke.click('{WHATS_NEW} [data-filter=improved]')")
    time.sleep(0.5)
    kinds = js(f"__smoke.all('{WHATS_NEW} .gf-notes-item').map((e) => e.classList.contains('is-improved'))") or []
    check("filtro Melhorado mostra só melhorias", bool(kinds) and all(kinds)
          and not js(f"!!__smoke.q('{WHATS_NEW} .gf-notes-highlight')"), count=len(kinds))
    shot("22b-novidades-filtro")
    js(f"__smoke.click('{WHATS_NEW} [data-filter=all]')")
    if js("!!__smoke.q('[data-testid=whats-new-all]')"):
        js("__smoke.click('[data-testid=whats-new-all]')")
        versions = wait("__smoke.all('[data-testid=notes-timeline] [data-version]').map((b) => b.dataset.version)", 5, "linha do tempo") or []
        check("Ver todas: linha do tempo com as versões", len(versions) > 1, versions=versions)
        if len(versions) > 1:
            last = versions[-1]
            js("__smoke.all('[data-testid=notes-timeline] [data-version]').pop().click()")
            time.sleep(0.9)
            jumped = js(
                "(() => { const box = __smoke.q('[data-testid=notes-scroll]');"
                " const node = __smoke.all('[data-testid=notes-scroll] [data-release]').pop();"
                " const top = node.getBoundingClientRect().top - box.getBoundingClientRect().top;"
                " return box.scrollTop > 0 && (top < 40 || box.scrollTop + box.clientHeight >= box.scrollHeight - 2) })()"
            )
            check("linha do tempo pula até a versão", bool(jumped), version=last)
        time.sleep(0.3)
        shot("22c-novidades-todas-as-versoes")
    js("(() => { const d = __smoke.all('[role=dialog]').find((e) => e.querySelector('[data-testid=whats-new]'));"
       " const b = Array.from(d.querySelectorAll('button')).find((x) => x.innerText.trim() === 'Fechar'); b.click() })()")
    wait(f"!__smoke.q('{WHATS_NEW}')", 5, "fechar Novidades")
    _close_settings()


FONT_FAMILIES = {"system": "Segoe UI", "plex": "IBM Plex Sans", "inter": "Inter", "geist": "Geist"}
MONO_FAMILIES = {"plex": "IBM Plex Mono", "geist": "Geist Mono"}

WIDTH_PROBLEMS = """(() => { const bad = [];
  const name = (b) => b.innerText.trim() || b.getAttribute('aria-label') || b.dataset.testid;
  for (const b of __smoke.all('[data-testid=topbar] button, [data-testid=side-rail] button, [data-testid=settings] button')) {
    if (!b.offsetParent) continue;
    if (b.scrollWidth > b.clientWidth + 1) bad.push('cortado: ' + name(b));
  }
  const bar = __smoke.q('[data-testid=topbar]');
  if (bar && bar.scrollWidth > bar.clientWidth + 1) bad.push('barra superior transborda');
  const pill = __smoke.q('[data-testid=stz-pill]');
  if (pill) {
    const p = pill.getBoundingClientRect();
    for (const b of __smoke.all('[data-testid=topbar] button')) {
      if (b === pill || !b.offsetParent) continue;
      const r = b.getBoundingClientRect();
      if (r.right > p.left && r.left < p.right) bad.push('sobre a pílula: ' + name(b));
    }
  }
  return bad })()"""


def _width_problems() -> list:
    """Botões da barra superior, do trilho e das Configurações com texto cortado ou sobre a pílula."""
    return js(WIDTH_PROBLEMS) or []


def _font_loaded(family: str) -> str:
    return (f"document.fonts.status === 'loaded' && document.fonts.check('400 13px \"{family}\"')"
            f" && document.fonts.check('600 13px \"{family}\"')")


def fonts_flow() -> None:
    for key in ("plex", "inter", "geist", "system"):
        _open_settings()
        wait("!!__smoke.q('[data-setting=web_font]')", 5, "seletor de fonte")
        js(f"__smoke.click('[data-setting=web_font] [data-value={key}]')")
        family = FONT_FAMILIES[key]
        applied = wait(
            f"getComputedStyle(document.body).fontFamily.includes({json.dumps(family)})"
            f" && (document.documentElement.dataset.font || 'system') === '{key}'", 5, f"fonte {key}",
        )
        loaded = key == "system" or bool(wait(_font_loaded(family), 8, f"arquivo da fonte {key}"))
        check(f"fonte {family} aplicada na hora", bool(applied) and loaded, family=js("getComputedStyle(document.body).fontFamily"))
        time.sleep(0.2)
        check(f"fonte {family} salva em web_font", app_module.prefs.get("web_font") == key, saved=app_module.prefs.get("web_font"))
        previews = js(
            "__smoke.all('[data-setting=web_font] .gf-font-name').map((e) => getComputedStyle(e).fontFamily.split(',')[0].split('\"').join(''))"
        ) or []
        check("cada opção escrita na sua fonte", previews == ["Segoe UI", "IBM Plex Sans", "Inter", "Geist"], previews=previews)
        time.sleep(0.6)  # a marca da opção escolhida desliza (Motion); mede depois que ela para
        problems = _width_problems()
        check(f"Configurações sem cortes com {family}", problems == [], problems=problems)
        if key != "system":
            shot(f"23-fonte-{key}-configuracoes")
        _close_settings()
        if key in MONO_FAMILIES:
            mono = js("getComputedStyle(document.documentElement).getPropertyValue('--font-mono')") or ""
            check(f"código e números em {MONO_FAMILIES[key]}", MONO_FAMILIES[key] in mono, mono=mono)
        problems = _width_problems()
        check(f"barra superior e painéis sem cortes com {family}", problems == [], problems=problems)
        if key != "system":
            time.sleep(0.3)
            shot(f"23-fonte-{key}-editor")
    # Ctrl+K também troca a fonte.
    for query, label, expected in (("Fonte", "Inter", "inter"), ("Segoe", "Segoe UI", "system")):
        js("__smoke.key('k', { ctrlKey: true })")
        wait("!!__smoke.q('[data-testid=command-input]')", 5, "paleta")
        js(f"__smoke.setValue('[data-testid=command-input]', '{query}')")
        wait(f"__smoke.all('[cmdk-item]').some((e) => e.innerText.includes('{label}'))", 5, f"{label} na paleta")
        if expected == "inter":
            shot("23-fonte-paleta")
        js(f"(() => {{ const item = __smoke.all('[cmdk-item]').find((e) => e.innerText.includes('{label}')); item && item.click() }})()")
        current = f"(document.documentElement.dataset.font || 'system') === '{expected}'"
        check(f"Ctrl+K troca a fonte para {label}", bool(wait(current, 5, f"fonte {label} pela paleta"))
              and app_module.prefs.get("web_font") == expected)


def stz_helpers_flow() -> None:
    js("__smoke.click('[data-testid=stz-pill]')")
    wait("!!__smoke.q('[data-testid=stz-card] [data-person]')", 5, "cartão STZ com pessoas")
    time.sleep(1.0)  # números contando e cartões entrando
    helpers = js("__smoke.text('[data-testid=stz-helpers]')") or ""
    card = js("__smoke.text('[data-testid=stz-card]')") or ""
    people = js("__smoke.all('[data-testid=stz-card] [data-person]').length") or 0
    # NumberFlow desenha os dígitos no shadow DOM: o número final fica em data-value.
    counts = js("['stz-people-count', 'stz-items-count'].map((id) => __smoke.q(`[data-testid=${id}]`)?.dataset.value ?? null)") or []
    items = js("__smoke.all('[data-testid=stz-card] [data-person]').reduce((n, c) => n + Number((c.innerText.match(/(\d+) contribuiç/) || [0, 0])[1]), 0)")
    check("cabeçalho com avatares e N pessoas ajudaram", people > 0 and "pessoas ajudaram" in helpers
          and js("__smoke.all('.gf-stz-stack .gf-stz-avatar').length") == people
          and counts == [str(people), str(items)], counts=counts, people=people, items=items, text=helpers[:120])
    check("tags coloridas por tipo", bool(js(
        "(() => { const tags = __smoke.all('[data-testid=stz-card] .gf-stz-tag[data-tag]');"
        " const colors = new Set(tags.map((t) => getComputedStyle(t).color)); return tags.length > 0 && colors.size > 1 })()"
    )))
    check("links e convite do Discord", all(text in card for text in ("GitHub", "Discord", "stzlabs.com", "Conte no Discord")))
    shot("24a-stz-pessoas")
    most = js("(() => { const card = __smoke.all('[data-testid=stz-card] [data-person]').sort((a, b) => b.dataset.count - a.dataset.count)[0];"
              " card.querySelector('button').click(); return [card.dataset.person, Number(card.dataset.count)] })()") or ["", 0]
    items = wait("__smoke.all('[data-testid=stz-person-items] li').length", 3, "pessoa expandida") or 0
    plus = js("__smoke.all('[data-testid=stz-card] button').some((b) => b.innerText.trim().startsWith('+'))")
    check("cartão da pessoa expande com todas as contribuições", items == most[1] and items > 0 and not plus, items=items, person=most)
    time.sleep(0.5)
    shot("24b-stz-pessoa-aberta")
    js("__smoke.click('[data-testid=stz-card] [data-view=versions]')")
    versions = wait("__smoke.all('[data-testid=stz-view-versions] [data-version]').map((v) => v.dataset.version)", 3, "vista por versão") or []
    line = js("(__smoke.q('[data-testid=stz-view-versions] .gf-stz-timeline-items li') || {}).innerText || ''") or ""
    check("vista por versão: linha do tempo", len(versions) >= 1 and " — " in line, versions=versions, line=line[:80])
    time.sleep(0.5)
    shot("24c-stz-por-versao")
    js("document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))")
    wait("!__smoke.q('[data-testid=stz-card]')", 3, "fecha cartão")


def updates_flow() -> None:
    version = "99.0.0"
    base = f"https://github.com/{updater.REPOSITORY}/releases/download/v{version}"
    release = {
        "tag_name": f"v{version}", "body": "Notas da página",
        "html_url": f"https://github.com/{updater.REPOSITORY}/releases/tag/v{version}",
        "assets": [
            {"name": f"GF-UI-Editor-Setup-{version}.exe", "browser_download_url": f"{base}/GF-UI-Editor-Setup-{version}.exe",
             "digest": "sha256:" + "0" * 64},
            {"name": "release-notes.json", "browser_download_url": f"{base}/release-notes.json"},
        ],
    }
    notes = {"version": version, "date": "2026-11-25", "notes": {
        "pt_BR": {"new": [["Configurações na interface nova.", "Tela própria com switches."]]},
        "en_US": {"new": [["Settings in the new interface.", "Own screen with switches."]]},
    }}
    NET[updater.LATEST_RELEASE_API] = json.dumps(release).encode()
    NET[updater.RELEASES_API] = json.dumps([release]).encode()
    NET[f"{base}/release-notes.json"] = json.dumps(notes).encode()

    _open_settings()
    _settings_section("updates")
    js("__smoke.click('[data-testid=settings-check-updates]')")
    dialog = wait("__smoke.text('[data-testid=update-dialog]')", 10, "janela de atualização") or ""
    check("atualização simulada oferecida com as notas",
          "O que chegou na 99.0.0" in dialog and "Configurações na interface nova." in dialog, dialog=dialog[:200])
    time.sleep(0.4)
    shot("17a-atualizacao-disponivel")
    js("__smoke.clickText('Pular esta versão', '[data-testid=update-dialog-footer]')")
    wait("!__smoke.q('[data-testid=update-dialog]')", 5, "fechar a oferta")
    time.sleep(0.2)
    check("Pular esta versão grava a versão", app_module.prefs.skipped_update_version == version)
    _settings_section("general")
    review = wait("__smoke.text('[data-testid=settings-general]')", 5, "seção Geral") or ""
    check("Geral mostra a versão pulada", "99.0.0" in review, review=review[:200])
    check("com versão pulada, Oferecer de novo aparece", bool(js("!!__smoke.q('[data-testid=settings-reset-skipped]')")))
    _close_settings()
    NET.clear()


def manifest_flow() -> None:
    MANIFEST[0] = remote_manifest.parse(json.dumps({
        "schema": 1,
        "disabled_features": ["export_texts"],
        "messages": [{"id": "smoke-aviso", "level": "warning", "url": "https://stzlabs.com/smoke",
                      "text": {"pt_BR": "Aviso simulado do smoke.", "en_US": "Smoke notice."}}],
    }).encode())
    check("manifesto simulado válido", MANIFEST[0] is not None)
    api._manifest_ready.clear()  # a página recarregada lê o manifesto de novo (como ao abrir)
    js("location.reload()")
    notice = wait(_dialog_with("Aviso simulado"), 20, "aviso do manifesto") or ""
    check("aviso do manifesto aparece ao abrir", "Abrir link" in notice, notice=notice[:200])
    time.sleep(0.3)
    shot("18a-aviso-do-manifesto")
    js("__smoke.clickText('OK', '[role=dialog]')")
    wait(f"!{_dialog_with('Aviso simulado')}", 5, "fechar aviso")
    time.sleep(0.2)
    check("aviso marcado como visto", "smoke-aviso" in app_module.prefs.manifest_seen)
    check("versão pulada não é oferecida de novo ao abrir", not js("!!__smoke.q('[data-testid=update-dialog]')"))

    wait("!!__smoke.q('[data-testid=project-button]')", 10, "casca depois de recarregar")
    js("__smoke.click('[data-testid=project-button]')")
    wait("!!__smoke.q('[role=menu]')", 5, "menu do projeto")
    js("__smoke.clickText('Exportar textos', '[role=menu]')")
    blocked = wait(_dialog_with("desativada temporariamente"), 8, "exportar textos desligado")
    check("Exportar textos desligado pelo manifesto avisa como a clássica", bool(blocked))
    js("__smoke.clickText('OK', '[role=dialog]')")
    wait("!__smoke.q('[role=dialog]')", 5, "fechar aviso de função desligada")
    MANIFEST[0] = None


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
    if js("(() => { const b = __smoke.q('[data-testid=open-atlas]'); return !!b && !b.disabled })()"):
        js("__smoke.click('[data-testid=open-atlas]')")
        check("Abrir atlas DDS pelo painel", bool(wait("!!__smoke.q('[data-testid=atlas-surface]')", 10, "atlas")))
        time.sleep(1.0)
        shot("11b-atlas")
        check("Atlas acompanha a troca de tema e usa mãozinha", js("""(() => {
            const html = document.documentElement;
            const theme = document.createElement('style');
            theme.textContent = 'html[data-theme="smoke"] { --color-panel: rgb(21, 43, 65); }';
            const previous = html.getAttribute('data-theme');
            document.head.append(theme);
            try {
                html.dataset.theme = 'smoke';
                return getComputedStyle(__smoke.q('.gf-atlas-dialog')).backgroundColor === 'rgb(21, 43, 65)' &&
                    getComputedStyle(__smoke.q('.gf-atlas-side .btn')).cursor === 'pointer';
            } finally {
                if (previous === null) html.removeAttribute('data-theme');
                else html.setAttribute('data-theme', previous);
                theme.remove();
            }
        })()"""))
        order = js("""(() => {
            const side = __smoke.q('[data-testid=atlas-side]');
            if (!side) return null;
            const top = (s) => { const e = side.querySelector(s); return e ? e.getBoundingClientRect().top : null };
            return [top('[data-testid=atlas-size]'), top('[data-testid=atlas-edit]'), top('[data-testid=atlas-uv-card]'),
                    top('[data-testid=atlas-open-dds]'), top('[data-testid=atlas-cursor]'), top('.gf-atlas-close')] })()""") or []
        # O cartão do recorte só aparece com NorUV editável; o resto sempre, nesta ordem.
        present = [value for index, value in enumerate(order) if not (index == 2 and value is None)]
        check("atlas com o Abrir .dds na lateral, abaixo do recorte",
              len(present) >= 5 and None not in present and present == sorted(present), order=order)
        js("__smoke.click('.gf-atlas-close')")  # <dialog> nativo: Esc sintético não fecha
        check("atlas fecha pelo ×", bool(wait("!__smoke.q('[data-testid=atlas-surface]')", 5, "fecha atlas")))
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
    palette_and_source(xml, child, new_x, before)
    js("__smoke.key('s', { ctrlKey: true })")
    diff = wait("__smoke.text('[data-testid=diff]')", 8, "diff antes de salvar") or ""
    check("Ctrl+S mostra o diff antes de gravar", "WindowLeft" in diff and xml.read_bytes() == before, diff=diff[:300])
    shot("13-diff-salvar")
    js("__smoke.click('[data-testid=diff-confirm]')")
    check("salvar grava o X novo", bool(wait("!__smoke.q('[data-testid=dirty-marker]')", 8, "salvo")))
    check("XML no disco com o X novo", f'WindowLeft="{new_x}"'.encode() in xml.read_bytes())
    edit_xml_source(xml, child, new_x)

    # Descartar ao trocar de XML.
    saved = xml.read_bytes()
    js(f"__smoke.setValue('input[name=geometry-x]', '{new_x + 5}')")
    js("__smoke.q('input[name=geometry-x]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
    wait("!!__smoke.q('[data-testid=dirty-marker]')", 5, "alterado de novo")
    _open_settings()
    js("__smoke.click('[data-setting=ui_mode] [data-value=web]')")
    prompt = _dialog_with("Reiniciar agora para usar a interface")
    check("trocar interface oferece Reiniciar agora e Depois", bool(wait(prompt, 5, "reiniciar interface"))
          and app_module.prefs.ui_mode == "web")
    js("__smoke.clickText('Depois', '[role=dialog][aria-label=Interface]')")
    wait(f"!({prompt})", 5, "reiniciar depois")
    js("__smoke.click('[data-setting=ui_mode] [data-value=classic]')")
    wait(prompt, 5, "reiniciar na clássica")
    js("__smoke.clickText('Reiniciar agora', '[role=dialog][aria-label=Interface]')")
    dirty_prompt = _dialog_with("alterações não salvas")
    choices = wait(dirty_prompt, 5, "salvar antes de reiniciar") or ""
    check("reiniciar com alterações oferece Salvar, Descartar e Cancelar",
          all(label in choices for label in ("Salvar", "Descartar", "Cancelar")))
    js("""__smoke.clickText('Cancelar', '[role=dialog][aria-label="Descartar alterações?"]')""")
    dismissed = wait(f"!({dirty_prompt})", 5, "cancelar reinício")
    check("cancelar mantém as alterações e a preferência", dismissed and js("!!__smoke.q('[data-testid=dirty-marker]')")
          and app_module.prefs.ui_mode == "classic" and xml.read_bytes() == saved)
    _close_settings()

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


CLICK_OTHER_LINE = r"""(() => {
    const lines = Array.from(document.querySelectorAll('[data-testid=source-editor] .cm-line'));
    const line = lines.find((l) => /<BaseWndProperty\b/.test(l.textContent) && !l.classList.contains('gf-source-marked'));
    if (!line) return null;
    const box = line.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, clientX: box.left + 24, clientY: box.top + box.height / 2, button: 0, buttons: 1, view: window };
    line.dispatchEvent(new MouseEvent('mousedown', opts));
    line.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, opts, { buttons: 0 })));
    line.dispatchEvent(new MouseEvent('click', Object.assign({}, opts, { buttons: 0 })));
    return (line.textContent.match(/WindowID="([^"]*)"/) || [])[1] || null })()"""


def palette_and_source(xml: Path, child, new_x: int, before: bytes) -> None:
    """Ctrl+K (paleta) abre "Ver código XML", que mostra o XML com a edição ainda não salva."""
    js("__smoke.key('k', { ctrlKey: true })")
    check("Ctrl+K abre a paleta de comandos", bool(wait("!!__smoke.q('[data-testid=command-palette] [data-testid=command-input]')", 5, "paleta")))
    time.sleep(0.3)
    shot("13a-paleta")
    js("__smoke.setValue('[data-testid=command-input]', 'código XML')")
    wait("((__smoke.q('[cmdk-item][data-selected=true]') || {}).innerText || '').includes('Ver código XML')", 5, "comando filtrado")
    js("__smoke.q('[data-testid=command-input]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))")
    check("comando da paleta abre Ver código XML", bool(wait(
        "!__smoke.q('[data-testid=command-palette]') && !!__smoke.q('[data-testid=source-panel]')", 5, "código pela paleta")))
    text = wait(
        "(() => { const c = __smoke.q('[data-testid=source-editor] .cm-content'); return c && c.innerText.includes('WindowLeft') ? c.innerText : null })()",
        8, "texto do XML",
    ) or ""
    check("Ver código mostra o XML com a edição não salva", f'WindowLeft="{new_x}"' in text and xml.read_bytes() == before)
    marked = wait("(__smoke.q('.gf-source-marked') || {}).innerText", 5, "linha do elemento") or ""
    check("Ver código leva à linha do elemento selecionado", f'WindowID="{child.window_id}"' in marked, line=marked[:120])
    check("Ver código com números de linha e dobrar blocos", bool(js(
        "!!__smoke.q('[data-testid=source-panel] .cm-foldGutter') && !!__smoke.q('[data-testid=source-panel] .cm-lineNumbers')")))
    js("(() => { const c = __smoke.q('[data-testid=source-editor] .cm-content'); c.focus();"
       " c.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', code: 'KeyF', keyCode: 70, ctrlKey: true, bubbles: true, cancelable: true })); return true })()")
    check("Ctrl+F abre a busca do código", bool(wait("!!__smoke.q('[data-testid=source-panel] .cm-search')", 3, "busca")))
    shot("13b-codigo-xml")
    picked = js(CLICK_OTHER_LINE)
    selected = wait(
        f"(() => {{ const r = __smoke.q('[data-testid=tree-row][aria-selected=true]'); return r && r.dataset.index !== '{child.index}' ? r.innerText : null }})()",
        5, "seleção pela linha",
    ) or ""
    marked_now = js("(__smoke.q('.gf-source-marked') || {}).textContent || null")
    rows = js("__smoke.all('[data-testid=tree-row][aria-selected=true]').map((r) => r.dataset.index + ':' + r.innerText.slice(0, 20))")
    check("clicar numa linha com WindowID seleciona o elemento", bool(picked) and picked in selected, picked=picked, row=selected[:60],
          marked=(marked_now or "")[:80], rows=rows)
    js(f"__smoke.click('[data-testid=tree-row][data-index=\"{child.index}\"]')")
    wait(f"__smoke.q('[data-testid=tree-row][data-index=\"{child.index}\"]').getAttribute('aria-selected') === 'true'", 3, "volta ao elemento")
    js("__smoke.key('u', { ctrlKey: true })")
    check("Ctrl+U fecha o código", bool(wait("!__smoke.q('[data-testid=source-panel]')", 3, "fecha código")))


def edit_xml_source(xml: Path, child, old_x: int) -> None:
    from gf_ui_editor.xml_document import START_TAG_RE

    before = xml.read_bytes()
    original = before.decode("big5")
    tag = list(START_TAG_RE.finditer(original))[child.index]
    new_x = old_x + 7
    applied = original[:tag.start()] + tag[0].replace(
        f'WindowLeft="{old_x}"', f'WindowLeft="{new_x}"',
    ) + original[tag.end():]
    ready = "!!__smoke.q('[data-testid=source-edit]:enabled')"
    editable = ".gf-source-editor .cm-content[contenteditable=true]"

    def paste(text: str) -> None:
        js(f"""(() => {{
            const content = __smoke.q('{editable}');
            content.focus();
            content.dispatchEvent(new KeyboardEvent('keydown', {{
                key: 'a', code: 'KeyA', keyCode: 65, ctrlKey: true, bubbles: true, cancelable: true,
            }}));
            const data = new DataTransfer();
            data.setData('text/plain', {json.dumps(text)});
            content.dispatchEvent(new ClipboardEvent('paste', {{clipboardData: data, bubbles: true, cancelable: true}}));
        }})()""")

    def edit() -> None:
        wait(ready, 8, "editar código disponível")
        js("__smoke.click('[data-testid=source-edit]')")
        wait(f"!!__smoke.q('{editable}')", 5, "CodeMirror editável")

    def state_at(x: int) -> str:
        return f"__gfDoc.state().selection[0] === {child.index} && " \
               f"__gfDoc.state().doc.elements[{child.index}].geometry[0] === {x}"

    js("__smoke.key('u', { ctrlKey: true })")
    edit()
    paste("<incompleto>")
    js("__smoke.click('[data-testid=source-apply]')")
    check("XML inválido marca o erro no CodeMirror", bool(wait(
        "!!__smoke.q('.gf-source-error, .gf-source-error-line') && "
        "(__smoke.text('.gf-source-panel [role=alert]') || '').includes('Linha 1, coluna')",
        5, "erro de XML",
    )) and xml.read_bytes() == before)
    js("__smoke.key('1', { ctrlKey: true })")
    js("__smoke.setValue('[data-testid=files-panel] input', 'Storage')")
    wait("!!__smoke.q('[data-section=all] [data-file=\"Storage.xml\"]')", 5, "outro XML")
    js("__smoke.click('[data-section=all] [data-file=\"Storage.xml\"]')")
    check("trocar de XML pergunta o que fazer com o rascunho", bool(wait(
        "(__smoke.text('[role=dialog]') || '').includes('Aplicar alterações no código XML?')", 5, "rascunho",
    )))
    js("__smoke.clickText('Cancelar', '[role=dialog]')")
    wait("!__smoke.q('[role=dialog]')", 5, "mantém o rascunho")
    js("__smoke.setValue('[data-testid=files-panel] input', '')")
    js("__smoke.key('3', { ctrlKey: true })")
    paste(applied)
    js("__smoke.click('[data-testid=source-apply]')")
    check("aplicar pelo painel atualiza seleção e geometria sem gravar", bool(wait(
        f"{ready} && {state_at(new_x)}", 8, "aplica o código",
    )) and xml.read_bytes() == before)
    js("__smoke.key('z', { ctrlKey: true })")
    check("Ctrl+Z desfaz o XML inteiro", bool(wait(f"{ready} && {state_at(old_x)}", 8, "desfaz o código")))
    js("__smoke.key('y', { ctrlKey: true })")
    check("Ctrl+Y refaz o XML inteiro", bool(wait(f"{ready} && {state_at(new_x)}", 8, "refaz o código")))
    js("__smoke.key('z', { ctrlKey: true })")
    wait(f"{ready} && {state_at(old_x)}", 8, "desfaz para reaplicar")
    edit()
    paste(applied)
    js("__smoke.click('[data-testid=source-apply]')")
    wait(f"{ready} && {state_at(new_x)}", 8, "reaplica o código")
    js("__smoke.key('s', { ctrlKey: true })")
    diff = wait("__smoke.text('[data-testid=diff]')", 8, "diff do código") or ""
    check("salvar o código mostra o diff", f'WindowLeft="{new_x}"' in diff and xml.read_bytes() == before)
    js("__smoke.click('[data-testid=diff-confirm]')")
    wait("!__smoke.q('[data-testid=dirty-marker]')", 8, "código gravado")
    check("XML gravado é idêntico ao código aplicado", xml.read_bytes() == applied.encode("big5"))
    js("__smoke.key('u', { ctrlKey: true })")
    wait("!__smoke.q('[data-testid=source-panel]')", 5, "fecha código após salvar")


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


def canvas_toolbar() -> None:
    def choose(label: str, value: str) -> None:
        selector = json.dumps(f'.gf-canvas-toolbar select[aria-label="{label}"]')
        js(f"__smoke.setValue({selector}, {json.dumps(value)})")

    toolbar = ".gf-canvas-toolbar"
    js(f"__smoke.clickText('Contornos', '{toolbar}')")
    check("Contornos desliga o tracejado", bool(wait(
        f"__smoke.q('{toolbar} button').getAttribute('aria-pressed') === 'false'", 5, "contornos desligados",
    )))
    js(f"__smoke.clickText('Contornos', '{toolbar}')")
    wait(f"__smoke.q('{toolbar} button').getAttribute('aria-pressed') === 'true'", 5, "contornos restaurados")
    ids = json.dumps(f'{toolbar} button[aria-label="Mostrar identificadores"]')
    js(f"__smoke.click({ids})")
    check("Mostrar identificadores liga os rótulos", bool(wait(
        f"__smoke.q({ids}).getAttribute('aria-pressed') === 'true'", 5, "IDs ligados",
    )))
    choose("Tela", "custom")
    wait(f"!!__smoke.q('{toolbar} form input')", 5, "resolução personalizada")
    js(f"__smoke.setValue('{toolbar} form input', '1367x769'); __smoke.q('{toolbar} form').requestSubmit()")
    check("Tela aceita e salva resolução personalizada", bool(wait(
        f"(__smoke.text('{toolbar}') || '').includes('Tela 1367 × 769')", 5, "resolução personalizada aplicada",
    )) and app_module.prefs.game_resolution == "1367x769")
    choose("Tela", "game")
    wait(f"(__smoke.text('{toolbar}') || '').includes('· jogo')", 5, "seguir client.ini")

    zoom = "[data-testid=canvas-zoom-reset]"
    js(f"__smoke.click('{zoom}')")
    check("Porcentagem volta a 100%", bool(wait(f"__smoke.text('{zoom}') === '100%'", 5, "zoom 100%")))
    js(f"__smoke.click('.gf-canvas-zoom button[aria-label=\"Diminuir zoom\"]')")
    wait(f"__smoke.text('{zoom}') !== '100%'", 5, "reduzir zoom")
    js("__smoke.key('0', { ctrlKey: true })")
    check("Ctrl+0 volta a 100%", bool(wait(f"__smoke.text('{zoom}') === '100%'", 5, "Ctrl+0")))
    js("__smoke.click('[data-testid=canvas-fit]')")
    check("Enquadrar ajusta a tela", bool(wait(f"__smoke.text('{zoom}') !== '100%'", 5, "enquadrar")))
    check("Pílulas flutuam sobre o canvas e recebem os próprios cliques", bool(js("""(() => {
      const viewport = __smoke.q('.gf-canvas-viewport').getBoundingClientRect();
      const bars = __smoke.all('.gf-canvas-toolbar, .gf-canvas-zoom');
      return bars.length === 2 && bars.every(bar => {
        const box = bar.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return box.top >= viewport.top && box.bottom <= viewport.bottom && bar.contains(hit);
      });
    })()""")))

    js(f"__smoke.clickText('User.ini', '{toolbar}')")
    wait(f"!__smoke.q('{toolbar} button[title*=User]').disabled", 5, "User.ini desligado")
    check("User.ini salva o estado", not app_module.prefs.canvas_saved_positions)
    js(f"__smoke.clickText('User.ini', '{toolbar}')")
    wait(f"__smoke.q('{toolbar} button[title*=User]').getAttribute('aria-pressed') === 'true'", 5, "User.ini restaurado")
    js(f"__smoke.clickText('Personagem', '{toolbar}')")
    wait(f"!__smoke.all('{toolbar} button').find(b => b.textContent === 'Personagem').disabled", 5, "Personagem desligado")
    check("Personagem salva o estado", not app_module.prefs.canvas_character)
    choose("Texto", "game")
    check("Texto salva o modo Jogo", bool(wait(
        "__smoke.q('select[aria-label=Texto]').value === 'game' && !__smoke.q('select[aria-label=Texto]').disabled",
        5, "textos do jogo",
    )) and app_module.prefs.text_mode == "game")

    from PIL import Image

    capture = OUT / "captura-canvas.png"
    Image.new("RGB", (64, 64), (111, 22, 144)).save(capture)
    ANSWERS.append(capture)
    choose("Fundo", "choose")
    check("Fundo carrega a captura própria", bool(wait(
        """(() => {
          if (__smoke.q('select[aria-label=Fundo]').value !== 'custom') return false;
          const c = __smoke.all('.gf-canvas-viewport canvas').at(-1);
          return c?.getContext('2d').getImageData(c.width / 2, c.height / 2, 1, 1).data.join(',') === '111,22,144,255';
        })()""", 8, "captura própria desenhada",
    )) and app_module.prefs.game_background == str(capture))
    choose("Fundo", "builtin")
    wait("__smoke.q('select[aria-label=Fundo]').value === 'builtin' && !__smoke.q('select[aria-label=Fundo]').disabled", 5, "fundo embutido")
    js("window.layerEvents = 0; window.addEventListener('gf:layers-changed', () => window.layerEvents++)")
    choose("Camadas", "default")
    check("Camadas monta o HUD na lista Arquivos", bool(wait(
        "window.layerEvents === 1 && !!__smoke.q('[data-section=layers] [data-file]') && __smoke.q('select[aria-label=Camadas]').dataset.active === 'true'",
        8, "camadas do HUD",
    )))
    shot("04b-canvas-camadas-e-ids")
    window.resize(1024, 680)
    check("Barra do canvas cabe na largura mínima", bool(wait(
        f"window.innerWidth <= 1024 && __smoke.q('{toolbar}').scrollWidth <= __smoke.q('{toolbar}').clientWidth",
        5, "barra estreita",
    )))
    shot("04c-canvas-janela-estreita")
    window.resize(1440, 900)
    wait("window.innerWidth > 1280", 5, "restaurar largura")
    choose("Camadas", "clear")
    check("Camadas limpa o HUD e a lista", bool(wait(
        "window.layerEvents === 2 && !__smoke.q('[data-section=layers]') && __smoke.q('select[aria-label=Camadas]').dataset.active === 'false'",
        8, "camadas limpas",
    )))
    choose("Texto", "off")
    wait("__smoke.q('select[aria-label=Texto]').value === 'off' && !__smoke.q('select[aria-label=Texto]').disabled", 5, "texto desligado")
    js(f"__smoke.clickText('Personagem', '{toolbar}')")
    wait(f"__smoke.all('{toolbar} button').find(b => b.textContent === 'Personagem').getAttribute('aria-pressed') === 'true'", 5, "Personagem restaurado")
    js(f"__smoke.click({ids})")


FINISHED = threading.Event()


def driver() -> None:
    try:
        scenario()
    except Exception:  # noqa: BLE001
        log("error", traceback=traceback.format_exc())
        FAILED.append("exceção no roteiro")
    finally:
        (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
        FINISHED.set()
        window.destroy()


webview.start(driver, gui="edgechromium", private_mode=True, storage_path=str(OUT / "webview"))
if not FINISHED.is_set():
    FAILED.append("a janela fechou antes de o roteiro terminar")
log("summary", failed=FAILED, checks=sum(1 for entry in LOG if entry["kind"] == "check"))
(OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(1 if FAILED else 0)
