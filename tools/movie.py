"""Opening movie RE-JP.mpg: replace the Japanese title logo with the Chinese one.

The logo is on screen in frames FIRST..LAST (59.94 fps). For each of those frames:
  bg      = the frame's background colour (median), which carries the flashes and fades;
  v       = how visible the logo is, measured against the clean logo over black (850)
            or white (920);
  reveal  = per-line wipe position while the light sweep draws the logo in;
  glare   = the original's light sweep, blurred so its katakana shape disappears;
and the frame is redrawn as bg + v * Chinese logo (masked by the wipe) + glare.
Other frames are passed through; the video is re-encoded to MPEG-1 at the original
size and frame rate, the MP2 audio is copied.

    python tools/movie.py [--preview]      -> work/movie/RE-JP.mpg (+ contact sheet)
"""
import subprocess, sys
import numpy as np
from pathlib import Path
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import logo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source/movie/RE-JP.mpg"
OUT = ROOT / "work/movie/RE-JP.mpg"
W, H = 640, 480
FIRST, LAST = 786, 937
Y0 = logo.CROP[1]
LINE1, LINE2 = (25, 115), (115, 182)   # crop rows of the two katakana lines
REVEAL_END = 813                         # wipe finished, DX flash follows


def frames():
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(SRC), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)


class Logo:
    def __init__(self):
        zh = logo.make(1)
        self.zh = np.asarray(zh).astype(float) / 255.0          # crop-size RGBA
        jp = logo.matte()
        self.jp_a = jp[..., 3].astype(float) / 255.0
        ref = np.asarray(Image.open(logo.FRAMES / "0850.png").convert("RGB")).astype(float)
        self.ref_dark = np.abs(ref[Y0:Y0 + 220] - 1).mean()
        refw = np.asarray(Image.open(logo.FRAMES / "0920.png").convert("RGB")).astype(float)
        self.ref_white = np.abs(refw[Y0:Y0 + 220] - 253).mean()

    def frame(self, f, n):
        img = f.astype(float)
        crop = img[Y0:Y0 + 220]
        bg = np.median(img.reshape(-1, 3), axis=0)
        lum = bg.mean()
        ref = self.ref_dark if lum < 128 else self.ref_white
        v = np.clip(np.abs(crop - bg).mean() / ref, 0, 1)
        a = self.zh[..., 3:4].copy()
        glare = np.zeros_like(crop)
        if n < REVEAL_END:
            # wipe: how far each line is lit in the original (left to right)
            lit = (np.abs(crop - bg).mean(2) > 60)
            mask = np.zeros((220, 640, 1))
            for (r0, r1) in (LINE1, LINE2):
                cols = np.nonzero(lit[r0:r1].any(0))[0]
                if len(cols):
                    x1 = cols.max() + 24
                    ramp = np.clip((x1 - np.arange(640)) / 24.0, 0, 1)
                    mask[r0 - 12 if r0 > 30 else 0:r1 + (12 if r1 < 182 else 38), :, 0] = ramp
            dx = np.arange(640)[None, :] >= np.vectorize(logo.d_left)(np.arange(220))[:, None] - 6
            mask[dx] = 0                         # DX comes in with the flash, not the sweep
            a = a * mask
            v = 1.0
            g = Image.fromarray(np.clip(crop - bg, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(14))
            glare = np.asarray(g).astype(float) * 1.6
        out = crop * 0 + bg
        out = out * (1 - a * v) + self.zh[..., :3] * 255 * a * v
        out = np.clip(out + glare, 0, 255)
        if 884 <= n <= 892:                     # the flash smears the logo sideways
            sm = Image.fromarray(out.astype(np.uint8)).filter(ImageFilter.BoxBlur(0))
            k = int(6 + (n - 884) * 3)
            arr = np.asarray(sm).astype(float)
            out = sum(np.roll(arr, s, 1) for s in range(-k, k + 1, 2)) / len(range(-k, k + 1, 2))
        res = img.copy()
        res[:Y0] = bg; res[Y0 + 220:] = bg
        res[Y0:Y0 + 220] = out
        return res.astype(np.uint8)


def main():
    preview = "--preview" in sys.argv
    lg = Logo()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not preview:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", "60000/1001", "-i", "-", "-i", str(SRC),
                                "-map", "0:v", "-map", "1:a", "-c:a", "copy",
                                "-c:v", "mpeg1video", "-q:v", "2", "-qmin", "1", "-maxrate", "15000k", "-bufsize", "1835k", "-mbd", "rd", "-trellis", "2",
                                "-g", "15", "-bf", "2", "-f", "mpeg", str(OUT)], stdin=subprocess.PIPE)
    sheet = []
    for n, f in enumerate(frames()):
        if FIRST <= n <= LAST:
            f = lg.frame(f, n)
            if (n - FIRST) % 6 == 0:
                sheet.append(Image.fromarray(f).resize((256, 192)))
        elif preview and n > LAST:
            break
        if not preview:
            enc.stdin.write(f.tobytes())
    if not preview:
        enc.stdin.close(); enc.wait()
    cols = 7
    s = Image.new("RGB", (256 * cols, 192 * ((len(sheet) + cols - 1) // cols)))
    for i, t in enumerate(sheet):
        s.paste(t, ((i % cols) * 256, (i // cols) * 192))
    s.save(ROOT / "work/movie/logo_zh_seq.png")
    print("done", OUT if not preview else "(preview)")


def build_into(out):
    if not OUT.exists() or OUT.stat().st_mtime < (ROOT / "tools/logo.py").stat().st_mtime:
        return {"movie": "not rendered (run tools/movie.py)"}
    (out / "system").mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(OUT, out / "system/RE-JP.mpg")
    return {"movie": "RE-JP.mpg"}


if __name__ == "__main__":
    main()
