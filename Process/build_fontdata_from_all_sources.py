#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont


FONT_ITEM_SIZE = 0x58
FONT_GLYPH_OFFSET = 0x10
FONT_GLYPH_SIZE = 72
JIS_MIN = 0x21
JIS_MAX = 0x7E
JIS_PLANE_COUNT = 94 * 94

BASE_ADDRS = {"SS": 0xCB46000, "MR": 0xCB4A000, "PAST": 0xCB4A000}
BASE_COUNTS = {"SS": 36, "MR": 5, "PAST": 20}


@dataclass
class TxtRow:
    file_path: str
    content_jp: str
    translated_content_zhtw: str


@dataclass
class IniRow:
    file_path: str
    line_number: int
    entry_key: str
    content_jp: str
    translated_content_zhtw: str


@dataclass
class BinLineRow:
    file_name: str
    line_id: str
    text_jp: str
    translated_text_zhtw: str


@dataclass
class MesGroup:
    event_flags: List[int] = field(default_factory=list)
    npc_flags: List[int] = field(default_factory=list)
    character: int = 0xFF
    voice: Optional[int] = None
    set_event_flag: Optional[int] = None
    lines: List[str] = field(default_factory=list)


@dataclass
class MesNpc:
    groups: List[MesGroup] = field(default_factory=list)


def u32le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little", signed=False)


def i32le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little", signed=True)


def u16le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 2], "little", signed=False)


def i16le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 2], "little", signed=True)


def i32be(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "big", signed=True)


def cstring(data: bytes, off: int, encoding: str = "cp932") -> str:
    if off < 0 or off >= len(data):
        return ""
    end = off
    while end < len(data) and data[end] != 0:
        end += 1
    return data[off:end].decode(encoding, errors="replace")


def ptr_to_off(data: bytes, off: int, image_base: int) -> int:
    return u32le(data, off) - image_base


