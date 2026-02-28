#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from pathlib import Path

BASE_ADDRS = {
    "SS": 0xCB46000,
    "MR": 0xCB4A000,
    "PAST": 0xCB4A000,
}
BASE_COUNTS = {
    "SS": 36,
    "MR": 5,
    "PAST": 20,
}

TARGET_FILES = [
    "CHAODX_MESSAGE_BLACKMARKET_J.BIN",
    "CHAODX_MESSAGE_HINT_J.BIN",
    "CHAODX_MESSAGE_ITEM_J.BIN",
    "CHAODX_MESSAGE_ODEKAKE_J.BIN",
    "CHAODX_MESSAGE_PLAYERACTION_J.BIN",
    "CHAODX_MESSAGE_RACE_J.BIN",
    "CHAODX_MESSAGE_SYSTEM_J.BIN",
    "MR_MES_A_J.BIN",
    "MR_MES_B_J.BIN",
    "MR_MES_E_J.BIN",
    "MR_MES_K_J.BIN",
    "MR_MES_L_J.BIN",
    "MR_MES_M_J.BIN",
    "MR_MES_S_J.BIN",
    "MSGALITEM_J.BIN",
    "MSGALKINDERBL_J.BIN",
    "MSGALKINDERPR_J.BIN",
    "MSGALWARN_J.BIN",
    "PAST_MES_A_J.BIN",
    "PAST_MES_B_J.BIN",
    "PAST_MES_E_J.BIN",
    "PAST_MES_K_J.BIN",
    "PAST_MES_M_J.BIN",
    "PAST_MES_S_J.BIN",
    "SS_MES_A_J.BIN",
    "SS_MES_B_J.BIN",
    "SS_MES_E_J.BIN",
    "SS_MES_K_J.BIN",
    "SS_MES_L_J.BIN",
    "SS_MES_M_J.BIN",
    "SS_MES_S_J.BIN",
]

MSG_RE = re.compile(r"^(SS|MR|PAST)_MES_([A-Z])_J\.BIN$", re.IGNORECASE)


def u32le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little", signed=False)


def i32le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little", signed=True)


def i16le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 2], "little", signed=True)


def i32be(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "big", signed=True)


def ptr_to_off(data: bytes, off: int, image_base: int) -> int:
    return u32le(data, off) - image_base


def cstring(data: bytes, off: int, encoding: str = "cp932") -> str:
    if off < 0 or off >= len(data):
        return ""
    end = off
    while end < len(data) and data[end] != 0:
        end += 1
    return data[off:end].decode(encoding, errors="replace")


def parse_chao_simple(data: bytes) -> list[dict]:
    rows = []
    addr = 0
    idx = 0
    while addr + 4 <= len(data):
        p = i32be(data, addr)
        if p == -1:
            break
        if p < 0 or p >= len(data):
            break
        txt = cstring(data, p)
        rows.append(
            {
                "message_index": idx,
                "npc_index": "",
                "group_index": "",
                "line_index": "",
                "text_jp": txt,
            }
        )
        idx += 1
        addr += 4
    return rows


def parse_mes_npc(data: bytes, field: str) -> list[dict]:
    image_base = BASE_ADDRS[field]
    base_count = BASE_COUNTS[field]

    count = i32le(data, 0) + base_count
    hdr_off = ptr_to_off(data, 4, image_base)
    if hdr_off < 0 or hdr_off + (count * 8) > len(data):
        return []

    rows: list[dict] = []

    for npc_idx in range(count):
        entry = hdr_off + npc_idx * 8
        ctrl_ptr = u32le(data, entry)
        text_ptr = u32le(data, entry + 4)

        has_text = text_ptr != 0
        text_off = text_ptr - image_base if has_text else -1

        group_index = 0

        if ctrl_ptr == 0:
            if not has_text or text_off < 0 or text_off >= len(data):
                continue
            line_index = 0
            while text_off + 4 <= len(data) and i32le(data, text_off) != 0:
                line_ptr_off = ptr_to_off(data, text_off, image_base)
                rows.append(
                    {
                        "message_index": "",
                        "npc_index": npc_idx,
                        "group_index": group_index,
                        "line_index": line_index,
                        "text_jp": cstring(data, line_ptr_off),
                    }
                )
                line_index += 1
                text_off += 4
            continue

        ctrl_off = ctrl_ptr - image_base
        if ctrl_off < 0 or ctrl_off >= len(data):
            continue

        while True:
            if has_text:
                if text_off < 0 or text_off >= len(data):
                    break
                line_index = 0
                while text_off + 4 <= len(data) and i32le(data, text_off) != 0:
                    line_ptr_off = ptr_to_off(data, text_off, image_base)
                    rows.append(
                        {
                            "message_index": "",
                            "npc_index": npc_idx,
                            "group_index": group_index,
                            "line_index": line_index,
                            "text_jp": cstring(data, line_ptr_off),
                        }
                    )
                    line_index += 1
                    text_off += 4
                text_off += 4

            while True:
                if ctrl_off + 2 > len(data):
                    return rows
                code = i16le(data, ctrl_off)
                ctrl_off += 2
                if code in (-7, -6, -5, -4, -3):
                    ctrl_off += 2
                    if ctrl_off > len(data):
                        return rows
                    continue
                if code == -2:  # new group
                    group_index += 1
                    break
                if code == -1:  # end
                    break
                # unknown code, abort current npc
                code = -1
                break

            if code == -2:
                continue
            break

    return rows


def main() -> int:
    system_dir = Path("SATranslation/system")
    out_csv = Path("Process/system_message_bins_extracted.csv")

    out_rows = []
    for name in TARGET_FILES:
        p = system_dir / name
        if not p.exists():
            continue
        data = p.read_bytes()

        m = MSG_RE.match(name)
        if m:
            field = m.group(1).upper()
            parsed = parse_mes_npc(data, field)
            fmt = "mes_npc"
        else:
            parsed = parse_chao_simple(data)
            fmt = "simple_ptr_table"

        for r in parsed:
            out_rows.append(
                {
                    "file_name": name,
                    "file_path": str(p).replace("\\", "/"),
                    "format": fmt,
                    "message_index": r["message_index"],
                    "npc_index": r["npc_index"],
                    "group_index": r["group_index"],
                    "line_index": r["line_index"],
                    "text_jp": r["text_jp"],
                }
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "file_name",
                "file_path",
                "format",
                "message_index",
                "npc_index",
                "group_index",
                "line_index",
                "text_jp",
            ],
        )
        w.writeheader()
        w.writerows(out_rows)

    print(f"rows={len(out_rows)}")
    print(f"csv={out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
