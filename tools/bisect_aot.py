#!/usr/bin/env python3
"""Find AOT functions that break a scripted route, by bisection.

Each probe forces a subset of AOT entry PCs to the interpreter through
SNESRECOMP_LLE_INTERP_TARGET_FILE (no rebuild), runs the route headless and
compares the WRAM dump taken at the route's `dump probe` line against a
reference dump from snesref. A probe passes when the dump exists and matches
the reference outside the ignored ranges (stacks, DP scratch).

Usage:
  python tools/bisect_aot.py --exe build/Release/X.exe --rom game.sfc \
      --script short.txt --ref-dump ref_short/probe.wram.bin --work out_dir
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

IGNORE = [(0x0000, 0x000F), (0x00F6, 0x0275), (0x02B4, 0x02B6), (0x02C4, 0x02C4)]


def aot_pcs(manifest: Path) -> list[int]:
    m = json.loads(manifest.read_text(encoding="utf-8"))
    pcs = {n["key"]["pc24"] for n in m["nodes"].values() if n.get("disposition") == "aot_eligible"}
    return sorted(pcs)


def masked(buf: bytes) -> bytes:
    b = bytearray(buf[:0x2000])
    for lo, hi in IGNORE:
        b[lo:hi + 1] = bytes(hi - lo + 1)
    return bytes(b)


class Prober:
    def __init__(self, args):
        self.a = args
        self.ref = masked(Path(args.ref_dump).read_bytes())
        self.n = 0

    def run(self, forced: list[int], label: str) -> tuple[bool, str]:
        self.n += 1
        d = Path(self.a.work) / f"p{self.n:03d}"
        d.mkdir(parents=True, exist_ok=True)
        tf = d / "interp_targets.txt"
        tf.write_text("".join(f"{pc:06X}\n" for pc in forced))
        env = dict(os.environ, SNESRECOMP_LLE_INTERP_TARGET_FILE=str(tf), SNESRECOMP_DUMP_DIR=str(d))
        env.pop("SNESRECOMP_WRAM_TRACE_FILE", None)
        exe = Path(self.a.exe).resolve()
        t0 = time.time()
        try:
            p = subprocess.run([str(exe), "--no-launcher", "--rom", self.a.rom, "--script", self.a.script],
                               cwd=exe.parent, env=env, capture_output=True, text=True,
                               timeout=self.a.timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rc = p.returncode
            (d / "stderr.txt").write_text(p.stderr, encoding="utf-8")
        except subprocess.TimeoutExpired as e:
            rc = "timeout"
            (d / "stderr.txt").write_text((e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or ""), encoding="utf-8")
        dump = d / "probe.wram.bin"
        if not dump.exists():
            ok, why = False, f"no dump (rc={rc})"
        else:
            got = masked(dump.read_bytes())
            diff = [i for i in range(0x2000) if got[i] != self.ref[i]]
            ok = not diff
            why = "match" if ok else f"{len(diff)} bytes differ, first ${diff[0]:04X}"
        print(f"[{self.n:03d}] {label}: forced={len(forced)} -> {'PASS' if ok else 'FAIL'} ({why}, {time.time()-t0:.0f}s)", flush=True)
        return ok, why


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--rom", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--ref-dump", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--manifest", default="src/gen/program_manifest.json")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    pcs = aot_pcs(Path(args.manifest))
    print(f"AOT entry PCs: {len(pcs)}")
    pr = Prober(args)

    base_ok, _ = pr.run([], "baseline (all AOT)")
    if base_ok:
        print("baseline passes - nothing to bisect")
        return
    all_ok, _ = pr.run(pcs, "all forced to interpreter")
    if not all_ok:
        print("fails even fully interpreted - not an AOT body bug")
        return

    # Find a minimal set S of AOT PCs that must stay AOT for the failure:
    # invariant: forcing (pcs - suspects) keeps the failure, forcing everything passes.
    suspects = pcs
    while len(suspects) > 1:
        half = suspects[: len(suspects) // 2]
        rest = suspects[len(suspects) // 2:]
        # keep `half` AOT, force everything else
        forced = [p for p in pcs if p not in set(half)]
        ok, _ = pr.run(forced, f"keep {len(half)} AOT ({half[0]:06X}..{half[-1]:06X})")
        if not ok:
            suspects = half
            continue
        forced = [p for p in pcs if p not in set(rest)]
        ok, _ = pr.run(forced, f"keep {len(rest)} AOT ({rest[0]:06X}..{rest[-1]:06X})")
        if not ok:
            suspects = rest
            continue
        print(f"failure needs AOT from both halves; stopping with {len(suspects)} suspects")
        break
    print("suspects:", " ".join(f"{p:06X}" for p in suspects))
    Path(args.work, "suspects.txt").write_text("".join(f"{p:06X}\n" for p in suspects))


if __name__ == "__main__":
    main()
