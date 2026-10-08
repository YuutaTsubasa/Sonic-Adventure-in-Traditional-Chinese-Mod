# 《索尼克大冒險 DX》繁體中文化 MOD

Sonic Adventure DX（PC，2004 版／Steam 版轉換後）的台灣繁體中文翻譯，給 SA Mod Manager 使用。

v1.0 是整個重新翻譯的版本：

- **文字全部重翻**：劇情字幕、角色回顧、提示、NPC 對話、巧歐花園／幼稚園／黑市、任務、選單訊息，共 3,195 句。相同的日文句子在遊戲裡任何地方都只有一個譯文，不會再出現同一句話不同翻譯。
- **名稱採用 SEGA 官方繁中譯名**：索尼克、塔爾斯、納克魯斯、艾咪、比谷、蛋頭博士、巧歐、王者翡翠、混沌翡翠、金環……；怪物カオス為「卡歐斯」，E-100 系列機器人名稱保留英文（Gamma、Beta…）。
- **圖片也翻譯了**：選單、操作說明、任務卡、關卡標題卡、成績畫面、巧歐賽跑與選單、冒險地區地圖、Game Gear 遊戲合集等 500 多張貼圖。
- **片頭影片與標題 Logo**：換成中文 Logo「索尼克大冒險DX」。
- **字型**：用 Noto Sans TC 重繪遊戲字型裡的 1,691 個中文字，標點採台灣置中寫法。

## 安裝（玩家）

1. 先用 [SADX Mod Installer](https://gamebanana.com/tools/6417) 把 Steam 版轉成 2004 版並裝好 SA Mod Manager。
2. 把 `SADX_zh-TW` 資料夾放進遊戲的 `mods` 資料夾。
3. 在 SA Mod Manager 啟用「Sonic Adventure DX 繁體中文化」，並停用舊版的「Traditional Chinese Version」。
4. 遊戲的**文字語言設為日本語**（語音可任選）。
5. 若同時使用 Dreamcast Conversion，請把本 MOD 排在它上面（優先）。

## 從原始碼建置

本 repo 不含任何遊戲檔案。建置時從你自己的遊戲讀取原始資料：

需要：Windows、Python 3.12（`pip install pillow numpy opencv-python`）、ffmpeg、[SA Tools](https://github.com/X-Hax/sa_tools)、Noto Sans TC（`NotoSansTC-VF.ttf`）。

```bash
set PYTHONUTF8=1
python tools/prepare.py --game "<遊戲資料夾>" --satools "<SA Tools 資料夾>"   # 讀取原始文字、BIN、貼圖、影片到 source/
python tools/extract.py           # 產生翻譯單位 text/ja/
python tools/tex.py extract       # 解出貼圖到 work/tex/
python tools/movie.py             # 片頭影片換 Logo
python tools/build.py [--install] # 建置到 out/SADX_zh-TW/
python tools/verify.py            # 從建置結果讀回所有文字並檢查
```

## 結構

| 路徑 | 內容 |
| --- | --- |
| `text/zh/*.json` | 譯文（以翻譯單位 id 為鍵） |
| `text/glossary.json` | 專有名詞表 |
| `text/charmap.json` | 中文字在遊戲字型中的編碼（固定不變） |
| `text/tex/*.json`、`text/tex/composite/*.json` | 每張貼圖的翻譯規格（擦除範圍、文字、樣式） |
| `tools/` | 擷取、翻譯流程（`tl.py`）、字型、貼圖、影片、建置與驗證工具 |
| `.claude/skills/` | 翻譯與貼圖作業流程說明 |

翻譯記憶 `text/tm.json` 含日文原文，不放在 repo；需要時用 `python tools/tl.py rebuild-tm` 從 `text/ja` 與 `text/zh` 重建。

## 技術筆記

- 中文字寫進日文字型 `FONTDATA0.BIN`（24×24 單色）。cp932 有的字沿用自己的編碼並重繪成繁中字形；其他字借用遊戲裡沒用到的漢字編碼。遊戲只接受 Shift-JIS 首位元組 0x81–0x9F，所以所有編碼都限制在 JIS 第 0x21–0x5E 區（用到 0xE0 以上會當機）。
- 文字經 Mod Loader 的 `EXEData`（`sonic_data.ini`）載入；`system/*_J.BIN` 訊息檔重新排列字串並修正指標，大小不超過遊戲的緩衝區。
- 貼圖用 Mod Loader 的 `replacetex/`（只替換有改的貼圖）；單張 PVR 以原格式重新編碼。
- PC 版的標題畫面與主選單背景不論語言都顯示英文 Logo，所以英文版 Logo 也一併換掉。

## 版權

《Sonic Adventure DX》及其文字、圖片、影片的權利屬於 SEGA。本 MOD 為非官方的粉絲作品，與 SEGA 無關。

製作：Yuuta Tsubasa
