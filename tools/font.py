"""FONTDATA0.BIN (the Japanese font) and the Chinese character map.

FONTDATA0.BIN holds one 0x58-byte record per JIS X 0208 code (94 x 94, row-major
from 0x2121): a 16-byte header (code, then constants) and a 24x24 1-bit glyph,
3 bytes per row, MSB = left pixel.

Text reaches the game as Shift-JIS, so every Chinese character needs a JIS code:
  * a character that exists in cp932 keeps its own code (glyph redrawn in the
    Traditional Chinese shape, so all Chinese text looks alike);
  * any other character (說, 這, 嗎 …) takes a kanji code that no Japanese text in
    the game uses, picked from the end of JIS level 2 backwards.
The assignments live in text/charmap.json and never change between builds.

    python tools/font.py preview <text> [out.png]   draw text with the rebuilt glyphs
"""
import json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CHARMAP = ROOT / "text/charmap.json"
REC, HDR, CELL = 0x58, 0x10, 24
FONT = r"C:/Windows/Fonts/NotoSansTC-VF.ttf"
WEIGHT = 700
SIZE = 21            # px em size inside the 24x24 cell
SS = 4               # supersampling
# Taiwanese style: these sit in the middle of the cell, not bottom-left
CENTRED_PUNCT = "，。、；：！？"


def jis_of(ch):
    """Unicode char -> JIS code (0x2121..0x7E7E) via cp932, or None."""
    try:
        b = ch.encode("cp932")
    except UnicodeEncodeError:
        return None
    if len(b) != 2:
        return None
    s1, s2 = b
    if 0x81 <= s1 <= 0x9F:
        ku = (s1 - 0x81) * 2 + 1
    elif 0xE0 <= s1 <= 0xEF:
        ku = (s1 - 0xC1) * 2 + 1
    else:
        return None
    if s2 >= 0x9F:
        ku += 1; ten = s2 - 0x9E
    else:
        ten = s2 - 0x3F if s2 < 0x7F else s2 - 0x40
    if not (1 <= ku <= 94 and 1 <= ten <= 94):
        return None
    return ((ku + 0x20) << 8) | (ten + 0x20)


def sjis_of(code):
    ku, ten = (code >> 8) - 0x20, (code & 0xFF) - 0x20
    s1 = (ku + 1) // 2 + (0x80 if ku <= 62 else 0xC0)
    s2 = ten + (0x3F if ten <= 63 else 0x40) if ku % 2 else ten + 0x9E
    return bytes([s1, s2])


def char_of(code):
    """The Unicode character cp932 gives for a JIS code (what goes into UTF-8 files)."""
    return sjis_of(code).decode("cp932")


def index(code):
    return ((code >> 8) - 0x21) * 94 + ((code & 0xFF) - 0x21)


def load_map():
    return json.loads(CHARMAP.read_text(encoding="utf-8")) if CHARMAP.exists() else {"extra": {}}


# The game only reads Shift-JIS lead bytes 0x81-0x9F as double-byte characters: a
# character from JIS row 0x5F up (lead 0xE0+) crashes the text drawing (Emerald Coast
# hint 9, 2026-10-09). So every code we use must sit in rows 0x21..0x5E.
MAX_ROW = 0x5E


def usable(code):
    return code is not None and (code >> 8) <= MAX_ROW


def assign(chars, japanese_text):
    """Give every char a JIS code; update and return the persistent map.

    A char keeps its own code when cp932 has it in rows <= MAX_ROW; any other char
    (not in cp932, or a level-2 kanji from row 0x5F up) takes a stand-in code: a kanji
    in rows 0x30..MAX_ROW that no Japanese text and no Chinese char uses as itself.
    japanese_text: all Japanese the game may still show; kanji in it are never reused.
    """
    m = load_map()
    extra = m["extra"]                      # char -> "XXXX" stand-in code
    native = {jis_of(c) for c in japanese_text} | {jis_of(c) for c in chars if usable(jis_of(c))}
    for ch, v in list(extra.items()):
        code = int(v, 16)
        if code in native or not usable(code) or (usable(jis_of(ch)) and ch in chars):
            print(f"charmap: {ch} loses {v}")
            del extra[ch]
    used = set(native) | {int(v, 16) for v in extra.values()}
    # level 2 rows first (rare kanji), then level 1 from the end
    pool = [((ku << 8) | ten) for ku in range(MAX_ROW, 0x2F, -1) for ten in range(0x7E, 0x20, -1)
            if char_of_safe((ku << 8) | ten)]
    pool = [c for c in pool if c not in used]
    for ch in sorted(chars):
        if not usable(jis_of(ch)) and ch not in extra:
            if not pool:
                raise SystemExit("no free JIS codes left")
            extra[ch] = f"{pool.pop(0):04X}"
    m["free_codes_left"] = len(pool)
    CHARMAP.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return m


