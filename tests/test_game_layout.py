from gf_ui_editor.game_layout import root_screen_position


SCREEN = (1280, 720)


def test_default_windows_stay_at_xml_position_inside_screen() -> None:
    assert root_screen_position("BasicChar.xml", SCREEN, (0, 0, 250, 95)) == (0, 0)
    assert root_screen_position("Untracked.xml", SCREEN, (-10, 900, 300, 200)) == (0, 520)
    assert root_screen_position("Untracked.xml", SCREEN, (1200, 10, 300, 200)) == (980, 10)


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
    # Fora da tela: o cliente descarta a posição salva e usa a do Create.
    assert root_screen_position("Inventory.xml", SCREEN, (5, 6, 422, 436), (1178, 366, 422, 436)) == (822, 186)


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


def test_windows_placed_by_formula_in_create() -> None:
    from gf_ui_editor.game_layout import placement

    # CInventoryUI::Create (0x006F88B0): canto inferior direito, margens 36 e 98.
    assert root_screen_position("Inventory.xml", (1920, 1080), (0, 0, 182, 426)) == (1702, 556)
    # CShopWnd: borda direita no centro da tela, centrado em Y.
    assert root_screen_position("Shop.xml", (1920, 1080), (0, 0, 346, 356)) == (614, 362)
    # Leilão: centro em 1/3 da largura.
    assert root_screen_position("AuctionBuy.xml", (1280, 720), (0, 0, 301, 200)) == (276, 260)
    # Awake: centro da tela menos 4/5 do tamanho (divisão do C trunca para zero).
    assert root_screen_position("Awake.xml", (1280, 720), (0, 0, 303, 101)) == (398, 280)
    assert root_screen_position("Revive.xml", (1280, 720), (0, 0, 102, 113)) == (589, 143)
    assert root_screen_position("Notify.xml", (1280, 720), (0, 0, 64, 256)) == (608, 16)
    assert root_screen_position("ShortcutBar.xml", (1280, 720), (0, 0, 55, 55)) == (237, 567)
    assert root_screen_position("ElfSchoolWnd.xml", (1280, 720), (0, 0, 150, 272)) == (965, 0)
    assert placement("Inventory.xml") == "placed"
    # A posição salva no User.ini vence (o User.ini é lido depois, no Create).
    assert root_screen_position("Shop.xml", (1920, 1080), (0, 0, 346, 356), (10, 20, 346, 356)) == (10, 20)


def test_windows_repositioned_only_when_off_screen() -> None:
    assert root_screen_position("Diary_Achievement.xml", SCREEN, (30, 40, 300, 200)) == (30, 40)
    assert root_screen_position("Diary_Achievement.xml", SCREEN, (1100, 40, 300, 200)) == (490, 260)
    assert root_screen_position("MailSend.xml", SCREEN, (-5, 40, 300, 200)) == (340, 260)
    from gf_ui_editor.game_layout import placement

    assert placement("MailSend.xml") == "xml"


def test_resize_anchored_windows_win_over_saved_position() -> None:
    assert root_screen_position("QuestAutoNotify.xml", SCREEN, (0, 0, 320, 34), (5, 5, 320, 34)) == (1240, 180)
    assert root_screen_position("TreasureInfo.xml", SCREEN, (0, 0, 150, 150)) == (565, 75)


def test_placement_kinds(tmp_path) -> None:
    from gf_ui_editor.game_layout import placement

    assert placement("Radar.xml") == "anchor"
    assert placement("Quest.xml") == "centered"
    assert placement("MailRead.xml") == "xml"
    assert placement("Bank.xml") == "unused"
    assert placement("CommonDlgA.xml") is None  # posição vem de quem abre o diálogo
    assert root_screen_position("MailRead.xml", SCREEN, (0, 0, 300, 200)) == (0, 0)
    assert placement("Leaderboard.xml") is None
    assert placement("AlchemyCombo.xml") is None
    (tmp_path / "Violet.dll").write_bytes(b"")
    assert placement("Leaderboard.xml", tmp_path) == "centered"
    assert placement("AlchemyCombo.xml", tmp_path) == "xml"
