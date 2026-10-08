---
name: sadx-translate
description: Translate Sonic Adventure DX (PC) game text from Japanese to Taiwanese Traditional Chinese (zh-TW) batch by batch with the shared glossary and translation memory. Use when asked to translate or continue translating a SADX text file, e.g. "/sadx-translate cut_sonic" or "/sadx-translate mes_amy 30".
---

# 《音速小子大冒險 DX》繁中翻譯流程

Arguments: `<FILE>... [N]`. FILE is one or more names in `text/ja/` (without `.json`); N is the batch size (default 40). With no FILE, run `python tools/tl.py status` and pick the file with the most remaining strings.

All commands run from the repo root (`C:\Users\User\Repo\SonicTranslations\sadx-zhtw`) with `PYTHONUTF8=1` set.

## Loop (repeat for each FILE until it reports `remaining: 0`)

1. **取下一批**：`python tools/tl.py next <FILE> <N>`
   - Strings already in the TM, and strings with no Japanese in them, are filled automatically.
   - The output lists the `glossary` terms and `similar_tm` entries found in this batch. **Use them.** A glossary term must be translated exactly as listed; similar sentences are worded consistently with their TM translations.
2. **翻譯**: translate every string in `strings` into natural Taiwanese Traditional Chinese.
3. **寫入批次檔** `work/tl_batch_<FILE>.json` (UTF-8):
   ```json
   {"strings": [{"id": "<id from next>", "zh": "譯文\n第二行"}],
    "terms": {"新しい名前": {"zh": "新譯名", "note": "角色/地名/道具/用語"}}}
   ```
   Put in `terms` every new proper noun or recurring game term you decide on (shop names, items, minigames, NPC names). No ordinary words.
4. **提交**: `python tools/tl.py commit <FILE> work/tl_batch_<FILE>.json`
   - Fix every `REJECTED` line and commit those ids again.
   - On `TERM CONFLICT` the glossary keeps its translation: change your strings to use it.
5. Continue with step 1.

## Format rules (checked on every commit)

- **Line breaks** are real `\n` in the JSON string, never the two characters backslash-n. A translation may have **no more lines** than `lines`, and no line wider than `max_units` (full-width character = 2 units, ASCII = 1). Chinese is usually shorter: rebalance lines naturally, and use fewer lines when the sentence fits. Never add a line break to a single-line string.
- `"wrap": true` strings (Chao Garden / Chao Kindergarten / Black Market boxes) wrap by themselves: write them as one paragraph without breaks unless the Japanese has one.
- Keep tokens such as `{v00}` `{v01}` exactly (inserted price or item name).
- **Punctuation:** full-width only: ，。！？：；「」『』…… ～ ── ・. No half-width `, ! ?`. Japanese text often uses an ASCII `,` as a comma: write `，`. Keep the full-width spaces the Japanese uses at the start of recap paragraphs (`　`); drop the half-width spaces Japanese puts between phrases (ソニックは 走った → 索尼克跑了起來).
- **Characters:** Taiwanese Traditional Chinese only (Big5). No Simplified or Japanese forms (戦→戰, 気→氣, 発→發, 説→說, 黒→黑), no kana. MOE standard forms: 祕, 裡, 著, 為, 台.
- Full-width Latin letters and digits stay as in the Japanese (Ｅ－１０２, ＧＥＴ, １００枚 → １００個). `GBA`, `GameCube` and button names stay in Latin letters.

## Names

The glossary (`text/glossary.json`) is law. The main ones:
索尼克、塔爾斯、納克魯斯、艾咪、比谷、蛋頭博士、蒂卡爾、帕查卡馬克、青蛙君（カエルくん）、巧歐（チャオ）、金屬索尼克;
怪物 **カオス = 卡歐斯**, but カオスエメラルド = **混沌翡翠**, マスターエメラルド = **王者翡翠**, リング = **金環**;
E-100 系列名字保留英文：Ｅ－１０２「Gamma」、E-101「Beta」、Delta、Epsilon、Zeta、ZERO;
車站廣場、神祕遺跡、蛋頭母艦、翡翠海岸、風之谷、賭城、冰帽雪山、閃耀樂園、高速公路、紅色山脈、天空甲板、失落世界、最終蛋頭基地、灼熱避難所.
Unsure of a name? `python tools/tl.py lookup <日文>`; official Sonic names: `python "%USERPROFILE%/.claude/skills/game-translation-mod/scripts/sonic_terms.py" find <詞>`.

## Voices

- **Sonic** (オレ): 輕快、自信、帶點痞 —「別擔心，交給我吧！」「真是的，太慢了啦！」
- **Tails** (ボク): 有禮貌的少年，稱索尼克為「索尼克」—「我、我也要去！」
- **Knuckles** (オレ): 粗獷直率、易怒 —「可惡！」「少囉唆！」
- **Amy** (アタシ): 活潑的女孩，迷戀索尼克 —「索尼克～等等我嘛！」
- **Big** (オラ): 憨厚緩慢，句尾拉長 —「青蛙君～你在哪裡～？」
- **Gamma** (ワタシ, all katakana): 機器人語氣，短句、生硬、不用語氣詞 —「確認。目標：蛋頭博士。」 Katakana in Gamma's lines does not mean anything special in Chinese.
- **Eggman** (ワシ): 「我」(not 老夫/本大爺)，自大、笑聲「哇哈哈哈！」「可惡的索尼克！」
- **Tikal**: 溫柔、古老部族的少女；**Pachacamac**: 威嚴的族長；族人說話較古風。
- **Chao Kindergarten teacher / Black Market**: 親切的說明口吻。
- NPCs in Station Square: 自然的口語，各有個性。

Recaps (`recap_*`) are the character's first-person story summary: keep the paragraph layout (leading `　`, blank lines) and the 「我是索尼克！刺蝟索尼克！」 style opening.

## Notes
- Files: `text/ja/*.json` (source, never edit), `text/zh/*.json` (output), `text/glossary.json`, `text/tm.json`.
- Identical Japanese anywhere in the game is one unit, translated once.
- Several translators may run in parallel on different FILEs; `tl.py` locks the shared glossary and TM.
- Do not print long runs of source text in chat. Report progress with `python tools/tl.py status`.
