# Rig Item Converter for Cyberpunk 2077 — Design

**Date:** 2026-10-30
**Status:** In progress. The build runs end to end and its output checks out offline; in-game testing is next. See [Implementation Status](#implementation-status).

## Overview

A tool that turns any "Unique V framework" body rig into its own equippable item for Equipment-EX. You can install many rigs at once and swap between them in-game without restarting.

The tool ships **no third-party assets**. Users run it on rig mods they downloaded themselves. That makes it publishable, unlike the personal proof of concept, which repackages other authors' files.

## Context

### The problem

- Vanilla has one deformation rig per body type, shared by V and every NPC with that body.
- Johnson's Unique V framework (mod 3725, now nutboy's ArchiveXL version, mod 29927) points V at a separate fixed path: `base\characters\base_entities\woman_base\deformations_rigs\female_plr_deformations.rig` and `.animgraph`.
- Every framework rig ships at that same path, so only one can be installed at a time. Testing a rig means toggling it in the mod manager and relaunching.
- The equippable framework only toggles that one path on and off.

### Proof of concept (working, personal use only)

- Location: `~/Games/rig-items-build/` (`build.py`, `rigs.json`).
- It produced 6 working items, each in the Left Toes slot and swappable live: Aphrodite, Aphrodite (Angel breasts), Hyst Angel Edition, mengleten, mengleten (Angel breasts), Brickhouse PAWG.
- Tooling: WolvenKit CLI 9.1.0 (Linux build), run as `convert serialize`, `convert deserialize` and `pack`.
- **Not publishable as-is:** it copies nutboy's entity, app and icon files as templates, plus the rig authors' `.rig` and `.animgraph` files.

### Resource chain per item

```
TweakXL item (Items.<name>)  entityName/appearanceName
  → factory.csv row          name → root entity path
  → root .ent                appearance → .app
  → .app                     appearance → mesh .ent
  → mesh .ent                entAnimatedComponent "deformations": rig + graph
  → .animgraph               internal reference to the .rig path
  → .rig
```

The conversion repoints the last three links to a unique folder per rig: `rigitems\<key>\<key>.rig`, `<key>.animgraph`, `<key>_mesh.ent`, `<key>.app` and `<key>_root.ent`. The animgraph contains the vanilla `woman_base_deformations.rig` path internally. It must be repointed too, or every item resolves to the same rig.

## Implementation Status

Updated 2026-10-30. This section is a handoff: it records what exists, what was learned, and what to do next.

### Environment

- **Game:** `~/.local/share/Steam/steamapps/common/Cyberpunk 2077`, with `Cyberpunk2077.exe` FileVersion 3.0.5813403 and Steam build 26161058. The proof-of-concept `zz_rigitems.archive` and `r6/tweaks/rigitems.yaml` are installed there. The new build uses the same file and item names (`Items.rigitem_<key>`), so it replaces them.
- **WolvenKit CLI 9.1.0:** `~/Games/tools/wolvenkit-cli-9.1.0/WolvenKit.CLI`. Set `WOLVENKIT_CLI` to this path; auto-detect also checks `~/Games/tools/wolvenkit*`.
- **Python 3.14** with Pillow 13. numpy is not installed. `7z`, `unrar` and `bsdtar` are on PATH.
- **Test inputs:** the 6 proof-of-concept rigs as `.archive` files, at `~/Games/rig-items-build/dl/<mod>_<file>/x/archive/pc/mod/*.archive`. The original zips (`pkg/`) were deleted.
- **Vanilla extracts:** `~/Games/rig-items-build/vanilla/`, raw files plus `json/`. Scratch only.
- **Test build for in-game checks:** `~/Games/rig-items-build/RigItems-cleanroom.zip`, built from the 6 test archives with `~/Games/rig-items-build/rigs-cleanroom.json`, which keeps the proof-of-concept keys (`aphrodite`, `hyst_angel`, …). Items already in the save carry over.

