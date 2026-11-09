# Super Ghouls 'n Ghosts Recomp

A static recompilation of **Super Ghouls 'n Ghosts** (SNES, USA, 1991) to native
C, built on [snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp).
The 65816 game code is translated ahead of time into C and compiled into a
native executable. Code that cannot be translated safely falls back to the
framework's built-in interpreter.

> **You must legally own a copy of the game.** No ROM data is distributed with
> this project, in the repository or in any release. The recompiled C is
> generated locally from your own copy and is never committed.

## Status

**Early, but playable through Level 1.** Verified against the snes9x emulator
by comparing the game's work RAM ($0000-$1FFF) frame by frame:

| Section | Result |
|---|---|
| Boot, intro, title screen | Identical game state |
| Level 1 (1012 gameplay frames) | Identical game state |
| Death and game over | Identical game state |
| Later levels, bosses, upgrades | Not tested yet |

Known issues:

- **Load-time drift.** During loading phases that run with NMI disabled
  (for example the SPC700 sound upload at `$01:931E`), the recomp takes a few
  frames longer than real hardware (+7 frames after boot, growing slightly
  after each load). Game logic is not affected; this comes from the
  framework's CPU/APU timing model.
- **Interpreted code.** About 1,255 code variants still run in the
  interpreter, mostly behind jump tables that are not resolved yet.

### Recompilation coverage

| | |
|---|---|
| Functions in `recomp/symbols.toml` | 607 |
| Imported from the disassembly | 603 (`emit = true`) |
| Ahead-of-time entry points | 564 |
| Kept interpreted on purpose | 2 (task system, see below) |

### The task system

The game runs its objects as cooperative tasks (coroutines) with eight
separate stacks at `$00F6-$0275`. `current_task_suspend` (`$01:A728`) and
`current_task_remove` (`$01:A717`) switch the stack with `TCS` and resume
another task with `RTL` from a different stack. Static C cannot express that,
so both routines are marked `emit = false` and stay interpreted. The bug was
found with `tools/bisect_aot.py`: the AOT version of `$01:A728` hung the game
at the start of Level 1.

## ROM identity

| | |
|---|---|
| Title | Super Ghouls 'n Ghosts |
| Publisher / Developer | Capcom |
| Year | 1991 |
| Region | USA (North America) |
| Mapping | LoROM |
| Coprocessor | none |
| CRC32 | `6aaba901` |
| SHA-256 | `7468c271d7240cf4e0d08c16e9969a1b1b1caf5adc0e5adc568d93c92651a057` |

`tools/regen.sh` refuses to run against anything else, so a mismatched
revision fails immediately instead of producing subtly wrong output.

## Build

Requirements: CMake, a C/C++ compiler (MSVC on Windows, GCC or Clang
elsewhere), Python 3, Rust (used by the snesrecomp analyzer) and Bash (Git Bash
on Windows).

```sh
git clone --recursive https://github.com/thatkidluke/SuperGhoulsNGhostsSNESRecomp.git
cd SuperGhoulsNGhostsSNESRecomp
bash tools/regen.sh --rom /path/to/sgng_usa.sfc
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j
```

Use a ROM file name without an apostrophe. Git Bash on Windows does not
convert such paths and the setup fails.

`tools/regen.sh` verifies the ROM, generates `src/gen/*.c`, and re-syncs
`recomp/funcs.h` and the `bank*.cfg` files. Re-run it whenever you change
anything under `recomp/`.

## Run

```sh
./build/Release/SuperGhoulsNGhostsSNESRecomp                         # launcher picks the ROM
./build/Release/SuperGhoulsNGhostsSNESRecomp --no-launcher --rom game.sfc  # skip the launcher
```

With no ROM on the command line the build opens the recomp-ui launcher: a ROM
picker with a verification badge, plus display, audio and input settings.

Testing options:

| Option / variable | Effect |
|---|---|
| `--script route.txt` | Plays a scripted input route (`wait`, `press`, `until`, `dump`, `quit`) |
| `SNESRECOMP_WRAM_TRACE_FILE` | Writes per-frame WRAM changes as JSONL |
| `SNESRECOMP_LLE_INTERP_TARGET_FILE` | Forces the listed PCs to the interpreter, no rebuild needed |

## Tools

| Script | Purpose |
|---|---|
| `tools/regen.sh` | ROM to C pipeline (from snesrecomp) |
| `tools/import_disasm_symbols.py` | Imports every `JSR`/`JSL` target from the disassembly into `recomp/symbols.toml`, named after its labels |
| `tools/wram_trace_compare.py` | Compares two WRAM traces (recomp vs. emulator), finds the best frame offset and the first divergence |
| `tools/bisect_aot.py` | Finds the AOT function that breaks a scripted route by bisection |

The reference traces come from `snesref`, the libretro frontend that ships with
snesrecomp (`snesrecomp/tools/snesref`), running the snes9x core with the same
input script.

## Layout

| Path | Contents |
|---|---|
| `recomp/` | Analysis input: `bank*.cfg`, `symbols.toml`, `disassembly-layout.json` (addresses only) |
| `rom_identity.txt` | ROM digests, read by the build, `tools/regen.sh` and CI |
| `src/` | Host code: `main.c`, `game_rtl.c` |
| `src/gen/` | Generated C. Never committed, regenerate locally |
| `snesrecomp/` | Framework submodule |
| `recomp-ui/` | Launcher submodule |
| `tools/` | Pipeline and verification scripts |
| `scripts/` | `package_release.sh`, builds the player zip |
| `framework_pins.txt` | Framework commits this project was scaffolded against |

## Roadmap

1. Resolve the remaining jump tables (the disassembly's `task_fns` tables are
   a good start) to move more code out of the interpreter.
2. Verify later levels, bosses and weapon upgrades against the emulator.
3. Fix the load-time drift in the framework's timing model.

## Credits

- [snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp), the
  recompilation framework
- [recomp-ui](https://github.com/mstan/recomp-ui), the launcher
- FredYeye's Super Ghouls 'n Ghosts disassembly, used for function names and
  boundaries. It is not included in this repository.
- [snes9x](https://github.com/snes9xgit/snes9x), the reference emulator for
  verification

Super Ghouls 'n Ghosts is a trademark of Capcom. This project is not
affiliated with or endorsed by Capcom or Nintendo.

## License

This project's own source is under the PolyForm Noncommercial License 1.0.0
(see `LICENSE`). The framework has its own terms, see `snesrecomp/LICENSE` and
`snesrecomp/THIRD_PARTY_ATTRIBUTION.md`. Neither covers the game data, which
is not distributed here.
