"""The vlog edit step: a small, fixed vocabulary, applied with
ffmpeg between the screening memo and the screening itself.

The director (Luna, the one with memory) writes one line in her
screening memo:

    編集：トリミング：1.0-4.0、速度：0.5、ループ、表紙：2.5

Vocabulary (nothing else is understood):
  そのまま          no edit (also the default when the line is absent)
  トリミング：A-B   keep seconds A..B
  速度：X           playback speed X (0.5 = half speed, 2 = double)
  ループ            boomerang: forward then reverse, duration doubles
  表紙：T           a cover still taken at T seconds of the EDITED cut

Application order is fixed: trim -> speed -> loop. The cover is
taken from the final edited file. An edit that fails raises; the
caller closes the request as failed and #vlog stays clean — an
unedited cut is never screened silently in its place.
"""

import re
import subprocess
from pathlib import Path


def parse_edit_spec(text: str | None) -> dict:
    spec = {"trim": None, "speed": None, "loop": False, "cover": None,
            "raw": (text or "").strip()}
    if not text:
        return spec
    for token in re.split(r"[、,\s]+", text.strip()):
        if not token or token == "そのまま":
            continue
        if token == "ループ":
            spec["loop"] = True
            continue
        m = re.match(r"トリミング[:：](\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", token)
        if m:
            spec["trim"] = (float(m.group(1)), float(m.group(2)))
            continue
        m = re.match(r"速度[:：](\d+(?:\.\d+)?)", token)
        if m:
            spec["speed"] = float(m.group(1))
            continue
        m = re.match(r"表紙[:：](\d+(?:\.\d+)?)", token)
        if m:
            spec["cover"] = float(m.group(1))
            continue
        raise ValueError(f"編集の指定が分からなかった: {token}")
    if spec["trim"] is not None and spec["trim"][1] <= spec["trim"][0]:
        raise ValueError("トリミングの終了が開始より前になっている")
    if spec["speed"] is not None and spec["speed"] <= 0:
        raise ValueError("速度は正の数で")
    return spec


def is_passthrough(spec: dict) -> bool:
    return (spec["trim"] is None and spec["speed"] is None
            and not spec["loop"] and spec["cover"] is None)


def _has_audio(path: Path) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _atempo_chain(speed: float) -> str:
    parts = []
    s = speed
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    while s > 100.0:
        parts.append("atempo=100.0")
        s /= 100.0
    parts.append(f"atempo={s}")
    return ",".join(parts)


def apply_edit(src: Path, spec: dict, out: Path) -> Path:
    """Render the edited cut to `out`. Raises on any failure."""
    has_audio = _has_audio(src)
    cmd = ["ffmpeg", "-y"]
    if spec["trim"] is not None:
        cmd += ["-ss", str(spec["trim"][0])]
    cmd += ["-i", str(src)]
    if spec["trim"] is not None:
        cmd += ["-t", str(spec["trim"][1] - spec["trim"][0])]
    vfilters: list[str] = []
    afilters: list[str] = []
    if spec["speed"] is not None:
        vfilters.append(f"setpts=PTS/{spec['speed']}")
        if has_audio:
            afilters.append(_atempo_chain(spec["speed"]))
    if spec["loop"]:
        # Boomerang needs a graph rather than a chain.
        graph = "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[v]"
        if vfilters:
            graph = ("[0:v]" + ",".join(vfilters) + "[vx];"
                      + graph.replace("[0:v]", "[vx]", 1))
        if has_audio:
            agraph = "[0:a]asplit[x][y];[y]areverse[ra];[x][ra]concat=n=2:v=0:a=1[au]"
            if afilters:
                agraph = ("[0:a]" + ",".join(afilters) + "[ax];"
                          + agraph.replace("[0:a]", "[ax]", 1))
            graph += ";" + agraph
            cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[au]"]
        else:
            cmd += ["-filter_complex", graph, "-map", "[v]"]
    elif vfilters or afilters:
        if vfilters:
            cmd += ["-vf", ",".join(vfilters)]
        if afilters:
            cmd += ["-af", ",".join(afilters)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac"] if has_audio else ["-an"]
    cmd += [str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not out.exists():
        tail = (proc.stderr or "")[-400:]
        raise RuntimeError(f"ffmpeg edit failed: {tail}")
    return out


def extract_cover(video: Path, at_seconds: float, out: Path) -> Path:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video),
         "-frames:v", "1", str(out)],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"cover extraction failed: {(proc.stderr or '')[-200:]}")
    return out
