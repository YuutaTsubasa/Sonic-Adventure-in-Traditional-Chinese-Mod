"""Textures with Japanese text: inventory, specs, rendering, packing.

    python tools/tex.py extract            decode every Japanese texture archive to work/tex/raw/
    python tools/tex.py sheets             contact sheets per archive -> work/tex/sheets/
    python tools/tex.py status             specs done / to do
    python tools/tex.py preview <id>...    render specs -> work/tex/preview/<id>.png (2x, on grey)
    python tools/tex.py render             render every spec (to check they all draw)
    python tools/tex.py show <id> [zoom]   zoomed texture with a pixel grid -> work/tex/show/<id>.png
    python tools/tex.py boxes <id> [gap]   bounding boxes of opaque glyph clusters
    python tools/tex.py colors <id> x0 y0 x1 y1   most common colours in a rect
    python tools/tex.py composite <ARCHIVE> show|preview   tiled pictures (maps), see COMPOSITES

Which archives: those the game swaps by language (X.PVM has an X_E.PVM English twin) plus
the *_J / *_JP ones. Every texture is known by its id: the first 10 hex digits of the
sha1 of its decoded RGBA pixels. text/tex/<id>.json is its spec:

  {"blocks": [{"rect": [x0, y0, x1, y1], "zh": "開始", "size": 14, "weight": 700,
               "color": "#ffffff", "stroke": "#000000", "stroke_w": 1, "align": "center"}],
   "erase": [[x0, y0, x1, y1]], "fill": "#00000000"}
  {"keep": true}                       no Japanese, or nothing to change

Coordinates are in the original texture's pixels. Erase rects are cleared to `fill`
(default transparent) or, with "erase_mode": "row", by interpolating each row from the
pixels left and right of the rect. Blocks are drawn at SCALE x for the texture pack.

Output (build_into): changed PVM textures go to replacetex/<NAME>/ (index.txt + PNGs at
SCALE x; the Mod Loader keeps the original size from index.txt); standalone PVR
files are re-encoded to PVR in their original pixel format with SA Tools TextureTool.
"""
import hashlib, json, re, shutil, struct, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "source/system"
RAW = ROOT / "work/tex/raw"
SPECS = ROOT / "text/tex"
SATOOLS = Path(r"C:/Users/User/Repo/SATraditional/SA.Tools.x64/bin")
FONT = r"C:/Windows/Fonts/NotoSansTC-VF.ttf"
SCALE = 2
LANG_SUFFIX = r"(_E|_US|_EN|_F|_G|_S|_I|_FR)"


def japanese_archives():
    names = {f.name.upper(): f.name for f in SYSTEM.iterdir() if f.suffix.upper() in (".PVM", ".PVR")}
    jp = set()
    for u in names:
        stem, ext = u.rsplit(".", 1)
        m = re.match(rf"(.*?){LANG_SUFFIX}$", stem)
        if m:
            for cand in (f"{m.group(1)}.{ext}", f"{m.group(1)}_J.{ext}", f"{m.group(1)}_JP.{ext}"):
                if cand in names:
                    jp.add(names[cand])
        if re.search(r"(_J|_JP|_J_TEX)\.(PVM|PVR)$", u):
            jp.add(names[u])
    # The PC title screen and main menu draw the *English* logo whatever the language
    for u in ("AVA_GTITLE0_E.PVM", "AVA_TITLE_BACK_E.PVM"):
        if u in names:
            jp.add(names[u])
    # Not language-swapped but drawn with Japanese labels anyway
    for u in names:
        if u.startswith("MAP_"):
            jp.add(names[u])
    return sorted(jp)


def tex_id(img):
    return hashlib.sha1(img.convert("RGBA").tobytes()).hexdigest()[:10]


