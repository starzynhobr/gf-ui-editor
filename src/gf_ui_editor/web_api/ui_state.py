"""Ponte: estado visual da interface nova (larguras dos painéis, tema).

Fica nas preferências compartilhadas (preferences.py: `web_layout`, `web_theme`) e não no
localStorage: o pywebview roda em modo privado e o armazenamento do navegador some ao fechar.
"""

from __future__ import annotations

THEMES = ("dark", "midnight", "light")


class UiStateApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def ui_state(self) -> dict:
        prefs = getattr(self, "_prefs", None)
        if prefs is None:
            return {"layout": {}, "theme": "dark"}
        layout = prefs.get("web_layout")
        theme = prefs.get("web_theme")
        return {"layout": layout if isinstance(layout, dict) else {}, "theme": theme if theme in THEMES else "dark"}

    def ui_set_layout(self, layout: dict) -> None:
        prefs = getattr(self, "_prefs", None)
        if prefs is not None and isinstance(layout, dict):
            clean = {str(key): value for key, value in layout.items() if isinstance(value, (int, float, str, bool))}
            prefs.set("web_layout", clean)

    def ui_set_theme(self, theme: str) -> None:
        prefs = getattr(self, "_prefs", None)
        if prefs is not None and theme in THEMES:
            prefs.set("web_theme", theme)


class AboutApi:
    """Popup da pílula STZ Labs: links e quem ajudou a construir (assets/contributors.json)."""

    def about_info(self) -> dict:
        from .. import __version__, about, updater

        language = getattr(self, "_language", "pt_BR")
        people = []
        for person in about.load_contributors():
            entries = about.contributor_items(person, language)
            versions = [version for _text, version in entries if version]
            people.append({
                "name": str(person.get("name", "")),
                "color": str(person.get("color", "#3F3F46")),
                "tags": [str(tag) for tag in person.get("tags", []) if isinstance(tag, str)],
                "items": [{"text": text, "version": version} for text, version in entries],
                "since": min(versions, key=updater.parse_version) if versions else None,
            })
        return {
            "version": __version__,
            "author": "StarzynhoBR",
            "site": "https://stzlabs.com/pt" if language == "pt_BR" else "https://stzlabs.com",
            "github": "https://github.com/starzynhobr?tab=repositories",
            "discord": "https://discord.com/invite/cTsJhtMzSe",
            "contributors": people,
        }


class TextureFileApi:
    """Abrir o .dds no programa padrão do sistema (Paint.NET etc.), como o "Abrir .dds" da clássica."""

    def open_texture_file(self, xml_path: str, texture: str) -> str:
        """Devolve "ok", "missing" (arquivo não existe) ou "failed" (sem programa associado)."""
        from pathlib import Path

        from .. import desktop, textures

        xml = Path(xml_path)
        project = getattr(self, "_project", None)
        if project is not None and not project.contains(xml):
            project = None
        name = Path(texture)
        if name.name != texture or name.suffix.lower() not in (".dds", ".tga"):
            return "missing"
        path = textures.find_texture(xml.parent, texture, project)
        if path is None:
            return "missing"
        try:
            if project is not None:
                project.materialize(path)
            desktop.open_path(path.resolve())
        except OSError:
            return "failed"
        return "ok"
