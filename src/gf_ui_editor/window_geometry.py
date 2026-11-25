"""Geometria da janela principal (raiz) quando o jogo decide onde ela fica, sem Qt.

O jogo prende a raiz ao centro (ou a um canto) e desenha cada elemento deslocado dela
por (elemento - raiz). Mover "a janela" no editor, então, é mover o conteúdo na tela: o
X/Y da raiz anda ao contrário. Se o conteúdo sai de cima da raiz, o retângulo dela fica
para trás, invisível, recebendo cliques (a "área fantasma").

Retângulos são tuplas (x, y, largura, altura). O que depende da janela do editor (onde o
jogo põe a raiz, se ela tem fundo visível, a posição salva no User.ini) entra como função,
chamada só quando a conta precisa, na mesma ordem de antes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

Rect = tuple[int, int, int, int]
RectF = tuple[float, float, float, float]
Change = tuple[Rect, Rect]  # (antes, depois)

GHOST_TOLERANCE = 8  # folga, em pixels, antes de considerar que o conteúdo saiu da raiz


def _edges(rect: RectF) -> tuple[float, float, float, float]:
    x, y, width, height = rect
    left, right = (x + width, x) if width < 0 else (x, x + width)
    top, bottom = (y + height, y) if height < 0 else (y, y + height)
    return left, top, right, bottom


def contains(outer: RectF, inner: RectF) -> bool:
    """``inner`` inteiro dentro de ``outer`` (bordas valem), como ``QRectF.contains``."""
    l1, t1, r1, b1 = _edges(outer)
    l2, t2, r2, b2 = _edges(inner)
    if l1 == r1 or t1 == b1 or l2 == r2 or t2 == b2:  # retângulo nulo
        return False
    return l1 <= l2 and r2 <= r1 and t1 <= t2 and b2 <= b1


def grown(rect: RectF, margin: float) -> RectF:
    x, y, width, height = rect
    return x - margin, y - margin, width + 2 * margin, height + 2 * margin


def content_bounds(elements: Iterable[tuple[Rect, tuple[float, float]]]) -> RectF | None:
    """Retângulo que envolve os elementos (geometria do XML + deslocamento do preview).

    Elementos sem largura ou altura contam com 1 px. None se não há elementos.
    """
    left = top = right = bottom = None
    for (x, y, width, height), (dx, dy) in elements:
        ax, ay = x + dx, y + dy
        aw, ah = max(1, width), max(1, height)
        if left is None:
            left, top, right, bottom = ax, ay, ax + aw, ay + ah
        else:
            left, top = min(left, ax), min(top, ay)
            right, bottom = max(right, ax + aw), max(bottom, ay + ah)
    if left is None:
        return None
    return left, top, right - left, bottom - top


def ghost_area(
    root: Rect, bounds: RectF, draws_background: Callable[[], bool], tolerance: float = GHOST_TOLERANCE
) -> Rect | None:
    """Parte da raiz que sobra longe do conteúdo (``bounds``), ou None.

    Só vale para raiz que o jogo posiciona sozinho, com o preview ligado: quem chama
    confere isso antes. ``draws_background`` só é chamada no fim (lê pixels da textura).
    """
    x, y, width, height = root
    if width <= 1 and height <= 1:
        return None
    area = (x, y, max(1, width), max(1, height))
    # Uma dentro da outra é uma janela comum (com folga ou com conteúdo maior); só
    # há área sobrando quando o conteúdo saiu de cima da janela principal.
    if contains(grown(bounds, tolerance), area):
        return None
    if contains(grown(area, tolerance), bounds):
        return None
    # Com fundo próprio visível a área não é invisível, e encolher apagaria o fundo.
    return None if draws_background() else area


def resized_root(geometry: Rect, width: int, height: int, screen_for: Callable[[Rect], tuple[int, int]]) -> Rect:
    """A raiz com outro tamanho, com o X/Y compensado para o conteúdo não sair do lugar.

    O ponto onde o jogo põe a janela depende do tamanho dela (centro, canto direito...):
    ``screen_for`` diz onde o jogo poria a raiz com uma dada geometria.
    """
    x, y = geometry[:2]
    before = screen_for(geometry)
    after = screen_for((x, y, width, height))
    return x + after[0] - before[0], y + after[1] - before[1], width, height


def collapsed_root(geometry: Rect, screen_for: Callable[[Rect], tuple[int, int]]) -> Rect:
    """A mesma raiz com 1 x 1, sem tirar o conteúdo do lugar."""
    return resized_root(geometry, 1, 1, screen_for)


def root_move_as_screen_move(
    changes: dict[int, Change],
    geometries: Mapping[int, Rect],
    locked: set[int] | frozenset[int],
    *,
    set_by_game: Callable[[], bool],
    resize_root: Callable[[Rect, int, int], Rect],
    frame_on_screen: Callable[[], tuple[int, int] | None],
    without_ghost_area: Callable[[Rect], Rect],
    preview_default_position: Callable[[], tuple[int, int] | None],
) -> dict[int, Change]:
    """Mudanças de um arraste em que a raiz entrou, já no sentido que o jogo entende.

    - Só a raiz, numa janela que o jogo fixa: o conteúdo vai aonde ela foi levada, então
      o X/Y da raiz anda ao contrário (e encolhe se ficaria uma área fantasma).
    - Só a raiz, numa janela comum: arrastá-la move a janela inteira (menos os bloqueados).
    - Raiz junto com elementos: a diferença entre eles não muda, nada é invertido.

    ``geometries``: geometria atual de cada elemento, por índice (0 = raiz).
    """
    if 0 not in changes:
        return changes
    # A moldura da raiz pode estar desenhada fora do X/Y do XML: vale o deslocamento.
    old, new = changes[0]
    dx, dy = new[0] - old[0], new[1] - old[1]
    root = geometries[0]
    x, y = root[:2]
    if set(changes) == {0} and set_by_game():
        if new[2:] != old[2:]:
            moved = (x - dx, y - dy, root[2], root[3])
            return {0: (root, resize_root(moved, new[2], new[3]))}
        moved = (x - dx, y - dy, new[2], new[3])
        if frame_on_screen() is not None and (dx or dy):
            moved = without_ghost_area(moved)
        return {0: (root, moved)}
    if set(changes) == {0} and new[2:] == old[2:] and (dx or dy):
        # Janela comum: arrastar a principal é mover a janela inteira. Movendo tudo junto,
        # muda a posição padrão dela sem mexer na relação entre os elementos.
        shown_at = preview_default_position()
        if shown_at is not None:
            # A janela estava desenhada na posição salva: o padrão do XML passa a ser
            # o ponto da tela onde ela foi solta, não o X/Y antigo mais o arraste.
            dx, dy = shown_at[0] + dx - x, shown_at[1] + dy - y
        return {
            index: (geometry, (geometry[0] + dx, geometry[1] + dy, geometry[2], geometry[3]))
            for index, geometry in geometries.items()
            if index == 0 or index not in locked
        }
    return {**changes, 0: (root, (x + dx, y + dy, new[2], new[3]))}


def root_from_panel(
    root: Rect,
    typed: Rect,
    frame: tuple[int, int],
    *,
    resize_root: Callable[[Rect, int, int], Rect],
    without_ghost_area: Callable[[Rect], Rect],
) -> Rect:
    """Geometria da raiz a partir do painel, quando ele mostra a posição da moldura na tela.

    ``typed`` é o que foi digitado (X/Y na tela, largura, altura) e ``frame`` onde a moldura
    está agora. A raiz anda ao contrário (ver ``root_move_as_screen_move``).
    """
    moved_root = (root[0] - (typed[0] - frame[0]), root[1] - (typed[1] - frame[1]), root[2], root[3])
    if typed[2:] != root[2:]:
        # Mudar o tamanho desloca o ponto onde o jogo põe a janela: o conteúdo não deve pular.
        return resize_root(moved_root, typed[2], typed[3])
    if moved_root != root:
        return without_ghost_area(moved_root)
    return moved_root
