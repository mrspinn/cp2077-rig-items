"""Build one standalone mod with an Equipment-EX item per rig."""
import contextlib
import copy
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import cr2w, icons, inputs, templates as tpl

MOD = "rigitems"
ARCHIVE = "zz_rigitems.archive"
VANILLA_RIG = inputs.RIG_DIR + r"\woman_base_deformations.rig"
DESCRIPTION = "Body rig for V. Equip one at a time to compare body shapes live."

# Equipment-EX reads placementSlots as [vanilla slot, outfit slot]: an item with only one slot gets an
# outfit slot guessed from its equipment area appended (Inner Torso here), so ToesLeft must be appended.
TWEAK = """Items.{name}:
  $base: Items.GenericInnerChestClothing
  placementSlots:
    - !append OutfitSlots.ToesLeft
  entityName: {name}
  appearanceName: {name}
  displayName: {name}
  localizedDescription: {mod}_desc
  appearanceSuffixes: []
  icon:
    atlasResourcePath: {mod}\\icons.inkatlas
    atlasPartName: {key}
  statModifiers:
    - !append Character.ScaleToPlayerLevel
"""


class BuildError(Exception):
    pass


def item_name(key):
    return f"rigitem_{key}"


def paths(key):
    d = f"{MOD}\\{key}"
    return {"dir": d, "rig": f"{d}\\{key}.rig", "graph": f"{d}\\{key}.animgraph",
            "mesh": f"{d}\\{key}_mesh.ent", "app": f"{d}\\{key}.app", "root": f"{d}\\{key}_root.ent"}


def repoint_graph(graph, rig_path):
    """Point the animgraph's internal rig reference at our copy; anything else left would make items share a rig."""
    cr2w.swap(graph, {VANILLA_RIG: rig_path, inputs.FRAMEWORK_RIG: rig_path})
    stray = {s for s in cr2w.iter_strings(graph) if s.lower().endswith(".rig") and s != rig_path}
    if stray:
        raise BuildError(f"animgraph references other rigs: {', '.join(sorted(stray))}")
    return graph


def stage_path(stage, depot):
    return stage / (depot.replace("\\", "/") + ".json")


@contextlib.contextmanager
def _workdir(work):
    """A kept --work folder (must be empty) or a temporary one."""
    if work is None:
        with tempfile.TemporaryDirectory(prefix="rigitems-") as d:
            yield Path(d)
        return
    work = Path(work)
    if work.exists() and any(work.iterdir()):
        raise BuildError(f"--work folder {work} is not empty")
    yield work


def build(rig_inputs, output, wk, overrides=None, template_dir=None, work=None, log=print):
    """Inputs as the user passed them -> output mod zip. Returns the named rigs."""
    with _workdir(work) as w:
        log("Scanning inputs...")
        rigs = inputs.name_rigs(inputs.collect(rig_inputs, wk, w / "inputs", log), inputs.load_overrides(overrides))
        return build_rigs(rigs, output, wk, template_dir, w / "build", log)


def build_rigs(rigs, output, wk, template_dir=None, work=None, log=print):
    """Already scanned and named rigs (see inputs.collect / name_rigs) -> output mod zip."""
    t = tpl.load_all(template_dir)
    with _workdir(work) as w:
        _build(rigs, output, wk, t, w, log)
    return rigs


