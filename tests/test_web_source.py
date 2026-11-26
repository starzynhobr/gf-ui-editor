from pathlib import Path

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
