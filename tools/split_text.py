"""Split every text item out of the player's SADX PC files with SA Tools split.exe.

Writes a reduced copy of each PC_SADX split ini (header + text-type sections only)
to work/split_ini/, then runs `split binary` into source/split/.
"""
import argparse, re, subprocess, sys
from pathlib import Path

TEXT_TYPES = {"cutscenetext", "singlestring", "multistring", "tikalhintsingle", "tikalhintmulti",
              "npctext", "triallevellist", "recapscreen", "soundtestlist", "missiontutorial",
              "missiondescription", "stringarray", "fixedstringarray", "creditstextlist",
              "bmitemattrlist", "chaoitemstats"}
ROOT = Path(__file__).resolve().parents[1]

def sections(text):
    head, secs, cur = [], [], None
    for line in text.splitlines():
        m = re.match(r"^\[(.*)\]\s*$", line)
        if m:
            cur = [line]; secs.append(cur)
        elif cur is None:
            head.append(line)
        else:
            cur.append(line)
    return head, secs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=r"C:/Program Files (x86)/Steam/steamapps/common/Sonic Adventure DX")
    ap.add_argument("--satools", default=r"C:/Users/User/Repo/SATraditional/SA.Tools.x64")
    a = ap.parse_args()
    cfg = Path(a.satools) / "GameConfig/PC_SADX"
    out_ini = ROOT / "work/split_ini"; out_ini.mkdir(parents=True, exist_ok=True)
    out = ROOT / "source/split"; out.mkdir(parents=True, exist_ok=True)
    for ini in sorted(cfg.glob("*.ini")):
        head, secs = sections(ini.read_text(encoding="utf-8", errors="replace"))
        keep = [s for s in secs if any(l.strip().lower() in {f"type={t}" for t in TEXT_TYPES} for l in s)]
        if not keep:
            continue
        df = next((l.split("=", 1)[1].strip() for l in head if l.lower().startswith("datafile=")), None)
        if not df:
            print("no datafile", ini.name); continue
        dst = out_ini / ini.name
        dst.write_text("\n".join(head + [l for s in keep for l in s]) + "\n", encoding="utf-8")
        r = subprocess.run([str(Path(a.satools) / "bin/split.exe"), "binary", str(Path(a.game) / df), str(dst), str(out)],
                           input="\n", capture_output=True, text=True)
        print(f"{ini.name}: {len(keep)} items, rc={r.returncode}")
        if r.returncode:
            print(r.stdout[-2000:], r.stderr[-2000:])

main()