### Findings

- **nutboy's templates are lightly edited vanilla files**, so clean-room templates reproduce them exactly:
  - The root entity is `base\gameplay\items\equipment\feet\player_feet_item.ent` (same components; only the appearances, one component id and an empty `visualTagsSchema` differ).
  - The app follows `base\characters\appearances\player\items\feet\s1_casual_01.app`, cut down to one appearance. Its part is the mesh entity and its partsOverride targets component `deformations` with appearance `default`.
  - The mesh entity is `base\characters\base_entities\woman_base\deformations_rigs\woman_base_deformations.ent` plus an `entExternalComponent` named `Component` (externalComponentName `root`). The `entAnimatedComponent` gets a `controlBinding` with bindName `root`, enabled, and excluded tag `NoBinding`.
  - The factory is vanilla `base\gameplay\factories\items\clothing.csv` with its rows replaced.
  - Vanilla sources live in `basegame_4_gamedata.archive` (root entity, csv) and `basegame_4_appearance.archive` (app, deformations entity).
- **WolvenKit `import` fails on Linux** for PNG, TGA and DDS ("invalid data or color space"), because DirectXTex has no native Linux library. Icons are therefore written as `.xbm` JSON directly, with raw BC3 bytes base64-encoded in `textureData.Bytes`, and then deserialized. The format follows nutboy's `.xbm`, except for one setting: nutboy's uses `TCM_QualityColor`, which is likely BC7, so this tool sets `TCM_DXTAlpha` to get BC3. The packed `.xbm` round-trips through WolvenKit and decodes to the right image. **Not yet verified in game.**
- **`WolvenKit.CLI archive -l` lists the rig paths by name** for every test archive, so detection works on the listing. Five of the six test rigs also ship first-person rigs (`base\characters\entities\player\deformations_rigs_wa\player_woman_base_deformations.*`). Hyst Angel does not.
- **Other rig-item mods** (funsix hotrigs, glym/corruptedfiles AXL) use the same pattern: `$base: Items.GenericInnerChestClothing`, `placementSlots: - !append OutfitSlots.ToesLeft`, and `appearanceSuffixes: [ itemsFactoryAppearanceSuffix.Camera ]`. The Camera suffix gives separate first- and third-person appearances, which may be a route to the first-person question below.
- **Handle ids are numbered across the whole CR2W JSON**, compiledData included. In the mesh entity, compiledData defines the `controlBinding` as `HandleId 0` and the top-level component points back at it with `HandleRefId "0"`. Defining it twice would duplicate the id. When appearances are dropped from the app, `cr2w.renumber_handles` closes the gaps.
- **Template diff vs nutboy (done):** the only differences are the root component id, the compiledData `Flags` (we keep vanilla's), `visualTagsSchema` (null in vanilla) and DismWoundConfig (23 vs 39). All four templates survive a deserialize → serialize round trip unchanged.
- **WolvenKit CLI quirks:** `convert serialize <dir> -o <out>` needs `<out>` to exist and flattens the folder structure. `unbundle` unpacks a whole archive.
- **BC3:** a min/max bounding-box encoder turned cyan+red blocks grey. The encoder now tries every pair of block colours as endpoints, weighted by alpha. That costs ~8s for 40 icons. A few three-colour blocks stay off; this is inherent to BC3.
- **`.xbm` rows are stored bottom-up**, but atlas UVs refer to the upright image. The first in-game test showed upside-down icons. nutboy's texture decodes upside down too, and on vanilla `item_icons0` the parts only cover whole icons once the texture is flipped. `icons.xbm_bytes` flips the image before encoding, and the UVs stay as they are.

### Code written (`rigitems/` package, run with `python -m rigitems`)

| File | Purpose |
|---|---|
| `wolvenkit.py` | Finds the CLI (`--wolvenkit`, `$WOLVENKIT_CLI`, PATH, `wolvenkit*` folders in common places). `run()` raises on a non-zero exit, an `Error`/`Critical` log tag, or "Unhandled exception". Wraps list, extract, serialize, deserialize and pack. Warns when the major.minor version isn't 9.1. |
| `cr2w.py` | Iterative `swap` and `iter_strings`, load/dump, the Header/Data `wrap`, and generators for the localization JsonResource, the `inkatlas` (slot 0 = 4K texture with parts, slot 1 = 1080 texture, slot 2 = empty) and the BC3 `xbm`. |
| `icons.py` | Pillow drawing of a rig-skeleton icon (cyan bones, red volumes) with the item title wrapped to 2 lines. 160px cells, 8 per row; the 1080 atlas is half size. Includes a pure-Python BC3 encoder (best endpoint pair, alpha-weighted) and decoder. |
| `templates.py` | `rigitems templates [--game]` extracts the vanilla files, serializes them, applies `make_root`, `make_app`, `make_mesh` and `make_factory`, and writes `rigitems/data/{root.ent,app.app,mesh.ent,factory.csv}.json` (package data, so pip installs ship it) plus `SOURCE.md` with the game and WolvenKit versions. Placeholders: `@NAME@ @APP@ @MESH@ @RIG@ @GRAPH@`. Headers are cleared of local paths. Also detects the game folder from Steam libraries, GOG and Epic paths. |
| `inputs.py` | Unpacks zip (with a path-traversal check), or 7z and rar (via 7z, unrar, then bsdtar). Collects `.archive` files and detects the framework pair. Skips archives with only non-framework `.rig` files. Errors on an input with no framework rig, or with more than one (one input → one item). Builds titles and keys from the archive name: strips load-order prefixes and suffixes like `With_UVF` and `With_Framework`; keys are lowercase with underscores, max 48 characters, deduplicated with `_2`. Takes `rigs.json` overrides as `{"<archive/input name or stem>": {"key", "title"}}`. |
| `build.py` | `rigitems build <inputs...> -o RigItems.zip [--rigs] [--templates] [--work]`. Per rig: extracts the pair, copies the `.rig`, serializes the animgraph, and repoints both the vanilla and the framework rig paths. Fails if any other `.rig` string is left. Then stages mesh, app and root from the templates, followed by the factory, localization, icons and atlas. It deserializes everything, packs, renames to `zz_rigitems.archive`, and checks the archive listing against the expected files. Finally it writes `.archive.xl`, `r6/tweaks/rigitems.yaml` and the zip. `cet_commands()` prints one line per item plus a Lua "add all" loop. `--work` refuses a non-empty folder. |
| `cli.py`, `__main__.py`, `__init__.py` | argparse entry point. |

**Tweak written per item:** base `Items.GenericInnerChestClothing`, `placementSlots: - !append OutfitSlots.ToesLeft`, `appearanceSuffixes: []`, and icon part = item key.

### Done on 2026-10-30

1. Templates generated (`rigitems/data/`, game 3.0.5813403 / Steam build 26161058). Fixed the duplicate top-level `controlBinding` handle and renumbered the app's handles.
2. Diffed against the proof of concept. Only the expected differences remain (see Findings).
3. End-to-end build of the 6 test archives (~2.5 min). The packed archive was unbundled, re-serialized, and the chain was walked for every item: factory → root → app → mesh → animgraph → rig. Each animgraph references only its own `.rig`, all 6 rigs are distinct, and icon parts, localization and tweak names line up. Zip, 7z and folder inputs work. A zip with no rig, an archive with only non-framework rigs, and a missing file each fail with a clear message. **Not tested:** `.rar` input (no `rar` here to make one).
4. Tests: `tests/test_rigitems.py`, 17 offline `unittest` cases covering naming, overrides, zip traversal, deep swap, `repoint_graph`, handle renumbering, BC3 round trip, atlas UVs and template integrity. Run with `python -m unittest`.
5. Packaging: `pyproject.toml` (a `pip install .` was checked in a venv: the `rigitems` script works and the templates ship), `README.md`, `.gitignore`, and `rigitems.bat` for drag and drop on Windows.

6. **Standalone app for Windows and Linux** (so users don't need Python):
   - `rigitems/gui.py` is a tkinter window: add files or folders, rename (names saved to `names.json` in the app folder; item IDs never change), build, then copy the CET "add all" line. Workers talk to the UI only through a queue. Another agent is restyling it.
   - `rigitems/toolchain.py` + `rigitems setup` / the **Set up WolvenKit** button download WolvenKit 9.1.0 from GitHub (sha256 pinned). If WolvenKit reports the .NET 10 runtime missing, they also download a private copy from Microsoft's release metadata (sha512 checked) and run WolvenKit with `DOTNET_ROOT`. Both go in the app folder (`%LOCALAPPDATA%\RigItems` or `~/.local/share/rigitems`). Nothing is bundled or installed system-wide.
   - The app opens the window when it has no arguments or only file arguments (files dropped onto the .exe). Otherwise it's the normal CLI.
   - `packaging/rigitems.spec` (PyInstaller one-file; windowed on Windows) and `.github/workflows/release.yml` (tests, then builds on windows-latest and ubuntu-22.04; a `v*` tag publishes a release). Licence: MIT.
   - **Tested here:** setup from a fresh home with .NET hidden via `bwrap` (download, runtime detection, private runtime, full build); the GUI driven under Xvfb (scan, build, first-run setup); and the PyInstaller Linux binary (CLI build plus the window with a dropped file).

### Not done yet (in order)

1. **In-game checks (user)** with `~/Games/rig-items-build/RigItems-cleanroom.zip`. It replaces the installed proof-of-concept `zz_rigitems.archive`, its `.xl` and `r6/tweaks/rigitems.yaml`:
   - icons render upright (rebuilt 2026-10-30 with the bottom-up fix, see Findings)
   - items appear in Equipment-EX under Left Toes (fixed 2026-10-30, see Findings: the first clean-room test put them under Inner Torso)
   - whether they also show as torso clothing in the vanilla inventory. If so, try a different `$base`, for example `Items.GenericFootClothing`, since Toes depends on the Feet slot. Keep two placement slots.
   - equip, unequip and swap all work
2. **Licence:** MIT (`LICENSE`, 2026-10-30).
3. **Windows is untested:** the `.exe` build, the GUI on Windows, the download/extract paths, `tar.exe` for 7z/rar, and `CREATE_NO_WINDOW`. Push to GitHub and run the workflow, then try the artifact on a Windows PC or VM.
4. **Publish:** create the GitHub repo, tag `v0.1.0`, and put the Nexus page together (a tool / modder's resource that links to the GitHub releases).
5. Later: first-person rigs (Camera suffix route), male V, coexistence checks (see Testing).

## Design Decisions

- **Clean-room templates.** Build the root entity, app and mesh entity from **vanilla game files** (an existing clothing item entity plus the vanilla deformations component), not nutboy's files. Generate them in code or from WolvenKit-serialized vanilla JSON committed as templates.
- **Own icons.** Draw a new icon atlas. Ideally add a per-item label, or at least use a neutral "Body Rig" icon.
- **Left Toes slot, appended.** Keep `!append OutfitSlots.ToesLeft` on the base record's slot. Equipment-EX expects `placementSlots` = [vanilla slot, outfit slot]. With a single entry, its `PatchCustomItems` appends an outfit slot guessed from the equipment area, and it uses the last slot. Replacing the list with `[ OutfitSlots.ToesLeft ]` put the items under Inner Torso. The vanilla equipment area comes from `$base`, not from `placementSlots`. So keeping the items out of the vanilla torso inventory needs a different `$base`, not a shorter slot list.
- **Input = what the user already has.** Accept mod zips, rars or 7z files, or loose `.archive` files. Detect rigs by finding `female_plr_deformations.rig/.animgraph` inside them. One input produces one item.
- **Output = one standalone mod.** `archive/pc/mod/zz_rigitems.archive` plus its `.xl` and `r6/tweaks/rigitems.yaml`, zipped for any mod manager. It needs only ArchiveXL, TweakXL and Equipment-EX, and no Unique V framework.
- **Item naming.** Keys and titles come from the archive name, with an optional `rigs.json` override. The CET command for each item is printed, plus a one-line "add all" loop.
- **Don't bundle WolvenKit.** The user downloads the official WolvenKit CLI and the tool locates it. That avoids license and packaging questions and keeps WolvenKit updates separate.

## Implementation Steps

### 1. Clean-room templates

1. Extract a vanilla clothing item's root entity, app and mesh entity, plus the vanilla female deformations rig, animgraph and component, using `WolvenKit.CLI extract` and `convert serialize`.
2. Build minimal templates that reproduce the proof of concept's chain with no nutboy-derived data.
3. Diff the result against the proof-of-concept output to confirm the same component type and fields: `entAnimatedComponent`, name `deformations`, and the `root` control binding.

### 2. Icons

Make a small atlas (`.inkatlas` plus 1080p and standard `.xbm`) by importing PNGs with `WolvenKit.CLI import`.

### 3. Converter

1. Generalize `build.py` into a CLI: `rigitems build <inputs...> -o RigItems.zip`.
2. Unpack the inputs (zip, rar, 7z), find the `.archive` files, run `extract`, and locate the rig pair.
3. Keep the iterative JSON path-swap (animgraphs nest past Python's recursion limit). Keep the WolvenKit error checks.
4. Fail clearly when an input has no framework rig, and skip `.archive` files that only touch NPC or global rigs.

### 4. Slot fix

Switch to a Left-Toes-only item definition and confirm it no longer appears in the vanilla torso inventory.

### 5. Packaging and UX

- Write a README with WolvenKit setup, usage and the CET commands.
- Linux and Windows. WolvenKit has both CLI builds, so the paths and executable name are the main differences.
- Possible later addition: a simple GUI or drag-and-drop wrapper for players who won't use a terminal.

### 6. Release

Publish on Nexus as a **modder's resource or tool**, with credit and links to the framework and to Equipment-EX. Pitch it to rig authors as "ship your rig as an item," so they can publish items themselves.

## Testing

For each converted rig, check in-game:
- The item appears in Equipment-EX → Left Toes.
- Equipping it changes V's third-person body (mirror, photo mode).
- Unequipping it restores the base body.
- Swapping straight from one rig to another works.

Regression set: the 6 proof-of-concept rigs, plus a rig without first-person files (Hyst Angel Edition) and one that has them (Aphrodite).

Coexistence:
- Works alongside funsix Hot Rigs AXL (mod 30039) and bodyelectric AXL (mod 32924).
- Check behaviour with the Equippable and Always Equipped Unique V framework enabled, and document any conflicts.

## Open Questions / Risks

- **First-person rigs.** Some rigs also ship `player_woman_base_deformations.rig/.animgraph` for first person. The proof of concept ignores them, so first person stays at the base body. Can a per-item first-person override work, or should it stay documented as "TPP only"?
- **Male V.** The proof of concept is female-only. `male_plr_deformations` would follow the same pattern.
- **Framework interaction.** funsix says to remove the Unique V framework. bodyelectric's AXL items say they need the Equippable one. Confirm whether our items care either way. The expectation is no.
- **Game patches.** Changes to vanilla entity or component layouts could break the templates. Pin and record the game version they were built from.
- **Rig-author expectations.** The tool is legal to share, but some authors forbid derivatives, for example bodyelectric. The README should tell users to respect each rig's permissions and keep converted output private unless the author allows otherwise.
