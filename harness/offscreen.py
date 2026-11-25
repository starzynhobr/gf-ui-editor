"""Janelas pywebview dos testes: sem foco e fora da área visível.

O WebView2 não tem modo headless (precisa de uma janela real para desenhar), mas uma
janela fora da tela e sem foco renderiza e captura normalmente sem piscar nem roubar o
foco. `hidden=True` não serve: o WebView2 pode parar de desenhar e as capturas saem
vazias. Para ver a janela (depurar um teste): GF_HARNESS_VISIBLE=1.
"""
from __future__ import annotations

import os


def window_options() -> dict:
    if os.environ.get("GF_HARNESS_VISIBLE") == "1":
        return {}
    return {"x": -12000, "y": -12000, "focus": False}


def capture_window(hwnd: int, path) -> bool:
    """Captura a janela pelo PrintWindow (PW_RENDERFULLCONTENT), mesmo fora da tela."""
    import ctypes
    import ctypes.wintypes

    from PIL import Image

    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    handle = ctypes.c_void_p
    user32.GetDC.restype = gdi32.CreateCompatibleDC.restype = gdi32.CreateCompatibleBitmap.restype = handle
    user32.GetDC.argtypes = [handle]
    gdi32.CreateCompatibleDC.argtypes = [handle]
    gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.argtypes = [handle, handle]
    gdi32.SelectObject.restype = handle
    user32.PrintWindow.argtypes = [handle, handle, ctypes.c_uint]
    user32.GetClientRect.argtypes = [handle, ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [handle, handle, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    gdi32.DeleteObject.argtypes = gdi32.DeleteDC.argtypes = [handle]
    user32.ReleaseDC.argtypes = [handle, handle]
    rect = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return False
    window_dc = user32.GetDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    ok = user32.PrintWindow(hwnd, memory_dc, 1 | 2)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(hwnd, window_dc)
    if not ok:
        return False
    Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1).save(path)
    return True
