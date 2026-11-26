"""Debounce changes to the physical file behind a logical XML path."""

from pathlib import Path
from time import monotonic


def _stamp(path: Path) -> tuple:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return (path,)
    return path, stat.st_ino, stat.st_ctime_ns, stat.st_mtime_ns, stat.st_size


def read_revision(path: Path) -> bytes | None:
    """Read a single snapshot and reject files replaced or changed during the read."""
    before = _stamp(path)
    raw = path.read_bytes() if len(before) > 1 else None
    if before != _stamp(path) or (raw is not None and len(raw) != before[-1]):
        raise OSError("O XML ainda está sendo gravado.")
    return raw


class XmlWatch:
    quiet_period = 0.45

    def __init__(self) -> None:
        self._candidate: tuple | None = None
        self._settled: tuple | None = None
        self._observed_at = 0.0

    def poll(self, path: Path) -> tuple[bytes | None] | None:
        """Return a settled revision once, including a stable deletion."""
        try:
            stamp = _stamp(path)
            if stamp == self._settled:
                self._candidate = stamp
                return None
            now = monotonic()
            if stamp != self._candidate:
                self._candidate, self._observed_at = stamp, now
                return None
            if now - self._observed_at < self.quiet_period:
                return None
            raw = read_revision(path)
            if _stamp(path) != stamp:
                return None
        except OSError:
            return None
        self._settled = stamp
        return (raw,)
