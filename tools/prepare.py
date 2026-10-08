"""Copy what the build needs from the player's own SADX PC install into source/.

    python tools/prepare.py [--game DIR] [--satools DIR]

  source/split/    text items split out of sonic.exe (SA Tools split.exe, see split_text.py)
  source/system/   *_J.BIN message files, FONTDATA0/1.BIN, and the textures listed in tex/
  source/movie/    RE-JP.mpg
Nothing in the game folder is changed.
"""
import argparse, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME = r"C:/Program Files (x86)/Steam/steamapps/common/Sonic Adventure DX"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--satools", default=r"C:/Users/User/Repo/SATraditional/SA.Tools.x64")
    a = ap.parse_args()
    game = Path(a.game)
    if not (game / "sonic.exe").exists():
        sys.exit(f"sonic.exe not found in {game} (run the SADX Steam -> 2004 conversion first)")
    sysdir = ROOT / "source/system"; sysdir.mkdir(parents=True, exist_ok=True)
    for f in sorted((game / "system").iterdir()):
        n = f.name.upper()
        if n.endswith("_J.BIN") or n.startswith("FONTDATA") or n.endswith((".PVM", ".PVR")):
            shutil.copy2(f, sysdir / f.name)
    (ROOT / "source/movie").mkdir(parents=True, exist_ok=True)
    shutil.copy2(game / "system/RE-JP.mpg", ROOT / "source/movie/RE-JP.mpg")
    # the two clean logo frames tools/logo.py mattes the original logo from
    frames = ROOT / "work/movie/frames"; frames.mkdir(parents=True, exist_ok=True)
    for n in (850, 920):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ROOT / "source/movie/RE-JP.mpg"),
                        "-vf", f"select=eq(n\\,{n})", "-vsync", "0", "-frames:v", "1",
                        str(frames / f"{n:04d}.png")], check=True)
    subprocess.run([sys.executable, str(Path(__file__).parent / "split_text.py"),
                    "--game", a.game, "--satools", a.satools], check=True)


if __name__ == "__main__":
    main()
