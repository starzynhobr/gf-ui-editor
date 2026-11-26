from pathlib import Path

import pytest

from gf_ui_editor.document_session import DocumentSession
from gf_ui_editor.web_shell import WebApi
from gf_ui_editor.xml_source import element_lines

XML = b'''<Root_Node>
  <BaseWndProperty WindowID="1" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="80">
    <Container_Node Child_Cnt="1">
      <BaseWndProperty WindowID="2" WindowLeft="20" WindowTop="30" WindowHeight="15" WindowWidth="12">
        <BackGroundMap BGmap="A.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="8" NorUVHeight="9"/></BackGroundMap>
      </BaseWndProperty>
    </Container_Node>
  </BaseWndProperty>
</Root_Node>
'''


def test_element_lines_follow_the_start_tags():
    text = "<a>\n<BaseWndProperty WindowID=\"1\">\n\n  <BaseWndProperty WindowID=\"2\"/>\n"
    assert element_lines(text, 2) == [2, 4]
    assert element_lines(text, 3) == []


def test_doc_source_shows_unsaved_edits_without_touching_the_file(tmp_path: Path):
    api = WebApi("pt_BR", False)
    assert api.doc_source() is None
    path = tmp_path / "Inventory.xml"
    path.write_bytes(XML)
    scene = api.doc_open(str(path))
    api.doc_edit([{
        "index": 1, "field": "geometry",
        "before": list(scene["elements"][1]["geometry"]), "after": [43, 30, 12, 15],
    }])
    source = api.doc_source()
    assert source["dirty"] is True
    assert 'WindowLeft="43"' in source["text"]
    assert source["lines"] == [2, 4]
    assert path.read_bytes() == XML


def test_apply_source_is_reversible_and_saves_exact_big5(tmp_path: Path):
    path = tmp_path / "Inventory.xml"
    original = XML.replace(b"\n", b"\r\n")
    path.write_bytes(original)
    session = DocumentSession()
    scene = session.open(path)
    before = scene["elements"][1]["geometry"]
    edit = {"index": 1, "field": "geometry", "before": before, "after": (43, *before[1:])}
    session.edit([edit])
    expected = session.source()["text"]
    applied = expected.replace('WindowLeft="43"', 'WindowLeft="52"').replace("</Root_Node>", "<!-- 中文 -->\r\n</Root_Node>")

    result = session.apply_source(str(path), applied, expected)
    assert result["changed"] and result["doc"]["elements"][1]["geometry"][0] == 52
    assert session.source()["text"] == applied
    assert "-      <BaseWndProperty WindowID=\"2\" WindowLeft=\"20\"" in session.diff()
    assert path.read_bytes() == original and session.watch(path) is None
    assert session.move_source_history(False)["elements"][1]["geometry"][0] == 43
    assert session.source()["text"] == expected
    assert not session.edit([{**edit, "before": edit["after"], "after": before}])["dirty"]
    session.edit([edit])
    assert session.move_source_history(True)["elements"][1]["geometry"][0] == 52
    session.save(None)
    assert path.read_bytes() == applied.encode("big5")
    assert not session.source()["dirty"]


@pytest.mark.parametrize(
    ("text", "line", "column", "message"),
    [
        ("<Root_Node>\n  </Other>", 2, 5, "XML inválido"),
        ("<Root_Node>\r\n  <!-- 😀 -->\r\n</Root_Node>", 2, 8, "Big5"),
        ("<Root_Node>\n  <!-- <BaseWndProperty WindowID=\"3\" /> -->\n</Root_Node>", 2, 8, "elementos"),
    ],
)
def test_apply_source_rejects_invalid_text_with_location(tmp_path, text, line, column, message):
    path = tmp_path / "Inventory.xml"
    path.write_bytes(XML)
    session = DocumentSession()
    session.open(path)
    expected = session.source()["text"]
    result = session.apply_source(str(path), text, expected)
    assert result["issue"]["line"] == line
    assert result["issue"]["column"] == column
    assert message in result["issue"]["message"]
    assert session.source()["text"] == expected
    assert path.read_bytes() == XML
    with pytest.raises(ValueError):
        session.move_source_history(False)