def char_of_safe(code):
    try:
        c = char_of(code)
    except UnicodeDecodeError:
        return False
    return re.match(r"[一-鿿]", c) is not None


def code_map(m):
    """char -> JIS code for every Chinese character (own or extra)."""
    out = {ch: int(v, 16) for ch, v in m["extra"].items()}
    return out


def encode_char(ch, m):
    """Unicode char -> the character to write into a UTF-8 file for the game."""
    if ch in m["extra"]:
        return char_of(int(m["extra"][ch], 16))
    return ch


_font = None


def glyph(ch):
    """24x24 bitmap ('1' mode) of a character in the game font's style."""
    global _font
    if _font is None:
        _font = ImageFont.truetype(FONT, SIZE * SS)
        try:
            _font.set_variation_by_axes([WEIGHT])
        except Exception:
            pass
    big = Image.new("L", (CELL * SS, CELL * SS), 0)
    d = ImageDraw.Draw(big)
    if ch in CENTRED_PUNCT:
        bb = d.textbbox((0, 0), ch, font=_font)
        x = (CELL * SS - (bb[2] - bb[0])) // 2 - bb[0] - SS
        y = (CELL * SS - (bb[3] - bb[1])) // 2 - bb[1]
    else:
        # the Japanese glyphs fill x 1..20, y 2..21: same box, by the font's own metrics
        asc, desc = _font.getmetrics()
        x = 1 * SS + (20 * SS - _font.getlength(ch)) / 2 - SS * 0.5
        y = 2 * SS + (20 * SS - (asc + desc)) / 2 + SS * 0.5
    d.text((x, y), ch, fill=255, font=_font)
    small = big.resize((CELL, CELL), Image.LANCZOS)
    return small.point(lambda v: 255 if v >= 110 else 0).convert("1")


def glyph_bytes(img):
    px = img.load()
    out = bytearray(72)
    for y in range(CELL):
        for x in range(CELL):
            if px[x, y]:
                out[y * 3 + x // 8] |= 0x80 >> (x % 8)
    return bytes(out)


def glyph_from(raw, code):
    rec = raw[index(code) * REC + HDR: index(code) * REC + HDR + 72]
    img = Image.new("1", (CELL, CELL), 0)
    for y in range(CELL):
        row = int.from_bytes(rec[y * 3:y * 3 + 3], "big")
        for x in range(CELL):
            if row >> (23 - x) & 1:
                img.putpixel((x, y), 1)
    return img


def patch(fontdata, chars, m):
    """Return FONTDATA0 with a Chinese glyph for every char in `chars`."""
    raw = bytearray(fontdata)
    assert len(raw) == 94 * 94 * REC
    extra = code_map(m)
    for ch in sorted(chars):
        code = extra.get(ch) or jis_of(ch)
        if code is None:
            raise ValueError(f"no code for {ch!r}")
        o = index(code) * REC + HDR
        raw[o:o + 72] = glyph_bytes(glyph(ch))
    return bytes(raw)


def preview(text, raw, m, out, scale=3):
    lines = text.split("\n")
    w = max(len(l) for l in lines) * CELL
    img = Image.new("RGB", (w, len(lines) * (CELL + 4)), (24, 24, 64))
    extra = code_map(m)
    for li, line in enumerate(lines):
        for i, ch in enumerate(line):
            code = extra.get(ch) or jis_of(ch)
            if code is None:
                continue
            g = glyph_from(raw, code)
            img.paste((255, 255, 255), (i * CELL, li * (CELL + 4)), g)
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "preview":
        src = ROOT / "work/build/FONTDATA0.BIN"
        if not src.exists():
            src = ROOT / "source/system/FONTDATA0.BIN"
        preview(sys.argv[2].replace("\\n", "\n"), src.read_bytes(), load_map(),
                sys.argv[3] if len(sys.argv) > 3 else str(ROOT / "work/preview.png"))
