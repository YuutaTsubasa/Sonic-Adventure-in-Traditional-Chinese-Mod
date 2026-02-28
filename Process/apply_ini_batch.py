# -*- coding: utf-8 -*-
# 批次套用 INI 翻譯：從 CSV 取出精確 JP bytes → src.txt，TW → tr.txt，呼叫 set-by-content
import csv, subprocess, sys

CSV_FILE = 'japanese_ini_translation_rows.csv'

# 讀取所有唯一 JP 字串（保留順序）
with open(CSV_FILE, 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

seen = {}
for r in rows:
    jp = r.get('content_jp', '')
    if jp and jp not in seen:
        seen[jp] = r.get('content_en', '')

unique_jp = list(seen.keys())

# 翻譯對照（key = 0-based index，value = TW 翻譯原始字串）
# \x07 = bell char，\\n = 字面 \n（兩個字元），實際換行 = 真正換行
translations = {
    440: '\t「監控室」',
    441: '\t使用監控器時\\n請將４個方塊放置到指定位置。',
    442: '\t「貨櫃方塊」',
    443: '\t要降下上方的方塊時，',
    444: '\t以「疊疊樂」的方式進行。',
    445: '\t「高速移動貨物」',
    446: '\t緊急時請按下頭號車廂的，\\n緊急停止開關。',
    447: '\t在台子上如果不保持平衡\\n就會掉落喔。',
}

ok = 0
fail = 0
for idx, tw in sorted(translations.items()):
    jp = unique_jp[idx]
    # 寫入精確 JP 原文（無尾隨換行）
    with open('src.txt', 'wb') as f:
        f.write(jp.encode('utf-8'))
    # 寫入 TW 翻譯（處理 \\n → 字面 \n）
    tw_bytes = tw.encode('utf-8')
    with open('tr.txt', 'wb') as f:
        f.write(tw_bytes)
    result = subprocess.run(
        ['python', 'csv_translator.py', '--csv', CSV_FILE,
         'set-by-content', 'src.txt', 'tr.txt'],
        capture_output=True
    )
    if result.returncode == 0:
        print(f'  OK [{idx}]')
        ok += 1
    else:
        print(f'FAIL [{idx}]: {result.stderr.decode("utf-8", errors="replace").strip()}')
        fail += 1

print(f'\n完成：{ok} OK，{fail} 失敗')