def _build(rigs, output, wk, t, work, log):
    stage, raw, mod = work / "stage", work / "raw", work / "mod"
    for r in rigs:
        log(f"  {r.key}: {r.title}  <- {r.archive.name}{'  (first-person rig ignored)' if r.has_fpp else ''}")
        p, name = paths(r.key), item_name(r.key)
        src = work / "src" / r.key
        wk.extract(r.archive, src, r"^base\\characters\\base_entities\\woman_base\\deformations_rigs\\"
                                   r"female_plr_deformations\.(rig|animgraph)$")
        rig_dir = src / inputs.RIG_DIR.replace("\\", "/")
        dst = raw / p["dir"].replace("\\", "/")
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy(rig_dir / "female_plr_deformations.rig", dst / f"{r.key}.rig")
        wk.serialize(rig_dir / "female_plr_deformations.animgraph", src / "json")
        graph = cr2w.load(src / "json/female_plr_deformations.animgraph.json")
        cr2w.dump(stage_path(stage, p["graph"]), repoint_graph(graph, p["rig"]))

        swaps = {tpl.NAME: name, tpl.APP: p["app"], tpl.MESH: p["mesh"], tpl.RIG: p["rig"], tpl.GRAPH: p["graph"]}
        for kind in ("mesh", "app", "root"):
            cr2w.dump(stage_path(stage, p[kind]), cr2w.swap(copy.deepcopy(t[kind]), swaps))

    rows = [[item_name(r.key), paths(r.key)["root"], "true"] for r in rigs]
    factory = copy.deepcopy(t["factory"])
    factory["Data"]["RootChunk"]["compiledData"] = rows
    factory["Data"]["RootChunk"]["data"] = copy.deepcopy(rows)
    cr2w.dump(stage_path(stage, f"{MOD}\\factory.csv"), factory)

    loc = {item_name(r.key): f"Rig: {r.title}" for r in rigs}
    loc[f"{MOD}_desc"] = DESCRIPTION
    cr2w.dump(stage_path(stage, f"{MOD}\\localization.json"), cr2w.localization(loc))

    log("Drawing icons...")
    big, small, parts = icons.render_atlas({r.key: r.title for r in rigs})
    cr2w.dump(stage_path(stage, f"{MOD}\\icons.xbm"), cr2w.xbm_bc3(*big.size, icons.xbm_bytes(big)))
    cr2w.dump(stage_path(stage, f"{MOD}\\icons_1080.xbm"), cr2w.xbm_bc3(*small.size, icons.xbm_bytes(small)))
    cr2w.dump(stage_path(stage, f"{MOD}\\icons.inkatlas"),
              cr2w.inkatlas(f"{MOD}\\icons.xbm", f"{MOD}\\icons_1080.xbm", big.size, parts))

    log("Packing...")
    for j in sorted(stage.rglob("*.json")):
        wk.deserialize(j, raw / j.relative_to(stage).parent)
    expected = {str(f.relative_to(stage).with_suffix("")).replace("/", "\\") for f in stage.rglob("*.json")}
    expected |= {str(f.relative_to(raw)).replace("/", "\\") for f in raw.rglob("*.rig")}
    archive_dir = mod / "archive/pc/mod"
    wk.pack(raw, archive_dir)
    packed = next(archive_dir.glob("*.archive"))
    packed.rename(archive_dir / ARCHIVE)
    listed = {s.lower() for s in wk.list(archive_dir / ARCHIVE)}
    if missing := {e for e in expected if e.lower() not in listed}:
        raise BuildError("packed archive is missing: " + ", ".join(sorted(missing)))
    (archive_dir / f"{ARCHIVE}.xl").write_text(
        f"factories:\n  - {MOD}\\factory.csv\n"
        f"localization:\n  onscreens:\n    en-us: {MOD}\\localization.json\n", encoding="utf-8")
    tweaks = mod / "r6/tweaks"
    tweaks.mkdir(parents=True)
    (tweaks / f"{MOD}.yaml").write_text(
        "\n".join(TWEAK.format(name=item_name(r.key), key=r.key, mod=MOD) for r in rigs), encoding="utf-8")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(mod.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(mod).as_posix())


def cet_commands(rigs):
    lines = [f'Game.AddToInventory("Items.{item_name(r.key)}", 1)  -- {r.title}' for r in rigs]
    keys = ", ".join(json.dumps(r.key) for r in rigs)
    lines.append(f'for _, k in ipairs({{{keys}}}) do Game.AddToInventory("Items.rigitem_" .. k, 1) end')
    return lines