def run(args, cwd):
    r = subprocess.run(args, cwd=cwd, input="\n", capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{args}: {r.stdout[-500:]} {r.stderr[-500:]}")
    return r.stdout


def cmd_extract():
    RAW.mkdir(parents=True, exist_ok=True)
    index = {}
    for name in japanese_archives():
        stem = Path(name).stem
        d = RAW / stem
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        shutil.copy2(SYSTEM / name, d / name)
        if name.upper().endswith(".PVM"):
            run([str(SATOOLS / "ArchiveTool.exe"), "-png", name], d)
            pack = d / stem
            entries = []
            for line in (pack / "index.txt").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                gbix, fn, *size = line.split(",")
                img = Image.open(pack / fn)
                entries.append({"gbix": gbix, "file": fn, "size": size[0] if size else f"{img.width}x{img.height}",
                                "id": tex_id(img)})
        else:
            run([str(SATOOLS / "TextureTool.exe"), name, "-o", stem + ".png"], d)
            img = Image.open(d / (stem + ".png"))
            entries = [{"file": stem + ".png", "size": f"{img.width}x{img.height}", "id": tex_id(img),
                        "pvr": pvr_info(SYSTEM / name)}]
        (d / (name)).unlink()
        index[name] = entries
        print(f"{name}: {len(entries)} textures")
    (ROOT / "work/tex/index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


def pvr_info(path):
    """GBIX, pixel format and data format of a standalone PVR."""
    b = path.read_bytes()
    gbix = None
    o = 0
    if b[:4] == b"GBIX":
        n = struct.unpack_from("<I", b, 4)[0]
        gbix = struct.unpack_from("<I", b, 8)[0]
        o = 8 + n
    assert b[o:o + 4] == b"PVRT", path
    return {"gbix": gbix, "pixel": b[o + 8], "data": b[o + 9]}


def index():
    return json.loads((ROOT / "work/tex/index.json").read_text(encoding="utf-8"))


def raw_png(arch, e):
    stem = Path(arch).stem
    p = RAW / stem / stem / e["file"]
    return p if p.exists() else RAW / stem / e["file"]


def unique():
    """id -> (archive, entry) of the first copy."""
    out = {}
    for arch, entries in index().items():
        for e in entries:
            out.setdefault(e["id"], (arch, e))
    return out


def cmd_sheets():
    dst = ROOT / "work/tex/sheets"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    lab = ImageFont.truetype(FONT, 12)
    seen = set()
    for arch, entries in index().items():
        tiles = []
        for e in entries:
            if e["id"] in seen or (spec(e["id"]) or {}).get("keep"):
                continue
            seen.add(e["id"])
            img = Image.open(raw_png(arch, e)).convert("RGBA")
            s = min(1.0, 256 / max(img.size))
            img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.NEAREST)
            tiles.append((e, img))
        if not tiles:
            continue
        W = 1024
        x = y = rowh = 0
        place = []
        for e, img in tiles:
            w, h = img.width, img.height + 14
            if x + w > W:
                x = 0; y += rowh + 6; rowh = 0
            place.append((x, y, e, img)); x += w + 6; rowh = max(rowh, h)
        sheet = Image.new("RGB", (W, y + rowh + 4), (90, 90, 110))
        d = ImageDraw.Draw(sheet)
        for x, y, e, img in place:
            bg = Image.new("RGB", img.size, (60, 60, 60))
            bg.paste(img, (0, 0), img)
            sheet.paste(bg, (x, y + 14))
            d.text((x, y), f"{e['id']} {e['size']}", fill=(255, 255, 0), font=lab)
        sheet.save(dst / f"{Path(arch).stem}.png")
    print("sheets in", dst)


def spec(tid):
    p = SPECS / f"{tid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cmd_status():
    u = unique()
    todo = [t for t in u if spec(t) is None]
    done = [t for t in u if spec(t) and not spec(t).get("keep")]
    print(f"textures {len(u)}  translated {len(done)}  keep {len(u) - len(todo) - len(done)}  unmarked {len(todo)}")


_fonts = {}


def get_font(size, weight):
    k = (size, weight)
    if k not in _fonts:
        f = ImageFont.truetype(FONT, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _fonts[k] = f
    return _fonts[k]


def erase(img, rects, mode, fill):
    px = img.load()
    for x0, y0, x1, y1 in rects:
        if mode == "row":
            for y in range(y0, y1):
                l = px[max(x0 - 1, 0), y]; r = px[min(x1, img.width - 1), y]
                for x in range(x0, x1):
                    t = (x - x0 + 0.5) / max(x1 - x0, 1)
                    px[x, y] = tuple(round(l[i] * (1 - t) + r[i] * t) for i in range(4))
        elif mode == "col":
            for x in range(x0, x1):
                a = px[x, max(y0 - 1, 0)]; b = px[x, min(y1, img.height - 1)]
                for y in range(y0, y1):
                    t = (y - y0 + 0.5) / max(y1 - y0, 1)
                    px[x, y] = tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(4))
        else:
            ImageDraw.Draw(img).rectangle([x0, y0, x1 - 1, y1 - 1], fill=fill)


def hexcol(s):
    s = s.lstrip("#")
    if len(s) == 6:
        s += "ff"
    return tuple(int(s[i:i + 2], 16) for i in range(0, 8, 2))


def draw_block(img, b, scale):
    """Draw one text block, shrinking horizontally if it does not fit its rect."""
    x0, y0, x1, y1 = [v * scale for v in b["rect"]]
    w, h = x1 - x0, y1 - y0
    size = round(b.get("size", (b["rect"][3] - b["rect"][1]) * 0.85) * scale)
    font = get_font(size, b.get("weight", 700))
    sw = round(b.get("stroke_w", 0) * scale)
    lines = b["zh"].split("\n")
    ss = 4
    layer = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    big = get_font(size * ss, b.get("weight", 700))
    d = ImageDraw.Draw(layer)
    lh = big.getmetrics()[0] + big.getmetrics()[1]
    lh = int(lh * b.get("leading", 1.0))
    total = lh * len(lines)
    for i, line in enumerate(lines):
        tw = big.getlength(line) + 2 * sw * ss
        sx = min(1.0, (w * ss) / max(tw, 1)) if not b.get("no_squeeze") else 1.0
        tmp = Image.new("RGBA", (int(tw) + 4 * ss, lh + 4 * ss), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((sw * ss + 2 * ss, 2 * ss), line, font=big, fill=hexcol(b.get("color", "#ffffff")),
                                 stroke_width=sw * ss, stroke_fill=hexcol(b.get("stroke", "#000000")))
        if sx < 1.0:
            tmp = tmp.resize((max(1, int(tmp.width * sx)), tmp.height), Image.LANCZOS)
        align = b.get("align", "center")
        if align == "left":
            tx = 0
        elif align == "right":
            tx = w * ss - tmp.width
        else:
            tx = (w * ss - tmp.width) // 2
        ty = (h * ss - total) // 2 + i * lh - 2 * ss + round(b.get("dy", 0) * scale * ss)
        layer.alpha_composite(tmp, (max(tx, 0), max(ty, -tmp.height)))
    if b.get("glow"):
        g = layer.split()[3].filter(ImageFilter.GaussianBlur(b.get("glow_r", 2) * scale * ss))
        glow = Image.new("RGBA", layer.size, hexcol(b["glow"]))
        glow.putalpha(g.point(lambda v: min(255, v * 2)))
        glow.alpha_composite(layer); layer = glow
    layer = layer.resize((w, h), Image.LANCZOS)
    img.alpha_composite(layer, (x0, y0))


def render(tid, scale=SCALE):
    sp = spec(tid)
    arch, e = unique()[tid]
    img = Image.open(raw_png(arch, e)).convert("RGBA")
    if sp.get("erase"):
        erase(img, sp["erase"], sp.get("erase_mode", "clear"), hexcol(sp.get("fill", "#00000000")))
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    for b in sp.get("blocks", []):
        draw_block(img, b, scale)
    return img


def cmd_preview(ids):
    dst = ROOT / "work/tex/preview"; dst.mkdir(parents=True, exist_ok=True)
    u = unique()
    for tid in ids:
        arch, e = u[tid]
        orig = Image.open(raw_png(arch, e)).convert("RGBA").resize(
            (int(e["size"].split("x")[0]) * SCALE, int(e["size"].split("x")[1]) * SCALE), Image.NEAREST)
        new = render(tid)
        bg = Image.new("RGBA", (orig.width, orig.height * 2 + 4), (70, 70, 90, 255))
        bg.alpha_composite(orig, (0, 0)); bg.alpha_composite(new.resize(orig.size), (0, orig.height + 4))
        bg.save(dst / f"{tid}.png")
        print(dst / f"{tid}.png")


def cmd_show(tid, zoom=None):
    """Zoomed view with a 10-px grid and pixel rulers -> work/tex/show/<id>.png"""
    arch, e = unique()[tid]
    img = Image.open(raw_png(arch, e)).convert("RGBA")
    z = int(zoom) if zoom else max(2, min(8, 1200 // max(img.size)))
    bg = Image.new("RGBA", img.size, (60, 60, 90, 255)); bg.alpha_composite(img)
    big = bg.resize((img.width * z, img.height * z), Image.NEAREST)
    pad = 28
    canvas = Image.new("RGB", (big.width + pad, big.height + pad), (20, 20, 20))
    canvas.paste(big, (pad, pad))
    d = ImageDraw.Draw(canvas); f = ImageFont.truetype(FONT, 10)
    for x in range(0, img.width + 1, 10):
        d.line([(pad + x * z, pad), (pad + x * z, pad + big.height)], fill=(255, 0, 255) if x % 50 == 0 else (120, 60, 120))
        if x % 20 == 0:
            d.text((pad + x * z + 1, 2), str(x), fill=(255, 255, 0), font=f)
    for y in range(0, img.height + 1, 10):
        d.line([(pad, pad + y * z), (pad + big.width, pad + y * z)], fill=(255, 0, 255) if y % 50 == 0 else (120, 60, 120))
        d.text((1, pad + y * z + 1), str(y), fill=(255, 255, 0), font=f)
    dst = ROOT / "work/tex/show"; dst.mkdir(parents=True, exist_ok=True)
    canvas.save(dst / f"{tid}.png")
    print(dst / f"{tid}.png", f"{img.width}x{img.height} zoom {z}")


def cmd_boxes(tid, gap="3"):
    """Bounding boxes of opaque pixel clusters (glyphs merged when closer than `gap` px)."""
    arch, e = unique()[tid]
    img = Image.open(raw_png(arch, e)).convert("RGBA")
    a = img.split()[3].point(lambda v: 255 if v > 40 else 0)
    a = a.filter(ImageFilter.MaxFilter(2 * int(gap) + 1))
    px = a.load(); W, H = a.size; seen = set(); boxes = []
    for y in range(H):
        for x in range(W):
            if px[x, y] and (x, y) not in seen:
                st = [(x, y)]; seen.add((x, y)); x0 = x1 = x; y0 = y1 = y
                while st:
                    cx, cy = st.pop()
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < W and 0 <= ny < H and px[nx, ny] and (nx, ny) not in seen:
                            seen.add((nx, ny)); st.append((nx, ny))
                g = int(gap)
                boxes.append((max(x0 + g, 0), max(y0 + g, 0), min(x1 - g + 1, W), min(y1 - g + 1, H)))
    for b in sorted(boxes, key=lambda b: (b[1] // 8, b[0])):
        print(list(b), f"{b[2]-b[0]}x{b[3]-b[1]}")


def cmd_colors(tid, x0, y0, x1, y1):
    """Most common colours in a rect (to match text fill / outline / background)."""
    from collections import Counter
    arch, e = unique()[tid]
    img = Image.open(raw_png(arch, e)).convert("RGBA").crop((int(x0), int(y0), int(x1), int(y1)))
    for c, n in Counter(img.getdata()).most_common(8):
        print("#%02x%02x%02x%02x" % c, n)


# Title logo archives: tiles that together form one picture with the logo on it.
# (archive, tile positions in the picture, logo box (x0, y0, x1, y1), picture has a background)
LOGO_ARCHIVES = {
    "AVA_GTITLE0.PVM": ([(x * 256, y * 256) for y in range(2) for x in range(4)], (143, 141, 965, 385), False),
    "AVA_TITLE_BACK.PVM": ([(0, 0), (0, 256), (256, 0), (256, 256), (512, 0), (512, 128), (512, 256), (512, 384)],
                           (54, 164, 596, 342), True),
    # the English logos, which the PC version shows in every language
    "AVA_GTITLE0_E.PVM": ([(x * 256, y * 256) for y in range(2) for x in range(4)], (170, 146, 947, 418), False),
    "AVA_TITLE_BACK_E.PVM": ([(0, 0), (0, 256), (256, 0), (256, 256), (512, 0), (512, 128), (512, 256), (512, 384)],
                             (84, 166, 592, 352), True),
}


def logo_tiles(arch):
    """{entry file: new tile image at SCALE x} for an archive in LOGO_ARCHIVES."""
    import numpy as np
    sys.path.insert(0, str(Path(__file__).parent))
    import logo
    pos, (x0, y0, x1, y1), has_bg = LOGO_ARCHIVES[arch]
    entries = index()[arch][:len(pos)]
    tiles = [Image.open(raw_png(arch, e)).convert("RGBA") for e in entries]
    W = max(p[0] + t.width for p, t in zip(pos, tiles)); H = max(p[1] + t.height for p, t in zip(pos, tiles))
    pic = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for p, t in zip(pos, tiles):
        pic.alpha_composite(t, p)
    lg1 = logo.fit(x1 - x0, y1 - y0, band=(40, 30, 110), scale=3, stretch=has_bg)
    if has_bg:
        import cv2
        rgb = np.asarray(pic.convert("RGB"))
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        water = (hsv[..., 2] > 150) & (((hsv[..., 0] > 85) & (hsv[..., 0] < 125)) | (hsv[..., 1] < 60))
        A = np.zeros((H, W)); A[y0:y1, x0:x1] = np.asarray(lg1)[..., 3] / 255
        mask = np.zeros((H, W), np.uint8)
        reg = np.zeros((H, W), bool); reg[y0 - 14:y1 + 8, x0 - 14:x1 + 14] = True
        logo_px = ~water
        twin = {"AVA_TITLE_BACK.PVM": "AVA_TITLE_BACK_E.PVM", "AVA_TITLE_BACK_E.PVM": "AVA_TITLE_BACK.PVM"}.get(arch)
        if twin in LOGO_ARCHIVES:
            # same picture, other logo: whatever differs is logo (of either language)
            other = Image.new("RGBA", (W, H))
            for p, e in zip(pos, index()[twin][:len(pos)]):
                other.alpha_composite(Image.open(raw_png(twin, e)).convert("RGBA"), p)
            diff = np.abs(rgb.astype(int) - np.asarray(other.convert("RGB")).astype(int)).max(2) > 20
            logo_px = logo_px | diff
        mask[reg & logo_px] = 255
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))  # also under the new logo, so old colours do not bleed back
        pic = Image.fromarray(cv2.inpaint(rgb, mask, 6, cv2.INPAINT_TELEA)).convert("RGBA")
    else:
        pic = Image.new("RGBA", (W, H), (0, 0, 0, 0))     # tiles hold only the logo
    big = pic.resize((W * SCALE, H * SCALE), Image.LANCZOS)
    lg = logo.fit((x1 - x0) * SCALE, (y1 - y0) * SCALE, band=(40, 30, 110), scale=3 * SCALE // 2 + 1, stretch=has_bg)
    big.alpha_composite(lg, (x0 * SCALE, y0 * SCALE))
    return {e["file"]: big.crop((p[0] * SCALE, p[1] * SCALE, (p[0] + t.width) * SCALE, (p[1] + t.height) * SCALE))
            for e, p, t in zip(entries, pos, tiles)}


# Pictures cut into tiles (the adventure-field maps): one spec for the whole picture.
# text/tex/composite/<ARCHIVE stem>.json:
#   {"tiles": ["map_ss_j0.png", ... row-major], "cols": 3, "twin": ["map_ss_e0.png", ...],
#    "erase": [[x0, y0, x1, y1], ...], "blocks": [...same as texture blocks...]}
# Coordinates are in the assembled picture. Inside each erase rect, the pixels that differ
# from the English twin picture (the Japanese label, dilated) are inpainted from around them.
# Optional "thresh" (default 24) and "dilate" (default 5) tune that mask, e.g. to catch a soft glow.
COMPOSITES = SPECS / "composite"


def composite_spec(arch):
    p = COMPOSITES / f"{Path(arch).stem}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def assemble(arch, files, cols):
    ents = {e["file"]: e for e in index()[arch]}
    tiles = [Image.open(raw_png(arch, ents[f])).convert("RGBA") for f in files]
    tw, th = tiles[0].size
    pic = Image.new("RGBA", (tw * cols, th * ((len(tiles) + cols - 1) // cols)))
    for k, t in enumerate(tiles):
        pic.paste(t, ((k % cols) * tw, (k // cols) * th))
    return pic, tw, th


def render_composite(arch, scale=SCALE):
    """(assembled result at scale x, {tile file: tile image})"""
    import numpy as np, cv2
    sp = composite_spec(arch)
    pic, tw, th = assemble(arch, sp["tiles"], sp["cols"])
    if sp.get("erase"):
        rgb = np.asarray(pic.convert("RGB"))
        mask = np.zeros(rgb.shape[:2], np.uint8)
        if sp.get("twin"):
            en = np.asarray(assemble(arch, sp["twin"], sp["cols"])[0].convert("RGB")).astype(int)
            diff = (np.abs(rgb.astype(int) - en).max(2) > sp.get("thresh", 24)).astype(np.uint8) * 255
            k = sp.get("dilate", 5)
            diff = cv2.dilate(diff, np.ones((k, k), np.uint8))
        else:
            diff = np.full(rgb.shape[:2], 255, np.uint8)
        for x0, y0, x1, y1 in sp["erase"]:
            mask[y0:y1, x0:x1] = diff[y0:y1, x0:x1]
        out = cv2.inpaint(rgb, mask, 5, cv2.INPAINT_TELEA)
        a = np.asarray(pic)[..., 3:]
        pic = Image.fromarray(np.dstack([out, a]), "RGBA")
    big = pic.resize((pic.width * scale, pic.height * scale), Image.LANCZOS)
    for b in sp.get("blocks", []):
        draw_block(big, b, scale)
    tiles = {}
    for k, f in enumerate(sp["tiles"]):
        x, y = (k % sp["cols"]) * tw * scale, (k // sp["cols"]) * th * scale
        tiles[f] = big.crop((x, y, x + tw * scale, y + th * scale))
    return big, tiles


def cmd_composite(arch_stem, mode="preview"):
    """show: assembled original with a grid; preview: original above, result below."""
    arch = next(a for a in index() if Path(a).stem == arch_stem)
    dst = ROOT / "work/tex/composite"; dst.mkdir(parents=True, exist_ok=True)
    sp = composite_spec(arch)
    if mode == "show":
        files = sp["tiles"] if sp else [e["file"] for e in index()[arch]][:6]
        pic = assemble(arch, files, sp["cols"] if sp else 3)[0]
        z = 2
        big = pic.resize((pic.width * z, pic.height * z), Image.NEAREST).convert("RGB")
        d = ImageDraw.Draw(big); f = ImageFont.truetype(FONT, 11)
        for x in range(0, pic.width, 20):
            d.line([(x * z, 0), (x * z, big.height)], fill=(255, 0, 255) if x % 100 == 0 else (110, 50, 110))
            if x % 100 == 0: d.text((x * z + 2, 2), str(x), fill=(255, 255, 0), font=f)
        for y in range(0, pic.height, 20):
            d.line([(0, y * z), (big.width, y * z)], fill=(255, 0, 255) if y % 100 == 0 else (110, 50, 110))
            if y % 100 == 0: d.text((2, y * z + 2), str(y), fill=(255, 255, 0), font=f)
        big.save(dst / f"{arch_stem}_show.png"); print(dst / f"{arch_stem}_show.png")
        return
    big, _ = render_composite(arch)
    orig = assemble(arch, sp["tiles"], sp["cols"])[0]
    w, h = orig.size
    out = Image.new("RGBA", (w, h * 2 + 6), (70, 70, 90, 255))
    out.alpha_composite(orig, (0, 0)); out.alpha_composite(big.resize((w, h), Image.LANCZOS), (0, h + 6))
    out.save(dst / f"{arch_stem}_preview.png"); print(dst / f"{arch_stem}_preview.png")


def build_into(out):
    """Write texture packs / PVRs for every archive that has a translated texture."""
    u = index()
    changed_arch = 0
    for arch, entries in u.items():
        todo = [e for e in entries if spec(e["id"]) and not spec(e["id"]).get("keep")]
        logos = logo_tiles(arch) if arch in LOGO_ARCHIVES else {}
        if composite_spec(arch):
            logos.update(render_composite(arch)[1])
        if not todo and not logos:
            continue
        changed_arch += 1
        stem = Path(arch).stem
        if arch.upper().endswith(".PVM"):
            # replacetex/: per-texture replacement inside the game's own PVM. It works on
            # every load path (a textures/ pack is skipped when the game loads a PVM with
            # njLoadTexturePvmFile, e.g. the title logo) and ships only what changed.
            d = out / "replacetex" / stem
            d.mkdir(parents=True, exist_ok=True)
            lines = []
            for e in entries:
                sp = spec(e["id"])
                if e["file"] in logos:
                    logos[e["file"]].save(d / e["file"])
                elif sp and not sp.get("keep"):
                    render(e["id"]).save(d / e["file"])
                else:
                    continue
                lines.append(f"{e['gbix']},{e['file']},{e['size']}")
            (d / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            e = entries[0]
            work = ROOT / "work/tex/pvr"; work.mkdir(parents=True, exist_ok=True)
            render(e["id"], scale=1).save(work / f"{stem}.png")
            info = e["pvr"]
            pix = {0: "-1555", 1: "-565", 2: "-4444", 3: "-y422", 6: "-8888"}.get(info["pixel"], "-4444")
            dat = {1: "-tw", 2: "-tw", 9: "-rect", 13: "-recttw"}.get(info["data"], "")
            args = [str(SATOOLS / "TextureTool.exe"), f"{stem}.png", "-pvr", pix] + ([dat] if dat else [])
            if info["gbix"] is not None:
                args += ["-gbix", str(info["gbix"])]
            args += ["-o", f"{stem}.PVR"]
            run(args, work)
            (out / "system").mkdir(parents=True, exist_ok=True)
            shutil.copy2(work / f"{stem}.PVR", out / "system" / arch)
    return {"texture_archives": changed_arch}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd, *args = sys.argv[1:] or ["status"]
    {"extract": cmd_extract, "sheets": cmd_sheets, "status": cmd_status,
     "preview": lambda: cmd_preview(args), "show": lambda: cmd_show(*args),
     "boxes": lambda: cmd_boxes(*args), "composite": lambda: cmd_composite(*args), "colors": lambda: cmd_colors(*args), "render": lambda: [render(t) for t in unique() if spec(t)]}[cmd]()
