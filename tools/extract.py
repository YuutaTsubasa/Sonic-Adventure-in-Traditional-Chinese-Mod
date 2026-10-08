"""Build translation units text/ja/<FILE>.json from the player's own game files.

Sources (made by tools/prepare.py):
  source/split/   Japanese text split out of sonic.exe by SA Tools
  source/system/  the *_J.BIN message files

One unit per distinct Japanese text: the same sentence anywhere in the game is
translated once, and the build writes it to every location (`locs`).
A unit belongs to the FILE where it first appears, in story order.

Leading control characters of each line (\\x07 centring, \\t) are not part of the
unit text; each location keeps its own (`lp`) and the build puts them back.
Inside a line, the Chao shop's \\x05NN (inserted value) becomes the token {vNN}.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sysbin

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "source/split"
SYSTEM = ROOT / "source/system"
JAPANESE = re.compile(r"[ぁ-ゖァ-ヺ一-鿿々ｦ-ﾝ０-９Ａ-Ｚａ-ｚ]")
CHARS = ["Sonic", "Tails", "Knuckles", "Amy", "Gamma", "Big", "Last"]
MES_CHAR = {"S": "sonic", "M": "tails", "K": "knuckles", "A": "amy", "E": "gamma", "B": "big", "L": "last"}


def units(line):
    line = re.sub(r"\{v\d\d\}", "00", line)
    return sum(1 if ord(c) < 0x80 or 0xff61 <= ord(c) <= 0xff9f else 2 for c in line)


def split_prefix(text):
    """'\\x07ab\\n\\tcd' -> ('ab\\ncd', ['\\x07', '\\t'])"""
    lines, lp = [], []
    for line in text.split("\n"):
        m = re.match(r"[\x00-\x1f]*", line)
        lp.append(m.group()); lines.append(line[m.end():])
    return "\n".join(lines), lp


def natkey(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def file_of_split(rel):
    p = rel.split("/")
    if p[0] == "Misc" and p[1] == "Cutscene Text":
        return "cut_" + p[2].lower()
    if p[0] == "Misc" and p[1] == "Recaps":
        return "recap_" + p[2].lower()
    if p[0] == "Misc" and p[1] == "Boss Hints":
        return "boss_hints"
    if p[0] == "Misc" and p[1] == "Messages" and p[2] in ("Chao Garden", "Chao Race"):
        return "chao_msg"
    if len(p) > 1 and p[1] == "hintdata":
        return "npc_" + re.sub(r"^(adv|stg)\d+_", "", p[0])
    if p[0] in ("mission", "summary"):
        return "mission"
    return "misc"


def split_sources():
    """Yield (FILE, loc, raw_text) for every Japanese string in the split files."""
    files = [f for f in SPLIT.rglob("*") if f.is_file() and
             (f.name.startswith("Japanese.") or f.name.endswith("_j.dat.ini") or f.name == "Japanese Level List.txt")]
    for f in sorted(files, key=lambda f: natkey(f.relative_to(SPLIT).as_posix())):
        rel = f.relative_to(SPLIT).as_posix()
        name = file_of_split(rel)
        text = f.read_text(encoding="utf-8")
        lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
        if f.suffix == ".txt":
            for i, line in enumerate(lines):
                if line.strip():
                    yield name, {"src": "split", "path": rel, "line": i}, line.replace("\\n", "\n")
            continue
        section, page = None, None
        for i, line in enumerate(lines):
            m = re.match(r"^\[(.*)\]$", line)
            if m:
                section = m.group(1); continue
            k, sep, v = line.partition("=")
            if not sep or not v.strip():
                continue
            if f.name.endswith("_j.dat.ini"):
                # mission tutorial: one unit per page, its lines are keys 0..NumLines-1
                if k.isdigit():
                    if k == "0":
                        page = {"src": "split", "path": rel, "page": section, "line": i, "n": 0, "v": []}
                    page["n"] += 1; page["v"].append(v)
                    nxt = lines[i + 1] if i + 1 < len(lines) else ""
                    if not re.match(r"^\d+=", nxt):
                        loc = {k2: page[k2] for k2 in ("src", "path", "page", "line", "n")}
                        yield name, loc, "\n".join(page["v"])
                continue
            if k in ("Line", "Text", "Title") or k.isdigit():
                yield name, {"src": "split", "path": rel, "line": i, "key": k}, v.replace("\\n", "\n")


def bin_sources():
    order = []
    for f in sorted(SYSTEM.glob("*_J.BIN")):
        kind, field = sysbin.kind_of(f.name)
        if not kind:
            continue
        if kind == "mes":
            c = f.name.split("_")[2]
            name = "mes_" + MES_CHAR[c]
            rank = ({"SS": 0, "MR": 1, "PAST": 2}[field], "SMKAEBL".index(c), "")
        else:
            name = "chao_msg"
            rank = (3, 0, f.name)
        order.append((rank, f, name))
    for _, f, name in sorted(order, key=lambda x: x[0]):
        for r in sysbin.parse(f.read_bytes(), f.name):
            text = r.raw.decode("cp932")
            text = re.sub(r"\x05(\d\d)", r"{v\1}", text)
            yield name, {"src": "bin", "file": f.name, "key": r.key}, text


# Widest line (half-width units) the text box takes, per FILE prefix: the widest
# Japanese line seen in that kind of box. Short lines may grow up to it.
BOX = {"cut": 38, "recap": 40, "boss": 36, "npc": 36, "mes": 36, "mission": 38}

FILE_ORDER = ([f"cut_{c.lower()}" for c in CHARS] + [f"recap_{c.lower()}" for c in CHARS] +
              ["boss_hints"] + [f"mes_{c}" for c in MES_CHAR.values()])


def main():
    found = list(split_sources()) + list(bin_sources())
    rank = {n: i for i, n in enumerate(FILE_ORDER)}
    found.sort(key=lambda x: rank.get(x[0], len(rank)))  # stable: keeps order inside a FILE
    by_ja, out = {}, {}
    nloc = 0
    for name, loc, raw in found:
        ja, lp = split_prefix(raw)
        if not JAPANESE.search(ja):
            continue
        if "\\" in ja:
            print("warning: backslash in", loc, repr(ja))
        loc["lp"] = lp
        nloc += 1
        u = by_ja.get(ja)
        if u is None:
            lid = loc.get("path", loc.get("file")) + ":" + str(loc.get("line", loc.get("key")))
            u = {"id": lid, "ja": ja, "lines": ja.count("\n") + 1,
                 "max_units": max(units(l) for l in ja.split("\n")), "locs": []}
            if name.split("_")[0] in BOX:
                u["box"] = BOX[name.split("_")[0]]
            if loc["src"] == "bin" and sysbin.kind_of(loc["file"])[0] == "simple":
                u["wrap"] = True  # the Chao boxes wrap long lines themselves
            by_ja[ja] = u
            out.setdefault(name, []).append(u)
        u["locs"].append(loc)
    dst = ROOT / "text/ja"
    dst.mkdir(parents=True, exist_ok=True)
    for old in dst.glob("*.json"):
        old.unlink()
    for name, rows in out.items():
        (dst / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{nloc} locations -> {len(by_ja)} units in {len(out)} files")
    for name in sorted(out, key=lambda n: rank.get(n, 99)):
        rows = out[name]
        print(f"  {name:16} {len(rows):5} units  {sum(len(r['ja']) for r in rows):7} chars")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
