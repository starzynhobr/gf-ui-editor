"""Posição da janela raiz na tela do jogo, conforme o cliente a calcula.

O cliente ignora `Screen_X`/`Screen_Y` do XML (são gravados e nunca lidos) e não
escala a interface. Por padrão, a raiz fica em `WindowLeft`/`WindowTop`, presa
aos limites da tela. Algumas classes reposicionam a raiz ao mudar a resolução;
as regras abaixo vêm da análise do `GrandFantasia.exe` no Ghidra (endereços da
função de cada classe entre parênteses; largura/altura da tela em
`DAT_00DE3FE4`/`DAT_00DE3FE8`).

Janelas arrastadas pelo jogador têm a posição salva no `User.ini` da pasta do
jogo (gravada em 0x00A12C70, lida em 0x00A12B20), usada quando a janela cabe
inteira na tela. Janelas ancoradas são reposicionadas depois (slot 24, ao ajustar
a resolução), então a regra delas vence: o relógio aparece em (1179, 180) a
1280×720 mesmo com (1146, 18) salvo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import struct


Rect = tuple[int, int, int, int]


def menu_shortcut_preview_y(
    filename: str, window_id: str, root_y: int, *, alternate_layout: bool = False
) -> int | None:
    """Y dos slots superiores de CFunctionWnd, não uma regra geral de controles.

    Em 0x00702500 (cliente Violet), apenas os IDs 2013..2036 são
    reposicionados: 0x0070297B usa raiz + 21; o ramo alternativo
    0x00702961 usa raiz + 23 (flag interna 0x1000). O XML não contém
    essa flag. O preview representa o ramo normal observado neste cliente,
    sem simular a ocupação/ocultação dos slots em tempo de execução.
    """
    if filename.lower() != "menu.xml":
        return None
    try:
        slot_id = int(window_id)
    except ValueError:
        return None
    if not 2013 <= slot_id <= 2036:
        return None
    return root_y + (23 if alternate_layout else 21)


def _half(value: int) -> int:
    # Divisão inteira do C: trunca em direção a zero.
    return int(value / 2)


@dataclass(frozen=True)
class AnchorRule:
    description: str
    position: Callable[[int, int, Rect], tuple[int, int]]


def _clamp(screen_w: int, screen_h: int, rect: Rect) -> tuple[int, int]:
    """CWnd::SetPos (0x00A126F0): mantém a janela inteira dentro da tela."""
    x, y, width, height = rect
    x = max(0, x)
    y = max(0, y)
    if x + width > screen_w:
        x = screen_w - width
    if y + height > screen_h:
        y = screen_h - height
    return x, y


def _center(screen_w: int, screen_h: int, rect: Rect) -> tuple[int, int]:
    return int((screen_w - rect[2]) / 2), int((screen_h - rect[3]) / 2)


def _top_right(margin: int) -> Callable[[int, int, Rect], tuple[int, int]]:
    return lambda screen_w, _screen_h, rect: (screen_w - rect[2] - margin, 0)


RULES: dict[str, AnchorRule] = {
    "radar.xml": AnchorRule("canto superior direito", _top_right(0)),  # 0x00879230
    "tinyclock.xml": AnchorRule(  # 0x007A2CA0
        "direita (margem 30), Y fixo 180",
        lambda screen_w, _h, rect: (screen_w - rect[2] - 30, 180),
    ),
    "gametimer.xml": AnchorRule("topo à direita (margem 150)", _top_right(150)),  # 0x009418D0
    "pkpalace.xml": AnchorRule("topo à direita (margem 130)", _top_right(130)),  # 0x00947B60
    "battlefield.xml": AnchorRule("topo à direita (margem 145)", _top_right(145)),  # 0x009B58F0
    "beaststowerinfo.xml": AnchorRule("topo à direita (margem 160)", _top_right(160)),  # 0x00908FF0
    "menu.xml": AnchorRule(  # 0x00703D80
        "centralizado na base",
        lambda screen_w, screen_h, rect: (
            _half(screen_w) - _half(rect[2]),
            screen_h - rect[3],
        ),
    ),
    "target.xml": AnchorRule(  # 0x00884550
        "centralizado na horizontal",
        lambda screen_w, screen_h, rect: (
            _half(screen_w) - _half(rect[2]),
            _clamp(screen_w, screen_h, rect)[1],
        ),
    ),
    "channel.xml": AnchorRule(  # 0x007197A0
        "à esquerda, 72 px acima da base",
        lambda _w, screen_h, rect: (0, screen_h - rect[3] - 72),
    ),
    "questautonotify.xml": AnchorRule(  # Create 0x008770D0, resize 0x00877080
        "X = largura da tela - 40, Y fixo 180",
        lambda screen_w, _h, _rect: (screen_w - 40, 180),
    ),
    "treasureinfo.xml": AnchorRule(  # Create 0x007942A0, resize 0x00793BF0
        "centralizado na horizontal, centro em Y = 150",
        lambda screen_w, _h, rect: (_div(screen_w - rect[2], 2), 150 - _div(rect[3], 2)),
    ),
}


def _div(value: int, divisor: int) -> int:
    # Divisão inteira do C: trunca em direção a zero.
    return int(value / divisor)


def _from_screen(
    x: Callable[[int, int], int], y: Callable[[int, int], int]
) -> Callable[[int, int, Rect], tuple[int, int]]:
    """Posição escrita no código: `x(W, w)` e `y(H, h)` (tela e raiz)."""
    return lambda screen_w, screen_h, rect: (x(screen_w, rect[2]), y(screen_h, rect[3]))


def _xml_unless_off_screen(
    fallback: Callable[[int, int, Rect], tuple[int, int]],
) -> Callable[[int, int, Rect], tuple[int, int]]:
    """Ao abrir (slot 33), o cliente só reposiciona se a janela sair da tela
    (0x00A127B0); senão fica no X/Y do XML."""

    def position(screen_w: int, screen_h: int, rect: Rect) -> tuple[int, int]:
        x, y, width, height = rect
        if x >= 0 and y >= 0 and x + width <= screen_w and y + height <= screen_h:
            return x, y
        return fallback(screen_w, screen_h, rect)

    return position


def _center_x(screen_w: int, width: int) -> int:
    return _div(screen_w - width, 2)


def _center_y(screen_h: int, height: int) -> int:
    return _div(screen_h - height, 2)


_RIGHT_OF_CENTER = _from_screen(lambda w, width: _div(w, 2) - width, _center_y)
_FOUR_FIFTHS = _from_screen(
    lambda w, width: _div(-width * 4, 5) + _div(w, 2), lambda h, height: _div(-height * 4, 5) + _div(h, 2)
)
_THIRD_OF_SCREEN = _from_screen(lambda w, width: _div(w, 2) - _div(width, 2), lambda h, height: _div(h, 3) - _div(height, 2))
_AUCTION = _from_screen(lambda w, width: _div(w, 3) - _div(width, 2), _center_y)
_INVENTORY = _from_screen(lambda w, width: w - width - 36, lambda h, height: h - height - 98)
# Largura do Radar.xml do cliente (WindowHeight, que é a largura no jogo): a
# escola de elfos abre colada à esquerda do radar.
_RADAR_WIDTH = 165


# Janelas que o cliente põe numa posição calculada no Create (slot 2) ou ao
# abrir (slot 33). Ao contrário de RULES, não há reposicionamento no resize:
# a posição salva no User.ini vence quando cabe na tela, como em CENTERED.
PLACED: dict[str, AnchorRule] = {
    "inventory.xml": AnchorRule("canto inferior direito (margens 36 e 98)", _INVENTORY),  # 0x006F88B0
    "elfattack.xml": AnchorRule(  # 0x00744290
        "canto inferior direito (margens 40 e 70)",
        _from_screen(lambda w, width: w - width - 40, lambda h, height: h - height - 70),
    ),
    "progress.xml": AnchorRule(  # 0x00945610
        "centralizado na horizontal, 70 px acima da base",
        _from_screen(_center_x, lambda h, height: h - height - 70),
    ),
    "shortcutbar.xml": AnchorRule(  # 0x007889E0
        "metade da tela - 403, 98 px acima da base",
        lambda screen_w, screen_h, rect: _clamp(
            screen_w, screen_h, (_div(screen_w, 2) - 403, screen_h - rect[3] - 98, rect[2], rect[3])
        ),
    ),
    "shop.xml": AnchorRule("à esquerda do centro, centrado em Y", _RIGHT_OF_CENTER),  # 0x009D8BF0
    "combine.xml": AnchorRule("à esquerda do centro, centrado em Y", _RIGHT_OF_CENTER),  # 0x009B96E0
    "strengthen.xml": AnchorRule("à esquerda do centro, centrado em Y", _RIGHT_OF_CENTER),  # 0x009BBF80
    "carvingwnd.xml": AnchorRule("à esquerda do centro, centrado em Y", _RIGHT_OF_CENTER),  # 0x008A3A40
    "buybacklist.xml": AnchorRule("à esquerda do centro, centrado em Y", _RIGHT_OF_CENTER),  # 0x008CC550
    "itemexchange.xml": AnchorRule("à esquerda do centro, centrado em Y", _RIGHT_OF_CENTER),  # 0x00905530
    "auctionbuy.xml": AnchorRule("centro em X = 1/3 da tela, centrado em Y", _AUCTION),  # 0x00726C20
    "auctionsell.xml": AnchorRule("centro em X = 1/3 da tela, centrado em Y", _AUCTION),  # 0x007280F0
    "awake.xml": AnchorRule("centro da tela - 4/5 do tamanho", _FOUR_FIFTHS),  # 0x008F39A0
    "carvingcombownd.xml": AnchorRule("centro da tela - 4/5 do tamanho", _FOUR_FIFTHS),  # 0x008A1650
    "newstarcombo.xml": AnchorRule("centro da tela - 4/5 do tamanho", _FOUR_FIFTHS),  # 0x008EFF50
    "elfsend.xml": AnchorRule("centrado em X, centro em Y = 1/3 da tela", _THIRD_OF_SCREEN),  # 0x00826BA0
    "elftrainsend.xml": AnchorRule("centrado em X, centro em Y = 1/3 da tela", _THIRD_OF_SCREEN),  # 0x008E1CB0
    "notify.xml": AnchorRule(  # 0x008542D0
        "centrado em X, centro em Y = 1/5 da tela",
        _from_screen(_center_x, lambda h, height: _div(h, 5) - _div(height, 2)),
    ),
    "revive.xml": AnchorRule(  # 0x0084D460
        "centrado em X, Y = 1/4 da tela - 1/3 da altura",
        _from_screen(lambda w, width: _div(w, 2) - _div(width, 2), lambda h, height: _div(h, 4) - _div(height, 3)),
    ),
    "arenascore.xml": AnchorRule(  # 0x00922AD0
        "topo, X = largura da tela - 2 × largura", _from_screen(lambda w, width: w - 2 * width, lambda _h, _height: 0)
    ),
    "arenascore2.xml": AnchorRule(  # 0x00922DA0
        "topo, X = largura da tela - 380", _from_screen(lambda w, _width: w - 380, lambda _h, _height: 0)
    ),
    "race_timer.xml": AnchorRule(  # 0x007D2060
        "topo, X = largura da tela - 380", _from_screen(lambda w, _width: w - 380, lambda _h, _height: 0)
    ),
    "fb_deepfathom.xml": AnchorRule(  # 0x00919A40
        "topo à direita (margem 165)", _from_screen(lambda w, width: w - width - 165, lambda _h, _height: 0)
    ),
    "questtracewnd.xml": AnchorRule(  # 0x007EF4C0
        "X = largura da tela - 240, Y fixo 135", _from_screen(lambda w, _width: w - 240, lambda _h, _height: 135)
    ),
    "elfschoolwnd.xml": AnchorRule(  # 0x0093CB20, encostada no CRadarWnd (DAT_00DE3908)
        "à esquerda do radar",
        _from_screen(lambda w, width: w - _RADAR_WIDTH - width, lambda _h, _height: 0),
    ),
    # Só saem do X/Y do XML quando não cabem na tela (OFF_SCREEN_ONLY).
    "mailsend.xml": AnchorRule("X/Y do XML; fora da tela, à esquerda do centro", _xml_unless_off_screen(_RIGHT_OF_CENTER)),  # 0x00774FB0
    "elfinventory.xml": AnchorRule("X/Y do XML; fora da tela, canto inferior direito", _xml_unless_off_screen(_INVENTORY)),  # 0x0074D320
    **{
        name: AnchorRule("X/Y do XML; fora da tela, centralizada", _xml_unless_off_screen(_center))
        for name in (
            "diary_achievement.xml",  # 0x0081DCC0
            "familyachievement.xml",  # 0x0081B370
            "familytreewnd.xml",  # 0x007C95F0
            "fellowship_familyaffairs.xml",  # 0x0084A5B0
        )
    },
}


# Janelas que o cliente centraliza na tela ao criá-las (0x00A12D50, chamada no
# Create de cada classe do GrandFantasia.exe): o WindowLeft/WindowTop da raiz é
# ignorado. Vale para o cliente base, comum aos servidores.
CENTERED = frozenset(
    """
    arenareward.xml autoelflotterygosetting.xml autoelflotterylog.xml autoelflotterysetting.xml
    battlefield_info.xml battlefield_result.xml battlefield_reward.xml beaststowerregister.xml
    carvingstylewnd.xml chaircombine.xml channelgroup.xml collection.xml
    collectionpointabilitywnd.xml commondlgf.xml commoninvite.xml cook.xml customkey.xml
    dailyawards.xml diary_prestige.xml elfbet.xml elfboxing.xml elfboxingschedule.xml
    elfequip.xml elflotterylist.xml elfracing.xml elfracingbuycoin.xml elfracingreward.xml
    elfreturn_new.xml elfschoolresultwnd.xml elfsearch.xml elfskill.xml elfskillmodify.xml
    elftablet.xml elfui.xml equipment.xml family_farm.xml familybank.xml familybattleresult.xml
    familybattleschedule.xml familybulletin.xml familycrop.xml familyelfalter.xml
    familyrecruit.xml familysetcadre.xml familysetprivilege.xml familywishingwell.xml
    fellowship_family.xml fellowship_friends.xml fellowship_mentorship.xml fellowship_race.xml
    fellowship_search.xml fellowship_searchopt.xml fellowship_searchteam.xml fightkingwnd.xml
    fishcontrol.xml fishing.xml gamehelp.xml insidem_1.xml insidem_2.xml insidem_3.xml
    insidem_4.xml insidem_5.xml isle.xml islealtar.xml isleelfview.xml isleelfwork.xml
    isleinfo.xml islerecord.xml islestatue.xml islestorage.xml islesummon.xml itemmallhot.xml
    itemmallnewdetail.xml itemmallsend.xml kickcoride.xml kusocombine.xml logoutcount.xml
    lootruleplus.xml lotterygo.xml lover.xml lovermessage.xml luckybar.xml luckybarelfnew.xml
    luckystar.xml maillist.xml megaphone.xml mentorship_lvup_reward.xml messageboard.xml
    messageread.xml messagewrite.xml missionbook.xml monsterinfo.xml nodelimitwnd.xml
    npctalk.xml option_case.xml optionalluckybag.xml optionalluckybagconfirm.xml
    partbreakingdrop.xml programinfo.xml race_comment.xml race_filter.xml race_rank.xml
    race_record.xml race_result.xml rainbowroadtypewnd.xml rankinfo.xml removerune.xml
    ridecombine.xml ridetrain.xml sceneeventstate.xml serverlistwnd.xml
    special_battlefield_info.xml special_battlefield_setting.xml spellaa.xml spellcard.xml
    spelllist.xml spelloverview.xml spellst.xml spellstorage.xml spellview.xml staravenue.xml
    starrewardlist.xml starshop.xml storage.xml strengthenex.xml systemwnd.xml territory.xml
    tinyclocksetting.xml tradeui.xml transport.xml upanishad.xml vkeyboard.xml vkeyboard_1.xml
    webbrowser.xml zonemapframe.xml zonemapoption.xml
    """.split()
) | frozenset(
    # Mesma conta do 0x00A12D50 escrita no próprio Create, ou o centro aplicado
    # ao abrir a janela (slot 33).
    """
    achievementmonsterinfo.xml detailattr.xml diary_autoacceptmission.xml diary_questlog.xml
    dressroom.xml dressroomfull.xml elfduel.xml elffacechange.xml elfgladiatorwnd.xml
    elfteamfight.xml elfteamfightplus.xml elfuigame.xml facechange.xml familyflag.xml
    optimizerecommendedevents.xml postcard.xml prestigeexchangewnd.xml quest.xml
    recommendedeventsnew.xml recruitplayer.xml
    """.split()
)

# Janelas cujo Create (slot 2), resize (slot 24) e abertura (slot 33) não mexem
# na raiz: o jogo usa o X/Y do XML (ou a posição salva no User.ini). Não cobre
# quem abre a janela de fora e a move depois.
XML_POSITIONED = frozenset(
    """
    addressbook.xml autoaltarwnd.xml autoawake.xml constantmessagewnd.xml contractwnd.xml
    elfcollect.xml elfdecompose.xml elfpicksetting.xml elftrain.xml elfwork.xml equiptrain.xml
    familyeditschedulemsginfo.xml familytreeitemviewwnd.xml fullenchantlist.xml hidui.xml
    lootrule.xml lotterygospecial.xml mailread.xml quickenchantlist.xml raid.xml
    rainbowroadgamewnd.xml rankprizewnd.xml rentstoragebag.xml team.xml templechallengewnd.xml
    tutorial.xml
    """.split()
)

# XML que nem o GrandFantasia.exe nem o Violet.dll carregam: sobras na pasta UI.
UNUSED = frozenset(
    """
    activities.xml bank.xml candidatwindow.xml charpassword.xml crystalcombo.xml elfreturn.xml
    fishcontro01.xml fonts.xml indulge.xml indulgenotify.xml itemmall.xml itemmallnew.xml
    log_dlg.xml luckybarelf.xml new_battlefield_info.xml option.xml pkopponentlistwnd.xml
    pkpalacerankwnd.xml pln.xml pln_1.xml pln_2.xml pln_3.xml pln_4.xml pln_5.xml pln_6.xml
    pln_7.xml pln_8.xml pln_9.xml pln_10.xml pln_11.xml pln_12.xml pln_13.xml pln_w.xml
    recommendedeventsui.xml reportdetail.xml reportwnd.xml runerecombo.xml shop2.xml
    starcombo.xml systemwnd_org.xml targettarget.xml testlist.xml testxy.xml tooltips_detail.xml
    uisetup.xml untitled.xml zonemap.xml zonemap-2.xml
    """.split()
)

# Janelas criadas por DLLs próprias de um servidor. Só valem quando a DLL existe
# na pasta do jogo. De propósito, esta tabela é mínima: para o resto, o usuário
# escolhe a posição da raiz por arquivo (ROOT_MODES), sem depender de análise
# do executável de cada servidor.
SERVER_CENTERED = {
    "Violet.dll": frozenset(['battlefieldlobby.xml', 'elementstrengthen.xml', 'equipmentpreset.xml', 'lookequipment.xml', 'lookstat.xml', 'selfequipment.xml', 'selfstat.xml', 'soullantern.xml',
                             # Centralizadas ao abrir (slot 33 chama 0x00A12D50).
                             'challengewnd.xml', 'contributionrank.xml', 'fortuneteller.xml', 'gameitemwiki.xml', 'leaderboard.xml']),
}
SERVER_XML_POSITIONED = {
    "Violet.dll": frozenset(["alchemycombo.xml"]),
}

# Como posicionar a raiz no preview: automático (regras acima), X/Y do XML ou centro.
ROOT_MODES = ("auto", "xml", "center")


def looks_like_game_dir(path: Path | None) -> bool:
    """Pasta do cliente: tem o client.ini ou o Launcher.ini."""
    return path is not None and ((path / "client.ini").is_file() or (path / "Launcher.ini").is_file())


def normalize_game_dir(path: Path) -> Path:
    """Quem escolhe a pasta UI (ou UICustom) no lugar da raiz do jogo recebe a raiz."""
    if not looks_like_game_dir(path) and looks_like_game_dir(path.parent):
        return path.parent
    return path


def is_centered(filename: str, game_dir: Path | None = None) -> bool:
    name = filename.lower()
    if name in CENTERED:
        return True
    if game_dir is None:
        return False
    return any(name in names and (game_dir / dll).is_file() for dll, names in SERVER_CENTERED.items())


# Seção do User.ini usada por cada XML (chamadas a 0x00A12B20 por classe).
# Ficaram de fora janelas com várias instâncias por XML (SHORTCUTnn, ENCHANTLISTn).
INI_SECTIONS = {
    "inventory.xml": "INVENTORY",
    "spellview.xml": "SPELLVIEW",
    "auctionbuy.xml": "AUCTION",
    "storage.xml": "STORAGE",
    "maillist.xml": "MAIL",
    "tinyclock.xml": "TINYCLOCK",
    "diary_autoacceptmission.xml": "AAMISSION",
    "race_timer.xml": "RACETIMER",
    "questtracewnd.xml": "QUESTTRACE",
    "spellaa.xml": "SPELLAA",
    "gamehelp.xml": "GAMEHELPLOG",
    "npctalk.xml": "NPCTALK",
    "diary_questlog.xml": "QUESTLOG",
    "fellowship_friends.xml": "FELLOWSHIP",
    "rankinfo.xml": "RANKINFOLOG",
    "carvingwnd.xml": "STRENGTHEN",
    "strengthen.xml": "STRENGTHEN",
    "equipment.xml": "EQUIPMENT",
    "spellst.xml": "SPELLST",
    "awake.xml": "AWAKE",
    "itemexchange.xml": "ITEM_EXCHANGE",
    "kusocombine.xml": "KUSOCOMBINE",
    "combine.xml": "COMBINE",
    "shop.xml": "SHOP",
}


def decode_position(text: str) -> Rect | None:
    """`Position=` guarda 4 int32 (x, y, largura, altura); cada byte vira duas
    letras 'A'..'P', nibble baixo primeiro."""
    text = text.strip()
    if len(text) != 32 or any(not "A" <= char <= "P" for char in text):
        return None
    data = bytes(
        (ord(text[i]) - 65) | ((ord(text[i + 1]) - 65) << 4) for i in range(0, 32, 2)
    )
    return struct.unpack("<4i", data)


def load_user_positions(path: Path) -> dict[str, Rect]:
    positions: dict[str, Rect] = {}
    section = None
    try:
        lines = path.read_text(encoding="latin-1").splitlines()
    except OSError:
        return positions
    for line in lines:
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].upper()
        elif section and line.lower().startswith("position="):
            rect = decode_position(line.split("=", 1)[1])
            if rect is not None:
                positions[section] = rect
    return positions


def saved_section_for(filename: str) -> str | None:
    return INI_SECTIONS.get(filename.lower())


def rule_for(filename: str) -> AnchorRule | None:
    return RULES.get(filename.lower())


# Em PLACED, as que ficam no X/Y do XML enquanto couberem na tela.
OFF_SCREEN_ONLY = frozenset(
    """
    diary_achievement.xml elfinventory.xml familyachievement.xml familytreewnd.xml
    fellowship_familyaffairs.xml mailsend.xml
    """.split()
)


def placed_rule_for(filename: str) -> AnchorRule | None:
    return PLACED.get(filename.lower())


def uses_xml_position(filename: str, game_dir: Path | None = None) -> bool:
    """O cliente deixa a raiz no X/Y do XML (confirmado no executável)."""
    name = filename.lower()
    if name in XML_POSITIONED or name in OFF_SCREEN_ONLY:
        return True
    if game_dir is None:
        return False
    return any(name in names and (game_dir / dll).is_file() for dll, names in SERVER_XML_POSITIONED.items())


def is_unused(filename: str) -> bool:
    return filename.lower() in UNUSED


def placement(filename: str, game_dir: Path | None = None) -> str | None:
    """Como o cliente decide onde fica a raiz: "anchor", "placed", "centered",
    "xml", "unused" ou None (ainda não mapeado)."""
    if rule_for(filename) is not None:
        return "anchor"
    if filename.lower() in OFF_SCREEN_ONLY:
        return "xml"
    if placed_rule_for(filename) is not None:
        return "placed"
    if is_centered(filename, game_dir):
        return "centered"
    if uses_xml_position(filename, game_dir):
        return "xml"
    if is_unused(filename):
        return "unused"
    return None


def saved_position_applies(screen: tuple[int, int], rect: Rect, saved: Rect | None) -> bool:
    """O cliente só usa a posição salva se a janela couber inteira na tela."""
    if saved is None:
        return False
    x, y = saved[0], saved[1]
    return x >= 0 and y >= 0 and x + rect[2] <= screen[0] and y + rect[3] <= screen[1]


def root_screen_position(
    filename: str,
    screen: tuple[int, int],
    rect: Rect,
    saved: Rect | None = None,
    *,
    mode: str = "auto",
    game_dir: Path | None = None,
) -> tuple[int, int]:
    """Onde a raiz (`rect` = x, y, largura, altura do XML) aparece na tela.

    `mode` "xml" ou "center" é a escolha manual do usuário para o arquivo e
    vence as regras automáticas.
    """
    if mode == "xml":
        return _clamp(screen[0], screen[1], rect)
    if mode == "center":
        return _center(screen[0], screen[1], rect)
    rule = rule_for(filename)
    if rule is None and saved is not None and saved_position_applies(screen, rect, saved):
        return saved[0], saved[1]
    screen_w, screen_h = screen
    if rule is None:
        placed = placed_rule_for(filename)
        if placed is not None:
            return placed.position(screen_w, screen_h, rect)
        if is_centered(filename, game_dir):
            return _center(screen_w, screen_h, rect)
        return _clamp(screen_w, screen_h, rect)
    return rule.position(screen_w, screen_h, rect)


def client_resolution(game_dir: Path) -> tuple[int, int] | None:
    """Resolução configurada no jogo (`client.ini`, seção [Option])."""
    try:
        lines = (game_dir / "client.ini").read_text(encoding="latin-1").splitlines()
    except OSError:
        return None
    values: dict[str, str] = {}
    in_option = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_option = stripped.lower() == "[option]"
        elif in_option and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip().lower()] = value.strip()
    try:
        width, height = int(values["screenwidth"]), int(values["screenheight"])
    except (KeyError, ValueError):
        return None
    return (width, height) if width > 0 and height > 0 else None
