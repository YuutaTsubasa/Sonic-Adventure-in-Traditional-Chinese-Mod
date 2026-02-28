#!/usr/bin/env python3
"""
INI translation pipeline tool.

Commands:
  extract : extract translatable rows from Japanese.ini into CSV
  apply   : apply translated_content_zhtw from CSV back to Japanese.ini by line number
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


JP_NAME = "Japanese.ini"
EN_NAME = "English.ini"


@dataclass
class Row:
    file_path: str
    line_number: int
    entry_key: str
    content_jp: str
    content_en: str
    translated_content_zhtw: str


def _has_japanese(text: str) -> bool:
    # Hiragana, Katakana, CJK Unified Ideographs
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))


def _is_numeric_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    return bool(re.fullmatch(r"[0-9,\-+. ]+", t))


def _clean_for_judge(value: str) -> str:
    # Keep printable chars for heuristics (do not mutate original value)
    return "".join(ch for ch in value if ord(ch) >= 0x20)


def _is_translatable_entry(key: str, value: str) -> bool:
    v = _clean_for_judge(value)
    if v == "":
        return False
    if _has_japanese(v):
        return True
    if key in ("Line", "Text"):
        return True
    if re.fullmatch(r"\d+", key) and not _is_numeric_like(v):
        return True
    return False


def _extract_value_from_line(line: str) -> Optional[tuple[str, str, str]]:
    # Returns (prefix_with_equal, key, value) or None
    if "=" not in line:
        return None
    idx = line.find("=")
    key = line[:idx].strip()
    prefix = line[: idx + 1]
    value = line[idx + 1 :]
    return prefix, key, value


def _read_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return f.readlines()


def cmd_extract(args: argparse.Namespace) -> int:
    root = Path(args.root)
    out_csv = Path(args.out_csv)

    rows: List[Row] = []
    for jp_path in sorted(root.rglob(JP_NAME)):
        en_path = jp_path.with_name(EN_NAME)
        jp_lines = _read_lines(jp_path)
        en_lines = _read_lines(en_path) if en_path.exists() else []

        for i, raw in enumerate(jp_lines, start=1):
            # Keep line terminator out of CSV value; it will be preserved on apply.
            line = raw.rstrip("\r\n")
            parsed = _extract_value_from_line(line)
            if not parsed:
                continue
            _, key, value = parsed
            if not _is_translatable_entry(key, value):
                continue

            en_value = ""
            if i <= len(en_lines):
                en_line = en_lines[i - 1].rstrip("\r\n")
                en_parsed = _extract_value_from_line(en_line)
                if en_parsed:
                    _, en_key, en_val = en_parsed
                    if en_key == key:
                        en_value = en_val

            rows.append(
                Row(
                    file_path=str(jp_path).replace("\\", "/"),
                    line_number=i,
                    entry_key=key,
                    content_jp=value,
                    content_en=en_value,
                    translated_content_zhtw="",
                )
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file_path",
                "line_number",
                "entry_key",
                "content_jp",
                "content_en",
                "translated_content_zhtw",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "file_path": r.file_path,
                    "line_number": r.line_number,
                    "entry_key": r.entry_key,
                    "content_jp": r.content_jp,
                    "content_en": r.content_en,
                    "translated_content_zhtw": r.translated_content_zhtw,
                }
            )

    print(f"Extracted rows: {len(rows)}")
    print(f"Output CSV: {out_csv}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    backup_root = Path(args.backup_dir)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    updates: Dict[str, List[dict]] = {}
    for row in rows:
        tr = row.get("translated_content_zhtw", "")
        if not tr.strip():
            continue
        updates.setdefault(row["file_path"], []).append(row)

    changed_files = 0
    changed_rows = 0

    for file_path, items in updates.items():
        path = Path(file_path)
        if not path.exists():
            print(f"Skip missing file: {file_path}")
            continue

        lines = _read_lines(path)
        dirty = False

        for item in items:
            ln = int(item["line_number"])
            key = item["entry_key"]
            tr = item["translated_content_zhtw"]
            if ln < 1 or ln > len(lines):
                continue

            raw = lines[ln - 1]
            nl = ""
            if raw.endswith("\r\n"):
                nl = "\r\n"
                core = raw[:-2]
            elif raw.endswith("\n"):
                nl = "\n"
                core = raw[:-1]
            elif raw.endswith("\r"):
                nl = "\r"
                core = raw[:-1]
            else:
                core = raw

            parsed = _extract_value_from_line(core)
            if not parsed:
                continue
            prefix, k, _ = parsed
            if k != key:
                continue

            new_line = f"{prefix}{tr}{nl}"
            if new_line != raw:
                lines[ln - 1] = new_line
                dirty = True
                changed_rows += 1

        if dirty:
            backup_path = backup_root / path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            if not backup_path.exists():
                shutil.copy2(path, backup_path)

            with path.open("w", encoding="utf-8", newline="") as f:
                f.writelines(lines)
            changed_files += 1

    print(f"Changed files: {changed_files}")
    print(f"Changed rows: {changed_rows}")
    print(f"Backup root: {backup_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract/apply translation rows for Japanese.ini.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="Extract translatable rows to CSV")
    p_extract.add_argument("--root", default="SATranslation", help="Root folder to scan")
    p_extract.add_argument(
        "--out-csv",
        default="Process/japanese_ini_translation_rows.csv",
        help="Output CSV path",
    )
    p_extract.set_defaults(func=cmd_extract)

    p_apply = sub.add_parser("apply", help="Apply translated CSV rows back to ini files")
    p_apply.add_argument(
        "--csv",
        default="Process/japanese_ini_translation_rows.csv",
        help="CSV path",
    )
    p_apply.add_argument(
        "--backup-dir",
        default="Process/backups/ini_apply",
        help="Backup root",
    )
    p_apply.set_defaults(func=cmd_apply)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

