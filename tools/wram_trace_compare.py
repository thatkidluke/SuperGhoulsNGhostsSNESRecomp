#!/usr/bin/env python3
"""Compare two per-frame low-WRAM change traces (snesref vs. recomp).

Both traces are JSONL lines {"f": frame, "adr": "0x....", "val": "0x.."}.
The script rebuilds the $0000-$1FFF state after every frame, finds the
frame offset that best aligns both runs and reports the first differing
frame with the addresses that differ.

Usage:
  python tools/wram_trace_compare.py ref.jsonl recomp.jsonl [--ignore 1F00-1FFF] [--max-offset 8]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict

SIZE = 0x2000


def load_states(path: str, frames_limit: int | None = None) -> list[bytes]:
    changes: dict[int, list[tuple[int, int]]] = defaultdict(list)
    last = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            f = rec["f"]
            adr = int(rec["adr"], 16)
            if adr >= SIZE:
                continue
            changes[f].append((adr, int(rec["val"], 16)))
            last = max(last, f)
    if frames_limit:
        last = min(last, frames_limit)
    ram = bytearray(SIZE)
    states = []
    for f in range(1, last + 1):
        for adr, val in changes.get(f, ()):
            ram[adr] = val
        states.append(bytes(ram))
    return states


def parse_ranges(specs: list[str]) -> list[range]:
    out = []
    for s in specs:
        a, _, b = s.partition("-")
        lo = int(a, 16)
        hi = int(b or a, 16)
        out.append(range(lo, hi + 1))
    return out


def masked(state: bytes, ignore: list[range]) -> bytes:
    if not ignore:
        return state
    b = bytearray(state)
    for r in ignore:
        for a in r:
            b[a] = 0
    return bytes(b)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("recomp")
    ap.add_argument("--ignore", nargs="*", default=[], help="hex ranges to ignore, e.g. 1F00-1FFF")
    ap.add_argument("--max-offset", type=int, default=8)
    ap.add_argument("--show", type=int, default=24, help="max differing addresses to print")
    args = ap.parse_args()

    ignore = parse_ranges(args.ignore)
    ref = [masked(s, ignore) for s in load_states(args.ref)]
    rec = [masked(s, ignore) for s in load_states(args.recomp)]
    print(f"frames: ref={len(ref)} recomp={len(rec)}")

    ref_index: dict[bytes, list[int]] = defaultdict(list)
    for i, s in enumerate(ref):
        ref_index[hashlib.sha1(s).digest()].append(i)

    # Best constant offset: recomp frame i corresponds to ref frame i + off.
    best = None
    for off in range(-args.max_offset, args.max_offset + 1):
        n = 0
        while True:
            i = n
            j = i + off
            if i >= len(rec) or j < 0 or j >= len(ref):
                break
            if j >= 0 and rec[i] != ref[j]:
                break
            n += 1
        # count frames matched from the first comparable frame
        start = max(0, -off)
        run = 0
        for i in range(start, len(rec)):
            j = i + off
            if j >= len(ref):
                break
            if rec[i] != ref[j]:
                break
            run += 1
        if best is None or run > best[1]:
            best = (off, run)
    off, run = best
    start = max(0, -off)
    print(f"best offset: recomp frame N == ref frame N{off:+d}; identical for {run} frames from recomp frame {start + 1}")

    first = start + run
    if first + off >= len(ref) or first >= len(rec):
        print("no divergence inside the compared window")
        return
    a, b = rec[first], ref[first + off]
    diffs = [x for x in range(SIZE) if a[x] != b[x]]
    print(f"first divergence: recomp frame {first + 1} vs ref frame {first + off + 1}: {len(diffs)} bytes differ")
    for x in diffs[: args.show]:
        print(f"  ${x:04X}: recomp={a[x]:02X} ref={b[x]:02X}")

    # Does the recomp state show up later/earlier in ref at all? (timing drift)
    h = hashlib.sha1(a).digest()
    if h in ref_index:
        print(f"recomp state at frame {first + 1} equals ref frame(s) {[i + 1 for i in ref_index[h][:5]]}")

    # Overall agreement after divergence, per frame, using the best offset
    total = same = 0
    for i in range(first, len(rec)):
        j = i + off
        if j >= len(ref):
            break
        total += 1
        same += rec[i] == ref[j]
    print(f"after divergence: {same}/{total} frames identical")

    # Persistent vs. transient differing addresses
    counts: dict[int, int] = defaultdict(int)
    for i in range(first, len(rec)):
        j = i + off
        if j >= len(ref):
            break
        for x in range(SIZE):
            if rec[i][x] != ref[j][x]:
                counts[x] += 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[: args.show]
    print("most often differing addresses (frames):")
    for x, c in top:
        print(f"  ${x:04X}: {c}")


if __name__ == "__main__":
    main()
