"""Exportar para várias resoluções, sem Qt.

O jogo não escala a interface: numa tela maior, cada janela continua com o mesmo tamanho
em pixels, e quem decide onde ela fica é o próprio jogo (`game_layout`). Para a UI parecer
igual em outra resolução, cada pedaço visível tem de ir para "o mesmo lugar" da tela maior.

Para cada XML, a conta é a do preview (`describe_scene`): a raiz aparece onde o jogo a põe
(`root_screen_position`) e cada elemento aparece deslocado dela por (elemento - raiz).

1. Os elementos viram **pedaços**: grupos que se encostam na tela (o BasicChar, por exemplo,
   tem o retrato no canto e as barras de vida no meio, longe dali). Elementos de tamanho zero
   entram no pedaço mais próximo; elementos estacionados fora da tela ficam onde estão.
2. Cada pedaço ganha uma **regra**, por eixo, a partir de onde o seu centro está na
   resolução base: nos 35% da esquerda (ou do topo) mantém a distância dessa borda; nos
   35% da direita (ou da base) mantém a distância dela; nos 30% do meio mantém a proporção
   do espaço livre (o que está centralizado continua centralizado). Em janelas que o jogo
   posiciona sozinho, o pedaço que ainda está junto da janela principal fica igual: o jogo
   já o leva junto.
3. Para cada resolução alvo, o pedaço vai para o lugar que a regra (ou o ajuste manual da
   pessoa, que vence a regra) manda, e o XML é reescrito com o mínimo de mudanças: quando
   tudo anda junto numa janela posicionada pelo jogo, só a raiz muda (como o Harlem fez no
   ElfAttack); senão, cada elemento do pedaço anda.

Os ajustes manuais e as variantes de arte ficam no projeto (`ResolutionStore`), só com o que
difere da base: `resolutions.json` e a pasta `resolutions/<L>x<A>/` com os arquivos que
valem só naquela resolução.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import TYPE_CHECKING
import zipfile

from . import game_layout
from .xml_document import DocumentError, UIDocument

if TYPE_CHECKING:
    from .project import Progress, Project

Rect = tuple[int, int, int, int]
Resolution = tuple[int, int]

# As quatro resoluções das UIs do Harlem (e as mais comuns entre os jogadores).
COMMON_RESOLUTIONS: tuple[Resolution, ...] = ((1366, 768), (1600, 900), (1920, 1080), (2560, 1440))
DEFAULT_BASE: Resolution = (1366, 768)
# Distância (px) até a qual dois elementos contam como o mesmo pedaço: junta botões e
# linhas de uma lista (os quadros do Team, por exemplo) e separa o que está longe de verdade
# (as barras de vida do BasicChar, a centenas de pixels do retrato).
GAP = 48
# Regras por eixo. "game": o jogo leva o pedaço junto da janela (fica igual).
START, MIDDLE, END, GAME = "start", "middle", "end", "game"
STORE_NAME = "resolutions.json"
VARIANTS_DIR = "resolutions"
STORE_FORMAT = 1
MIN_SIZE, MAX_SIZE = 640, 7680


def resolution_key(resolution: Resolution) -> str:
    return f"{resolution[0]}x{resolution[1]}"


def parse_resolution_key(text: str) -> Resolution | None:
    match = re.fullmatch(r"\s*(\d{3,5})\s*[x×]\s*(\d{3,5})\s*", str(text))
    if not match:
        return None
    size = int(match.group(1)), int(match.group(2))
    return size if valid_resolution(size) else None


def valid_resolution(size: object) -> bool:
    return (
        isinstance(size, (tuple, list)) and len(size) == 2
        and all(type(value) is int and MIN_SIZE // 2 <= value <= MAX_SIZE for value in size)
    )


# ---- geometria ----------------------------------------------------------------------------
def _intersects(a: Rect, b: Rect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _grown(rect: Rect, margin: int) -> Rect:
    return rect[0] - margin, rect[1] - margin, rect[2] + 2 * margin, rect[3] + 2 * margin


def _union(rects: Iterable[Rect]) -> Rect:
    rects = list(rects)
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return left, top, right - left, bottom - top


def _distance(a: Rect, b: Rect) -> int:
    dx = max(0, b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
    dy = max(0, b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
    return max(dx, dy)


EDGE_ZONE = 0.35


def infer_axis(start: int, length: int, size: int) -> str:
    """Faixa da tela em que o centro do pedaço está: perto do começo, no meio ou perto do fim."""
    if size - length <= 0:
        return START
    center = (start + length / 2) / size
    if center < EDGE_ZONE:
        return START
    if center > 1 - EDGE_ZONE:
        return END
    return MIDDLE


def place_axis(rule: str, start: int, length: int, size: int, target: int) -> int:
    """Começo do pedaço na tela alvo, pela regra do eixo."""
    if rule == END:
        position = target - length - (size - start - length)
    elif rule == MIDDLE:
        free = size - length
        position = round(start / free * (target - length)) if free > 0 else start
    else:  # START e GAME (este não chega aqui: quem chama mantém o pedaço)
        position = start
    # Mantém na tela quando cabe (o jogo empurraria a janela inteira para dentro).
    if length <= target:
        position = min(max(0, position), target - length)
    return position


# ---- análise de uma janela ----------------------------------------------------------------
@dataclass(frozen=True)
class WindowSource:
    """Um XML com o que define onde o jogo o põe (modo da raiz e pasta do jogo)."""

    relative: str
    document: UIDocument
    mode: str = "auto"
    game_dir: Path | None = None

    @property
    def name(self) -> str:
        return Path(self.relative).name

    def screen_for(self, resolution: Resolution, rect: Rect) -> tuple[int, int]:
        return game_layout.root_screen_position(
            self.name, resolution, rect, None, mode=self.mode, game_dir=self.game_dir
        )


GAME_PLACED, FIXED, UNKNOWN = "game", "fixed", "unknown"


def window_kind(name: str, mode: str = "auto", game_dir: Path | None = None) -> str | None:
    """Quem decide onde a janela fica.

    "game": o jogo (centraliza ou ancora); "fixed": o X/Y do XML (confirmado no executável,
    ou a escolha "X/Y do XML" da pessoa); "unknown": ainda não mapeado, então fica como
    está; None: arquivo que o jogo não carrega.
    """
    if mode == "center":
        return GAME_PLACED
    if mode == "xml":
        return FIXED
    placement = game_layout.placement(name, game_dir)
    if placement == "unused":
        return None
    if placement in ("anchor", "placed", "centered"):
        return GAME_PLACED
    return FIXED if placement == "xml" else UNKNOWN


@dataclass(frozen=True)
class Piece:
    key: str  # "id:<WindowID do primeiro elemento>" (estável entre resoluções)
    indexes: tuple[int, ...]
    rect: Rect  # na tela, na resolução base
    rule: tuple[str, str]  # (horizontal, vertical)


@dataclass(frozen=True)
class WindowPlan:
    relative: str
    kind: str  # GAME_PLACED, FIXED ou UNKNOWN
    base: Resolution
    pieces: tuple[Piece, ...]
    parked: tuple[int, ...] = ()  # elementos fora da tela: ficam onde estão

    @property
    def by_game(self) -> bool:
        return self.kind == GAME_PLACED

    def piece(self, key: str) -> Piece | None:
        return next((piece for piece in self.pieces if piece.key == key), None)


def _has_texture(document: UIDocument, index: int) -> bool:
    element = document.elements[index]
    return bool(element.texture_name) and element.uv is not None and element.uv.width > 0 and element.uv.height > 0


def screen_rects(source: WindowSource, resolution: Resolution, document: UIDocument | None = None) -> list[Rect]:
    """Onde cada elemento aparece na tela (mesma conta do preview)."""
    document = document or source.document
    root = document.elements[0].geometry
    screen_x, screen_y = source.screen_for(resolution, root)
    rects = [(screen_x, screen_y, root[2], root[3])]
    for element in document.elements[1:]:
        x, y, width, height = element.geometry
        rects.append((screen_x + x - root[0], screen_y + y - root[1], width, height))
    return rects


def analyze(source: WindowSource, base: Resolution) -> WindowPlan | None:
    """Pedaços da janela e a regra de cada um. None: arquivo que o jogo não usa ou sem elementos."""
    document = source.document
    kind = window_kind(source.name, source.mode, source.game_dir)
    if kind is None or not document.elements:
        return None
    rects = screen_rects(source, base)
    screen = (0, 0, *base)
    root_rect = (rects[0][0], rects[0][1], max(1, rects[0][2]), max(1, rects[0][3]))
    solid: list[int] = []  # semeiam pedaços
    points: list[int] = []  # tamanho zero: entram no pedaço mais próximo
    parked: list[int] = []
    for index, rect in enumerate(rects):
        sized = (rect[0], rect[1], max(1, rect[2]), max(1, rect[3]))
        if index == 0 and not _has_texture(document, 0):
            continue  # raiz sem fundo é só o ponto de referência da janela
        if not _intersects(sized, screen):
            parked.append(index)
        elif rect[2] > 1 and rect[3] > 1:
            solid.append(index)
        elif index:
            points.append(index)

    # União dos elementos que se encostam (com folga de GAP px).
    parent = {index: index for index in solid}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    grown = {index: _grown(rects[index], GAP) for index in solid}
    for position, a in enumerate(solid):
        for b in solid[position + 1:]:
            if _intersects(grown[a], rects[b]) and find(a) != find(b):
                parent[find(b)] = find(a)
    groups: dict[int, list[int]] = {}
    for index in solid:
        groups.setdefault(find(index), []).append(index)
    bounds = {leader: _union(rects[i] for i in members) for leader, members in groups.items()}
    for index in points:
        point = (rects[index][0], rects[index][1], 1, 1)
        if bounds:
            leader = min(bounds, key=lambda key: (_distance(bounds[key], point), key))
            groups[leader].append(index)
        else:
            groups.setdefault(index, []).append(index)
            bounds[index] = point

    # Numa janela que o jogo posiciona, só o conteúdo que a pessoa soltou da janela principal
    # (a raiz encolhida para 0 ou 1 px, como o editor faz ao arrastar) ganha regra própria.
    # Com a raiz no tamanho real, o jogo leva tudo junto e a janela fica como está.
    detached_root = root_rect[2] <= 1 or root_rect[3] <= 1
    pieces = []
    for leader, members in sorted(groups.items(), key=lambda item: min(item[1])):
        members.sort()
        rect = _union(
            (rects[i][0], rects[i][1], max(1, rects[i][2]), max(1, rects[i][3])) for i in members
        )
        inside = rect[0] >= 0 and rect[1] >= 0 and rect[0] + rect[2] <= base[0] and rect[1] + rect[3] <= base[1]
        follows = kind == UNKNOWN or not inside or (
            kind == GAME_PLACED and (not detached_root or _intersects(_grown(rect, GAP), root_rect))
        )
        if follows:
            rule = (GAME, GAME)
        else:
            rule = (infer_axis(rect[0], rect[2], base[0]), infer_axis(rect[1], rect[3], base[1]))
        key = f"id:{document.elements[members[0]].window_id}"
        if any(piece.key == key for piece in pieces):
            key = f"{key}#{members[0]}"
        pieces.append(Piece(key, tuple(members), rect, rule))
    return WindowPlan(source.relative, kind, base, tuple(pieces), tuple(parked))


def target_rect(piece: Piece, base: Resolution, target: Resolution, adjusted: tuple[int, int] | None = None) -> Rect:
    """Onde o pedaço deve aparecer na tela alvo (o ajuste manual vence a regra)."""
    x, y, width, height = piece.rect
    if adjusted is not None:
        return adjusted[0], adjusted[1], width, height
    if piece.rule == (GAME, GAME):
        return piece.rect  # quem chama troca pela posição que o jogo dá
    return (
        place_axis(piece.rule[0], x, width, base[0], target[0]),
        place_axis(piece.rule[1], y, height, base[1], target[1]),
        width, height,
    )


@dataclass
class PiecePlacement:
    key: str
    indexes: tuple[int, ...]
    rule: tuple[str, str]
    base_rect: Rect  # na resolução base
    rect: Rect  # na resolução alvo, depois da regra ou do ajuste
    adjusted: bool
    moved: bool = False  # o XML muda para este pedaço ficar no lugar


@dataclass
class WindowResult:
    relative: str
    kind: str
    pieces: list[PiecePlacement]
    geometries: dict[int, Rect]  # só os elementos que mudam no XML
    text: str | None  # XML reescrito, ou None se fica igual

    @property
    def changed(self) -> bool:
        return self.text is not None


def generate(
    source: WindowSource,
    plan: WindowPlan,
    target: Resolution,
    adjustments: Mapping[str, tuple[int, int]] | None = None,
) -> WindowResult:
    """Coordenadas do XML que deixam cada pedaço no lugar certo na resolução alvo."""
    adjustments = adjustments or {}
    document = source.document
    now = screen_rects(source, target)  # com o XML como está
    corrections: dict[str, tuple[int, int]] = {}
    placements = []
    for piece in plan.pieces:
        current = _union((now[i][0], now[i][1], max(1, now[i][2]), max(1, now[i][3])) for i in piece.indexes)
        adjusted = adjustments.get(piece.key)
        if adjusted is None and piece.rule == (GAME, GAME):
            wanted = current
        else:
            wanted = target_rect(piece, plan.base, target, adjusted)
        corrections[piece.key] = (wanted[0] - current[0], wanted[1] - current[1])
        placements.append(PiecePlacement(
            piece.key, piece.indexes, piece.rule, piece.rect, wanted, adjusted is not None,
            corrections[piece.key] != (0, 0),
        ))

    geometries: dict[int, Rect] = {}
    moving = {key: delta for key, delta in corrections.items() if delta != (0, 0)}
    if moving:
        root = document.elements[0].geometry
        deltas = set(corrections.values())
        whole = len(deltas) == 1 and not plan.parked and all(
            0 not in piece.indexes for piece in plan.pieces
        )
        shifted = None
        if whole and plan.by_game:
            (dx, dy), = deltas
            candidate = (root[0] - dx, root[1] - dy, root[2], root[3])
            # Só vale se a raiz continua no mesmo ponto da tela (o jogo a posiciona pelo tamanho).
            if source.screen_for(target, candidate) == source.screen_for(target, root):
                shifted = candidate
        if shifted is not None:
            geometries[0] = shifted
        else:
            for piece in plan.pieces:
                dx, dy = corrections[piece.key]
                if (dx, dy) == (0, 0):
                    continue
                for index in piece.indexes:
                    x, y, width, height = document.elements[index].geometry
                    geometries[index] = (x + dx, y + dy, width, height)
    text = None
    if geometries:
        originals = {index: document.elements[index].geometry for index in geometries}
        try:
            for index, geometry in geometries.items():
                document.set_geometry(index, geometry)
            text = document.render_text()
        finally:
            for index, geometry in originals.items():
                document.set_geometry(index, geometry)
    return WindowResult(source.relative, plan.kind, placements, geometries, text)


# ---- ajustes e variantes guardados no projeto ----------------------------------------------
@dataclass
class ResolutionSettings:
    base: Resolution | None = None
    targets: list[Resolution] = field(default_factory=list)
    # arquivo -> "LxA" -> pedaço -> (x, y) na tela daquela resolução
    adjustments: dict[str, dict[str, dict[str, tuple[int, int]]]] = field(default_factory=dict)

    def for_file(self, relative: str, target: Resolution) -> dict[str, tuple[int, int]]:
        for name, by_resolution in self.adjustments.items():
            if name.lower() == relative.lower():
                return dict(by_resolution.get(resolution_key(target), {}))
        return {}


class ResolutionStore:
    """`resolutions.json` (ajustes) e `resolutions/<LxA>/` (arquivos só daquela resolução)."""

    def __init__(self, root: Path):
        self.root = root

    @property
    def path(self) -> Path:
        return self.root / STORE_NAME

    @property
    def variants_root(self) -> Path:
        return self.root / VARIANTS_DIR

    def load(self) -> ResolutionSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ResolutionSettings()
        if not isinstance(data, dict):
            return ResolutionSettings()
        base = tuple(data.get("base") or ()) or None
        targets = [tuple(item) for item in data.get("targets") or [] if valid_resolution(item)]
        adjustments: dict[str, dict[str, dict[str, tuple[int, int]]]] = {}
        for name, by_resolution in (data.get("adjustments") or {}).items():
            if not isinstance(by_resolution, dict):
                continue
            for key, pieces in by_resolution.items():
                if parse_resolution_key(key) is None or not isinstance(pieces, dict):
                    continue
                for piece, point in pieces.items():
                    if isinstance(point, list) and len(point) == 2 and all(type(v) is int for v in point):
                        adjustments.setdefault(str(name), {}).setdefault(key, {})[str(piece)] = (point[0], point[1])
        return ResolutionSettings(base if valid_resolution(base) else None, targets, adjustments)

    def save(self, settings: ResolutionSettings) -> None:
        adjustments = {
            name: {key: {piece: list(point) for piece, point in pieces.items()} for key, pieces in by_res.items() if pieces}
            for name, by_res in sorted(settings.adjustments.items())
        }
        adjustments = {name: by_res for name, by_res in adjustments.items() if by_res}
        data = {
            "format": STORE_FORMAT,
            "base": list(settings.base) if settings.base else None,
            "targets": [list(item) for item in settings.targets],
            "adjustments": adjustments,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".resolutions.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def set_adjustment(self, relative: str, target: Resolution, piece: str, point: tuple[int, int] | None) -> ResolutionSettings:
        settings = self.load()
        name = next((known for known in settings.adjustments if known.lower() == relative.lower()), relative)
        by_res = settings.adjustments.setdefault(name, {})
        pieces = by_res.setdefault(resolution_key(target), {})
        if point is None:
            pieces.pop(piece, None)
        else:
            pieces[piece] = (int(point[0]), int(point[1]))
        if not pieces:
            by_res.pop(resolution_key(target), None)
        if not by_res:
            settings.adjustments.pop(name, None)
        self.save(settings)
        return settings

    def variant_dir(self, target: Resolution) -> Path:
        return self.variants_root / resolution_key(target)

    def variants(self, target: Resolution) -> dict[str, Path]:
        """Arquivos que valem só nesta resolução, por caminho relativo à pasta ui."""
        folder = self.variant_dir(target)
        if not folder.is_dir():
            return {}
        return {
            path.relative_to(folder).as_posix(): path
            for path in sorted(folder.rglob("*")) if path.is_file()
        }

    def add_variant(self, target: Resolution, relative: str, source: Path) -> Path:
        relative_path = Path(relative)
        if relative_path.anchor or ".." in relative_path.parts or not relative_path.parts:
            raise ValueError(f"Caminho inválido: {relative}")
        destination = self.variant_dir(target) / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Uma variante por nome, sem diferença de maiúsculas (o jogo roda no Windows).
        for existing, path in self.variants(target).items():
            if existing.lower() == relative_path.as_posix().lower() and path != destination:
                path.unlink()
        shutil.copyfile(source, destination)
        return destination

    def remove_variant(self, target: Resolution, relative: str) -> bool:
        for existing, path in self.variants(target).items():
            if existing.lower() == relative.lower():
                path.unlink()
                folder = path.parent
                while folder != self.variants_root and folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                    folder = folder.parent
                return True
        return False


# ---- o projeto inteiro ---------------------------------------------------------------------
def project_sources(project: "Project", relatives: Iterable[str] | None = None) -> list[WindowSource]:
    """Os XMLs do projeto como `WindowSource` (ignora os que não abrem)."""
    wanted = {name.lower() for name in relatives} if relatives is not None else None
    modes = {name.lower(): mode for name, mode in project.root_modes.items()}
    sources = []
    for relative in project.files():
        key = relative.as_posix()
        if relative.suffix.lower() != ".xml" or (wanted is not None and key.lower() not in wanted):
            continue
        try:
            document = project.load_document(project.ui_dir / relative)
        except (DocumentError, OSError):
            continue
        sources.append(WindowSource(key, document, modes.get(key.lower(), "auto"), project.game_dir))
    return sources


@dataclass
class ResolutionOutput:
    target: Resolution
    windows: list[WindowResult]  # todas as janelas analisadas
    files: dict[str, bytes | Path]  # o que muda nesta resolução (XML gerado ou variante)


def build_outputs(
    sources: Iterable[WindowSource],
    base: Resolution,
    targets: Iterable[Resolution],
    settings: ResolutionSettings,
    store: ResolutionStore | None = None,
) -> list[ResolutionOutput]:
    plans = [(source, plan) for source in sources if (plan := analyze(source, base)) is not None]
    return outputs_from_plans(plans, targets, settings, store)


def outputs_from_plans(
    plans: Iterable[tuple[WindowSource, WindowPlan]],
    targets: Iterable[Resolution],
    settings: ResolutionSettings,
    store: ResolutionStore | None = None,
) -> list[ResolutionOutput]:
    """O que vai no zip de cada resolução: XML gerados e, por cima, as variantes da pessoa."""
    plans = list(plans)
    outputs = []
    for target in targets:
        windows: list[WindowResult] = []
        files: dict[str, bytes | Path] = {}
        for source, plan in plans:
            result = generate(source, plan, target, settings.for_file(source.relative, target))
            windows.append(result)
            if result.text is not None:
                files[source.relative] = result.text.encode(UIDocument.encoding)
        if store is not None:
            for relative, path in store.variants(target).items():
                for name in [name for name in files if name.lower() == relative.lower()]:
                    del files[name]
                files[relative] = path
        outputs.append(ResolutionOutput(target, windows, files))
    return outputs


def zip_name(custom_name: str, target: Resolution | None) -> str:
    suffix = resolution_key(target) if target else "All Resolution"
    return f"{custom_name} {suffix}"


def export_zips(
    project: "Project",
    folder: Path,
    outputs: list[ResolutionOutput],
    *,
    whole: bool,
    all_resolution: bool,
    progress: "Progress" = None,
) -> list[tuple[Resolution | None, Path, int]]:
    """Um zip por resolução (`<Projeto> 1920x1080.zip`) e, se pedido, o "All Resolution".

    `whole`: cada zip leva a UI exportável inteira com os arquivos da resolução por cima;
    senão, só o que muda naquela resolução. Resoluções sem nada a mudar, no modo "só o que
    muda", não geram zip (contagem 0 no resultado).
    """
    folder.mkdir(parents=True, exist_ok=True)
    shipped: list[Path] = project.shipped_files()[0] if whole or all_resolution else []
    jobs: list[tuple[Resolution | None, dict[str, bytes | Path]]] = []
    for output in outputs:
        files: dict[str, bytes | Path] = {}
        if whole:
            files = {relative.as_posix(): project.resolve(relative) for relative in shipped}
            for name, content in output.files.items():
                for existing in [key for key in files if key.lower() == name.lower()]:
                    del files[existing]
                files[name] = content
        else:
            files = dict(output.files)
        jobs.append((output.target, files))
    if all_resolution:
        jobs.append((None, {relative.as_posix(): project.resolve(relative) for relative in shipped}))
    total = sum(len(files) for _target, files in jobs) or 1
    done = 0
    results = []
    for target, files in jobs:
        name = zip_name(project.custom_name, target)
        if not files:
            results.append((target, folder / f"{name}.zip", 0))
            continue
        destination = folder / f"{name}.zip"
        fd, temporary = tempfile.mkstemp(prefix=".gf-ui-", suffix=".zip", dir=folder)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                for relative in sorted(files, key=str.lower):
                    content = files[relative]
                    arcname = f"{name}/{relative}"
                    if isinstance(content, Path):
                        archive.write(content, arcname)
                    else:
                        archive.writestr(arcname, content)
                    done += 1
                    if progress is not None:
                        progress(done, total)
            os.replace(temporary, destination)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        results.append((target, destination, len(files)))
    return results


def window_summary(result: WindowResult) -> dict:
    """Resumo para a interface (JSON)."""
    return {
        "file": result.relative,
        "kind": result.kind,
        "changed": result.changed,
        "pieces": [
            {
                "key": piece.key,
                "indexes": list(piece.indexes),
                "rule": list(piece.rule),
                "base": list(piece.base_rect),
                "rect": list(piece.rect),
                "adjusted": piece.adjusted,
                "moved": piece.moved,
            }
            for piece in result.pieces
        ],
    }


def describe_rule(rule: tuple[str, str]) -> str:
    """Frase curta, sem jargão, para logs e testes (a interface traduz pelos códigos)."""
    if rule == (GAME, GAME):
        return "o jogo cuida"
    horizontal = {START: "esquerda", MIDDLE: "meio", END: "direita"}[rule[0]]
    vertical = {START: "topo", MIDDLE: "meio", END: "base"}[rule[1]]
    if horizontal == vertical == "meio":
        return "fica no meio"
    return f"fica em {vertical}/{horizontal}"


def resolution_list(values: Iterable[object]) -> list[Resolution]:
    """Resoluções válidas, sem repetir, na ordem dada."""
    result: list[Resolution] = []
    for value in values:
        size = parse_resolution_key(value) if isinstance(value, str) else (tuple(value) if valid_resolution(value) else None)
        if size is not None and size not in result:
            result.append(size)
    return result


__all__ = [
    "COMMON_RESOLUTIONS", "WindowSource", "WindowPlan", "Piece", "analyze", "generate", "target_rect",
    "ResolutionStore", "ResolutionSettings", "build_outputs", "outputs_from_plans", "export_zips", "project_sources",
    "window_summary", "resolution_key", "parse_resolution_key", "window_kind", "screen_rects",
]

