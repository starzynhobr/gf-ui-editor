"""Atualização automática pela release mais recente do GitHub.

O instalador (Inno Setup) é baixado, conferido pelo SHA-256 que o GitHub
publica para cada arquivo da release e executado em modo silencioso; ele
fecha o editor se ainda estiver aberto e o reabre ao terminar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

from . import __version__
from .release_notes import ReleaseNotes, parse as parse_release_notes

REPOSITORY = "starzynhobr/gf-ui-editor"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
TIMEOUT_SECONDS = 15
NOTES_ASSET = "release-notes.json"
NOTES_SIZE_LIMIT = 200_000


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    notes: str
    page_url: str
    asset_name: str
    asset_url: str
    sha256: str | None
    notes_url: str | None = None
    structured_notes: ReleaseNotes | None = None


def parse_version(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text)
    return tuple(int(number) for number in numbers[:4]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def is_installed_build() -> bool:
    """Só o executável instalado se atualiza; rodando pelo código, apenas avisa."""
    return bool(getattr(sys, "frozen", False))


def _request(url: str):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"gf-ui-editor/{__version__}", "Accept": "application/vnd.github+json"},
    )
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)  # noqa: S310 - URL fixa em https


def release_from_json(data: dict) -> UpdateInfo | None:
    version = str(data.get("tag_name", "")).lstrip("vV")
    if not version:
        return None
    assets = {asset.get("name", ""): asset for asset in data.get("assets", [])}
    asset = assets.get(f"GF-UI-Editor-Setup-{version}.exe") or assets.get("GF-UI-Editor-Setup.exe")
    if asset is None:
        return None
    digest = str(asset.get("digest") or "")
    return UpdateInfo(
        version=version,
        notes=str(data.get("body") or ""),
        page_url=str(data.get("html_url") or f"https://github.com/{REPOSITORY}/releases/latest"),
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
        notes_url=(assets.get(NOTES_ASSET) or {}).get("browser_download_url"),
    )


def fetch_structured_notes(info: UpdateInfo) -> ReleaseNotes | None:
    """Notas traduzidas anexadas à release; None se não houver ou vierem inválidas."""
    url = info.notes_url
    if not url or not url.startswith(f"https://github.com/{REPOSITORY}/releases/download/"):
        return None
    try:
        with _request(url) as response:
            payload = response.read(NOTES_SIZE_LIMIT + 1)
    except OSError:
        return None
    if len(payload) > NOTES_SIZE_LIMIT:
        return None
    return parse_release_notes(payload)


def check_for_update(current: str = __version__) -> UpdateInfo | None:
    """Release mais nova que `current`, ou None. Levanta UpdateError se falhar."""
    try:
        with _request(LATEST_RELEASE_API) as response:
            data = json.load(response)
    except (OSError, ValueError) as exc:
        raise UpdateError(str(exc)) from exc
    info = release_from_json(data)
    if info is None or not is_newer(info.version, current):
        return None
    return replace(info, structured_notes=fetch_structured_notes(info))


def download_installer(
    info: UpdateInfo,
    destination_dir: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    if not info.asset_url.startswith(f"https://github.com/{REPOSITORY}/releases/download/"):
        raise UpdateError(f"Endereço de download inesperado: {info.asset_url}")
    folder = destination_dir or Path(tempfile.mkdtemp(prefix="gf-ui-editor-update-"))
    target = folder / info.asset_name
    digest = hashlib.sha256()
    try:
        with _request(info.asset_url) as response, open(target, "wb") as output:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(256 * 1024):
                output.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except OSError as exc:
        raise UpdateError(str(exc)) from exc
    if info.sha256 is not None and digest.hexdigest() != info.sha256:
        target.unlink(missing_ok=True)
        raise UpdateError("O arquivo baixado não confere com o SHA-256 publicado na release.")
    return target


def launch_installer(installer: Path) -> None:
    """Instala sem perguntas; o Inno fecha o editor se preciso e o reabre no fim."""
    subprocess.Popen(  # noqa: S603 - instalador baixado e conferido acima
        [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        close_fds=True,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
