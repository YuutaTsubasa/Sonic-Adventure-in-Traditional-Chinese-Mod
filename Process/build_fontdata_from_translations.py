#!/usr/bin/env python3
"""
Build FONTDATA0.BIN glyphs from translated Chinese text and write encoded proxy
UTF-8 text back into Japanese.txt and Japanese.ini files.

Flow:
1) Collect unique characters from translated_content_zhtw in TXT+INI CSV.
2) Render each char using a TTF font (default: Fonts/NotoSansTC-Bold.ttf).
3) Assign codes from 0x3021 onward (JIS 0x21-0x7E grid) and patch FONTDATA0.BIN.
4) Replace translated chars with proxy Unicode chars that become target Shift-JIS
   codepoints at runtime, then overwrite source files.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont


FONT_ITEM_SIZE = 0x58
FONT_MISC_OFFSET = 0x02
FONT_GLYPH_OFFSET = 0x10
FONT_GLYPH_SIZE = 72  # 24 * 24 / 8
JIS_MIN = 0x21
JIS_MAX = 0x7E
JIS_PLANE_COUNT = 94 * 94


@dataclass
class TranslationRow:
    file_path: str
    content_jp: str
    translated_content_zhtw: str


@dataclass
class IniTranslationRow:
    file_path: str
    line_number: int
    entry_key: str
    content_jp: str
    translated_content_zhtw: str


def read_txt_rows(csv_path: Path) -> List[TranslationRow]:
    rows: List[TranslationRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                TranslationRow(
                    file_path=row.get("file_path", "").strip(),
                    content_jp=row.get("content_jp", ""),
                    translated_content_zhtw=row.get("translated_content_zhtw", ""),
                )
            )
    return rows


def read_ini_rows(csv_path: Path) -> List[IniTranslationRow]:
    rows: List[IniTranslationRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ln_raw = (row.get("line_number", "") or "").strip()
            try:
                line_number = int(ln_raw)
            except ValueError:
                continue
            rows.append(
                IniTranslationRow(
                    file_path=(row.get("file_path", "") or "").strip(),
                    line_number=line_number,
                    entry_key=(row.get("entry_key", "") or "").strip(),
                    content_jp=row.get("content_jp", "") or "",
                    translated_content_zhtw=row.get("translated_content_zhtw", "") or "",
                )
            )
    return rows


def is_visible_char(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    if ch in ("\r", "\n", "\t"):
        return False
    if o < 0x20:
        return False
    # Keep full-width space for CJK typography.
    if ch.isspace() and ord(ch) < 0x80:
        return False
    return True


def collect_unique_chars(texts: List[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for text in texts:
        if not text:
            continue
        for ch in text:
            if not is_visible_char(ch):
                continue
            # Treat only non-ASCII chars as custom FONTDATA glyph targets.
            if ord(ch) < 0x80:
                continue
            if ch not in seen:
                seen.add(ch)
                ordered.append(ch)
    return ordered


def next_jis_code(code: int) -> int:
    hi = (code >> 8) & 0xFF
    lo = code & 0xFF
    lo += 1
    if lo > JIS_MAX:
        lo = JIS_MIN
        hi += 1
    return (hi << 8) | lo


def code_to_index(code: int) -> int:
    hi = (code >> 8) & 0xFF
    lo = code & 0xFF
    if not (JIS_MIN <= hi <= JIS_MAX and JIS_MIN <= lo <= JIS_MAX):
        raise ValueError(f"Invalid JIS code: 0x{code:04X}")
    return (hi - JIS_MIN) * 94 + (lo - JIS_MIN)


def jis_code_to_shift_jis_bytes(code: int) -> bytes:
    """Convert JIS X 0208 ku-ten bytes (0x21-0x7E,0x21-0x7E) to Shift-JIS bytes."""
    ku = (code >> 8) & 0xFF
    ten = code & 0xFF
    if not (JIS_MIN <= ku <= JIS_MAX and JIS_MIN <= ten <= JIS_MAX):
        raise ValueError(f"Invalid JIS code for conversion: 0x{code:04X}")

    if ku <= 0x5E:
        lead = ((ku + 1) // 2) + 0x70
    else:
        lead = ((ku + 1) // 2) + 0xB0

    if ku % 2 == 1:
        trail = ten + 0x1F
        if trail >= 0x7F:
            trail += 1
    else:
        trail = ten + 0x7E
    return bytes([lead, trail])


def jis_code_to_proxy_char(code: int) -> str:
    """Return a Unicode proxy character whose cp932 bytes equal this JIS slot."""
    sjis = jis_code_to_shift_jis_bytes(code)
    return sjis.decode("cp932")


def build_mapping(chars: List[str], start_code: int) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    code = start_code
    for ch in chars:
        if code_to_index(code) >= JIS_PLANE_COUNT:
            raise ValueError("FONTDATA0 code space exhausted while assigning chars.")
        mapping[ch] = code
        code = next_jis_code(code)
    return mapping


def render_char_to_24x24(char: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    img = Image.new("L", (24, 24), 0)
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), char, font=font)
    w = max(0, bbox[2] - bbox[0])
    h = max(0, bbox[3] - bbox[1])
    x = (24 - w) // 2 - bbox[0]
    y = (24 - h) // 2 - bbox[1]
    draw.text((x, y), char, fill=255, font=font)
    return img


def image_to_font72_bytes(img: Image.Image) -> bytes:
    px = img.load()
    out = bytearray(FONT_GLYPH_SIZE)
    for y in range(24):
        for group in range(3):
            b = 0
            for i in range(8):
                x = group * 8 + i
                bit = 1 if px[x, y] >= 128 else 0
                b |= (bit << (7 - i))
            out[y * 3 + group] = b
    return bytes(out)


def patch_fontdata(
    fontdata_path: Path,
    font_out_path: Path,
    mapping: Dict[str, int],
    font_ttf: Path,
    font_size: int,
) -> None:
    raw = bytearray(fontdata_path.read_bytes())
    if len(raw) % FONT_ITEM_SIZE != 0:
        raise ValueError(
            f"Unexpected FONTDATA size {len(raw)} (not multiple of 0x{FONT_ITEM_SIZE:X})."
        )
    item_count = len(raw) // FONT_ITEM_SIZE
    if item_count != JIS_PLANE_COUNT:
        raise ValueError(
            f"Unexpected FONTDATA item count {item_count}, expected {JIS_PLANE_COUNT}."
        )

    font = ImageFont.truetype(str(font_ttf), size=font_size)
    for ch, code in mapping.items():
        idx = code_to_index(code)
        base = idx * FONT_ITEM_SIZE
        glyph = image_to_font72_bytes(render_char_to_24x24(ch, font))
        raw[base + FONT_GLYPH_OFFSET : base + FONT_GLYPH_OFFSET + FONT_GLYPH_SIZE] = glyph

    font_out_path.parent.mkdir(parents=True, exist_ok=True)
    font_out_path.write_bytes(raw)


def map_text_to_proxy_utf8(
    text: str, custom_map: Dict[str, int], missing: Set[str], shift_jis_fallback: bool
) -> str:
    out: List[str] = []
    for ch in text:
        if ch in custom_map:
            out.append(jis_code_to_proxy_char(custom_map[ch]))
            continue
        # Controls/newlines/ASCII pass through.
        if ord(ch) < 0x80:
            out.append(ch)
            continue
        # Keep original char only if cp932 can represent it.
        try:
            ch.encode("cp932")
            out.append(ch)
            continue
        except UnicodeEncodeError:
            pass
        if shift_jis_fallback:
            # If fallback requested, replace with '?' rather than leaving unencodable.
            missing.add(ch)
            out.append("?")
        else:
            missing.add(ch)
            out.append("?")
    return "".join(out)


def _split_keepends(text: str) -> List[str]:
    return text.splitlines(keepends=True)


def _extract_line_parts(line: str) -> Tuple[str, str, str]:
    nl = ""
    if line.endswith("\r\n"):
        core = line[:-2]
        nl = "\r\n"
    elif line.endswith("\n"):
        core = line[:-1]
        nl = "\n"
    elif line.endswith("\r"):
        core = line[:-1]
        nl = "\r"
    else:
        core = line
    return core, nl, line


def _merge_template_controls(template_core: str, translated_core: str) -> str:
    # Preserve all control chars (<0x20) from template at exact positions.
    trans_plain = [c for c in translated_core if ord(c) >= 0x20]
    ti = 0
    out: List[str] = []
    for tc in template_core:
        if ord(tc) < 0x20:
            out.append(tc)
        else:
            if ti < len(trans_plain):
                out.append(trans_plain[ti])
                ti += 1
            else:
                out.append("")
    if ti < len(trans_plain):
        out.extend(trans_plain[ti:])
    return "".join(out)


def merge_control_prefixes(template_text: str, translated_text: str) -> str:
    """Preserve control chars from template lines while keeping translated line structure."""
    tpl_lines = _split_keepends(template_text)
    tr_lines = _split_keepends(translated_text)
    out: List[str] = []
    for idx, tr in enumerate(tr_lines):
        tr_core, tr_nl, _ = _extract_line_parts(tr)
        tpl_core = ""
        if idx < len(tpl_lines):
            tpl_core, _, _ = _extract_line_parts(tpl_lines[idx])
        merged_core = _merge_template_controls(tpl_core, tr_core)
        out.append(merged_core + tr_nl)
    return "".join(out)


def _extract_value_from_ini_line(line_core: str) -> Optional[Tuple[str, str, str]]:
    # Returns: (prefix_with_equal, normalized_key, value)
    if "=" not in line_core:
        return None
    idx = line_core.find("=")
    key = line_core[:idx].strip()
    prefix = line_core[: idx + 1]
    value = line_core[idx + 1 :]
    return prefix, key, value


def _read_file_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return f.readlines()


def _dedupe_txt_rows(rows: List[TranslationRow]) -> List[TranslationRow]:
    # Keep the last translated row per file path.
    by_file: Dict[str, TranslationRow] = {}
    order: List[str] = []
    for r in rows:
        if not r.file_path:
            continue
        if r.file_path not in by_file:
            order.append(r.file_path)
        by_file[r.file_path] = r
    return [by_file[p] for p in order]


def write_mapping_report(mapping: Dict[str, int], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["char", "code_hex", "code_dec"])
        for ch, code in mapping.items():
            writer.writerow([ch, f"0x{code:04X}", str(code)])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build FONTDATA0 from translated TXT+INI and apply proxy UTF-8 back."
    )
    parser.add_argument(
        "--txt-csv",
        default="Process/japanese_txt_translation_files_full.csv",
        help="TXT CSV with file_path/content_jp/translated_content_zhtw.",
    )
    parser.add_argument(
        "--ini-csv",
        default="Process/japanese_ini_translation_rows.csv",
        help="INI CSV with file_path/line_number/entry_key/content_jp/translated_content_zhtw.",
    )
    parser.add_argument(
        "--fontdata-in",
        default="SATranslation/system/FONTDATA0.BIN",
        help="Original FONTDATA0.BIN path.",
    )
    parser.add_argument(
        "--fontdata-out",
        default="SATranslation/system/FONTDATA0.BIN",
        help="Output FONTDATA0.BIN path.",
    )
    parser.add_argument(
        "--font-ttf",
        default="Fonts/NotoSansTC-Bold.ttf",
        help="TTF font path used for glyph rendering.",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=22,
        help="TTF render size for 24x24 glyph target.",
    )
    parser.add_argument(
        "--start-code",
        default="0x3021",
        help="Start JIS code (hex) for assigning custom chars, e.g. 0x3021.",
    )
    parser.add_argument(
        "--mapping-out",
        default="Process/fontdata0_char_map.csv",
        help="Output CSV report for char->code mapping.",
    )
    parser.add_argument(
        "--txt-backup-dir",
        default="Process/backups/japanese_txt_bin",
        help="Backup root for Japanese.txt before overwrite.",
    )
    parser.add_argument(
        "--ini-backup-dir",
        default="Process/backups/japanese_ini_bin",
        help="Backup root for Japanese.ini before overwrite.",
    )
    parser.add_argument(
        "--shift-jis-fallback",
        action="store_true",
        help="Fallback non-custom chars to cp932 when possible.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report changes; do not write files.",
    )
    parser.add_argument(
        "--skip-txt",
        action="store_true",
        help="Do not apply translated_content_zhtw back into Japanese.txt.",
    )
    parser.add_argument(
        "--skip-ini",
        action="store_true",
        help="Do not apply translated_content_zhtw back into Japanese.ini.",
    )
    args = parser.parse_args()

    txt_csv_path = Path(args.txt_csv)
    ini_csv_path = Path(args.ini_csv)
    fontdata_in = Path(args.fontdata_in)
    fontdata_out = Path(args.fontdata_out)
    font_ttf = Path(args.font_ttf)
    mapping_out = Path(args.mapping_out)
    txt_backup_dir = Path(args.txt_backup_dir)
    ini_backup_dir = Path(args.ini_backup_dir)

    if not args.skip_txt and not txt_csv_path.exists():
        raise FileNotFoundError(f"TXT CSV not found: {txt_csv_path}")
    if not args.skip_ini and not ini_csv_path.exists():
        raise FileNotFoundError(f"INI CSV not found: {ini_csv_path}")
    if not fontdata_in.exists():
        raise FileNotFoundError(f"FONTDATA0 not found: {fontdata_in}")
    if not font_ttf.exists():
        raise FileNotFoundError(f"TTF not found: {font_ttf}")

    start_code = int(args.start_code, 16)
    txt_rows = read_txt_rows(txt_csv_path) if txt_csv_path.exists() else []
    ini_rows = read_ini_rows(ini_csv_path) if ini_csv_path.exists() else []

    txt_target_rows = []
    if not args.skip_txt:
        txt_target_rows = [
            r for r in _dedupe_txt_rows(txt_rows) if r.file_path and (r.translated_content_zhtw or "").strip()
        ]
    ini_target_rows = []
    if not args.skip_ini:
        ini_target_rows = [
            r for r in ini_rows if r.file_path and r.entry_key and (r.translated_content_zhtw or "").strip()
        ]

    merged_texts = [r.translated_content_zhtw for r in txt_target_rows] + [
        r.translated_content_zhtw for r in ini_target_rows
    ]
    chars = collect_unique_chars(merged_texts)
    mapping = build_mapping(chars, start_code)

    print(f"TXT rows with translated text: {len(txt_target_rows)}")
    print(f"INI rows with translated text: {len(ini_target_rows)}")
    print(f"Unique custom chars: {len(mapping)}")
    if mapping:
        first_code = next(iter(mapping.values()))
        last_code = list(mapping.values())[-1]
        print(f"Code range used: 0x{first_code:04X}..0x{last_code:04X}")

    if not args.dry_run:
        patch_fontdata(
            fontdata_path=fontdata_in,
            font_out_path=fontdata_out,
            mapping=mapping,
            font_ttf=font_ttf,
            font_size=args.font_size,
        )
        write_mapping_report(mapping, mapping_out)

    missing_chars: Set[str] = set()
    txt_written = 0
    ini_files_written = 0
    ini_rows_written = 0

    for row in txt_target_rows:
        target = Path(row.file_path)
        if not target.exists():
            print(f"Skip missing TXT file: {target}")
            continue
        src_with_controls = merge_control_prefixes(row.content_jp, row.translated_content_zhtw)
        proxy_text = map_text_to_proxy_utf8(
            src_with_controls, mapping, missing_chars, args.shift_jis_fallback
        )
        if args.dry_run:
            txt_written += 1
            continue

        backup_path = txt_backup_dir / target
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if not backup_path.exists():
            shutil.copy2(target, backup_path)
        target.write_text(proxy_text, encoding="utf-8", newline="")
        txt_written += 1

    ini_updates: Dict[str, List[IniTranslationRow]] = {}
    for row in ini_target_rows:
        ini_updates.setdefault(row.file_path, []).append(row)

    for file_path, items in ini_updates.items():
        target = Path(file_path)
        if not target.exists():
            print(f"Skip missing INI file: {target}")
            continue
        lines = _read_file_lines(target)
        dirty = False
        for row in items:
            ln = row.line_number
            if ln < 1 or ln > len(lines):
                continue
            raw = lines[ln - 1]
            core, nl, _ = _extract_line_parts(raw)
            parsed = _extract_value_from_ini_line(core)
            if not parsed:
                continue
            prefix, key, value = parsed
            if key != row.entry_key:
                continue

            merged_value = _merge_template_controls(value, row.translated_content_zhtw)
            proxy_value = map_text_to_proxy_utf8(
                merged_value, mapping, missing_chars, args.shift_jis_fallback
            )
            new_line = f"{prefix}{proxy_value}{nl}"
            if new_line != raw:
                lines[ln - 1] = new_line
                dirty = True
                ini_rows_written += 1

        if dirty:
            if not args.dry_run:
                backup_path = ini_backup_dir / target
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if not backup_path.exists():
                    shutil.copy2(target, backup_path)
                with target.open("w", encoding="utf-8", newline="") as f:
                    f.writelines(lines)
            ini_files_written += 1

    print(f"Japanese.txt files processed: {txt_written}")
    print(f"Japanese.ini files processed: {ini_files_written}")
    print(f"Japanese.ini rows updated: {ini_rows_written}")
    if args.dry_run:
        print("Dry-run mode: no files written.")
    else:
        print(f"Mapping report: {mapping_out}")
        print(f"TXT backup root: {txt_backup_dir}")
        print(f"INI backup root: {ini_backup_dir}")

    if missing_chars:
        print(f"Missing non-encodable chars replaced with '?': {len(missing_chars)}")
        print("Chars:", "".join(sorted(missing_chars)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
