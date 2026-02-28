# CSV翻譯工具使用說明

## 工具文件
- `csv_translator.py` - 主要翻譯工具
- `set-string.bat` - Windows批處理腳本 (簡化使用)
- `tr.txt` - 翻譯內容文件

## 基本使用方法

### 1. 列出未翻譯的項目
```bash
# Python方式
python csv_translator.py list-untranslated 5

# 批處理方式
set-string.bat list 5
```

### 2. 設置翻譯
```bash
# 準備翻譯內容 (放在tr.txt中)
# 然後執行:
python csv_translator.py set-string "SATranslation/Misc/Cutscene Text/Knuckles/10 Before Sonic Fight/Japanese.txt" tr.txt

# 或使用批處理 (預設使用tr.txt)
set-string.bat "SATranslation/Misc/Cutscene Text/Knuckles/10 Before Sonic Fight/Japanese.txt"
```

### 3. 查看現有翻譯
```bash
# Python方式
python csv_translator.py get-string "SATranslation/Misc/Cutscene Text/Knuckles/10 Before Sonic Fight/Japanese.txt"

# 批處理方式
set-string.bat get "SATranslation/Misc/Cutscene Text/Knuckles/10 Before Sonic Fight/Japanese.txt"
```

## 工作流程

1. **查看需要翻譯的項目**
   ```
   python csv_translator.py list-untranslated 5
   ```

2. **準備翻譯內容**
   - 將翻譯內容寫入 `tr.txt` 文件
   - **重要**: 區分 `\n` 和實際換行：
     - **實際換行** = 不同句子/對話之間的分隔
     - **`\n`** = 同一句話內部的換行標記
   - 範例：
     ```
     第一句對話內容
     第二句對話內容
     這是包含\n內部換行的句子
     ```

3. **設置翻譯**
   ```
   python csv_translator.py set-string "file_path" tr.txt
   ```

4. **驗證翻譯**
   ```
   python csv_translator.py get-string "file_path"
   ```

## 優點
- ✅ 避免字符編碼問題
- ✅ 精確定位文件路徑
- ✅ 避免多重匹配問題  
- ✅ 保持原有格式
- ✅ 支援批量處理

## 注意事項
- 確保 Python 已安裝
- 翻譯文件使用 UTF-8 編碼
- 保持 \n 和實際換行的區別
- 文件路徑需要完全匹配