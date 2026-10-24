import xml.etree.ElementTree as ET

import pytest

from gf_ui_editor.controls import (
    ControlError,
    delete_control,
    duplicate_control,
    free_window_id,
    new_image_control,
    owner_of,
)
from gf_ui_editor.xml_document import UVRect

XML = (
    '<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="T.xml">\r\n'
    '\t<BaseWndProperty WindowID="1">\r\n\t\t<Container_Node Child_Cnt="2">\r\n'
    '\t\t\t<Style ParentNode="1" CtrlType="268435456" />\r\n'
    '\t\t\t<BaseWndProperty WindowID="2" WindowLeft="10" WindowTop="20" WindowHeight="30" WindowWidth="8">\r\n'
    '\t\t\t\t<BackGroundMap BGmap="main.dds">\r\n\t\t\t\t\t<NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="30" NorUVHeight="8" />\r\n'
    '\t\t\t\t</BackGroundMap>\r\n\t\t\t</BaseWndProperty>\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="3" />\r\n'
    '\t\t</Container_Node>\r\n\t</BaseWndProperty>\r\n</Root_Node>\r\n'
)


def _children(text: str) -> tuple[str, list[str]]:
    container = ET.fromstring(text).find(".//Container_Node")
    return container.get("Child_Cnt"), [node.get("WindowID") for node in container.findall("BaseWndProperty")]


def test_free_id_skips_used_and_reserved_ids() -> None:
    assert free_window_id(XML, "2") == "4"  # 3 já existe
    assert free_window_id(XML, "2", reserved={"4", "5"}) == "6"


def test_duplicate_places_a_shifted_copy_after_the_original() -> None:
    text = duplicate_control(XML, "2", "9")
    assert _children(text) == ("3", ["2", "9", "3"])
    copy = ET.fromstring(text).find(".//BaseWndProperty[@WindowID='9']")
    assert (copy.get("WindowLeft"), copy.get("WindowTop")) == ("18", "28")
    assert copy.find("BackGroundMap").get("BGmap") == "main.dds"
    assert "\n" not in text.replace("\r\n", "")
    assert delete_control(text, "9") == XML  # o resto do arquivo não mudou
    with pytest.raises(ControlError):
        duplicate_control(XML, "2", "3")  # ID em uso
    with pytest.raises(ControlError):
        duplicate_control(XML, "1", "9")  # janela com filhos


def test_new_image_goes_to_the_end_of_the_window() -> None:
    text = new_image_control(XML, "1", "4", "meu.dds", UVRect(5, 6, 40, 12), (3, 4))
    assert _children(text) == ("3", ["2", "3", "4"])
    image = ET.fromstring(text).find(".//BaseWndProperty[@WindowID='4']")
    assert (image.get("WindowHeight"), image.get("WindowWidth"), image.get("WindowLeft")) == ("40", "12", "3")
    assert image.find("BackGroundMap/NorUV").get("NorUVLeft") == "5"
    assert owner_of(text, "4") == "1"


def test_delete_removes_the_pair_and_the_line() -> None:
    text = delete_control(XML, "3")
    assert _children(text) == ("1", ["2"])
    assert text == XML.replace('\r\n\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="3" />', "").replace(
        'Child_Cnt="2"', 'Child_Cnt="1"'
    )
    assert delete_control(duplicate_control(XML, "2", "9"), "9") == XML
