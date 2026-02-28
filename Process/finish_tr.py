# -*- coding: utf-8 -*-
import csv

with open('japanese_txt_translation_files_full.csv', 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    fieldnames = reader.fieldnames

translations = {
    'Gold Statue It Looks Like a Key':
        '金石像…像是某處的鑰匙\r\n',
    'Ice Stone It Looks Like a Key':
        '冰之石…像是某處的鑰匙，\\\n或許可以在神祕遺跡使用？\r\n',
    'Ice Stone It Looks Like a Key 2':
        '冰之石…像是某處的鑰匙，\\\n或許可以在神祕遺跡使用？\r\n',
    'It says Monkey Destruction Switch':
        '自爆開關…如果按下去\\\n\r\n就會自爆，上面這樣寫著\r\n',
    'Lure Powerup':
        '升級魚餌！\r\n用這個可以釣到大魚了。\r\n',
    'Silver Statue It Looks Like a Key':
        '銀石像…像是某處的鑰匙\r\n',
    'Switch On!':
        '開關啟動！\r\n',
    'Switch Pressed But Nothing Happened':
        '按下了開關但什麼都沒發生\r\n',
    'Switch Pressed But Nothing Happened 2':
        '按下了開關但什麼都沒發生\r\n',
    'The Key is Floating':
        '鑰匙從手中飛走了…。\r\n',
    'This Must Be a Different Key':
        '不合適。\\\n好像是不同的鑰匙。\r\n',
    'Welcome to Twinkle Circuit':
        '歡迎來到閃爍賽車場！\r\n',
    'Wind Stone It Looks Like a Key':
        '風之石…像是某處的鑰匙，\\\n得找找相同的圖案才行\r\n',
}

count = 0
for row in rows:
    parts = row['file_path'].split('/')
    key = parts[-2] if len(parts) >= 2 else ''
    if key in translations:
        row['translated_content_zhtw'] = translations[key]
        print('OK:', key)
        count += 1

clean_rows = [{k: v for k, v in row.items() if k is not None} for row in rows]
with open('japanese_txt_translation_files_full.csv', 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(clean_rows)

print(f'Total updated: {count}')
