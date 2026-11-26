"""Run the same classic flows on full and converted copies of a real game fixture."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("pristine", type=Path)
    args = parser.parse_args()
    work, pristine = args.work.resolve(), args.pristine.resolve()
    if not (pristine / "UI").is_dir() or work == pristine or work in pristine.parents or pristine in work.parents:
        parser.error("Use uma cópia do jogo e uma pasta de saída separada.")
    source = Path(__file__).resolve().with_name("run_flows.py")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(source.parent.parent / "src")}
    work.mkdir(parents=True, exist_ok=True)
    for mode, flags in (("full", []), ("light", ["--light"])):
        folder = work / mode
        with (work / f"{mode}.log").open("wb") as log:
            subprocess.run(
                [sys.executable, str(source), str(folder), str(pristine), *flags],
                env=env, check=True, stdout=log, stderr=subprocess.STDOUT,
            )
        entries = json.loads((folder / "log.json").read_text(encoding="utf-8"))
        failures = [item for item in entries if item["kind"] in {"error", "unexpected_input", "unexpected_menu"}]
        if failures:
            raise SystemExit(f"{mode}: {failures}")
    full, light = (
        json.loads((work / mode / "outputs.json").read_text(encoding="utf-8"))
        for mode in ("full", "light")
    )
    for key in ("game_ui", "uicustom", "translate", "launcher_ini", "project_ui", "text_edits"):
        if full[key] != light[key]:
            if isinstance(full[key], dict):
                names = sorted(name for name in full[key].keys() | light[key].keys() if full[key].get(name) != light[key].get(name))
                raise SystemExit(f"Divergência em {key}: {names[:20]}")
            raise SystemExit(f"Divergência em {key}")
        print(f"{key}: igual ({len(full[key])} entradas)" if isinstance(full[key], dict) else f"{key}: igual")
    sizes = json.loads((work / "light" / "size.json").read_text(encoding="utf-8"))
    print(json.dumps(sizes))
    if sizes["project_after"] >= sizes["project_before"] or sizes["ui_after"] >= sizes["ui_before"]:
        raise SystemExit("A conversão não reduziu o tamanho do projeto.")


if __name__ == "__main__":
    main()
