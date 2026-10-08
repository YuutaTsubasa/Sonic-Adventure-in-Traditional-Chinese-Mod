"""The Chinese title logo 「索尼克大冒險DX」 in the style of the Japanese one.

The Japanese logo is matted out of the opening movie (the same logo appears over black
at frame 850 and over white at frame 920), its katakana part is removed, and the
Chinese lines are drawn in the same layers: yellow/white faces, a cyan rim, a navy band
and a black edge, all slanted like the original. The DX letters stay.

    python tools/logo.py            -> work/movie/logo_zh.png (+ previews on black/white)

make(scale) returns the RGBA logo in the coordinates of the movie crop
(x 0..640, y 140..360 of the 640x480 frame) at `scale`x.
"""
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "work/movie/frames"
FONT = r"C:/Windows/Fonts/NotoSansTC-VF.ttf"
CROP = (0, 140, 640, 360)
SHEAR = 0.21


def matte():
    """RGBA of the Japanese logo (crop coords) from the black and white frames."""
    B = np.asarray(Image.open(FRAMES / "0850.png").convert("RGB").crop(CROP)).astype(float)
    W = np.asarray(Image.open(FRAMES / "0920.png").convert("RGB").crop(CROP)).astype(float)
    a = np.clip(1 - (W - B).mean(2) / 252.0, 0, 1)
    col = np.clip((B - 1 * (1 - a[..., None])) / np.maximum(a[..., None], 1e-3), 0, 255)
    col[a < 0.02] = 0
    return np.dstack([col, a * 255]).astype(np.uint8)


def d_left(y):
    """Left edge of the D (crop coords): everything left of it is the katakana block."""
    return 404 - (y - 20) * 0.25


def text_mask(text, size, weight, stretch, spacing, scale):
    f = ImageFont.truetype(FONT, size * scale)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    w = int(sum(f.getlength(c) for c in text) + spacing * scale * (len(text) - 1)) + 40 * scale
    h = int(size * scale * 1.5)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    x = 20 * scale
    for c in text:
        d.text((x, 0), c, font=f, fill=255)
        x += f.getlength(c) + spacing * scale
    m = m.crop(m.getbbox())
    m = m.resize((int(m.width * stretch), m.height), Image.LANCZOS)
    # slant like the original italic
    pad = int(m.height * SHEAR) + 2
    m2 = Image.new("L", (m.width + pad, m.height), 0)
    m2.paste(m, (0, 0))
    return m2.transform(m2.size, Image.AFFINE, (1, SHEAR, -SHEAR * m.height, 0, 1, 0), Image.BICUBIC)


def grad(size, top, bottom):
    w, h = size
    t = np.linspace(0, 1, h)[:, None, None]
    c = np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t
    return Image.fromarray(np.repeat(c, w, 1).astype(np.uint8), "RGB")


def layer_line(canvas, mask, pos, face, scale, rim=(40, 170, 235), band=(12, 28, 84)):
    """Draw one text line with rim, band, black edge onto RGBA canvas at pos (top-left)."""
    W, H = canvas.size
    full = Image.new("L", (W, H), 0)
    full.paste(mask, pos)
    def grow(m, r):
        r = max(1, int(r * scale))
        return m.filter(ImageFilter.MaxFilter(2 * r + 1)) if r < 12 else \
            m.filter(ImageFilter.GaussianBlur(r * 0.6)).point(lambda v: 255 if v > 18 else 0)
    def close(m, r):
        r = int(r * scale)
        return m.filter(ImageFilter.GaussianBlur(r)).point(lambda v: 255 if v > 60 else 0)
    band_m = close(grow(full, 9), 4)
    edge_m = grow(band_m, 3)
    rim_m = grow(full, 3.2)
    for m, color in ((edge_m, (0, 0, 0)), (band_m, band), (rim_m, rim)):
        canvas.paste(Image.new("RGBA", (W, H), color + (255,)), (0, 0), m)
    canvas.paste(face if isinstance(face, Image.Image) else Image.new("RGBA", (W, H), face + (255,)),
                 (0, 0), full)


