"""SADX PC system message BINs (cp932 text).

Two layouts:
  simple  CHAODX_MESSAGE_*_J.BIN, MSGAL*_J.BIN: big-endian int32 offsets ending in -1,
          strings after the table (offsets are file-relative).
  mes     {SS,MR,PAST}_MES_?_J.BIN: NPC message tables with absolute little-endian
          pointers into a buffer loaded at a fixed address (BASE).

parse() returns the strings with every pointer that refers to them.
build() writes new strings without moving anything else: a string that fits its old
slot stays there; a longer one goes into space freed by shorter strings, and only
then to the end of the file.

    python tools/sysbin.py check <system dir>     round-trip every file
    python tools/sysbin.py dump <file>
"""
import struct, sys
from pathlib import Path

BASE = {"SS": 0xCB46000, "MR": 0xCB4A000, "PAST": 0xCB4A000}
CONTROL = {0x07, 0x0A, 0x0C}  # 0x07 starts most lines (seen in every MES file)


def max_size(name):
    """Largest safe size of a MES file. All fields share one buffer at 0xCB46000 that
    holds SS_MES_S_J.BIN (30152 bytes); MR and PAST files load 0x4000 into it."""
    kind, field = kind_of(name)
    if kind != "mes":
        return None
    return 30152 - (BASE[field] - BASE["SS"])


def kind_of(name):
    n = Path(name).name.upper()
    if n.startswith(("CHAODX_MESSAGE_", "MSGAL")) and n.endswith("_J.BIN"):
        return "simple", None
    for f in ("SS", "MR", "PAST"):
        if n.startswith(f + "_MES_") and n.endswith("_J.BIN"):
            return "mes", f
    return None, None


def cstr(data, off):
    end = data.index(b"\0", off)
    return data[off:end]


class Ref:
    """One string with the pointer fields that point at it."""
    def __init__(self, off, raw, key):
        self.off, self.raw, self.key, self.ptrs = off, raw, key, []


def _add(refs, by_off, off, key, ptr):
    r = by_off.get(off[0])
    if r is None:
        r = Ref(off[0], None, key)
        by_off[off[0]] = r
        refs.append(r)
    r.ptrs.append(ptr)  # (field offset, fmt, base)


def parse(data, name):
    kind, field = kind_of(name)
    refs, by_off = [], {}
    if kind == "simple":
        i = 0
        while i + 4 <= len(data):
            p = struct.unpack_from(">i", data, i)[0]
            if p == -1 or not 0 <= p < len(data):
                break
            _add(refs, by_off, (p,), f"{i // 4}", (i, ">I", 0))
            i += 4
    elif kind == "mes":
        # The NPC header reaches only some of the line tables; the executable addresses
        # others directly (the buffer sits at a fixed address). So take every aligned
        # word that points at the start of a string.
        base = BASE[field]
        found = []
        for po in range(8, len(data) - 3, 4):
            p = struct.unpack_from("<I", data, po)[0] - base
            if 8 <= p < len(data) and _is_string_start(data, p, base):
                found.append((p, po))
        for p, po in sorted(found):
            _add(refs, by_off, (p,), f"{p:04x}", (po, "<I", base))
    else:
        raise ValueError(f"not a message BIN: {name}")
    for r in refs:
        r.raw = cstr(data, r.off)
    return refs


def _is_string_start(data, p, base):
    if p % 4 or data[p] == 0:
        return False
    if p + 4 <= len(data) and 0 <= struct.unpack_from("<I", data, p)[0] - base < len(data):
        return False  # a line table, not text
    try:
        s = cstr(data, p)
    except ValueError:
        return False
    if not s or any(b < 0x20 and b not in CONTROL for b in s):
        return False
    try:
        s.decode("cp932")
    except UnicodeDecodeError:
        return False
    return True


def slot_end(data, r, starts):
    """End of the bytes a string may occupy: its NUL padded to 4, never past another string."""
    end = r.off + len(r.raw) + 1
    while end % 4:
        if end >= len(data) or data[end] != 0 or end in starts:
            break
        end += 1
    return end


def build(data, name, new):
    """new: {key: bytes (no NUL)}. Strings not in `new` keep their bytes.

    With any change, every string slot is freed and all strings are placed again,
    longest first, into the freed space (first fit); only what does not fit goes
    to the end of the file. Nothing but strings and their pointers moves.
    """
    refs = parse(data, name)
    if all(new.get(r.key, r.raw) == r.raw for r in refs):
        return bytes(data)
    align = 4 if kind_of(name)[0] == "mes" else 1
    out = bytearray(data)
    starts = {r.off for r in refs}
    spans = sorted((r.off, slot_end(data, r, starts)) for r in refs)
    free = []
    for s, e in spans:
        out[s:e] = bytes(e - s)
        if free and free[-1][1] == s:
            free[-1][1] = e
        else:
            free.append([s, e])
    for r in sorted(refs, key=lambda r: (-len(new.get(r.key, r.raw)), r.off)):
        raw = new.get(r.key, r.raw)
        need = len(raw) + 1
        slot = None
        for f in free:
            a = -(-f[0] // align) * align
            if f[1] - a >= need:
                slot = a; f[0] = a + need; break
        if slot is None:
            while len(out) % 4:
                out.append(0)
            slot = len(out); out.extend(bytes(need))
        out[slot:slot + len(raw)] = raw
        for (po, fmt, base) in r.ptrs:
            struct.pack_into(fmt, out, po, slot + base)
    return bytes(out)


def read_back(orig, out, name):
    """{key: bytes} as the game will see them: follow the original pointer fields in `out`."""
    res = {}
    for r in parse(orig, name):
        vals = {cstr(out, struct.unpack_from(fmt, out, po)[0] - base) for po, fmt, base in r.ptrs}
        res[r.key] = vals.pop() if len(vals) == 1 else None
    return res


def main():
    cmd, path = sys.argv[1], Path(sys.argv[2])
    if cmd == "dump":
        for r in parse(path.read_bytes(), path.name):
            print(r.key, r.raw.decode("cp932", "replace").replace("\n", "⏎"))
    elif cmd == "check":
        bad = 0
        for f in sorted(path.glob("*.BIN")):
            if not kind_of(f.name)[0]:
                continue
            d = f.read_bytes()
            refs = parse(d, f.name)
            same = build(d, f.name, {}) == d
            # every string re-placed must also round-trip
            moved = build(d, f.name, {r.key: r.raw for r in refs}) == d
            cover = sum(len(r.raw) for r in refs)
            print(f"{f.name:36} strings={len(refs):4} bytes={cover:6} roundtrip={'ok' if same and moved else 'FAIL'}")
            bad += not (same and moved)
        print("FAILED" if bad else "all ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
