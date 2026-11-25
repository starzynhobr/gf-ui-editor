"""Ações do Windows usadas pela interface web, sem Qt: Lixeira, abrir pasta/link/editor.

A clássica faz o mesmo com o Qt (``QFile.moveToTrash``, ``QDesktopServices``, ``QProcess``).
"""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import subprocess
import sys
import webbrowser

from .about import text_editor_command


def move_to_trash(path: Path) -> bool:
    """Manda arquivo ou pasta para a Lixeira (dá para recuperar). False se não conseguiu."""
    if not path.exists() or sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    fo_delete = 3
    flags = 0x4 | 0x10 | 0x40 | 0x400  # silencioso, sem confirmar, permite desfazer (Lixeira), sem erro na tela
    operation = SHFILEOPSTRUCTW()
    operation.wFunc = fo_delete
    operation.pFrom = str(path.resolve()) + "\0"  # lista terminada em dois nulos
    operation.fFlags = flags
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    return result == 0 and not operation.fAnyOperationsAborted and not path.exists()


def open_path(path: Path) -> None:
    """Abre a pasta (ou arquivo) no Explorer."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_url(url: str) -> None:
    webbrowser.open(url)


def open_in_text_editor(path: Path, launch: Callable[[list[str]], object] | None = None) -> str:
    """Abre o XML no Notepad++ (ou Bloco de Notas) sem esperar; devolve o nome do programa.

    Erro ao iniciar (OSError) sobe para quem chamou.
    """
    program, label = text_editor_command()
    (launch or (lambda args: subprocess.Popen(args, close_fds=True)))([program, str(path)])
    return label
