"""Translation workflow for Sonic Adventure DX text (ja -> zh-TW).

Data (all under text/):
  ja/<FILE>.json      source strings [{id, ja}]
  zh/<FILE>.json      translations {id: zh}
  glossary.json       proper nouns / terms {ja: {"zh": ..., "note": ...}}
  tm.json             sentence memory {ja: zh}

Commands:
  status                         progress per file
  next <FILE> [N]                next N untranslated strings (exact TM hits and strings
                                 without Japanese are filled automatically) + matching
                                 glossary terms and similar TM entries
  commit <FILE> <batch.json>     save translations, update TM and glossary
  lookup <text>                  search glossary + TM
  term <ja> <zh> [note]          add/update a glossary term
  check [FILE]                   re-validate saved translations
  rebuild-tm                     rebuild text/tm.json from text/ja + text/zh
"""
import difflib, json, os, re, sys, time
from contextlib import contextmanager

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "text")
GLOSSARY = os.path.join(ROOT, "glossary.json")
TM = os.path.join(ROOT, "tm.json")
LOCK = os.path.join(ROOT, ".lock")

# control tags, printf tokens and button/icon glyphs that must survive unchanged
TOKEN = re.compile(r"\{v\d\d\}|%[-0-9.]*[dsxX]")  # Chao shop: inserted price / item name
JAPANESE = re.compile(r"[ぁ-ゖァ-ヺ一-鿿々ｦ-ﾝ]")
KANA = re.compile(r"[ぁ-ゖァ-ヺｦ-ﾝ]")


@contextmanager
def locked():
    """Cross-process lock so parallel translators can share glossary/TM."""
    for _ in range(1200):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY); break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > 60:
                    os.remove(LOCK)
            except FileNotFoundError:
                pass
            time.sleep(0.1)
    else:
        raise RuntimeError("lock timeout")
    try:
        yield
    finally:
        os.close(fd); os.remove(LOCK)


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=isinstance(data, dict))
    os.replace(tmp, path)


def src(name):
    return load(os.path.join(ROOT, "ja", name + ".json"), None)


def zh_path(name):
    return os.path.join(ROOT, "zh", name + ".json")


def units(line):
    """Display width in half-width units (full-width = 2). {vNN} counts as 2 digits."""
    line = TOKEN.sub("00", line)
    return sum(1 if ord(c) < 0x80 or 0xff61 <= ord(c) <= 0xff9f else 2 for c in line)


def max_units(s):
    return max((units(l) for l in s.split("\n")), default=0)


def glossary_hits(text, glossary):
    return {k: v for k, v in glossary.items() if k in text}


def width_limit(row, ja):
    """A line may fill its text box (`box`); outside boxes, the Japanese width + 2."""
    mu = row.get("max_units", max_units(ja))
    return max(mu, row["box"]) if "box" in row else max(mu, 8) + 2


def enc_len(line):
    """Stored byte length (Chinese characters take 2 bytes, ASCII 1)."""
    return units(line)


def check(ja, zh, row=None):
    """Return list of problems with a translation. row = the text/ja entry (limits)."""
    row = row or {}
    if zh == ja:          # kept in the original on purpose (音樂卡曲名, 人名)
        return []
    errs = []
    a, b = sorted(TOKEN.findall(ja)), sorted(TOKEN.findall(zh))
    if a != b:
        errs.append(f"tokens differ: {a} vs {b}")
    if "\\n" in zh:
        errs.append("literal backslash-n; use a real line break")
    if KANA.search(TOKEN.sub("", zh)):
        errs.append("Japanese kana left in translation")
    for ch in set(TOKEN.sub("", zh)):
        if ch == "\n" or ch in "·":
            continue
        if ord(ch) < 0x20:
            errs.append(f"control character {ch!r} in text")
        elif re.match(r"[一-鿿]", ch):
            try:
                ch.encode("cp950")
            except UnicodeEncodeError:
                errs.append(f"not a Traditional Chinese (Big5) character: {ch}")
        elif ord(ch) >= 0x80:
            try:
                ch.encode("cp932")
            except UnicodeEncodeError:
                errs.append(f"symbol not in the game font: {ch!r} (use full-width ，。！？「」…～・)")
    if re.search(r"[,!?]", zh):
        errs.append("half-width , ! ? ; use full-width ，！？")
    if row.get("wrap"):          # Chao boxes wrap by themselves: no line or width limit
        return errs
    if "\n" not in ja and "\n" in zh and row.get("lines", 1) == 1:
        errs.append("added line break to single-line text")
    zl = zh.split("\n")
    maxl = row.get("lines", ja.count("\n") + 1)
    if len(zl) > maxl:
        errs.append(f"too many lines ({len(zl)} > {maxl})")
    limit = width_limit(row, ja)
    if max_units(zh) > limit:
        errs.append(f"line too wide ({max_units(zh)} > {limit} half-width units); rebalance lines")
    if "max_bytes" in row and enc_len(zh.replace("\n", " ")) > row["max_bytes"]:
        errs.append(f"too long for its field ({enc_len(zh)} > {row['max_bytes']} bytes); shorten")
    if "max_bytes_line" in row:
        for l in zl:
            if enc_len(l) > row["max_bytes_line"]:
                errs.append(f"line too long for its field ({enc_len(l)} > {row['max_bytes_line']} bytes)")
    return errs