def esc_unescape(s: str) -> str:
    out: List[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= len(s):
            out.append("\\")
            i += 1
            continue
        n = s[i + 1]
        if n == "n":
            out.append("\n")
        elif n == "r":
            out.append("\r")
        elif n == "t":
            out.append("\t")
        elif n == "\\":
            out.append("\\")
        else:
            out.append(n)
        i += 2
    return "".join(out)


def is_visible_char(ch: str) -> bool:
    if not ch:
        return False
    if ch in ("\r", "\n", "\t"):
        return False
    if ord(ch) < 0x20:
        return False
    if ch.isspace() and ord(ch) < 0x80:
        return False
    return True


def collect_unique_chars(texts: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for t in texts:
        if not t:
            continue
        for ch in t:
            if not is_visible_char(ch):
                continue
            if ord(ch) < 0x80:
                continue
            if ch in seen:
                continue
            seen.add(ch)
            out.append(ch)
    return out


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


def build_mapping(chars: List[str], start_code: int) -> Dict[str, int]:
    m: Dict[str, int] = {}
    code = start_code
    for ch in chars:
        if code_to_index(code) >= JIS_PLANE_COUNT:
            raise ValueError("FONTDATA0 code space exhausted.")
        m[ch] = code
        code = next_jis_code(code)
    return m


def jis_code_to_shift_jis_bytes(code: int) -> bytes:
    ku = (code >> 8) & 0xFF
    ten = code & 0xFF
    if not (JIS_MIN <= ku <= JIS_MAX and JIS_MIN <= ten <= JIS_MAX):
        raise ValueError(f"Invalid JIS code: 0x{code:04X}")
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
    return jis_code_to_shift_jis_bytes(code).decode("cp932")


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
        for g in range(3):
            b = 0
            for i in range(8):
                x = g * 8 + i
                bit = 1 if px[x, y] >= 128 else 0
                b |= bit << (7 - i)
            out[y * 3 + g] = b
    return bytes(out)


def patch_fontdata(fontdata_in: Path, fontdata_out: Path, mapping: Dict[str, int], font_ttf: Path, font_size: int) -> None:
    raw = bytearray(fontdata_in.read_bytes())
    if len(raw) % FONT_ITEM_SIZE != 0:
        raise ValueError("Unexpected FONTDATA0 size.")
    if len(raw) // FONT_ITEM_SIZE != JIS_PLANE_COUNT:
        raise ValueError("Unexpected FONTDATA0 item count.")
    font = ImageFont.truetype(str(font_ttf), size=font_size)
    for ch, code in mapping.items():
        idx = code_to_index(code)
        base = idx * FONT_ITEM_SIZE
        glyph = image_to_font72_bytes(render_char_to_24x24(ch, font))
        raw[base + FONT_GLYPH_OFFSET : base + FONT_GLYPH_OFFSET + FONT_GLYPH_SIZE] = glyph
    fontdata_out.parent.mkdir(parents=True, exist_ok=True)
    fontdata_out.write_bytes(raw)


def map_text_to_proxy_utf8(text: str, mapping: Dict[str, int], missing: Set[str]) -> str:
    out: List[str] = []
    for ch in text:
        if ch in mapping:
            out.append(jis_code_to_proxy_char(mapping[ch]))
            continue
        if ord(ch) < 0x80:
            out.append(ch)
            continue
        try:
            ch.encode("cp932")
            out.append(ch)
        except UnicodeEncodeError:
            missing.add(ch)
            out.append("?")
    return "".join(out)


def map_text_to_bin_bytes(text: str, mapping: Dict[str, int], missing: Set[str]) -> bytes:
    out = bytearray()
    for ch in text:
        if ch in mapping:
            out.extend(jis_code_to_shift_jis_bytes(mapping[ch]))
            continue
        try:
            out.extend(ch.encode("cp932"))
        except UnicodeEncodeError:
            missing.add(ch)
            out.extend(b"?")
    return bytes(out)


def read_txt_rows(csv_path: Path) -> List[TxtRow]:
    rows: List[TxtRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(TxtRow(r.get("file_path", "").strip(), r.get("content_jp", ""), r.get("translated_content_zhtw", "")))
    return rows


def read_ini_rows(csv_path: Path) -> List[IniRow]:
    rows: List[IniRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ln = int((r.get("line_number", "") or "").strip())
            except ValueError:
                continue
            rows.append(
                IniRow(
                    file_path=(r.get("file_path", "") or "").strip(),
                    line_number=ln,
                    entry_key=(r.get("entry_key", "") or "").strip(),
                    content_jp=r.get("content_jp", "") or "",
                    translated_content_zhtw=r.get("translated_content_zhtw", "") or "",
                )
            )
    return rows


def read_bin_text_rows(bin_text_dir: Path) -> List[BinLineRow]:
    rows: List[BinLineRow] = []
    for p in sorted(bin_text_dir.glob("*.BIN.txt")):
        file_name = p.name[:-4]
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue
            rows.append(BinLineRow(file_name=file_name, line_id=parts[0], text_jp=esc_unescape(parts[1]), translated_text_zhtw=esc_unescape(parts[2])))
    return rows


def _split_keepends(text: str) -> List[str]:
    return text.splitlines(keepends=True)


def _extract_line_parts(line: str) -> Tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _merge_template_controls(template_core: str, translated_core: str) -> str:
    trans_plain = [c for c in translated_core if ord(c) >= 0x20]
    ti = 0
    out: List[str] = []
    for tc in template_core:
        if ord(tc) < 0x20:
            out.append(tc)
        elif ti < len(trans_plain):
            out.append(trans_plain[ti])
            ti += 1
    if ti < len(trans_plain):
        out.extend(trans_plain[ti:])
    return "".join(out)


def merge_control_prefixes(template_text: str, translated_text: str) -> str:
    tpl_lines = _split_keepends(template_text)
    tr_lines = _split_keepends(translated_text)
    out: List[str] = []
    for i, tr in enumerate(tr_lines):
        tr_core, tr_nl = _extract_line_parts(tr)
        tpl_core = _extract_line_parts(tpl_lines[i])[0] if i < len(tpl_lines) else ""
        out.append(_merge_template_controls(tpl_core, tr_core) + tr_nl)
    return "".join(out)


def _extract_ini_value(line_core: str) -> Optional[Tuple[str, str, str]]:
    if "=" not in line_core:
        return None
    i = line_core.find("=")
    return line_core[: i + 1], line_core[:i].strip(), line_core[i + 1 :]


def _read_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return f.readlines()


def _id_simple(idx: int) -> str:
    return f"m:{idx}"


def _id_mes(n: int, g: int, l: int) -> str:
    return f"n:{n}|g:{g}|l:{l}"


def parse_simple_bin(data: bytes) -> List[str]:
    msgs: List[str] = []
    off = 0
    while off + 4 <= len(data):
        p = i32be(data, off)
        if p == -1:
            break
        if p < 0 or p >= len(data):
            break
        msgs.append(cstring(data, p))
        off += 4
    return msgs


def build_simple_bin(messages: List[str], mapping: Dict[str, int], missing: Set[str]) -> bytes:
    header = bytearray()
    body = bytearray()
    header_size = (len(messages) + 1) * 4
    for msg in messages:
        header.extend((header_size + len(body)).to_bytes(4, "big", signed=True))
        body.extend(map_text_to_bin_bytes(msg, mapping, missing))
        body.append(0)
        while len(body) % 4 != 0:
            body.append(0)
    header.extend((-1).to_bytes(4, "big", signed=True))
    return bytes(header + body)


def parse_mes_bin(data: bytes, field_name: str) -> List[MesNpc]:
    base = BASE_ADDRS[field_name]
    count = i32le(data, 0) + BASE_COUNTS[field_name]
    hdr_off = ptr_to_off(data, 4, base)
    if hdr_off < 0 or hdr_off + count * 8 > len(data):
        return []
    npcs: List[MesNpc] = []
    for n in range(count):
        eoff = hdr_off + n * 8
        ctrl_ptr = u32le(data, eoff)
        text_ptr = u32le(data, eoff + 4)
        npc = MesNpc()
        if ctrl_ptr == 0 and text_ptr == 0:
            npcs.append(npc)
            continue
        text_off = text_ptr - base if text_ptr else -1
        if ctrl_ptr == 0:
            g = MesGroup()
            while text_off >= 0 and text_off + 4 <= len(data) and i32le(data, text_off) != 0:
                g.lines.append(cstring(data, ptr_to_off(data, text_off, base)))
                text_off += 4
            npc.groups.append(g)
            npcs.append(npc)
            continue

        ctrl_off = ctrl_ptr - base
        g = MesGroup()
        while True:
            if text_ptr:
                while text_off >= 0 and text_off + 4 <= len(data) and i32le(data, text_off) != 0:
                    g.lines.append(cstring(data, ptr_to_off(data, text_off, base)))
                    text_off += 4
                text_off += 4
            while True:
                if ctrl_off + 2 > len(data):
                    break
                code = i16le(data, ctrl_off)
                ctrl_off += 2
                if code == -7:
                    g.event_flags.append(u16le(data, ctrl_off))
                    ctrl_off += 2
                    continue
                if code == -6:
                    g.npc_flags.append(u16le(data, ctrl_off))
                    ctrl_off += 2
                    continue
                if code == -5:
                    g.character = u16le(data, ctrl_off)
                    ctrl_off += 2
                    continue
                if code == -4:
                    g.voice = u16le(data, ctrl_off)
                    ctrl_off += 2
                    continue
                if code == -3:
                    g.set_event_flag = u16le(data, ctrl_off)
                    ctrl_off += 2
                    continue
                if code == -2:
                    npc.groups.append(g)
                    g = MesGroup()
                    break
                if code == -1:
                    npc.groups.append(g)
                    code = -1
                    break
                code = -1
                break
            if code == -2:
                continue
            break
        npcs.append(npc)
    return npcs


def build_mes_bin(npcs: List[MesNpc], field_name: str, mapping: Dict[str, int], missing: Set[str]) -> bytes:
    base = BASE_ADDRS[field_name]
    base_count = BASE_COUNTS[field_name]
    data = bytearray()
    headers = bytearray()

    for npc in npcs:
        if not npc.groups:
            headers.extend(b"\x00" * 8)
            continue
        has_control = any(
            g.event_flags or g.npc_flags or g.character != 0xFF or g.voice is not None or g.set_event_flag is not None
            for g in npc.groups
        )
        has_text = any(g.lines for g in npc.groups)

        if has_control:
            headers.extend((base + len(data) + 8).to_bytes(4, "little", signed=False))
            first = True
            for g in npc.groups:
                if not first:
                    data.extend((-2).to_bytes(2, "little", signed=True))
                first = False
                for v in g.event_flags:
                    data.extend((-7).to_bytes(2, "little", signed=True))
                    data.extend(int(v).to_bytes(2, "little", signed=False))
                for v in g.npc_flags:
                    data.extend((-6).to_bytes(2, "little", signed=True))
                    data.extend(int(v).to_bytes(2, "little", signed=False))
                if g.character != 0xFF:
                    data.extend((-5).to_bytes(2, "little", signed=True))
                    data.extend(int(g.character).to_bytes(2, "little", signed=False))
                if g.voice is not None:
                    data.extend((-4).to_bytes(2, "little", signed=True))
                    data.extend(int(g.voice).to_bytes(2, "little", signed=False))
                if g.set_event_flag is not None:
                    data.extend((-3).to_bytes(2, "little", signed=True))
                    data.extend(int(g.set_event_flag).to_bytes(2, "little", signed=False))
            data.extend((-1).to_bytes(2, "little", signed=True))
        else:
            headers.extend(b"\x00" * 4)

        if has_text:
            text_ptr_table = bytearray()
            for g in npc.groups:
                for line in g.lines:
                    text_ptr_table.extend((base + len(data) + 8).to_bytes(4, "little", signed=False))
                    data.extend(map_text_to_bin_bytes(line, mapping, missing))
                    data.append(0)
                    while len(data) % 4 != 0:
                        data.append(0)
                text_ptr_table.extend(b"\x00" * 4)
            headers.extend((base + len(data) + 8).to_bytes(4, "little", signed=False))
            data.extend(text_ptr_table)
        else:
            headers.extend(b"\x00" * 4)

    out = bytearray()
    out.extend((len(npcs) - base_count).to_bytes(4, "little", signed=True))
    out.extend((base + len(data) + 8).to_bytes(4, "little", signed=False))
    out.extend(data)
    out.extend(headers)
    return bytes(out)


def apply_bin_text(system_dir: Path, bin_rows: List[BinLineRow], mapping: Dict[str, int], backup_dir: Path, dry_run: bool, missing: Set[str]) -> Tuple[int, int]:
    by_file: Dict[str, Dict[str, str]] = {}
    for r in bin_rows:
        tr = (r.translated_text_zhtw or "").strip()
        if not tr:
            continue
        by_file.setdefault(r.file_name, {})[r.line_id] = r.translated_text_zhtw

    changed_files = 0
    changed_lines = 0
    for file_name, line_map in by_file.items():
        p = system_dir / file_name
        if not p.exists():
            continue
        raw = p.read_bytes()
        m = file_name.upper().split("_MES_", 1)
        if len(m) == 2 and m[0] in ("SS", "MR", "PAST"):
            field_name = m[0]
            npcs = parse_mes_bin(raw, field_name)
            dirty = False
            for ni, npc in enumerate(npcs):
                for gi, grp in enumerate(npc.groups):
                    for li, txt in enumerate(grp.lines):
                        lid = _id_mes(ni, gi, li)
                        tr = line_map.get(lid)
                        if tr is None:
                            continue
                        grp.lines[li] = tr
                        dirty = True
                        changed_lines += 1
            if not dirty:
                continue
            rebuilt = build_mes_bin(npcs, field_name, mapping, missing)
        else:
            msgs = parse_simple_bin(raw)
            dirty = False
            for i in range(len(msgs)):
                lid = _id_simple(i)
                tr = line_map.get(lid)
                if tr is None:
                    continue
                msgs[i] = tr
                dirty = True
                changed_lines += 1
            if not dirty:
                continue
            rebuilt = build_simple_bin(msgs, mapping, missing)

        if not dry_run:
            bp = backup_dir / p
            bp.parent.mkdir(parents=True, exist_ok=True)
            if not bp.exists():
                shutil.copy2(p, bp)
            p.write_bytes(rebuilt)
        changed_files += 1
    return changed_files, changed_lines


def write_mapping_report(mapping: Dict[str, int], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["char", "code_hex", "code_dec"])
        for ch, code in mapping.items():
            w.writerow([ch, f"0x{code:04X}", str(code)])


def main() -> int:
    ap = argparse.ArgumentParser(description="Build FONTDATA from TXT+INI+BIN_TEXT and apply back.")
    ap.add_argument("--txt-csv", default="Process/japanese_txt_translation_files_full.csv")
    ap.add_argument("--ini-csv", default="Process/japanese_ini_translation_rows.csv")
    ap.add_argument("--bin-text-dir", default="Process/BIN_TEXT")
    ap.add_argument("--fontdata-in", default="SATranslation/system/FONTDATA0.BIN")
    ap.add_argument("--fontdata-out", default="SATranslation/system/FONTDATA0.BIN")
    ap.add_argument("--font-ttf", default="Fonts/NotoSansTC-Bold.ttf")
    ap.add_argument("--font-size", type=int, default=22)
    ap.add_argument("--start-code", default="0x3021")
    ap.add_argument("--mapping-out", default="Process/fontdata0_char_map.csv")
    ap.add_argument("--txt-backup-dir", default="Process/backups/japanese_txt_bin")
    ap.add_argument("--ini-backup-dir", default="Process/backups/japanese_ini_bin")
    ap.add_argument("--bin-backup-dir", default="Process/backups/system_bin")
    ap.add_argument("--skip-txt", action="store_true")
    ap.add_argument("--skip-ini", action="store_true")
    ap.add_argument("--skip-bin", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    txt_csv = Path(args.txt_csv)
    ini_csv = Path(args.ini_csv)
    bin_text_dir = Path(args.bin_text_dir)
    fontdata_in = Path(args.fontdata_in)
    fontdata_out = Path(args.fontdata_out)
    font_ttf = Path(args.font_ttf)
    mapping_out = Path(args.mapping_out)

    if not args.skip_txt and not txt_csv.exists():
        raise FileNotFoundError(f"TXT CSV not found: {txt_csv}")
    if not args.skip_ini and not ini_csv.exists():
        raise FileNotFoundError(f"INI CSV not found: {ini_csv}")
    if not args.skip_bin and not bin_text_dir.exists():
        raise FileNotFoundError(f"BIN_TEXT dir not found: {bin_text_dir}")
    if not fontdata_in.exists():
        raise FileNotFoundError(f"FONTDATA0 not found: {fontdata_in}")
    if not font_ttf.exists():
        raise FileNotFoundError(f"TTF not found: {font_ttf}")

    txt_rows = [] if args.skip_txt else read_txt_rows(txt_csv)
    ini_rows = [] if args.skip_ini else read_ini_rows(ini_csv)
    bin_rows = [] if args.skip_bin else read_bin_text_rows(bin_text_dir)

    txt_targets = [r for r in txt_rows if r.file_path and (r.translated_content_zhtw or "").strip()]
    ini_targets = [r for r in ini_rows if r.file_path and r.entry_key and (r.translated_content_zhtw or "").strip()]
    bin_targets = [r for r in bin_rows if (r.translated_text_zhtw or "").strip()]

    all_translated = [r.translated_content_zhtw for r in txt_targets]
    all_translated += [r.translated_content_zhtw for r in ini_targets]
    all_translated += [r.translated_text_zhtw for r in bin_targets]

    mapping = build_mapping(collect_unique_chars(all_translated), int(args.start_code, 16))

    print(f"TXT translated rows: {len(txt_targets)}")
    print(f"INI translated rows: {len(ini_targets)}")
    print(f"BIN translated rows: {len(bin_targets)}")
    print(f"Unique custom chars: {len(mapping)}")
    if mapping:
        vals = list(mapping.values())
        print(f"Code range used: 0x{vals[0]:04X}..0x{vals[-1]:04X}")

    if not args.dry_run:
        patch_fontdata(fontdata_in, fontdata_out, mapping, font_ttf, args.font_size)
        write_mapping_report(mapping, mapping_out)

    missing_chars: Set[str] = set()

    txt_files = 0
    for r in txt_targets:
        p = Path(r.file_path)
        if not p.exists():
            continue
        merged = merge_control_prefixes(r.content_jp, r.translated_content_zhtw)
        proxy = map_text_to_proxy_utf8(merged, mapping, missing_chars)
        if not args.dry_run:
            bp = Path(args.txt_backup_dir) / p
            bp.parent.mkdir(parents=True, exist_ok=True)
            if not bp.exists():
                shutil.copy2(p, bp)
            p.write_text(proxy, encoding="utf-8", newline="")
        txt_files += 1

    ini_files = 0
    ini_rows_changed = 0
    by_ini: Dict[str, List[IniRow]] = {}
    for r in ini_targets:
        by_ini.setdefault(r.file_path, []).append(r)
    for fp, items in by_ini.items():
        p = Path(fp)
        if not p.exists():
            continue
        lines = _read_lines(p)
        dirty = False
        for r in items:
            if r.line_number < 1 or r.line_number > len(lines):
                continue
            core, nl = _extract_line_parts(lines[r.line_number - 1])
            parsed = _extract_ini_value(core)
            if not parsed:
                continue
            prefix, key, value = parsed
            if key != r.entry_key:
                continue
            merged = _merge_template_controls(value, r.translated_content_zhtw)
            proxy = map_text_to_proxy_utf8(merged, mapping, missing_chars)
            newline = f"{prefix}{proxy}{nl}"
            if newline != lines[r.line_number - 1]:
                lines[r.line_number - 1] = newline
                dirty = True
                ini_rows_changed += 1
        if dirty:
            if not args.dry_run:
                bp = Path(args.ini_backup_dir) / p
                bp.parent.mkdir(parents=True, exist_ok=True)
                if not bp.exists():
                    shutil.copy2(p, bp)
                with p.open("w", encoding="utf-8", newline="") as f:
                    f.writelines(lines)
            ini_files += 1

    bin_files = 0
    bin_rows_changed = 0
    if not args.skip_bin:
        bin_files, bin_rows_changed = apply_bin_text(
            system_dir=Path("SATranslation/system"),
            bin_rows=bin_rows,
            mapping=mapping,
            backup_dir=Path(args.bin_backup_dir),
            dry_run=args.dry_run,
            missing=missing_chars,
        )

    print(f"Japanese.txt files processed: {txt_files}")
    print(f"Japanese.ini files processed: {ini_files}")
    print(f"Japanese.ini rows updated: {ini_rows_changed}")
    print(f"SYSTEM BIN files processed: {bin_files}")
    print(f"SYSTEM BIN lines updated: {bin_rows_changed}")
    if args.dry_run:
        print("Dry-run mode: no files written.")
    else:
        print(f"Mapping report: {mapping_out}")
        print(f"TXT backup root: {args.txt_backup_dir}")
        print(f"INI backup root: {args.ini_backup_dir}")
        print(f"BIN backup root: {args.bin_backup_dir}")
    if missing_chars:
        print(f"Missing non-encodable chars replaced with '?': {len(missing_chars)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

