"""Build the SA Mod Manager mod into out/<MODDIR>/.

    python tools/build.py [--install]     --install also copies it into the game's mods folder

For every unit: text/zh, else the TM, else the original Japanese.
  * split text files (Misc/, hintdata/, mission/, summary/) are rewritten line by line,
    and sonic_data.ini lists every item that changed (EXEData);
  * the *_J.BIN message files are rebuilt with tools/sysbin.py;
  * FONTDATA0.BIN gets a glyph for every Chinese character (tools/font.py);
  * textures and the movie come from tools/tex.py and tools/movie.py when present.
Chinese characters outside cp932 are written as their stand-in kanji from text/charmap.json.
"""
import argparse, json, re, shutil, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import font, sysbin

ROOT = Path(__file__).resolve().parents[1]
SPLIT, SYSTEM = ROOT / "source/split", ROOT / "source/system"
MODDIR = "SADX_zh-TW"
OUT = ROOT / "out" / MODDIR
GAME = Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sonic Adventure DX")
VERSION = "1.0.1"
CJK = re.compile(r"[一-鿿]")


def load(p, d):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else d


def final_texts():
    """Yield (unit, text-to-use, translated?) for every unit."""
    tm = load(ROOT / "text/tm.json", {})
    for f in sorted((ROOT / "text/ja").glob("*.json")):
        zh = load(ROOT / "text/zh" / f.name, {})
        for u in json.loads(f.read_text(encoding="utf-8")):
            t = zh.get(u["id"], tm.get(u["ja"]))
            yield u, (t if t is not None else u["ja"]), t is not None


def with_prefixes(text, lp):
    lines = text.split("\n")
    return "\n".join((lp[i] if i < len(lp) else "") + l for i, l in enumerate(lines))


def to_game(text, m):
    """Unicode text -> what the game's cp932 text must contain (still Unicode)."""
    text = text.replace("·", "・")
    return "".join(font.encode_char(c, m) for c in text)


def japanese_still_shown():
    """Every Japanese text the game may still draw: kanji in it keep their glyph."""
    s = []
    for f in SPLIT.rglob("*"):
        if f.is_file() and (f.name.startswith("Japanese") or f.name.endswith("_j.dat.ini")):
            s.append(f.read_text(encoding="utf-8"))
    for f in SYSTEM.glob("*_J.BIN"):
        if sysbin.kind_of(f.name)[0]:
            s.extend(r.raw.decode("cp932", "replace") for r in sysbin.parse(f.read_bytes(), f.name))
    exe = ROOT / "work/exe_sjis.json"
    if exe.exists():
        s.extend(t for _, t in json.loads(exe.read_text(encoding="utf-8")))
    return "".join(s)


def write_split(per_file, m, out):
    """Rewrite each Japanese split file; return the set of item folders/files changed."""
    changed = set()
    for rel, edits in sorted(per_file.items()):
        src = SPLIT / rel
        text = src.read_text(encoding="utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(nl)
        pages = []
        for loc, value in edits:
            v = to_game(with_prefixes(value, loc["lp"]), m)
            if "page" in loc:
                pages.append((loc, v)); continue
            i = loc["line"]
            if "key" in loc:
                k, _, old = lines[i].partition("=")
                assert k == loc["key"], (rel, i)
                lines[i] = f"{k}={v.replace(chr(10), chr(92) + 'n')}"
            else:
                lines[i] = v.replace("\n", "\\n")
        # mission tutorial pages: the loader writes NumLines strings into the game's own
        # line array but never the game's line count, so keep NumLines and pad short
        # pages with empty lines (otherwise the last Japanese line would still show)
        for loc, v in sorted(pages, key=lambda p: -p[0]["line"]):
            i, n = loc["line"], loc["n"]
            new = v.split("\n")
            assert len(new) <= n, (rel, loc)
            new += [""] * (n - len(new))
            lines[i:i + n] = [f"{j}={t}" for j, t in enumerate(new)]
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(nl.join(lines), encoding="utf-8")
        changed.add(rel)
    return changed


def winpath(p):
    """Windows drops trailing dots and spaces of path parts ("22 Here's the Long Hammer.")."""
    return "/".join(part.rstrip(". ") or part for part in p.split("/"))


def write_data_ini(changed, out):
    """sonic_data.ini: every split item whose Japanese file we rewrote, and its other languages."""
    sections = []
    for ini in sorted(SPLIT.glob("*_data.ini")):
        cur = None
        for line in ini.read_text(encoding="utf-8").splitlines():
            if line.startswith("["):
                cur = [line]; sections.append(cur)
            elif cur is not None and line.strip() and not line.startswith("md5="):
                cur.append(line)
    keep = []
    for sec in sections:
        fn = next((l.split("=", 1)[1] for l in sec if l.startswith("filename=")), None)
        if fn is None:
            continue
        fnn = winpath(fn)
        hit = [c for c in changed if c == fnn or c.startswith(fnn.rstrip("/") + "/")]
        if not hit:
            continue
        keep.append(sec)
        # copy the item's other files (other languages) so the loader finds a full set
        p = SPLIT / fnn
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        for f in files:
            d = out / f.relative_to(SPLIT)
            if not d.exists():
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, d)
    for sec in keep:
        fit_string_array(sec, out)
    (out / "sonic_data.ini").write_text("\n\n".join("\n".join(s) for s in keep) + "\n", encoding="utf-8")
    return len(keep)


