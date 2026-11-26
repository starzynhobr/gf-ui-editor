"""Uma janela só da interface nova: o segundo .exe entrega o arquivo à primeira e fecha.

Sem Qt: um named pipe do Windows (``multiprocessing.connection``, da stdlib), com nome por
usuário. O primeiro processo cria o pipe com ``FILE_FLAG_FIRST_PIPE_INSTANCE``; se outro já
o criou, a criação falha e este processo vira cliente: manda ``{"open": caminho}`` e sai.
Fora do Windows, um socket Unix na pasta temporária faz o mesmo papel.

Só JSON passa pelo pipe (``send_bytes``/``recv_bytes``; nunca pickle) e a conexão é
autenticada com uma chave por usuário, então outro programa não manda comandos por ele.
"""

from __future__ import annotations

from collections.abc import Callable
import getpass
import hashlib
import json
import os
from multiprocessing.connection import Client, Listener
from pathlib import Path
import sys
import tempfile
import threading

APP_ID = "stz-gf-ui-editor-web"
MESSAGE_LIMIT = 64 * 1024


def _user_tag() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - sem nome de usuário, um nome fixo ainda separa os apps
        user = "user"
    return hashlib.sha256(f"{APP_ID}:{user}".encode()).hexdigest()[:16]


def default_address() -> str:
    tag = _user_tag()
    if sys.platform == "win32":
        return rf"\\.\pipe\{APP_ID}-{tag}"
    return str(Path(tempfile.gettempdir()) / f"{APP_ID}-{tag}.sock")


def _family(address: str) -> str:
    return "AF_PIPE" if sys.platform == "win32" else "AF_UNIX"


def _authkey(address: str) -> bytes:
    return hashlib.sha256(f"{APP_ID}|{address}".encode()).digest()


class Instance:
    """O processo dono da janela: recebe os pedidos dos que abrirem depois."""

    def __init__(self, listener: Listener, address: str) -> None:
        self._listener = listener
        self.address = address
        self._handler: Callable[[dict], None] | None = None
        self._queued: list[dict] = []
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._serve, name="gf-ui-single-instance", daemon=True)
        self._thread.start()

    def on_message(self, handler: Callable[[dict], None]) -> None:
        """Liga quem trata os pedidos; os que chegaram antes são entregues agora."""
        with self._lock:
            self._handler = handler
            queued, self._queued = self._queued, []
        for message in queued:
            handler(message)

    def _deliver(self, message: dict) -> None:
        with self._lock:
            handler = self._handler
            if handler is None:
                self._queued.append(message)
                return
        handler(message)

    def _serve(self) -> None:
        while not self._closed:
            try:
                connection = self._listener.accept()
            except Exception:  # noqa: BLE001 - autenticação recusada ou pipe fechado
                if self._closed:
                    return
                continue
            if self._closed:
                connection.close()
                return
            try:
                with connection:
                    if not connection.poll(5.0):
                        continue  # conectou e não mandou nada: não prende os próximos
                    payload = connection.recv_bytes(MESSAGE_LIMIT)
                    message = json.loads(payload.decode("utf-8"))
                    if isinstance(message, dict):
                        self._deliver(message)
                    connection.send_bytes(b'{"ok": true}')
            except Exception:  # noqa: BLE001 - mensagem ruim: ignora e segue escutando
                continue

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # O accept() espera numa instância do pipe que o close() do Listener não fecha:
        # uma conexão de mentira o acorda, e a thread sai antes de o pipe ser fechado.
        _send(self.address, {"closing": True}, timeout=0.5)
        self._thread.join(2.0)
        try:
            self._listener.close()
        except OSError:
            pass
        if _family(self.address) == "AF_UNIX":
            Path(self.address).unlink(missing_ok=True)


def _send(address: str, message: dict, timeout: float = 5.0) -> bool:
    if sys.platform == "win32":
        # Deixa a janela que já está aberta vir para a frente (o Windows só deixa quem foi
        # clicado por último trazer janelas à frente).
        try:
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:  # noqa: BLE001
            pass
    try:
        with Client(address, family=_family(address), authkey=_authkey(address)) as connection:
            connection.send_bytes(json.dumps(message).encode("utf-8"))
            if connection.poll(timeout):
                connection.recv_bytes(MESSAGE_LIMIT)
        return True
    except (OSError, EOFError, ValueError):
        return False
    except Exception:  # noqa: BLE001 - AuthenticationError: outro programa com o mesmo nome
        return False


def acquire(address: str | None = None) -> Instance | None:
    """Tenta ser a instância principal. None = já há uma (então use ``send_open``)."""
    address = address or default_address()
    family = _family(address)
    if family == "AF_UNIX" and Path(address).exists():
        # Sobra de uma execução que caiu: se ninguém responde, o arquivo é removido.
        if _send(address, {"ping": True}, timeout=1.0):
            return None
        Path(address).unlink(missing_ok=True)
    try:
        listener = Listener(address, family=family, authkey=_authkey(address))
    except OSError:
        return None  # o pipe já existe: outra janela é a principal
    return Instance(listener, address)


def send_open(path: Path | None, address: str | None = None) -> bool:
    """Manda a janela aberta mostrar ``path`` (ou só vir para a frente). False se ninguém ouviu."""
    message = {"open": str(Path(path).resolve()) if path is not None else None, "pid": os.getpid()}
    return _send(address or default_address(), message)


__all__ = ["Instance", "acquire", "default_address", "send_open"]
