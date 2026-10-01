import struct
from pathlib import Path

from PIL import Image

from gf_ui_editor.game_layout import client_resolution
from gf_ui_editor.texture_cache import open_dds_rgba


def _dds_header(width: int, height: int, bits: int, masks: tuple[int, int, int, int]) -> bytes:
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<IIII", header, 4, 124, 0x100F, height, width)
    red, green, blue, alpha = masks
    struct.pack_into("<II4sIIIII", header, 76, 32, 0x41, b"\0\0\0\0", bits, red, green, blue, alpha)
    return bytes(header)


def test_argb4444_matches_pillow(tmp_path: Path) -> None:
    pixels = bytes(range(256)) * 2  # 16x16 pixels de 16 bits com todos os nibbles
    path = tmp_path / "a.dds"
    path.write_bytes(_dds_header(16, 16, 16, (0xF00, 0xF0, 0xF, 0xF000)) + pixels)
    fast = open_dds_rgba(path)
    with Image.open(path) as reference:
        assert fast.tobytes() == reference.convert("RGBA").tobytes()


def test_bgra8888_matches_pillow(tmp_path: Path) -> None:
    pixels = bytes(range(256)) * 4
    path = tmp_path / "b.dds"
    path.write_bytes(_dds_header(16, 16, 32, (0xFF0000, 0xFF00, 0xFF, 0xFF000000)) + pixels)
    fast = open_dds_rgba(path)
    with Image.open(path) as reference:
        assert fast.tobytes() == reference.convert("RGBA").tobytes()


def test_client_resolution(tmp_path: Path) -> None:
    (tmp_path / "client.ini").write_text("[Option]\nFullScreenMode=0\nScreenWidth=1600\nScreenHeight=900\n[Channel]\nScreenWidth=1\n")
    assert client_resolution(tmp_path) == (1600, 900)
    assert client_resolution(tmp_path / "nada") is None
