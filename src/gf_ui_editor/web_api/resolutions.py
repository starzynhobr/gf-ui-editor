"""Ponte: "Exportar para várias resoluções…" (tela em web/src/resolutions).

O trabalho fica em `multi_resolution` (sem Qt). Aqui só se escolhe a resolução base (a do
preview), guarda os ajustes da pessoa, monta as cenas das miniaturas (mesma conta do canvas)
e grava os zips.
"""

from __future__ import annotations

import os
from pathlib import Path

from .. import game_layout, multi_resolution as mr
from ..about import GAME_RESOLUTIONS, parse_resolution
from ..canvas_document import PreviewContext, describe_scene
from ..text_preview import layer_text
from ..xml_document import DocumentError

# Quantas janelas no máximo vão para as miniaturas além das do HUD (o resto só na lista).
SCENE_LIMIT = 40


def _size(value: object) -> mr.Resolution:
    size = mr.parse_resolution_key(value) if isinstance(value, str) else tuple(value) if mr.valid_resolution(value) else None
    if size is None:
        raise ValueError("Resolução inválida. Use largura x altura, por exemplo 1920x1080.")
    return size  # type: ignore[return-value]


class ResolutionsApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    # ---- estado em memória -------------------------------------------------------------
    def _mr_sources(self) -> list[mr.WindowSource]:
        """XMLs do projeto, relidos só quando algum arquivo mudou (o diálogo pede várias vezes)."""
        project = self._require_project()
        files = [relative for relative in project.files(refresh=True) if relative.suffix.lower() == ".xml"]
        stamp = []
        for relative in files:
            try:
                stat = os.stat(project.resolve(relative))
                stamp.append((relative.as_posix(), stat.st_size, stat.st_mtime_ns))
            except OSError:
                stamp.append((relative.as_posix(), -1, -1))
        key = (str(project.root), tuple(sorted(project.root_modes.items())), tuple(stamp))
        cached = getattr(self, "_mr_cache", None)
        if cached is None or cached[0] != key:
            cached = (key, mr.project_sources(project), {})
            self._mr_cache = cached
        return cached[1]

    def _mr_plans(self, base: mr.Resolution) -> list[tuple[mr.WindowSource, mr.WindowPlan]]:
        sources = self._mr_sources()
        plans = self._mr_cache[2]
        if base not in plans:
            plans[base] = [(source, plan) for source in sources if (plan := mr.analyze(source, base)) is not None]
        return plans[base]

    def _mr_store(self) -> mr.ResolutionStore:
        return mr.ResolutionStore(self._require_project().root)

    def _mr_preview_base(self) -> mr.Resolution:
        """A resolução em que a pessoa edita: a do preview do canvas."""
        size = parse_resolution(self._prefs.game_resolution or "")
        if size is None and self._project is not None and self._project.game_dir is not None:
            size = game_layout.client_resolution(self._project.game_dir)
        return size or mr.DEFAULT_BASE

    def _mr_hud(self) -> list[str]:
        project = self._require_project()
        wanted = [name.lower() for name in (*game_layout.DEFAULT_HUD, *project.reference_layers)]
        known = {source.relative.lower(): source.relative for source in self._mr_sources()}
        result = []
        for name in wanted:
            if name in known and known[name] not in result:
                result.append(known[name])
        return result

    # ---- chamadas da tela ----------------------------------------------------------------
    def resolutions_info(self) -> dict:
        project = self._require_project()
        store = self._mr_store()
        settings = store.load()
        base = settings.base or self._mr_preview_base()
        targets = settings.targets or list(mr.COMMON_RESOLUTIONS)
        return {
            "project": project.custom_name,
            "base": list(base),
            "previewBase": list(self._mr_preview_base()),
            "common": [list(size) for size in mr.COMMON_RESOLUTIONS],
            "presets": [list(size) for size in GAME_RESOLUTIONS],
            "targets": [list(size) for size in targets],
            "hud": self._mr_hud(),
        }

    def resolutions_set_choice(self, base: list[int], targets: list) -> None:
        """Guarda a base e as resoluções marcadas (a próxima abertura volta igual)."""
        store = self._mr_store()
        settings = store.load()
        settings.base = _size(base)
        settings.targets = mr.resolution_list(targets)
        store.save(settings)

    def resolutions_plan(self, base: list[int], targets: list) -> dict:
        """Para cada resolução: as janelas que mudam (ou que a pessoa ajustou) e os arquivos do zip."""
        base_size = _size(base)
        sizes = mr.resolution_list(targets)
        store = self._mr_store()
        settings = store.load()
        plans = self._mr_plans(base_size)
        hud = {name.lower() for name in self._mr_hud()}
        result = []
        for target in sizes:
            windows = []
            files = []
            for source, plan in plans:
                outcome = mr.generate(source, plan, target, settings.for_file(source.relative, target))
                if outcome.changed:
                    files.append(source.relative)
                summary = mr.window_summary(outcome)
                summary["hud"] = source.relative.lower() in hud
                summary["moves"] = any(piece.rule != (mr.GAME, mr.GAME) or piece.adjusted for piece in outcome.pieces)
                if summary["moves"] or summary["hud"] or outcome.changed:
                    windows.append(summary)
            variants = sorted(store.variants(target))
            windows.sort(key=lambda item: (not item["moves"], item["file"].lower()))
            result.append({
                "size": list(target),
                "key": mr.resolution_key(target),
                "windows": windows,
                "files": sorted({*files, *variants}, key=str.lower),
                "variants": variants,
            })
        return {"base": list(base_size), "targets": result, "windows": len(plans)}

    def resolutions_scenes(self, base: list[int], target: list[int], files: list[str]) -> list[dict]:
        """Cenas do canvas (como as camadas de referência) com o XML já gerado para `target`."""
        project = self._require_project()
        base_size, target_size = _size(base), _size(target)
        settings = self._mr_store().load()
        wanted = {name.lower() for name in files[: SCENE_LIMIT + len(game_layout.DEFAULT_HUD)]}
        scenes = []
        for source, plan in self._mr_plans(base_size):
            if source.relative.lower() not in wanted:
                continue
            outcome = mr.generate(source, plan, target_size, settings.for_file(source.relative, target_size))
            document = source.document.with_text(outcome.text) if outcome.text is not None else source.document
            path = project.ui_dir / source.relative
            try:
                context = PreviewContext.load(path, target_size, saved_positions=False)
            except (OSError, ValueError, DocumentError):
                continue
            scene = describe_scene(document, context)
            for item, element in zip(scene["elements"], document.elements, strict=True):
                item["layer_text"] = layer_text(element, {})
            asset = self.asset_base(str(path)) if getattr(self, "_canvas_assets", None) is not None else ""
            scenes.append({"name": source.relative, "base": asset, "scene": scene})
        return scenes

    def resolutions_adjust(self, file: str, piece: str, target: list[int], point: list[int] | None) -> None:
        """Arrastar na prévia: grava (ou, com `point` None, desfaz) o ajuste só daquela resolução."""
        target_size = _size(target)
        if point is not None and not (isinstance(point, list) and len(point) == 2 and all(type(v) is int for v in point)):
            raise ValueError("Posição inválida.")
        known = {source.relative.lower(): source.relative for source in self._mr_sources()}
        if file.lower() not in known:
            raise ValueError("Arquivo fora do projeto.")
        self._mr_store().set_adjustment(known[file.lower()], target_size, piece, tuple(point) if point else None)

    def resolutions_reset(self, target: list[int] | None = None) -> None:
        """Desfaz todos os ajustes (de uma resolução, ou de todas)."""
        store = self._mr_store()
        settings = store.load()
        key = mr.resolution_key(_size(target)) if target is not None else None
        for name in list(settings.adjustments):
            if key is None:
                settings.adjustments.pop(name)
            else:
                settings.adjustments[name].pop(key, None)
        store.save(settings)

    def resolutions_add_variant(self, target: list[int]) -> list[str] | None:
        """Escolhe um arquivo (ex.: main.dds desenhado para 1920x1080) que vale só nesta resolução."""
        project = self._require_project()
        target_size = _size(target)
        chosen = self._ask_path("open", project.ui_dir, ("Arquivos da UI (*.dds;*.tga;*.xml;*.ini;*.txt)",))
        if chosen is None:
            return None
        if not chosen.is_file():
            raise ValueError("Arquivo não encontrado.")
        relative = chosen.name
        for item in project.files():
            if item.name.lower() == chosen.name.lower():
                relative = item.as_posix()
                break
        store = self._mr_store()
        store.add_variant(target_size, relative, chosen)
        return sorted(store.variants(target_size))

    def resolutions_remove_variant(self, target: list[int], name: str) -> list[str]:
        store = self._mr_store()
        target_size = _size(target)
        store.remove_variant(target_size, name)
        return sorted(store.variants(target_size))

    def resolutions_pick_folder(self) -> str | None:
        chosen = self._ask_path("folder", Path.home() / "Documents")
        return str(chosen) if chosen is not None else None

    def resolutions_export(self, folder: str, base: list[int], targets: list, whole: bool, all_resolution: bool) -> dict:
        """Grava `<Projeto> LxA.zip` (e o "All Resolution"). Erro de disco sobe."""
        project = self._require_project()
        base_size = _size(base)
        sizes = mr.resolution_list(targets)
        if not sizes:
            raise ValueError("Marque pelo menos uma resolução.")
        store = self._mr_store()
        settings = store.load()
        settings.base, settings.targets = base_size, sizes
        store.save(settings)
        outputs = mr.outputs_from_plans(self._mr_plans(base_size), sizes, settings, store)
        results = mr.export_zips(
            project, Path(folder), outputs, whole=bool(whole), all_resolution=bool(all_resolution),
            progress=self._progress("export"),
        )
        return {
            "folder": folder,
            "zips": [
                {"key": mr.resolution_key(target) if target else "all", "path": str(path), "count": count}
                for target, path, count in results
            ],
        }


__all__ = ["ResolutionsApi"]
