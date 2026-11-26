"""Ponte: fechar um XML avulso pela lista "Arquivos avulsos" (o × da linha).

A abertura, a comparação e a importação ficam em document.py/projects.py; aqui só sai da lista.
"""

from __future__ import annotations

from pathlib import Path


class StandaloneApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def standalone_close(self, path: str) -> dict:
        """Tira o avulso da lista. Se era o aberto, abre o próximo avulso, senão o último XML do projeto.

        O front confirma alterações não salvas antes de chamar.
        """
        target = Path(path).resolve()
        with self._standalone_lock:
            self._standalone_paths.pop(target, None)
            if self._open_path is not None and Path(self._open_path).resolve() == target:
                remaining = [item for item in self._standalone_paths if self._project_for_path(item) is None]
                following = remaining[-1] if remaining else self._last_file()
                if following is not None:
                    self._open_xml(following)
                else:
                    self._open_path = None
            return self.shell_state()
