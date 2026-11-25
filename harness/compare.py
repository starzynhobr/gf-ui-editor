"""Compara duas saídas do run_flows.py (referência x candidata).

Uso: python harness/compare.py <saida_referencia> <saida_candidata>
Sai com código 1 se algo diferir: log de passos/mensagens, arquivos gravados ou capturas.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Linhas de diagnóstico que dependem de APIs que só existem numa das versões.
VOLATILE = {"users_now"}


def _load(folder: Path, name: str):
    text = (folder / name).read_text(encoding="utf-8").replace(str(folder), "<OUT>")
    text = text.replace(json.dumps(str(folder))[1:-1], "<OUT>")
    return json.loads(text)


def _clean(entries: list[dict]) -> list[dict]:
    return [{k: v for k, v in entry.items() if k != "tb" and k not in VOLATILE} for entry in entries]


def main(reference: Path, candidate: Path) -> int:
    problems = 0
    ref_log, cand_log = _clean(_load(reference, "log.json")), _clean(_load(candidate, "log.json"))
    for kind in ("error",):
        for entry in cand_log:
            if entry["kind"] == kind:
                print(f"ERRO no fluxo {entry['step']}: {entry.get('error')}")
                problems += 1
    if ref_log != cand_log:
        problems += 1
        print(f"LOG diferente ({len(ref_log)} x {len(cand_log)} entradas). Primeiras diferenças:")
        shown = 0
        for index in range(max(len(ref_log), len(cand_log))):
            a = ref_log[index] if index < len(ref_log) else None
            b = cand_log[index] if index < len(cand_log) else None
            if a != b:
                print(f"  #{index}\n    referência: {json.dumps(a, ensure_ascii=False)[:400]}\n    candidata:  {json.dumps(b, ensure_ascii=False)[:400]}")
                shown += 1
                if shown >= 8:
                    break
    else:
        print(f"log igual ({len(ref_log)} entradas)")

    ref_out, cand_out = _load(reference, "outputs.json"), _load(candidate, "outputs.json")
    for key in sorted(set(ref_out) | set(cand_out)):
        a, b = ref_out.get(key), cand_out.get(key)
        if a == b:
            print(f"igual: {key}" + (f" ({len(a)} arquivos)" if isinstance(a, dict) else ""))
            continue
        problems += 1
        if isinstance(a, dict) and isinstance(b, dict):
            names = sorted(name for name in set(a) | set(b) if a.get(name) != b.get(name))
            print(f"DIFERENTE: {key}: {len(names)} arquivo(s): {names[:12]}")
        else:
            print(f"DIFERENTE: {key}: {a!r} x {b!r}")

    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])  # noqa: F841 - QImage precisa do app
    for shot in sorted((reference / "shots").glob("*.png")):
        other = candidate / "shots" / shot.name
        if not other.exists():
            print(f"DIFERENTE: captura {shot.name} só na referência")
            problems += 1
            continue
        a, b = QImage(str(shot)), QImage(str(other))
        if a.size() != b.size() or a != b:
            print(f"DIFERENTE: captura {shot.name}")
            problems += 1
    print("capturas conferidas" if problems == 0 else f"{problems} diferença(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
