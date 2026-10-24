"""Controles que a UI oficial do jogo tem e uma UI custom não.

O launcher guarda em `GameDataFileList.txt` o tamanho e o CRC32 de cada arquivo
oficial (`UI\\BasicChar.xml|31651|E01700FF|…`). Sempre que um XML em `<jogo>/UI`
bate com essa lista ele é a versão oficial atual, e uma cópia vai para um cache
(`<projetos>/.official-ui/<CRC>.xml`), junto com a ordem em que cada versão foi
vista (`versions.json`): o launcher sobrescreve `UI/` com a UI custom escolhida.

Faltar um controle do oficial não quer dizer que algo quebrou: quem redesenha a
UI remove controles de propósito. Só são "novos" (e só esses geram aviso) os
WindowIDs que surgiram de uma versão oficial para a seguinte, seja no histórico
do cache, seja comparando com a versão oficial de onde o projeto partiu. Os
demais aparecem como "outros que o oficial tem", sem nada marcado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
import json
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zlib

from . import project as project_module
from .xml_document import ANY_TAG_RE, UIDocument, _kind_for


FILE_LIST = "GameDataFileList.txt"
CACHE_FOLDER = ".official-ui"
VERSIONS = "versions.json"
_NAME_RE = re.compile(r"<\s*/?\s*([A-Za-z_][\w.-]*)")
_WINDOW_ID_RE = re.compile(r'\bWindowID\s*=\s*"([^"]*)"')
_CHILD_CNT_RE = re.compile(r'(\bChild_Cnt\s*=\s*")(\d+)(")')
_CPP_RE = re.compile(r"([A-Za-z_]\w*\.cpp)\b", re.IGNORECASE)
_ID_RE = re.compile(r"\bID\s*=\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class OfficialEntry:
    relative: str  # "BasicChar.xml" ou "sub/arquivo.xml", relativo a UI/
    size: int
    crc: str


@dataclass(frozen=True)
class ControlInfo:
    window_id: str
    kind: str
    texture: str
    position: tuple[int, int]
    size: tuple[int, int]


@dataclass
class FileDiff:
    relative: str
    new_ids: list[str] = field(default_factory=list)  # vieram de uma atualização: certeza
    other_ids: list[str] = field(default_factory=list)  # o oficial tem; podem ter sido removidos
    missing_file: bool = False


def _crc(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


# ---- UI oficial ---------------------------------------------------------------
def official_entries(game_dir: Path) -> dict[str, OfficialEntry]:
    """XMLs oficiais da UI segundo o launcher, por nome relativo em minúsculas."""
    try:
        lines = (game_dir / FILE_LIST).read_text(encoding="latin-1").splitlines()
    except OSError:
        return {}
    entries: dict[str, OfficialEntry] = {}
    for line in lines:
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name = parts[0].replace("\\", "/")
        if not name.lower().startswith("ui/") or not name.lower().endswith(".xml"):
            continue
        try:
            size = int(parts[1])
        except ValueError:
            continue
        entries[name[3:].lower()] = OfficialEntry(name[3:], size, parts[2].strip().upper())
    return entries


def cache_dir() -> Path:
    return project_module.PROJECTS_ROOT / CACHE_FOLDER


def _versions() -> dict[str, list[str]]:
    try:
        data = json.loads((cache_dir() / VERSIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _record_version(relative: str, crc: str) -> None:
    versions = _versions()
    seen = versions.setdefault(relative.lower(), [])
    if crc in seen:
        return
    seen.append(crc)
    path = cache_dir() / VERSIONS
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(versions, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def cached_version(crc: str) -> Path | None:
    path = cache_dir() / f"{crc}.xml"
    return path if path.is_file() else None


def official_xml(game_dir: Path, entry: OfficialEntry) -> Path | None:
    """Cópia da versão oficial atual; guarda no cache quando `UI/` ainda a tem."""
    cached = cached_version(entry.crc)
    if cached is not None:
        try:
            _record_version(entry.relative, entry.crc)
        except OSError:
            pass
        return cached
    source = game_dir / "UI" / entry.relative
    try:
        if source.stat().st_size != entry.size:
            return None
        data = source.read_bytes()
    except OSError:
        return None
    if _crc(data) != entry.crc:
        return None
    try:
        target = cache_dir() / f"{entry.crc}.xml"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        _record_version(entry.relative, entry.crc)
    except OSError:
        return source
    return target


def snapshot_official_ui(game_dir: Path) -> tuple[int, int]:
    """Guarda no cache todo XML oficial que ainda está em `UI/`. Devolve (disponíveis, total)."""
    entries = official_entries(game_dir)
    available = sum(1 for entry in entries.values() if official_xml(game_dir, entry) is not None)
    return available, len(entries)


def cached_count(game_dir: Path) -> tuple[int, int]:
    """(XMLs oficiais atuais já guardados no cache, total na lista do launcher). Não lê a pasta UI."""
    entries = official_entries(game_dir)
    return sum(1 for entry in entries.values() if cached_version(entry.crc) is not None), len(entries)


def reference_ready(game_dir: Path) -> bool:
    """A cópia oficial serve de referência: a lista do launcher às vezes cita arquivos que
    nem a UI Padrão traz iguais (ex.: Team.bckp.xml), então não se exige 100%."""
    cached, total = cached_count(game_dir)
    return total > 0 and cached >= total * 0.9


def previous_official(entry: OfficialEntry) -> Path | None:
    """Versão oficial vista antes da atual (a de antes da última atualização)."""
    seen = _versions().get(entry.relative.lower(), [])
    if entry.crc not in seen:
        return None
    for crc in reversed(seen[: seen.index(entry.crc)]):
        path = cached_version(crc)
        if path is not None:
            return path
    return None


def official_version_of(data: bytes) -> Path | None:
    """O arquivo do cache igual a `data`, se `data` for uma versão oficial já vista."""
    return cached_version(_crc(data))


# ---- estrutura do XML por texto (preserva bytes) -------------------------------
@dataclass
class _Node:
    name: str
    start: int
    open_end: int
    end: int = -1
    window_id: str | None = None
    children: list["_Node"] | None = None


def _parse(text: str) -> _Node:
    root = _Node("#document", 0, 0, len(text), children=[])
    stack = [root]
    for match in ANY_TAG_RE.finditer(text):
        tag = match.group(0)
        if tag.startswith(("<?", "<!")):
            continue
        name_match = _NAME_RE.match(tag)
        if name_match is None:
            continue
        name = name_match.group(1)
        if tag.startswith("</"):
            while len(stack) > 1:
                node = stack.pop()
                node.end = match.end()
                if node.name == name:
                    break
            continue
        id_match = _WINDOW_ID_RE.search(tag)
        node = _Node(name, match.start(), match.end(), window_id=id_match.group(1) if id_match else None, children=[])
        stack[-1].children.append(node)
        if tag.rstrip().endswith("/>"):
            node.end = match.end()
        else:
            stack.append(node)
    for node in stack[1:]:
        node.end = len(text)
    return root


def _containers(node: _Node, owner: str | None = None) -> list[tuple[str | None, _Node]]:
    """(WindowID do BaseWndProperty dono, Container_Node) em ordem de documento."""
    found = []
    for child in node.children or []:
        if child.name == "Container_Node":
            found.append((owner, child))
        found.extend(_containers(child, child.window_id if child.name == "BaseWndProperty" else owner))
    return found


def _blocks(container: _Node) -> list[tuple[str, int, int]]:
    """(WindowID, início, fim) de cada controle; o início inclui o <Style> que o precede."""
    blocks = []
    children = container.children or []
    for index, child in enumerate(children):
        if child.name != "BaseWndProperty" or child.window_id is None:
            continue
        start = child.start
        if index > 0 and children[index - 1].name == "Style":
            start = children[index - 1].start
        blocks.append((child.window_id, start, child.end))
    return blocks


def _line_indent(text: str, position: int) -> str:
    line_start = text.rfind("\n", 0, position) + 1
    indent = text[line_start:position]
    return indent if not indent.strip() else ""


def window_ids(text: str) -> set[str]:
    return {window_id for _owner, node in _containers(_parse(text)) for window_id, _s, _e in _blocks(node)}


def missing_controls(project_text: str, official_text: str) -> list[str]:
    """WindowIDs que o oficial tem e o projeto não, contêiner por contêiner, em ordem."""
    return _plan(project_text, official_text, None)[1]


def _plan(
    project_text: str, official_text: str, wanted: set[str] | None
) -> tuple[list[tuple[int, int, str]], list[str]]:
    project_containers = {owner: node for owner, node in _containers(_parse(project_text))}
    nl = "\r\n" if "\r\n" in project_text else "\n"
    edits: list[tuple[int, int, str]] = []
    missing: list[str] = []
    for owner, official in _containers(_parse(official_text)):
        mine = project_containers.get(owner)
        if mine is None:
            continue
        my_blocks = {window_id: (start, end) for window_id, start, end in _blocks(mine)}
        anchor_end = mine.open_end
        anchor_indent = None
        pending: list[str] = []
        added = 0
        for window_id, start, end in _blocks(official):
            if window_id in my_blocks:
                if pending:
                    edits.append((anchor_end, anchor_end, "".join(pending)))
                    pending = []
                my_start, anchor_end = my_blocks[window_id]
                anchor_indent = _line_indent(project_text, my_start)
                continue
            missing.append(window_id)
            if wanted is not None and window_id not in wanted:
                continue
            block = official_text[start:end].replace("\r\n", "\n").replace("\n", nl)
            indent = anchor_indent if anchor_indent is not None else _line_indent(official_text, start)
            pending.append(nl + indent + block)
            added += 1
        if pending:
            edits.append((anchor_end, anchor_end, "".join(pending)))
        if added:
            open_tag = project_text[mine.start:mine.open_end]
            count = _CHILD_CNT_RE.search(open_tag)
            if count is not None:
                new_tag = open_tag[:count.start(2)] + str(int(count.group(2)) + added) + open_tag[count.end(2):]
                edits.append((mine.start, mine.open_end, new_tag))
    return edits, missing


def insert_controls(project_text: str, official_text: str, ids: set[str] | None = None) -> tuple[str, list[str]]:
    """Texto com os controles do oficial que faltam (só `ids`, se dado) na mesma posição.

    O Child_Cnt de cada contêiner cresce na mesma medida; o resto não muda.
    """
    edits, missing = _plan(project_text, official_text, ids)
    text = project_text
    for start, end, replacement in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        text = text[:start] + replacement + text[end:]
    inserted = [window_id for window_id in missing if ids is None or window_id in ids]
    return text, inserted


def control_info(official_text: str, ids: list[str]) -> dict[str, ControlInfo]:
    """Tipo, textura e posição dos controles `ids` no XML oficial."""
    infos: dict[str, ControlInfo] = {}
    wanted = set(ids)
    for _owner, node in _containers(_parse(official_text)):
        children = node.children or []
        for index, child in enumerate(children):
            if child.name != "BaseWndProperty" or child.window_id not in wanted:
                continue
            try:
                base = ET.fromstring(official_text[child.start:child.end])
                style = (
                    ET.fromstring(official_text[children[index - 1].start:children[index - 1].end])
                    if index > 0 and children[index - 1].name == "Style"
                    else None
                )
            except ET.ParseError:
                continue
            background = base.find("BackGroundMap")

            def number(name: str) -> int:
                try:
                    return int(base.get(name, "0"))
                except ValueError:
                    return 0

            infos[child.window_id] = ControlInfo(
                child.window_id,
                _kind_for(base, style.get("CtrlType") if style is not None else None),
                background.get("BGmap", "") if background is not None else "",
                (number("WindowLeft"), number("WindowTop")),
                (number("WindowHeight"), number("WindowWidth")),  # largura/altura visuais trocadas no jogo
            )
    return infos


# ---- comparação com um projeto ------------------------------------------------
def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode(UIDocument.encoding)
    except (OSError, UnicodeDecodeError):
        return None


def file_diff(
    game_dir: Path,
    ui_dir: Path,
    relative: str,
    base_bytes: Callable[[str], bytes | None] | None = None,
) -> FileDiff | None:
    """Controles do oficial atual que `ui_dir/relative` não tem; None se nada a mostrar.

    `base_bytes(relative)` devolve o arquivo como era quando o projeto foi criado:
    se for uma versão oficial já vista, o que surgiu desde então também é "novo".
    """
    entry = official_entries(game_dir).get(relative.replace("\\", "/").lower())
    if entry is None:
        return None
    official_path = official_xml(game_dir, entry)
    if official_path is None:
        return None
    mine_path = ui_dir / entry.relative
    if not mine_path.is_file():
        return FileDiff(entry.relative, missing_file=True)
    official_raw = official_path.read_bytes()
    mine_raw = mine_path.read_bytes()
    if mine_raw == official_raw:
        return None
    mine_text, official_text = _read_text(mine_path), official_raw.decode(UIDocument.encoding, "replace")
    if mine_text is None:
        return None
    missing = missing_controls(mine_text, official_text)
    if not missing:
        return None
    references = [previous_official(entry)]
    base = base_bytes(entry.relative) if base_bytes is not None else None
    if base is not None and _crc(base) != entry.crc:
        references.append(official_version_of(base))
    new: set[str] = set()
    for reference in references:
        old_text = _read_text(reference) if reference is not None else None
        if old_text is not None:
            new |= window_ids(official_text) - window_ids(old_text)
    return FileDiff(
        entry.relative,
        [window_id for window_id in missing if window_id in new],
        [window_id for window_id in missing if window_id not in new],
    )


def scan(
    game_dir: Path,
    ui_dir: Path,
    base_bytes: Callable[[str], bytes | None] | None = None,
) -> tuple[dict[str, FileDiff], int]:
    """Diferenças por arquivo (chave em minúsculas) e quantos oficiais não têm cópia."""
    diffs: dict[str, FileDiff] = {}
    unavailable = 0
    for key, entry in official_entries(game_dir).items():
        if official_xml(game_dir, entry) is None:
            unavailable += 1
            continue
        diff = file_diff(game_dir, ui_dir, entry.relative, base_bytes)
        if diff is not None:
            diffs[key] = diff
    return diffs, unavailable


def official_text_for(game_dir: Path, relative: str) -> str | None:
    entry = official_entries(game_dir).get(relative.replace("\\", "/").lower())
    path = official_xml(game_dir, entry) if entry is not None else None
    return path.read_bytes().decode(UIDocument.encoding, "replace") if path is not None else None


def copy_official_file(game_dir: Path, ui_dir: Path, relative: str) -> Path:
    """Copia para o projeto um XML oficial que ele não tem."""
    entry = official_entries(game_dir)[relative.lower()]
    source = official_xml(game_dir, entry)
    if source is None:
        raise FileNotFoundError(relative)
    target = ui_dir / entry.relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


# ---- erro do jogo ---------------------------------------------------------------
def parse_game_error(text: str) -> tuple[str, str] | None:
    """("MiniInfo.cpp", "8301") de "..\\MiniInfo.cpp ERROR: ID=8301 Child control can not found!"."""
    id_match = _ID_RE.search(text)
    if id_match is None:
        return None
    # O .cpp que interessa é o da linha do ID; "FrameWnd.cpp" antes é só onde o erro é exibido.
    sources = _CPP_RE.findall(text[: id_match.start()])
    return (sources[-1], id_match.group(1)) if sources else None


def error_candidates(game_dir: Path, cpp: str, window_id: str) -> list[str]:
    """XMLs oficiais carregados por `cpp` que têm o controle `window_id`."""
    from .error_sources import CPP_TO_XML

    names = next((xmls for name, xmls in CPP_TO_XML.items() if name.lower() == cpp.lower()), ())
    found, unknown = [], []
    pattern = re.compile(r'\bWindowID\s*=\s*"%s"' % re.escape(window_id))
    for name in names:
        text = official_text_for(game_dir, name)
        if text is None:
            unknown.append(name)
        elif pattern.search(text):
            found.append(name)
    return found or unknown  # sem cópia oficial para conferir, oferece todos os do .cpp
