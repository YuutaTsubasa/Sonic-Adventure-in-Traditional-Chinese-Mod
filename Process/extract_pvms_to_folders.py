#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DEFAULT_ARCHIVETOOL = Path(r"C:\Users\User\Repo\SATraditional\SA.Tools.x64\bin\ArchiveTool.exe")


def find_archivetool(explicit: str) -> Path:
    if explicit:
        tool = Path(explicit)
    else:
        tool = DEFAULT_ARCHIVETOOL
    if not tool.exists():
        raise FileNotFoundError(f"ArchiveTool not found: {tool}")
    return tool


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract PVM files into one folder per PVM using SA Tools ArchiveTool -png."
    )
    ap.add_argument("--input-dir", default="Process/PVMs")
    ap.add_argument("--output-dir", default="Process/PVM_EXTRACTED")
    ap.add_argument("--glob", default="*.PVM")
    ap.add_argument("--archivetool", default="")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tool = find_archivetool(args.archivetool)

    pvm_files = unique_paths(sorted(input_dir.glob(args.glob)) + sorted(input_dir.glob(args.glob.lower())))

    extracted = 0
    for pvm_path in pvm_files:
        temp_pvm = output_dir / pvm_path.name
        out_folder = output_dir / pvm_path.stem

        if out_folder.exists():
            shutil.rmtree(out_folder)
        if temp_pvm.exists():
            temp_pvm.unlink()

        shutil.copy2(pvm_path, temp_pvm)
        try:
            subprocess.run(
                [str(tool), "-png", temp_pvm.name],
                cwd=str(output_dir),
                check=True,
            )
            extracted += 1
        finally:
            if temp_pvm.exists():
                temp_pvm.unlink()

    print(f"pvm_files={len(pvm_files)}")
    print(f"folders_extracted={extracted}")
    print(f"output_dir={output_dir}")
    print(f"archivetool={tool}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