def make(scale=1, plate=False, band=(12, 28, 84)):
    """plate: keep the old katakana silhouette as a solid navy plate (for logos drawn
    over a picture, where the old letters cannot be erased cleanly)."""
    base = Image.fromarray(matte(), "RGBA").resize((640 * scale, 220 * scale), Image.LANCZOS)
    a = np.asarray(base).copy()
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    left = xs < np.vectorize(d_left)(ys / scale) * scale
    old = Image.fromarray(((a[..., 3] > 100) & left).astype(np.uint8) * 255, "L")
    a[left] = 0
    # デラックス: turn its white glyphs black (a black label), the new label goes on top
    box = (slice(86 * scale, 122 * scale), slice(424 * scale, 600 * scale))
    sub = a[box]
    white = (sub[..., :3].min(-1) > 150) & (sub[..., 3] > 100)
    sub[white, :3] = 0
    a[box] = sub
    out = Image.fromarray(a, "RGBA")
    # a black label box over the old reading, slanted like the rest
    lb = Image.new("L", out.size, 0)
    sk = SHEAR * 32 * scale
    ImageDraw.Draw(lb).polygon([(428 * scale + sk, 87 * scale), (604 * scale + sk, 87 * scale),
                                (604 * scale, 121 * scale), (428 * scale, 121 * scale)], fill=255)
    lb = lb.filter(ImageFilter.GaussianBlur(1.2 * scale))
    out.paste(Image.new("RGBA", out.size, (0, 0, 0, 255)), (0, 0), lb)
    if plate:
        old = old.filter(ImageFilter.GaussianBlur(6 * scale)).point(lambda v: 255 if v > 40 else 0)
        edge = old.filter(ImageFilter.MaxFilter(2 * max(1, int(2 * scale)) + 1))
        out.paste(Image.new("RGBA", out.size, (0, 0, 0, 255)), (0, 0), edge)
        out.paste(Image.new("RGBA", out.size, band + (255,)), (0, 0), old)

    l1 = text_mask("索尼克", 78, 900, 1.2, 14, scale)
    l2 = text_mask("大冒險", 56, 900, 1.25, 26, scale)
    canvas = Image.new("RGBA", out.size, (0, 0, 0, 0))
    # slanted panels with the old block's footprint: black edge, navy band, cyan rim
    def panel(x0, x1, y0, y1, grow):
        m = Image.new("L", out.size, 0)
        sk = SHEAR * (y1 - y0)
        g = grow * scale
        ImageDraw.Draw(m).rounded_rectangle([0, 0, 1, 1], 0)  # (keeps PIL import order stable)
        poly = [((x0 + sk) * scale - g, y0 * scale - g), ((x1 + sk) * scale + g, y0 * scale - g),
                (x1 * scale + g, y1 * scale + g), (x0 * scale - g, y1 * scale + g)]
        ImageDraw.Draw(m).polygon(poly, fill=255)
        return m.filter(ImageFilter.GaussianBlur(2.5 * scale)).point(lambda v: 255 if v > 128 else 0)
    P1, P2 = (46, 384, 26, 110), (26, 396, 116, 178)
    for (x0, x1, y0, y1) in (P2, P1):
        for grow, col in ((7, (0, 0, 0)), (4, band), (-1, (40, 170, 235)), (-5, band)):
            canvas.paste(Image.new("RGBA", out.size, col + (255,)), (0, 0), panel(x0, x1, y0, y1, grow))
    def centre(mask, box):
        x0, x1, y0, y1 = box
        cx = ((x0 + x1) / 2 + SHEAR * (y1 - y0) / 2) * scale
        cy = (y0 + y1) / 2 * scale
        return (int(cx - mask.width / 2), int(cy - mask.height / 2))
    p1, p2 = centre(l1, P1), centre(l2, P2)
    face2 = Image.new("RGBA", out.size, (255, 255, 255, 255))
    layer_line(canvas, l2, p2, face2, scale, band=band)
    g = grad((out.width, l1.height), (255, 246, 40), (255, 128, 0))
    face1 = Image.new("RGBA", out.size, (0, 0, 0, 0)); face1.paste(g, (0, p1[1]))
    layer_line(canvas, l1, p1, face1, scale, band=band)
    # new small label over the old デラックス
    f = ImageFont.truetype(FONT, 26 * scale)
    try:
        f.set_variation_by_axes([900])
    except Exception:
        pass
    lab = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(lab).text((518 * scale, 104 * scale), "豪 華 版", font=f, anchor="mm", fill=(255, 255, 255, 255),
                             stroke_width=4 * scale, stroke_fill=(0, 0, 0, 255))
    # grey drop shadow (seen only on white), like the original's
    sh = canvas.split()[3].point(lambda v: 90 if v > 0 else 0)
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", out.size, (0, 0, 0, 255)), (int(9 * scale), int(10 * scale)), sh)
    out = Image.alpha_composite(shadow, out)
    out = Image.alpha_composite(out, canvas)
    out = Image.alpha_composite(out, lab)
    return out


def fit(box_w, box_h, plate=False, band=(32, 8, 104), scale=4, stretch=False):
    """The logo cropped to its own bounds and fitted (aspect kept) into box_w x box_h."""
    lg = make(scale, plate=plate, band=band)
    lg = lg.crop(lg.getbbox())
    if stretch:
        lg = lg.resize((box_w, box_h), Image.LANCZOS)
    else:
        k = min(box_w / lg.width, box_h / lg.height)
        lg = lg.resize((round(lg.width * k), round(lg.height * k)), Image.LANCZOS)
    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    out.alpha_composite(lg, ((box_w - lg.width) // 2, (box_h - lg.height) // 2))
    return out


if __name__ == "__main__":
    logo = make(1)
    logo.save(ROOT / "work/movie/logo_zh.png")
    prev = Image.new("RGBA", (640, 440), (0, 0, 0, 255))
    prev.alpha_composite(logo, (0, 0))
    white = Image.new("RGBA", (640, 220), (253, 253, 253, 255)); white.alpha_composite(logo)
    prev.alpha_composite(white, (0, 220))
    prev.resize((1280, 880), Image.LANCZOS).save(ROOT / "work/movie/logo_zh_preview.png")
    print("ok")
