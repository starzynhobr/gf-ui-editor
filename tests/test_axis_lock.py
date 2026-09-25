from gf_ui_editor.editor_widgets import constrain_to_axis


def test_selects_dominant_horizontal_axis() -> None:
    assert constrain_to_axis(18, 5) == (18, 0.0, "horizontal")


def test_selects_dominant_vertical_axis() -> None:
    assert constrain_to_axis(3, -12) == (0.0, -12, "vertical")


def test_keeps_axis_selected_at_start_of_drag() -> None:
    assert constrain_to_axis(4, 30, "horizontal") == (4, 0.0, "horizontal")
    assert constrain_to_axis(40, 6, "vertical") == (0.0, 6, "vertical")

