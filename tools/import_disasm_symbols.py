#!/usr/bin/env python3
"""Promote call targets from the SGnG disassembly into recomp/symbols.toml.

Reads the authority JSON (instruction list) and the asar WLA symbol file,
collects every JSR abs / JSL long target, names it from the disassembly
labels and rewrites the [[func]] list. Existing hand-written entries are kept.

Usage:
  python tools/import_disasm_symbols.py --authority authority.json \
      --symbols assembled.sym --toml recomp/symbols.toml [--emit]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

JSR_ABS = 0x20
JSL_LONG = 0x22


def load_labels(sym_path: Path) -> dict[int, str]:
    labels: dict[int, str] = {}
    in_labels = False
    for line in sym_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("["):
            in_labels = line == "[labels]"
            continue
        if not in_labels or not line or line.startswith(";"):
            continue
        m = re.match(r"([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+:?(\S+)", line)
        if not m:
            continue
        name = m.group(3)
        # Skip asar macro-internal and anonymous labels.
        if name.startswith("macro_") or name.startswith(":") or "+" in name or "-" in name:
            continue
        pc = (int(m.group(1), 16) << 16) | int(m.group(2), 16)
        pc &= 0x7FFFFF  # fold FastROM mirror ($80+) onto the LoROM bank
        labels.setdefault(pc, re.sub(r"[^A-Za-z0-9_]", "_", name))
    return labels


def call_targets(authority: dict) -> set[int]:
    targets: set[int] = set()
    for ins in authority["instructions"]:
        raw = bytes.fromhex(ins["bytes"])
        pc = int(ins["pc24"], 16)
        if raw[0] == JSR_ABS and len(raw) == 3:
            targets.add((pc & 0xFF0000) | raw[1] | (raw[2] << 8))
        elif raw[0] == JSL_LONG and len(raw) == 4:
            targets.add(raw[1] | (raw[2] << 8) | (raw[3] << 16))
    return {t & 0x7FFFFF for t in targets if (t & 0xFFFF) >= 0x8000}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authority", required=True, type=Path)
    ap.add_argument("--symbols", required=True, type=Path)
    ap.add_argument("--toml", required=True, type=Path)
    ap.add_argument("--emit", action="store_true", help="mark imported funcs emit = true")
    args = ap.parse_args()

    authority = json.loads(args.authority.read_text(encoding="utf-8"))
    code_pcs = {int(i["pc24"], 16) & 0x7FFFFF for i in authority["instructions"]}
    labels = load_labels(args.symbols)
    targets = sorted(t for t in call_targets(authority) if t in code_pcs)

    text = args.toml.read_text(encoding="utf-8")
    begin, end = "# >>> BEGIN disassembly import", "# <<< END disassembly import"
    # Drop the previous import block first so only hand-written entries count as existing.
    text = re.sub(rf"\n?{re.escape(begin)}.*?{re.escape(end)}\n?", "\n", text, flags=re.S)
    existing = {int(a, 16) | (int(b) << 16)
                for a, b in re.findall(r'addr = "([0-9a-fA-F]+)"\s*\nbank = (\d+)', text)}
    used_names = set(re.findall(r'name = "([^"]+)"', text))

    out = [begin]
    added = 0
    for pc in targets:
        if pc in existing:
            continue
        name = labels.get(pc, f"sub_{pc:06X}")
        if name in used_names:
            name = f"{name}_{pc:06X}"
        used_names.add(name)
        out += ["", "[[func]]", f'name = "{name}"', f'addr = "{pc & 0xFFFF:04x}"',
                f"bank = {pc >> 16}", f"emit = {'true' if args.emit else 'false'}",
                'note = "call target from FredYeye SGnG disassembly"']
        added += 1
    out.append(end)
    args.toml.write_text(text.rstrip() + "\n\n" + "\n".join(out) + "\n", encoding="utf-8", newline="\n")
    named = sum(1 for pc in targets if pc in labels)
    print(f"call targets: {len(targets)} ({named} named), added: {added}")


if __name__ == "__main__":
    main()
