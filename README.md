# SATraditional

This repository contains the Traditional Chinese translation workspace for SADX-related text and texture assets.

## Structure

- `Fonts/`
  - Fonts used for FONTDATA generation and menu texture rendering.
- `Process/`
  - Scripts, extracted working folders, translation CSV/TXT files, and build outputs.
- `SATranslation/`
  - Project data to be patched back into the game/mod.

## Requirements

- Windows
- Python 3
- `Pillow` installed for image rendering scripts
- SA Tools binaries available at:
  - `C:\Users\User\Repo\SATraditional\SA.Tools.x64\bin\ArchiveTool.exe`

## Text Pipeline

Main script:

- `Process/build_fontdata_from_all_sources.py`

This pipeline combines translated content from:

- `Process/japanese_txt_translation_files_full.csv`
- `Process/japanese_ini_translation_rows.csv`
- `Process/BIN_TEXT/*.BIN.txt`

It then:

1. Collects a combined character set from `TXT + INI + BIN`.
2. Generates/patches custom glyphs into `SATranslation/system/FONTDATA0.BIN`.
3. Rewrites translated `Japanese.txt`.
4. Rewrites translated `Japanese.ini`.
5. Rewrites translated system message `.BIN` files.

Run:

```powershell
python .\Process\build_fontdata_from_all_sources.py
```

Outputs and backups:

- `Process/fontdata0_char_map.csv`
- `Process/backups/japanese_txt_bin`
- `Process/backups/japanese_ini_bin`
- `Process/backups/system_bin`

## BIN Text Workflow

Scripts:

- `Process/extract_system_bin_messages_to_csv.py`
- `Process/bin_text_tool.py`

Purpose:

1. Extract system message `.BIN` files into translation-friendly text form.
2. Store one editable text file per BIN under `Process/BIN_TEXT/`.
3. Feed translated text back into the global BIN rebuild pipeline.

Export per-BIN text files:

```powershell
python .\Process\bin_text_tool.py export
```

Import edited BIN text back into CSV:

```powershell
python .\Process\bin_text_tool.py import
```

## PVM Texture Workflow

These scripts now use SA Tools `ArchiveTool.exe` as the real backend.

Scripts:

- `Process/extract_pvms_to_folders.py`
- `Process/repack_pvms_from_folders.py`

### Extract PVM to PNG folders

Input:

- `Process/PVMs/*.PVM`

Output:

- `Process/PVM_EXTRACTED/<PVM_NAME>/`

Run all:

```powershell
python .\Process\extract_pvms_to_folders.py --input-dir .\Process\PVMs --output-dir .\Process\PVM_EXTRACTED
```

Run one PVM:

```powershell
python .\Process\extract_pvms_to_folders.py --input-dir .\Process\PVMs --output-dir .\Process\PVM_EXTRACTED --glob AVA_DLG.PVM
```

### Repack edited PNG folders back to PVM

Output:

- `Process/PVM_REPACKED/<PVM_NAME>.pvm`

Run one folder:

```powershell
python .\Process\repack_pvms_from_folders.py --input-dir .\Process\PVM_EXTRACTED --output-dir .\Process\PVM_REPACKED --folder AVA_DLG
```

Run all folders:

```powershell
python .\Process\repack_pvms_from_folders.py --input-dir .\Process\PVM_EXTRACTED --output-dir .\Process\PVM_REPACKED
```

Notes:

- `PVM_EXTRACTED` is the editable working area.
- `PVM_REPACKED` is build output.
- Current verified workflow uses SA Tools `ArchiveTool`, not the earlier experimental custom parser.

## Menu Text Rendering

Script:

- `Process/render_centered_text_png.py`

This renders transparent PNGs for menu textures with configurable:

- font file
- font size
- fill color
- stroke width / stroke color
- horizontal alignment
- vertical alignment

Examples:

```powershell
python .\Process\render_centered_text_png.py --text "取消" --width 128 --height 16 --font-size 14 --font .\Fonts\NotoSansTC-Bold.ttf --output .\Process\cancel.png
```

```powershell
python .\Process\render_centered_text_png.py --text "設定" --width 256 --height 32 --font-size 28 --font .\Fonts\NotoSansTC-Bold.ttf --stroke-width 1 --stroke-fill "#000000FF" --align left --padding-x 8 --output .\Process\setting.png
```

Useful options:

- `--align left|center|right`
- `--padding-x`
- `--valign top|center|bottom`
- `--padding-y`
- `--stroke-width`
- `--stroke-fill`

## Current Working Folders

Common asset folders used during current work:

- `Process/PVMs`
- `Process/PVM_EXTRACTED`
- `Process/PVM_REPACKED`
- `Process/BIN_TEXT`

## Git

This project is intended to be managed as a git repository from this folder:

- `C:\Users\User\Repo\SATraditional\Projects\SATranslation`

Recommended workflow:

1. Edit translation CSV/TXT/PNG assets.
2. Rebuild outputs with the scripts above.
3. Review changed files with `git status` / `git diff`.
4. Commit in logical steps.