def loader_entries(text):
    """How many strings the Mod Loader reads from a text file: one per getline() while
    the stream is good, so a final newline adds an empty (NULL) entry."""
    return len(text.split("\n"))


def fit_string_array(sec, out):
    """A stringarray item is copied over the array with one pointer per line read and no
    bound. A trailing newline made 'Japanese Level List' write a 40th pointer over the
    table after it (VS Knuckles became Sonic, 2026-10-11). Trim it to exactly `length`."""
    kv = dict(l.split("=", 1) for l in sec[1:] if "=" in l)
    if kv.get("type") != "stringarray":
        return
    p = out / winpath(kv["filename"])
    if not p.exists():
        return
    with open(p, encoding="utf-8", newline="") as f:   # keep the CRLF line ends
        text = f.read()
    n = int(kv["length"])
    while loader_entries(text) > n and text.endswith(("\r\n", "\n")):
        text = text[:-2] if text.endswith("\r\n") else text[:-1]
    if loader_entries(text) != n:
        raise SystemExit(f"{kv['filename']}: loader would read {loader_entries(text)} entries, array holds {n}")
    p.write_bytes(text.encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    per_split, per_bin = defaultdict(list), defaultdict(dict)
    chars, n_tr, n_all = set(), 0, 0
    for u, text, done in final_texts():
        n_all += 1; n_tr += done
        if not done:
            continue
        chars.update(c for c in text if CJK.match(c))
        for loc in u["locs"]:
            if loc["src"] == "split":
                per_split[loc["path"]].append((loc, text))
            else:
                per_bin[loc["file"]][loc["key"]] = (loc, text)
    # fullwidth punctuation is redrawn Taiwanese-style (centred) as well
    chars |= set(font.CENTRED_PUNCT)

    m = font.assign(chars, japanese_still_shown())
    changed = write_split(per_split, m, OUT)
    nsec = write_data_ini(changed, OUT)

    sysout = OUT / "system"; sysout.mkdir()
    for name, items in sorted(per_bin.items()):
        data = (SYSTEM / name).read_bytes()
        new = {}
        for key, (loc, text) in items.items():
            s = to_game(with_prefixes(text, loc["lp"]), m)
            s = re.sub(r"\{v(\d\d)\}", lambda mm: "\x05" + mm.group(1), s)
            new[key] = s.encode("cp932")
        out = sysbin.build(data, name, new)
        (sysout / name).write_bytes(out)
        back = sysbin.read_back(data, out, name)
        bad = [k for k, v in new.items() if back.get(k) != v]
        if bad:
            raise SystemExit(f"{name}: {len(bad)} strings did not read back: " +
                             ", ".join(f"{k}={new[k]!r}/{back.get(k)!r}" for k in bad[:3]))
        limit = sysbin.max_size(name)
        if limit and len(out) > limit:
            raise SystemExit(f"{name}: {len(out)} bytes > {limit}, the buffer it loads into")
        if len(out) > len(data):
            print(f"note: {name} grew {len(data)} -> {len(out)} bytes (limit {limit})")

    fontdata = font.patch((SYSTEM / "FONTDATA0.BIN").read_bytes(), chars, m)
    (sysout / "FONTDATA0.BIN").write_bytes(fontdata)
    (ROOT / "work/build").mkdir(parents=True, exist_ok=True)
    (ROOT / "work/build/FONTDATA0.BIN").write_bytes(fontdata)

    extras = []
    for tool in ("tex", "movie"):
        p = ROOT / "tools" / f"{tool}.py"
        if p.exists():
            mod = __import__(tool)
            if hasattr(mod, "build_into"):
                extras.append(mod.build_into(OUT))

    (OUT / "mod.ini").write_text(
        "Name=Sonic Adventure DX 繁體中文化\n"
        "Author=Yuuta Tsubasa\n"
        f"Version={VERSION}\n"
        "Category=Translation\n"
        "Description=日文版文字、圖片與影片的台灣繁體中文翻譯。請把遊戲文字語言設為日本語。\n"
        "ModID=sadx.yuutatsubasa.traditionalchineseversion\n"
        "EXEData=sonic_data.ini\n", encoding="utf-8")

    shutil.copy2(ROOT / "tools/README_mod.txt", OUT / "README_zh-TW.txt")

    report = {"units": n_all, "translated": n_tr, "chinese_chars": len(chars),
              "stand_in_codes": len(m["extra"]), "free_codes_left": m["free_codes_left"],
              "split_files": len(changed), "data_ini_items": nsec, "bin_files": len(per_bin), "extras": extras}
    (ROOT / "work/build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

    if a.install:
        dst = GAME / "mods" / MODDIR
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(OUT, dst)
        print("installed to", dst)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
