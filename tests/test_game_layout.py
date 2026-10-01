from gf_ui_editor.game_layout import root_screen_position


SCREEN = (1280, 720)


def test_default_windows_stay_at_xml_position_inside_screen() -> None:
    assert root_screen_position("BasicChar.xml", SCREEN, (0, 0, 250, 95)) == (0, 0)
    assert root_screen_position("Quest.xml", SCREEN, (-10, 900, 300, 200)) == (0, 520)
    assert root_screen_position("Quest.xml", SCREEN, (1200, 10, 300, 200)) == (980, 10)


def test_anchored_windows_match_game_screenshot_at_1280x720() -> None:
    # Medidas conferidas numa captura do cliente em 1280×720.
    assert root_screen_position("Radar.xml", SCREEN, (0, 0, 185, 158)) == (1095, 0)
    assert root_screen_position("TinyClock.xml", SCREEN, (0, 0, 71, 41)) == (1179, 180)
    assert root_screen_position("Menu.xml", SCREEN, (0, 0, 740, 118)) == (270, 602)


def test_rules_are_case_insensitive_and_follow_c_integer_division() -> None:
    assert root_screen_position("TARGET.XML", (1025, 768), (9, -6, 195, 69)) == (512 - 97, 0)


def test_user_ini_position_decoding_and_priority(tmp_path) -> None:
    from gf_ui_editor.game_layout import decode_position, load_user_positions

    assert decode_position("KHEAAAAACBAAAAAAHEAAAAAAJCAAAAAA") == (1146, 18, 71, 41)
    assert decode_position("bad") is None
    ini = tmp_path / "User.ini"
    ini.write_text(
        "[TINYCLOCK]\nPosition=KHEAAAAACBAAAAAAHEAAAAAAJCAAAAAA\n[X]\nData=AD\n", encoding="latin-1"
    )
    saved = load_user_positions(ini)["TINYCLOCK"]
    # Visto no jogo: a regra da janela ancorada vence a posição salva.
    assert root_screen_position("TinyClock.xml", SCREEN, (0, 0, 71, 41), saved) == (1179, 180)
    assert root_screen_position("Inventory.xml", SCREEN, (0, 0, 422, 436), (600, 200, 422, 436)) == (600, 200)
    # Fora da tela: o cliente descarta a posição salva.
    assert root_screen_position("Inventory.xml", SCREEN, (5, 6, 422, 436), (1178, 366, 422, 436)) == (5, 6)
