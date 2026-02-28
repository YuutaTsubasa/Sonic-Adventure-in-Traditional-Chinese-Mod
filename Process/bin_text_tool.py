#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def esc(s: str) -> str:
    return (
        s.replace('\\', '\\\\')
        .replace('\t', '\\t')
        .replace('\r', '\\r')
        .replace('\n', '\\n')
    )


def unesc(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        if i + 1 >= len(s):
            out.append('\\')
            i += 1
            continue
        n = s[i + 1]
        if n == 'n':
            out.append('\n')
        elif n == 'r':
            out.append('\r')
        elif n == 't':
            out.append('\t')
        elif n == '\\':
            out.append('\\')
        else:
            out.append(n)
        i += 2
    return ''.join(out)


def make_id(row: dict) -> str:
    fmt = row.get('format', '')
    if fmt == 'simple_ptr_table':
        return f"m:{row.get('message_index', '').strip()}"
    return f"n:{row.get('npc_index', '').strip()}|g:{row.get('group_index', '').strip()}|l:{row.get('line_index', '').strip()}"


def cmd_export(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir)

    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))

    by_file: dict[str, list[dict]] = {}
    for r in rows:
        by_file.setdefault(r['file_name'], []).append(r)

    out_dir.mkdir(parents=True, exist_ok=True)

    for file_name, items in sorted(by_file.items()):
        txt_path = out_dir / f"{file_name}.txt"
        with txt_path.open('w', encoding='utf-8', newline='\n') as f:
            f.write('# BIN_TEXT v1\n')
            f.write(f"# file_name={file_name}\n")
            f.write('# columns=id\ttext_jp\ttranslated_text_zhtw\n')
            for r in items:
                rid = make_id(r)
                jp = esc(r.get('text_jp', '') or '')
                tr = esc(r.get('translated_text_zhtw', '') or '')
                f.write(f"{rid}\t{jp}\t{tr}\n")

    print(f"files={len(by_file)}")
    print(f"out_dir={out_dir}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    in_dir = Path(args.in_dir)

    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

    index: dict[tuple[str, str], dict] = {}
    for r in rows:
        index[(r['file_name'], make_id(r))] = r

    updated = 0
    txt_files = sorted(in_dir.glob('*.BIN.txt'))
    for tf in txt_files:
        file_name = tf.name[:-4]  # remove .txt
        with tf.open('r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.rstrip('\r\n')
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) < 3:
                    continue
                rid = parts[0]
                tr = unesc(parts[2])
                k = (file_name, rid)
                row = index.get(k)
                if row is None:
                    continue
                if row.get('translated_text_zhtw', '') != tr:
                    row['translated_text_zhtw'] = tr
                    updated += 1

    if 'translated_text_zhtw' not in fields:
        fields.append('translated_text_zhtw')

    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"txt_files={len(txt_files)}")
    print(f"updated_rows={updated}")
    print(f"csv={csv_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='Convert BIN message CSV <-> per-BIN TXT files')
    sub = p.add_subparsers(dest='cmd', required=True)

    p_export = sub.add_parser('export', help='Export CSV rows into one TXT per BIN')
    p_export.add_argument('--csv', default='Process/system_message_bins_extracted.csv')
    p_export.add_argument('--out-dir', default='Process/BIN_TEXT')
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser('import', help='Import translated_text_zhtw from TXT back to CSV')
    p_import.add_argument('--csv', default='Process/system_message_bins_extracted.csv')
    p_import.add_argument('--in-dir', default='Process/BIN_TEXT')
    p_import.set_defaults(func=cmd_import)

    args = p.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
