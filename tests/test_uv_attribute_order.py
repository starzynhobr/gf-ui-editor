import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from gf_ui_editor.xml_document import UIDocument, UVRect


def client_rect(node: ET.Element, state: str) -> tuple[int, int, int, int]:
    # Leitor do cliente em 0x00A2BBF0: acumula Width/Height na posição já lida.
    left = top = right = bottom = 0
    for name, value in node.attrib.items():
        if name == state + "Left":
            left = int(value)
        elif name == state + "Top":
            top = int(value)
        elif name == state + "Width":
            right = left + int(value)
        elif name == state + "Height":
            bottom = top + int(value)
    return left, top, right - left, bottom - top


@pytest.mark.parametrize("state", ["NorUV", "FocusUV", "DownUV", "DisableUV"])
def test_moving_and_saving_repairs_existing_uv_before_publish(tmp_path: Path, state: str) -> None:
    from gf_ui_editor.project import Project

    game = tmp_path / "game"
    ui = game / "UI"
    ui.mkdir(parents=True)
    bad = f'<{state} {state}Top="254" {state}Width="88" {state}Height="88" {state}Left="18" />'
    fixed = f'<{state} {state}Top="254" {state}Left="18" {state}Height="88" {state}Width="88" />'
    children = (
        f'<BackGroundMap BGmap="main.dds">{bad}</BackGroundMap>'
        if state == "NorUV" else f'<ButtonNode>{bad}</ButtonNode>'
    )
    original = (
        '<?xml version="1.0" ?>\r\n<Root_Node>\r\n'
        '<BaseWndProperty WindowID="2" WindowLeft="18" WindowTop="2" WindowHeight="88" WindowWidth="88">'
        f'{children}</BaseWndProperty>\r\n</Root_Node>\r\n'
    ).encode("big5")
    (ui / "BasicChar.xml").write_bytes(original)
    project = Project.create("UV repair", ui, game, projects_root=tmp_path / "projects")
    path = project.ui_dir / "BasicChar.xml"
    document = UIDocument.load(path)
    assert not document.is_dirty
    assert document.render_text().encode("big5") == original
    document.set_geometry(0, (17, 2, 88, 88))  # só move; não abre nem modifica o atlas
    expected = original.replace(b'WindowLeft="18"', b'WindowLeft="17"').replace(bad.encode(), fixed.encode())
    assert document.render_text().encode("big5") == expected
    backup = document.save(project.history_path_for(path))
    assert backup.read_bytes() == original
    project.publish()
    assert (ui / path.name).read_bytes() == expected
    assert (game / "UICustom" / project.custom_name / path.name).read_bytes() == expected
    saved = UIDocument.load(ui / path.name)
    assert client_rect(ET.fromstring(saved.text).find(f".//{state}"), state) == (18, 254, 88, 88)
    assert saved.render_text().encode("big5") == expected
    assert not saved.is_dirty


@pytest.mark.parametrize("state", ["NorUV", "FocusUV", "DownUV", "DisableUV"])
@pytest.mark.parametrize("positions", ["missing", "after_size", "before_size"])
def test_edited_uv_survives_client_attribute_order(tmp_path: Path, state: str, positions: str) -> None:
    size = f'{state}Width="88" {state}Height="88"'
    position = f'{state}Left="2" {state}Top="3"'
    attrs = {
        "missing": size,
        "after_size": f"{size} {position}",
        "before_size": f"{position} {size}",
    }[positions]
    tag = f'<{state} {attrs} />'
    normal = '<NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="88" NorUVHeight="88" />'
    children = (
        f'<BackGroundMap BGmap="main.dds">{tag}</BackGroundMap>'
        if state == "NorUV" else
        f'<BackGroundMap BGmap="main.dds">{normal}</BackGroundMap><ButtonNode>{tag}</ButtonNode>'
    )
    original = (
        '<?xml version="1.0" ?>\r\n<Root_Node>\r\n'
        f'  <BaseWndProperty WindowID="2" WindowText="測試">{children}</BaseWndProperty>\r\n'
        '</Root_Node>\r\n'
    ).encode("big5")
    path = tmp_path / "Frame.xml"
    path.write_bytes(original)
    document = UIDocument.load(path)
    assert document.render_text().encode("big5") == original
    uv = UVRect(18, 254, 88, 88)
    if state == "NorUV":
        document.set_uv(0, uv)
    else:
        document.set_button_uv(0, state, uv)

    rendered = document.render_text()
    node = ET.fromstring(rendered).find(f".//{state}")
    assert client_rect(node, state) == (18, 254, 88, 88)
    # O resto do arquivo, incluindo Big5 e CRLF, deve continuar byte a byte igual.
    start = rendered.index(f"<{state} ")
    end = rendered.index("/>", start) + 2
    assert rendered[:start] + tag + rendered[end:] == original.decode("big5")
    backup = document.save()
    assert backup.read_bytes() == original
    assert not document.is_dirty
    saved = UIDocument.load(path)
    assert saved.render_text() == rendered
    assert client_rect(ET.fromstring(saved.text).find(f".//{state}"), state) == (18, 254, 88, 88)
