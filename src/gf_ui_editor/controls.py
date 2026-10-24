"""Criar, duplicar e apagar controles direto no texto do XML (o resto fica byte a byte igual).

Cada controle é um par `<Style …/>` + `<BaseWndProperty WindowID="…">…</BaseWndProperty>`
dentro do `Container_Node` da janela, que declara quantos filhos tem (`Child_Cnt`).

O jogo procura os controles que usa pelo WindowID. Um controle com ID novo é só
desenhado (imagem, moldura, texto fixo): a UI-Hero tem dezenas assim. Um botão
duplicado aparece, mas não faz nada, porque o jogo não conhece o ID dele.
"""

from __future__ import annotations

import re

from .game_updates import _blocks, _containers, _line_indent, _parse, _Node, window_ids
from .xml_document import UVRect


_WINDOW_ID_ATTR = re.compile(r'(\bWindowID\s*=\s*")([^"]*)(")')
_CHILD_CNT_RE = re.compile(r'(\bChild_Cnt\s*=\s*")(\d+)(")')


class ControlError(ValueError):
    """A operação não pode ser feita neste controle (motivo na mensagem)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _find(text: str, window_id: str) -> tuple[_Node, _Node, int, int]:
    """(Container_Node, BaseWndProperty, início do bloco com o Style, fim) do controle."""
    for _owner, container in _containers(_parse(text)):
        for block_id, start, end in _blocks(container):
            if block_id == window_id:
                node = next(child for child in container.children or [] if child.window_id == window_id)
                return container, node, start, end
    raise ControlError("not_found")


def _has_children(node: _Node) -> bool:
    return any(child.name == "Container_Node" for child in node.children or [])


def _set_attribute(tag: str, name: str, value: str) -> str:
    pattern = re.compile(rf'(\b{re.escape(name)}\s*=\s*")[^"]*(")')
    if pattern.search(tag):
        return pattern.sub(lambda match: f"{match.group(1)}{value}{match.group(2)}", tag, count=1)
    closing = re.search(r"\s*/?>$", tag)
    return tag[:closing.start()] + f' {name}="{value}"' + tag[closing.start():]


def _number(tag: str, name: str) -> int:
    match = re.search(rf'\b{re.escape(name)}\s*=\s*"(-?\d+)"', tag)
    return int(match.group(1)) if match else 0


def _bump_count(text: str, container: _Node, delta: int) -> tuple[int, int, str] | None:
    open_tag = text[container.start:container.open_end]
    count = _CHILD_CNT_RE.search(open_tag)
    if count is None:
        return None
    new_tag = open_tag[:count.start(2)] + str(max(0, int(count.group(2)) + delta)) + open_tag[count.end(2):]
    return container.start, container.open_end, new_tag


def _apply(text: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, replacement in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def free_window_id(text: str, after: str, reserved: set[str] = frozenset()) -> str:
    """Primeiro WindowID livre depois de `after`, fora dos usados no arquivo e dos `reserved`
    (os IDs que o jogo procura, para um enfeite novo não ocupar um deles)."""
    used = set(re.findall(r'\bWindowID\s*=\s*"([^"]*)"', text)) | set(reserved)
    candidate = int(after) + 1 if after.isdigit() else 1
    while str(candidate) in used:
        candidate += 1
    return str(candidate)


def duplicate_control(text: str, window_id: str, new_id: str, offset: tuple[int, int] = (8, 8)) -> str:
    """Cópia do controle logo depois dele, com `new_id` e deslocada para não ficar por cima."""
    container, node, start, end = _find(text, window_id)
    if _has_children(node):
        raise ControlError("has_children")
    if new_id in window_ids(text):
        raise ControlError("id_in_use")
    nl = "\r\n" if "\r\n" in text else "\n"
    block = text[start:end]
    tag_start = node.start - start
    tag_end = node.open_end - start
    tag = block[tag_start:tag_end]
    tag = _WINDOW_ID_ATTR.sub(lambda match: f"{match.group(1)}{new_id}{match.group(3)}", tag, count=1)
    tag = _set_attribute(tag, "WindowLeft", str(_number(tag, "WindowLeft") + offset[0]))
    tag = _set_attribute(tag, "WindowTop", str(_number(tag, "WindowTop") + offset[1]))
    copy = block[:tag_start] + tag + block[tag_end:]
    edits = [(end, end, nl + _line_indent(text, start) + copy)]
    bump = _bump_count(text, container, 1)
    if bump is not None:
        edits.append(bump)
    return _apply(text, edits)


def new_image_control(
    text: str,
    owner_id: str,
    new_id: str,
    texture: str,
    uv: UVRect,
    position: tuple[int, int],
) -> str:
    """Imagem nova no fim do contêiner da janela `owner_id`, no formato mínimo que o jogo aceita."""
    containers = {owner: node for owner, node in _containers(_parse(text))}
    container = containers.get(owner_id)
    if container is None:
        raise ControlError("no_container")
    if new_id in window_ids(text):
        raise ControlError("id_in_use")
    nl = "\r\n" if "\r\n" in text else "\n"
    blocks = _blocks(container)
    if blocks:
        anchor = blocks[-1][2]
        indent = _line_indent(text, blocks[-1][1])
    else:
        anchor = container.open_end
        indent = _line_indent(text, container.start) + "\t"
    unit = "    " if indent and "\t" not in indent else "\t"
    inner = indent + unit
    deeper = inner + unit
    parent = f' ParentNode="{owner_id}"' if owner_id else ""
    block = (
        f'<Style{parent} CtrlType="268435456" />{nl}'
        f'{indent}<BaseWndProperty WindowID="{new_id}" WindowLeft="{position[0]}" WindowTop="{position[1]}" '
        f'WindowHeight="{uv.width}" WindowWidth="{uv.height}" Visible="1">{nl}'
        f'{inner}<BackGroundMap BGmap="{texture}">{nl}'
        f'{deeper}<NorUV NorUVLeft="{uv.left}" NorUVTop="{uv.top}" NorUVWidth="{uv.width}" NorUVHeight="{uv.height}" />{nl}'
        f'{inner}</BackGroundMap>{nl}'
        f'{indent}</BaseWndProperty>'
    )
    edits = [(anchor, anchor, nl + indent + block)]
    bump = _bump_count(text, container, 1)
    if bump is not None:
        edits.append(bump)
    return _apply(text, edits)


def delete_control(text: str, window_id: str) -> str:
    """Tira o par Style + BaseWndProperty do controle (e a linha que ele ocupava)."""
    container, node, start, end = _find(text, window_id)
    if _has_children(node):
        raise ControlError("has_children")
    line_start = text.rfind("\n", 0, start)
    if line_start >= 0 and not text[line_start + 1:start].strip():
        start = line_start - 1 if line_start > 0 and text[line_start - 1] == "\r" else line_start
    edits = [(start, end, "")]
    bump = _bump_count(text, container, -1)
    if bump is not None:
        edits.append(bump)
    return _apply(text, edits)


def owner_of(text: str, window_id: str) -> str | None:
    """WindowID da janela em cujo contêiner o controle está."""
    for owner, container in _containers(_parse(text)):
        if any(block_id == window_id for block_id, _s, _e in _blocks(container)):
            return owner
    return None
