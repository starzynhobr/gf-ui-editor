from __future__ import annotations

from pathlib import Path

import pytest

from gf_ui_editor.xml_document import ExternalModificationError, UIDocument, UVRect


SAMPLE = """<?xml version="1.0" ?>\r
<Root_Node UI_File_Name="Teste.xml">\r
  <Style Style="65536" />\r
  <BaseWndProperty WindowID="1" WindowHeight="300" WindowWidth="120">\r
    <BackGroundMap BGmap="Slot32.dds" />\r
    <Container_Node Child_Cnt="1">\r
      <Style ParentNode="1" CtrlType="33554432" />\r
      <BaseWndProperty WindowID="2000" WindowText="測試" WindowLeft="10" WindowTop="20" WindowHeight="80" WindowWidth="16">\r
        <BackGroundMap BGmap="main.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="80" NorUVHeight="16" /></BackGroundMap>\r
        <BaseCtrlProperty FontColor="16777215" FontStyle="1" />\r
        <TextNode TextAlign="0" MultiLine="0" />\r
      </BaseWndProperty>\r
    </Container_Node>\r
  </BaseWndProperty>\r
</Root_Node>\r
"""


def write_sample(path: Path) -> bytes:
    raw = SAMPLE.encode("big5")
    path.write_bytes(raw)
    return raw


def test_parses_geometry_hierarchy_and_texture(tmp_path: Path) -> None:
    path = tmp_path / "Teste.xml"
    write_sample(path)
    document = UIDocument.load(path)

    assert len(document.elements) == 2
    root, text = document.elements
    assert root.geometry == (0, 0, 300, 120)
    assert text.geometry == (10, 20, 80, 16)
    assert text.parent_id == "1"
    assert text.kind == "text"
    assert text.texture_name == "main.dds"
    assert text.uv is not None and text.uv.width == 80


def test_save_changes_only_target_attributes_and_creates_exact_backup(tmp_path: Path) -> None:
    path = tmp_path / "Teste.xml"
    original = write_sample(path)
    document = UIDocument.load(path)
    document.set_geometry(1, (14, 25, 90, 18))

    backup = document.save()

    assert backup.read_bytes() == original
    saved = path.read_bytes()
    expected = original.replace(
        b'WindowLeft="10" WindowTop="20" WindowHeight="80" WindowWidth="16"',
        b'WindowLeft="14" WindowTop="25" WindowHeight="90" WindowWidth="18"',
    )
    assert saved == expected
    assert not document.is_dirty


def test_adds_missing_zero_based_position_without_reformatting(tmp_path: Path) -> None:
    path = tmp_path / "Teste.xml"
    original = write_sample(path)
    document = UIDocument.load(path)
    document.set_geometry(0, (7, 8, 300, 120))

    document.save()

    assert path.read_bytes() == original.replace(
        b'WindowID="1" WindowHeight="300" WindowWidth="120">',
        b'WindowID="1" WindowHeight="300" WindowWidth="120" WindowLeft="7" WindowTop="8">',
    )


def test_refuses_to_overwrite_external_change(tmp_path: Path) -> None:
    path = tmp_path / "Teste.xml"
    write_sample(path)
    document = UIDocument.load(path)
    document.set_geometry(1, (11, 20, 80, 16))
    path.write_bytes(path.read_bytes() + b"\r\n")

    with pytest.raises(ExternalModificationError):
        document.save()


def test_unified_diff_previews_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "Teste.xml"
    original = write_sample(path)
    document = UIDocument.load(path)
    document.set_geometry(1, (14, 20, 80, 16))

    preview = document.unified_diff()

    assert '-      <BaseWndProperty WindowID="2000"' in preview
    assert '+      <BaseWndProperty WindowID="2000"' in preview
    assert 'WindowLeft="14"' in preview
    assert path.read_bytes() == original


def test_edits_only_changed_nor_uv_attribute_and_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "Teste.xml"
    original = write_sample(path)
    document = UIDocument.load(path)
    document.set_uv(1, UVRect(448, 2, 80, 16))

    rendered = document.render_text()

    assert 'NorUVLeft="448"' in rendered
    assert 'NorUVTop="2" NorUVWidth="80" NorUVHeight="16"' in rendered
    backup = document.save()
    assert backup.read_bytes() == original
    assert path.read_bytes() == original.replace(
        b'NorUVLeft="1"', b'NorUVLeft="448"'
    )


def test_parses_progress_texture_offset(tmp_path: Path) -> None:
    path = tmp_path / "Progress.xml"
    path.write_bytes(
        b'''<?xml version="1.0" ?>
<Root_Node><Style CtrlType="67108864" /><BaseWndProperty WindowID="3000" WindowHeight="4" WindowWidth="4">
<BackGroundMap BGmap="atlas.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>
<ProgressNode><OffSetUV UVCnt="1"><SOffset-0 x="2" y="6" /></OffSetUV></ProgressNode>
</BaseWndProperty></Root_Node>'''
    )

    element = UIDocument.load(path).elements[0]

    assert element.kind == "progress"
    assert element.progress_offset == (2, 6)
