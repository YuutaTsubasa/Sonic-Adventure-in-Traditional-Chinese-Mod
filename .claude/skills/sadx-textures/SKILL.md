---
name: sadx-textures
description: Translate the Japanese text drawn in Sonic Adventure DX (PC) textures into Taiwanese Traditional Chinese by writing per-texture specs (text/tex/<id>.json) and checking rendered previews. Use when asked to do or continue SADX texture translation for given archives.
---

# SADX 貼圖翻譯流程

All commands run from `C:\Users\User\Repo\SonicTranslations\sadx-zhtw` with `PYTHONUTF8=1`.

## What exists
- `work/tex/sheets/<ARCHIVE>.png` — contact sheet of every texture in that archive that still needs a decision; each tile is labelled `<id> <W>x<H>`.
- `text/tex/<id>.json` — the spec for texture `<id>` (one spec covers every copy of that texture in any archive). Textures already identical to the English version are marked `{"keep": true}`.
- `python tools/tex.py status` — counts.

## For every texture on your sheets

1. Look at the sheet (Read the PNG). Decide:
   - **No Japanese** (pictures, icons, numbers, English-only, button glyphs, logos without Japanese) → write `{"keep": true, "why": "<short reason>"}`.
   - **Japanese text** → write a spec (below).
2. Measure: `python tools/tex.py show <id>` writes `work/tex/show/<id>.png` (zoomed, grid every 10 px, rulers in texture pixels) — Read it. `python tools/tex.py boxes <id>` prints bounding boxes of opaque glyph clusters; `python tools/tex.py colors <id> x0 y0 x1 y1` prints the main colours in a rect (text fill, outline, background).
3. Write `text/tex/<id>.json`:
   ```json
   {"archive": "AVA_DLG", "ja": "キャンセル",
    "erase": [[0, 0, 128, 16]],
    "blocks": [{"rect": [0, 1, 128, 16], "zh": "取消", "size": 13, "weight": 700,
                "color": "#ffffff", "stroke": "#000000", "stroke_w": 1, "align": "center"}]}
   ```
   - Coordinates are original texture pixels, `[x0, y0, x1, y1]` with x1/y1 exclusive.
   - `erase` rects are cleared to transparent (`"fill": "#rrggbbaa"` to clear to a colour instead). On a picture or gradient background use `"erase_mode": "row"` (each row interpolated from the pixels just left and right of the rect) or `"col"` (from above and below). Erase **only** the Japanese; keep key/button icons (Space, V, Q/W, arrows), pictures, frames and any English.
   - Block keys: `rect`, `zh` (may contain `\n` for two lines), `size` (font px; CJK glyphs look about 0.85 × size tall, so to match a 10-px-tall Japanese glyph use size 12–13), `weight` (400 Regular, 700 Bold, 900 Black), `color`, optional `stroke` + `stroke_w` (outline), `glow` + `glow_r` (soft outer glow), `align` (left/center/right), `dy` (vertical nudge in px), `leading` (line spacing factor, default 1.0). Text wider than its rect is squeezed horizontally automatically; prefer a shorter wording over heavy squeeze.
   - Several blocks for text split around icons: e.g. `[V] を押し続けるとパワーがたまる` keeps the V icon and gets one block to its right.
   - Never draw outside the label's own area: textures are atlases.
4. `python tools/tex.py preview <id> [<id>...]` writes `work/tex/preview/<id>.png` (original on top, result below, 2×). **Read it and check**: same position, similar size and weight, same colours/outline, nothing Japanese left, nothing clipped, icons intact. Fix and re-preview until it looks like it shipped that way.

## Wording
- Taiwanese Traditional Chinese, short UI language: 決定、取消、是、否、返回、開始遊戲、重試、初始化、遊戲說明.
- Names follow `text/glossary.json` (`python tools/tl.py lookup <日文>`): 索尼克、塔爾斯、納克魯斯、艾咪、比谷、Ｅ－１０２「Gamma」、蛋頭博士、巧歐、金環、混沌翡翠; stages 翡翠海岸、風之谷、賭城、冰帽雪山、閃耀樂園、高速公路、紅色山脈、天空甲板、失落世界、最終蛋頭基地、灼熱避難所; areas 車站廣場、神祕遺跡、蛋頭母艦. The monster カオス is 卡歐斯.
- Stage title cards: the big English name stays; only the small Japanese subtitle under it becomes Chinese.
- Mission cards: the two-line Japanese objective becomes a two-line Chinese objective in the same box, same black bold style.
- Tutorial lines: translate naturally, keep each key icon where the sentence needs it.
- Keep it consistent across textures: the same Japanese label gets the same Chinese everywhere.

## Report
When done, run `python tools/tex.py status` and reply briefly: textures translated, kept, anything you could not do well (with ids). Do not paste spec JSON in the reply.
