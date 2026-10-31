# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Rig Items converts Cyberpunk 2077 "Unique V framework" body rigs (from mods the user downloaded) into one standalone mod with an Equipment-EX item per rig in the Left Toes slot. It is a Python 3.10+ package (`rigitems/`, only dependency Pillow, tkinter for the GUI) that drives the external WolvenKit CLI.

## Commands

```
python -m unittest                                   # offline tests; no WolvenKit or game needed (what CI runs)
python -m unittest tests.test_rigitems.Icons.test_bc3_round_trip   # single test
python -m rigitems                                   # GUI window (no args, or only existing file paths as args)
python -m rigitems build <inputs...> -o RigItems.zip [--rigs rigs.json] [--work DIR]
python -m rigitems templates [--game <Cyberpunk 2077 folder>]   # regenerate rigitems/data/ from vanilla files
python -m rigitems setup                             # download WolvenKit 9.1.0 (+ private .NET 10 if missing)
pyinstaller --noconfirm packaging/rigitems.spec      # one-file app in dist/
```

There is no linter config. Real builds need WolvenKit: found via `--wolvenkit`, `$WOLVENKIT_CLI`, the app data dir, PATH, or `WolvenKit*` folders under `~/Games/tools`, `~/tools`, `Downloads`, cwd. `--work DIR` (must be empty) keeps intermediates for debugging.

CI (`.github/workflows/release.yml`) runs tests and PyInstaller on windows-latest and ubuntu-22.04 for every push/PR; a `v*` tag publishes a GitHub release.

## Architecture

The resource chain each item needs, and which the build repoints into `rigitems\<key>\`:

```
TweakXL item Items.rigitem_<key> → factory.csv row → <key>_root.ent → <key>.app → <key>_mesh.ent
  (entAnimatedComponent "deformations") → <key>.animgraph → <key>.rig
```

The animgraph internally references the vanilla/framework `.rig` path; `build.repoint_graph` must swap it and fails if any other `.rig` string remains, otherwise all items would share one rig.

Module roles:
- `inputs.py` — unpack zip/7z/rar/folders, find `.archive` files, detect exactly one `female_plr_deformations.rig/.animgraph` pair per input (one input → one item), derive titles/keys, apply `rigs.json` overrides.
- `build.py` — per rig: extract, copy `.rig`, serialize + repoint animgraph, stamp templates; then factory, localization, icon atlas; deserialize all staged JSON, pack, verify the archive listing, write `.archive.xl`, `r6/tweaks/rigitems.yaml`, zip. Staging works in WolvenKit CR2W-JSON (`stage/<depot path>.json`) and deserializes to `raw/`.
- `templates.py` — clean-room templates generated from **vanilla** game files into `rigitems/data/*.json` with placeholders `@NAME@ @APP@ @MESH@ @RIG@ @GRAPH@`; `SOURCE.md` records the game/WolvenKit versions. Regenerated templates in the user data dir override the bundled ones.
- `cr2w.py` — iterative tree `swap`/`iter_strings` (animgraphs nest past Python's recursion limit, so never recurse), handle renumbering, and generators for localization, inkatlas and BC3 `.xbm` resources written directly as JSON.
- `icons.py` — Pillow-drawn icon atlas and a pure-Python BC3 encoder/decoder.
- `wolvenkit.py` — locate and run the CLI. WolvenKit often exits 0 after logging an error, so `run()` also scans output for `Error`/`Critical`/`Unhandled exception`.
- `toolchain.py` — hash-checked downloads of WolvenKit and .NET into `data_dir()` (`%LOCALAPPDATA%\RigItems` or `~/.local/share/rigitems`).
- `cli.py` (argparse entry, opens GUI when no args/dropped files), `gui.py` (tkinter; worker threads talk to the UI only through a queue), `theme.py` (styling).
- `packaging/app.py` is the PyInstaller entry (absolute import; patches `sys.stdout` for the windowed Windows build). `packaging/nexus_images.py` renders Nexus page images.

## Constraints and non-obvious rules

- **Ship no third-party assets.** Templates must come from vanilla files only (never nutboy's or rig authors' files); WolvenKit is downloaded, never bundled.
- Tweak keeps `placementSlots: - !append OutfitSlots.ToesLeft` on `$base: Items.GenericInnerChestClothing`. Equipment-EX expects [vanilla slot, outfit slot]; replacing the list puts items under Inner Torso.
- Item keys (`Items.rigitem_<key>`) are save-game identity: changing how keys are derived orphans users' existing items. GUI renames change titles only.
- CR2W handle ids are numbered across the whole JSON including `compiledData`; after removing chunks call `cr2w.renumber_handles`.
- WolvenKit `import` doesn't work on Linux for images, hence icons are written as raw BC3 `.xbm` JSON (`TCM_DXTAlpha`). `.xbm` rows are bottom-up: `icons.xbm_bytes` flips before encoding while atlas UVs stay upright.
- WolvenKit CLI quirks: `convert serialize <dir> -o <out>` needs `<out>` to exist and flattens folders. The tested version is 9.1.0 (also hardcoded in `cr2w.WK_JSON_HEADER` and `toolchain`).
- Code must run on both Windows and Linux (depot paths use `\`, filesystem paths use `/`; subprocesses pass `NO_WINDOW`).

## Not yet verified

- In game: icons render upright, items show under Equipment-EX → Left Toes, equip/unequip/swap work, and whether items also appear as torso clothing in the vanilla inventory (if so, try a different `$base` such as `Items.GenericFootClothing`, keeping two placement slots).
- Windows: the `.exe`, GUI, download/extract paths, `tar.exe` for 7z/rar, `CREATE_NO_WINDOW`. `.rar` input is untested everywhere.
- Out of scope so far: first-person rigs (`player_woman_base_deformations.*` is ignored; the `itemsFactoryAppearanceSuffix.Camera` suffix may be a route), male V (`male_plr_deformations`), coexistence with funsix Hot Rigs AXL and bodyelectric AXL.
