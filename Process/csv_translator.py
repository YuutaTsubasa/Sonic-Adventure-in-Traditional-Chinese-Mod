#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV Translation Tool
使用方法: python csv_translator.py set-string "file_path" translation_file.txt
         python csv_translator.py --csv FILE set-by-content source.txt translation_file.txt
"""

import csv
import sys
import os
from typing import List, Dict, Optional

class CSVTranslator:
    def __init__(self, csv_file: str = "japanese_txt_translation_files_full.csv"):
        self.csv_file = csv_file
        self.encoding = 'utf-8-sig'  # 處理BOM
        
    def read_csv(self) -> List[Dict[str, str]]:
        """讀取CSV文件並返回行列表"""
        rows = []
        try:
            with open(self.csv_file, 'r', encoding=self.encoding, newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    rows.append(row)
        except UnicodeDecodeError:
            # 如果UTF-8失敗，嘗試其他編碼
            with open(self.csv_file, 'r', encoding='utf-8', newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    rows.append(row)
        return rows
    
    def write_csv(self, rows: List[Dict[str, str]]):
        """寫入CSV文件"""
        if not rows:
            return
            
        fieldnames = rows[0].keys()
        
        with open(self.csv_file, 'w', encoding=self.encoding, newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    
    def find_row_by_file_path(self, rows: List[Dict[str, str]], file_path: str) -> Optional[int]:
        """根據file_path找到對應的行索引"""
        for i, row in enumerate(rows):
            if row.get('file_path', '').strip() == file_path.strip():
                return i
        return None
    
    def set_translation(self, file_path: str, translation_file: str) -> bool:
        """設置翻譯"""
        # 讀取翻譯內容
        if not os.path.exists(translation_file):
            print(f"錯誤: 翻譯文件 '{translation_file}' 不存在")
            return False
            
        with open(translation_file, 'r', encoding='utf-8') as f:
            translation_content = f.read()
            
        # 允許只有換行符的內容（空內容項目）
        if not translation_content.strip():
            if translation_content != '\n':  # 如果不是單純的換行符
                print(f"錯誤: 翻譯文件 '{translation_file}' 為空")
                return False
        
        # 讀取CSV
        rows = self.read_csv()
        
        # 找到對應行
        row_index = self.find_row_by_file_path(rows, file_path)
        
        if row_index is None:
            print(f"錯誤: 找不到文件路徑 '{file_path}'")
            return False
            
        # 更新翻譯
        rows[row_index]['translated_content_zhtw'] = translation_content
        
        # 寫回CSV
        self.write_csv(rows)
        
        print(f"成功: 已更新 '{file_path}' 的翻譯")
        return True
    
    def get_translation(self, file_path: str) -> Optional[str]:
        """獲取翻譯"""
        rows = self.read_csv()
        row_index = self.find_row_by_file_path(rows, file_path)
        
        if row_index is None:
            return None
            
        return rows[row_index].get('translated_content_zhtw', '')
    
    def set_by_content(self, source_file: str, translation_file: str) -> bool:
        """將翻譯套用到所有 content_jp 相符的列"""
        if not os.path.exists(source_file):
            print(f"錯誤: 原文文件 '{source_file}' 不存在")
            return False
        if not os.path.exists(translation_file):
            print(f"錯誤: 翻譯文件 '{translation_file}' 不存在")
            return False

        with open(source_file, 'r', encoding='utf-8', newline='') as f:
            source_content = f.read()
        with open(translation_file, 'r', encoding='utf-8') as f:
            translation_content = f.read()

        if not translation_content.strip():
            print(f"錯誤: 翻譯文件 '{translation_file}' 為空")
            return False

        rows = self.read_csv()
        count = 0
        for row in rows:
            if row.get('content_jp', '') == source_content:
                row['translated_content_zhtw'] = translation_content
                count += 1

        if count == 0:
            print(f"錯誤: 找不到符合的 content_jp")
            return False

        self.write_csv(rows)
        print(f"成功: 已更新 {count} 列")
        return True

    def list_untranslated(self, limit: int = 10):
        """列出未翻譯的項目"""
        rows = self.read_csv()
        untranslated = []
        
        for row in rows:
            file_path = row.get('file_path', '')
            translation = row.get('translated_content_zhtw', '').strip()
            source = row.get('content_jp', '').strip()

            if not translation and source and file_path:
                untranslated.append(file_path)
                
        print(f"找到 {len(untranslated)} 個未翻譯項目")
        for i, path in enumerate(untranslated[:limit]):
            print(f"{i+1}. {path}")
            
        if len(untranslated) > limit:
            print(f"... 還有 {len(untranslated) - limit} 個項目")

def main():
    args = sys.argv[1:]

    # 解析 --csv 參數
    csv_file = "japanese_txt_translation_files_full.csv"
    if args and args[0] == "--csv":
        if len(args) < 2:
            print("錯誤: --csv 需要指定文件名")
            sys.exit(1)
        csv_file = args[1]
        args = args[2:]

    if not args:
        print("使用方法:")
        print("  python csv_translator.py [--csv FILE] set-string \"file_path\" translation_file.txt")
        print("  python csv_translator.py [--csv FILE] set-by-content source.txt translation_file.txt")
        print("  python csv_translator.py [--csv FILE] get-string \"file_path\"")
        print("  python csv_translator.py [--csv FILE] list-untranslated [數量]")
        sys.exit(1)

    translator = CSVTranslator(csv_file)
    command = args[0]
    
    if command == "set-string":
        if len(args) != 3:
            print("錯誤: set-string 需要文件路徑和翻譯文件")
            sys.exit(1)

        file_path = args[1]
        translation_file = args[2]

        success = translator.set_translation(file_path, translation_file)
        sys.exit(0 if success else 1)

    elif command == "set-by-content":
        if len(args) != 3:
            print("錯誤: set-by-content 需要原文文件和翻譯文件")
            sys.exit(1)

        source_file = args[1]
        translation_file = args[2]

        success = translator.set_by_content(source_file, translation_file)
        sys.exit(0 if success else 1)

    elif command == "get-string":
        if len(args) != 2:
            print("錯誤: get-string 需要文件路徑")
            sys.exit(1)

        file_path = args[1]
        translation = translator.get_translation(file_path)

        if translation is not None:
            print(translation)
        else:
            print(f"找不到文件路徑: {file_path}")
            sys.exit(1)

    elif command == "list-untranslated":
        limit = 10
        if len(args) > 1:
            try:
                limit = int(args[1])
            except ValueError:
                print("錯誤: 數量必須是整數")
                sys.exit(1)

        translator.list_untranslated(limit)

    else:
        print(f"錯誤: 未知命令 '{command}'")
        sys.exit(1)

if __name__ == "__main__":
    main()