def cmd_status():
    tot_n = tot_d = 0
    for fn in sorted(os.listdir(os.path.join(ROOT, "ja"))):
        name = fn[:-5]
        rows = src(name); zh = load(zh_path(name), {})
        done = sum(1 for r in rows if r["id"] in zh)
        tot_n += len(rows); tot_d += done
        if done < len(rows) or "-a" in sys.argv:
            print(f"{name:16} {done:5}/{len(rows):5}  {100*done/len(rows):5.1f}%")
    g = load(GLOSSARY, {}); tm = load(TM, {})
    print(f"{'TOTAL':16} {tot_d:5}/{tot_n:5}  {100*tot_d/max(tot_n,1):5.1f}%   glossary={len(g)} tm={len(tm)}")


def cmd_next(name, n=40):
    rows = src(name)
    with locked():
        zh = load(zh_path(name), {}); tm = load(TM, {})
        auto = 0
        for r in rows:
            k = r["id"]
            if k not in zh and (r["ja"] in tm or not JAPANESE.search(r["ja"])):
                zh[k] = tm.get(r["ja"], r["ja"]); auto += 1
        if auto:
            save(zh_path(name), zh)
    glossary = load(GLOSSARY, {})
    todo = [r for r in rows if r["id"] not in zh][:int(n)]
    terms, similar = {}, {}
    tm_keys = list(tm.keys())
    for r in todo:
        terms.update(glossary_hits(r["ja"], glossary))
        if len(r["ja"]) > 8:
            for m in difflib.get_close_matches(r["ja"], tm_keys, n=2, cutoff=0.7):
                similar[m] = tm[m]
    out = {
        "file": name, "auto_filled": auto,
        "remaining": sum(1 for r in rows if r["id"] not in zh),
        "glossary": {k: v["zh"] + (f"  ({v['note']})" if v.get("note") else "") for k, v in terms.items()},
        "similar_tm": similar,
        "strings": [{"id": r["id"], "ja": r["ja"],
                     **({"wrap": True} if r.get("wrap") else
                        {"max_units": width_limit(r, r["ja"]), "lines": r.get("lines", r["ja"].count("\n") + 1)}),
                     **({"max_bytes": r["max_bytes"]} if "max_bytes" in r else {})} for r in todo],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_commit(name, batch_path):
    batch = load(batch_path, None)
    items = batch["strings"] if isinstance(batch, dict) else batch
    terms = batch.get("terms", {}) if isinstance(batch, dict) else {}
    rows = {r["id"]: r for r in src(name)}
    ja = {k: r["ja"] for k, r in rows.items()}
    ok, bad = {}, []
    for it in items:
        k = str(it["id"])
        if k not in ja:
            bad.append((k, "unknown id")); continue
        errs = check(ja[k], it["zh"], rows[k])
        if errs:
            bad.append((k, "; ".join(errs)))
        else:
            ok[k] = it["zh"]
    with locked():
        zh = load(zh_path(name), {}); tm = load(TM, {}); g = load(GLOSSARY, {})
        zh.update(ok)
        for k, v in ok.items():
            tm[ja[k]] = v
        conflicts = []
        for t, v in terms.items():
            v = v if isinstance(v, dict) else {"zh": v}
            if t in g and g[t]["zh"] != v["zh"]:
                conflicts.append(f"{t}: glossary={g[t]['zh']} batch={v['zh']}")
                continue
            g[t] = {"zh": v["zh"], **({"note": v["note"]} if v.get("note") else {})}
        save(zh_path(name), zh); save(TM, tm); save(GLOSSARY, g)
    print(f"committed {len(ok)} strings, {len(terms) - len(conflicts)} terms")
    for k, e in bad:
        print(f"REJECTED {k}: {e}")
    for c in conflicts:
        print(f"TERM CONFLICT (kept glossary) {c}")


def cmd_lookup(text):
    g = load(GLOSSARY, {}); tm = load(TM, {})
    for k, v in g.items():
        if text in k or text in v["zh"]:
            print(f"[term] {k} => {v['zh']} {v.get('note', '')}")
    n = 0
    for k, v in tm.items():
        if text in k or text in v:
            print(f"[tm] {k!r} => {v!r}"); n += 1
            if n >= 20: break


def cmd_term(ja, zh, note=""):
    with locked():
        g = load(GLOSSARY, {})
        g[ja] = {"zh": zh, **({"note": note} if note else {})}
        save(GLOSSARY, g)
    print(f"{ja} => {zh}")


def cmd_rebuild_tm():
    """text/tm.json is not published (it holds the Japanese script): rebuild it from
    text/ja (made by tools/extract.py) and text/zh."""
    tm = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "ja"))):
        zh = load(zh_path(fn[:-5]), {})
        for r in src(fn[:-5]):
            if r["id"] in zh:
                tm[r["ja"]] = zh[r["id"]]
    with locked():
        save(TM, tm)
    print(f"tm={len(tm)}")


def cmd_check(name=None):
    names = [name] if name else [f[:-5] for f in sorted(os.listdir(os.path.join(ROOT, "ja")))]
    nbad = 0
    for nm in names:
        rows = {r["id"]: r for r in src(nm)}
        for k, v in load(zh_path(nm), {}).items():
            errs = check(rows[k]["ja"], v, rows[k]) if k in rows else ["unknown id"]
            if errs:
                nbad += 1; print(f"{nm} {k}: {'; '.join(errs)}")
    print(f"{nbad} problems")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd, *args = sys.argv[1:] or ["status"]
    args = [a for a in args if a != "-a"]
    {"status": cmd_status, "next": cmd_next, "commit": cmd_commit,
     "lookup": cmd_lookup, "term": cmd_term, "check": cmd_check,
     "rebuild-tm": cmd_rebuild_tm}[cmd](*args)
