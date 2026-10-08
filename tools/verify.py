"""Read every translated string back out of the built mod and compare with text/zh.

    python tools/verify.py

Split files are parsed the way the Mod Loader reads them (line / key=value, "\\n"),
BINs through their pointers (sysbin.read_back); stand-in kanji are mapped back through
text/charmap.json. Also checks that every character the game will draw exists in
the rebuilt FONTDATA0 (a non-empty glyph) and that sonic_data.ini names every file.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build, font, sysbin

ROOT = build.ROOT
OUT = build.OUT


def main():
    m = font.load_map()
    back = {font.char_of(int(v, 16)): ch for ch, v in m["extra"].items()}
    fontdata = (OUT / "system/FONTDATA0.BIN").read_bytes()
    def decode(s):
        return "".join(back.get(c, c) for c in s)
    def expect(text, lp):
        return build.with_prefixes(text, lp).replace("·", "・")
    bad, n, drawn = [], 0, set()
    cache, bins = {}, {}
    for u, text, done in build.final_texts():
        if not done:
            continue
        for loc in u["locs"]:
            n += 1
            want = expect(text, loc["lp"])
            if loc["src"] == "split":
                p = OUT / loc["path"]
                lines = cache.setdefault(p, p.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"))
                if "page" in loc:     # pages may have shrunk: find them by section
                    i = lines.index(f"[{loc['page']}]") + 1
                    vals = []
                    while i < len(lines) and not lines[i].startswith("["):
                        k, _, v = lines[i].partition("=")
                        if k.isdigit():
                            vals.append(v)
                        i += 1
                    got = "\n".join(vals)
                elif "key" in loc:
                    got = lines[loc["line"]].split("=", 1)[1].replace("\\n", "\n")
                else:
                    got = lines[loc["line"]].replace("\\n", "\n")
                raw = got
            else:
                f = loc["file"]
                if f not in bins:
                    bins[f] = sysbin.read_back((build.SYSTEM / f).read_bytes(), (OUT / "system" / f).read_bytes(), f)
                raw = bins[f][loc["key"]].decode("cp932")
                raw = re.sub(r"\x05(\d\d)", r"{v\1}", raw)
            drawn.update(c for c in raw if ord(c) > 0x7F)
            if decode(raw) != want:
                bad.append((u["id"], want[:30], decode(raw)[:30]))
    # the game reads only lead bytes 0x81-0x9F as double-byte (E0+ crashes it)
    high = sorted(c for c in drawn if len(c.encode("cp932", "replace")) == 2 and c.encode("cp932")[0] >= 0xE0)
    if high:
        print("LEAD BYTE >= 0xE0 (crashes the game):", "".join(high))
        bad.append(("lead", "", ""))
    # glyph check: every drawn full-width character has a non-empty glyph
    empty = []
    for c in sorted(drawn):
        code = font.jis_of(c)
        if code is None:
            empty.append(c); continue
        o = font.index(code) * font.REC + font.HDR
        if not any(fontdata[o:o + 72]) and c != "　":
            empty.append(c)
    # data ini covers every rewritten split file
    ini = (OUT / "sonic_data.ini").read_text(encoding="utf-8")
    names = [build.winpath(f) for f in re.findall(r"^filename=(.*)$", ini, re.M)]
    orphan = [p for p in {l["path"] for u, t, d in build.final_texts() if d for l in u["locs"] if l["src"] == "split"}
              if not any(p == f or p.startswith(f.rstrip("/") + "/") for f in names)]
    print(f"locations {n}, mismatches {len(bad)}, characters drawn {len(drawn)}, missing glyphs {len(empty)}, "
          f"split files not in sonic_data.ini {len(orphan)}")
    for b in bad[:20]:
        print("MISMATCH", b)
    if empty:
        print("NO GLYPH", "".join(empty))
    for o in orphan[:10]:
        print("NOT LOADED", o)
    return 1 if bad or empty or orphan else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
