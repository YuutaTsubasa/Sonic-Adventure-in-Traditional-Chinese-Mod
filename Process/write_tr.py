# -*- coding: utf-8 -*-
import sys

item = sys.argv[1] if len(sys.argv) > 1 else ""

data = {
    "gold":   ["金石像…像是某處的鑰匙"],
    "ice":    [r"冰之石…像是某處的鑰匙，\n或許可以在神祕遺跡使用？"],
    "monkey": [r"自爆開關…如果按下去\n", "就會自爆，上面這樣寫著"],
    "lure":   ["升級魚餌！", "用這個可以釣到大魚了。"],
    "silver": ["銀石像…像是某處的鑰匙"],
    "swon":   ["開關啟動！"],
    "swnoth": ["按下了開關但什麼都沒發生"],
    "float":  ["鑰匙從手中飛走了…。"],
    "diffk":  [r"不合適。\n好像是不同的鑰匙。"],
    "twink":  ["歡迎來到閃爍賽車場！"],
    "wind":   [r"風之石…像是某處的鑰匙，\n得找找相同的圖案才行"],
}

lines = data[item]
with open("tr.txt", "wb") as f:
    for line in lines:
        f.write(line.encode("utf-8") + b"\r\n")

print(f"Written {item} to tr.txt")
