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


def test_windows_centered_by_the_client(tmp_path) -> None:
    from gf_ui_editor.game_layout import is_centered

    # Cliente base: vale em qualquer servidor.
    assert is_centered("Storage.xml")
    assert root_screen_position("Storage.xml", (1920, 1080), (10, 20, 300, 200)) == (810, 440)
    assert not is_centered("BasicChar.xml")  # HUD não é centralizado
    # A posição salva pelo jogador continua valendo quando cabe na tela.
    assert root_screen_position("Equipment.xml", (1920, 1080), (0, 0, 302, 308), (649, 296, 302, 308)) == (649, 296)


def test_server_dll_windows_only_apply_when_the_dll_exists(tmp_path) -> None:
    from gf_ui_editor.game_layout import is_centered

    rect = (275, 401, 434, 306)
    other_server = tmp_path / "other"
    other_server.mkdir()
    assert not is_centered("SelfEquipment.xml")
    assert not is_centered("SelfEquipment.xml", other_server)
    assert root_screen_position("SelfEquipment.xml", (1920, 1080), rect, game_dir=other_server) == (275, 401)

    violet = tmp_path / "violet"
    violet.mkdir()
    (violet / "Violet.dll").write_bytes(b"")
    assert is_centered("SelfEquipment.xml", violet)
    # Medido num print 1920x1080 do Violet: a janela 434x306 aparece em ~(745, 388).
    assert root_screen_position("SelfEquipment.xml", (1920, 1080), rect, game_dir=violet) == (743, 387)


def test_manual_root_mode_overrides_automatic_rules() -> None:
    rect = (275, 401, 434, 306)
    # Forçar o X/Y do XML numa janela que o automático centralizaria (e numa ancorada).
    assert root_screen_position("Storage.xml", (1920, 1080), rect, mode="xml") == (275, 401)
    assert root_screen_position("Radar.xml", (1920, 1080), rect, mode="xml") == (275, 401)
    # Forçar o centro numa janela que o automático deixaria no X/Y do XML.
    assert root_screen_position("QualquerCoisa.xml", (1920, 1080), rect, mode="center") == (743, 387)
