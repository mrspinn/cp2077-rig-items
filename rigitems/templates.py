"""Clean-room templates: built from vanilla game files only, with placeholders the build swaps per rig.

`rigitems templates --game <Cyberpunk 2077 folder>` regenerates rigitems/data/ after a game or WolvenKit update.
"""
import copy
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import cr2w, toolchain

TEMPLATE_DIR = Path(__file__).resolve().parent / "data"
NAMES = ("root.ent", "app.app", "mesh.ent", "factory.csv")


def user_template_dir():
    """Where `rigitems templates` writes from the standalone app (which can't change its own files)."""
    return toolchain.data_dir() / "templates"


def default_dir():
    """Regenerated templates in the app folder win over the bundled ones."""
    user = user_template_dir()
    return user if all((user / f"{n}.json").is_file() for n in NAMES) else TEMPLATE_DIR

# Placeholders swapped by the build.
NAME = "@NAME@"
APP = "@APP@"
MESH = "@MESH@"
RIG = "@RIG@"
GRAPH = "@GRAPH@"

# Vanilla sources, by archive.
VANILLA = {
    "basegame_4_gamedata.archive": {
        "root": r"base\gameplay\items\equipment\feet\player_feet_item.ent",
        "factory": r"base\gameplay\factories\items\clothing.csv",
    },
    "basegame_4_appearance.archive": {
        "app": r"base\characters\appearances\player\items\feet\s1_casual_01.app",
        "mesh": r"base\characters\base_entities\woman_base\deformations_rigs\woman_base_deformations.ent",
    },
}
ROOT_COMPONENT_ID = "2034565680883912704"   # id of the "root" external component added to the mesh entity

STEAM_LIBS = ["~/.local/share/Steam", "~/.steam/steam", "C:/Program Files (x86)/Steam", "C:/Program Files/Steam"]
GAME_DIRS = ["~/Games/cyberpunk-2077", "C:/GOG Games/Cyberpunk 2077",
             "C:/Program Files (x86)/GOG Galaxy/Games/Cyberpunk 2077",
             "C:/Program Files/Epic Games/Cyberpunk 2077"]


def load_all(directory=None):
    d = Path(directory) if directory else default_dir()
    missing = [n for n in NAMES if not (d / f"{n}.json").is_file()]
    if missing:
        raise FileNotFoundError(f"templates missing in {d}: {', '.join(missing)} (run `rigitems templates`)")
    return {n.split(".")[0]: cr2w.load(d / f"{n}.json") for n in NAMES}


def find_game(explicit=None):
    candidates = [explicit] if explicit else []
    for lib in STEAM_LIBS:
        lib = Path(lib).expanduser()
        candidates.append(lib / "steamapps/common/Cyberpunk 2077")
        vdf = lib / "steamapps/libraryfolders.vdf"
        if vdf.is_file():
            for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
                candidates.append(Path(p.replace("\\\\", "/")) / "steamapps/common/Cyberpunk 2077")
    candidates += GAME_DIRS
    for c in candidates:
        if c and (Path(c).expanduser() / "archive/pc/content/basegame_4_appearance.archive").is_file():
            return Path(c).expanduser()
    raise FileNotFoundError("Cyberpunk 2077 install not found; pass --game PATH")


def _strip_header(doc):
    doc["Header"]["ArchiveFileName"] = ""
    doc["Header"]["ExportedDateTime"] = cr2w.WK_JSON_HEADER["ExportedDateTime"]
    return doc


def make_root(doc):
    """Vanilla player clothing root entity, appearances replaced by one placeholder appearance."""
    rc = doc["Data"]["RootChunk"]
    rc["appearances"] = [{"$type": "entTemplateAppearance", "appearanceName": cr2w.cname(NAME),
                          "appearanceResource": cr2w.res(APP), "name": cr2w.cname(NAME)}]
    return doc


def make_app(doc):
    """Vanilla clothing app, cut down to one appearance whose only part is the deformations mesh entity."""
    rc = doc["Data"]["RootChunk"]
    a = rc["appearances"][0]
    rc["appearances"] = [a]
    ad = a["Data"]
    ad["name"] = cr2w.cname(NAME)
    ad["components"] = []
    ad["compiledData"]["Data"].update({"Sections": 6, "CruidIndex": -1, "CruidDict": {}, "Chunks": []})
    ad["partsMasks"] = []
    ad["resolvedDependencies"] = []
    ad["looseDependencies"] = []
    ad["inheritedVisualTags"]["tags"] = []
    ad["partsValues"] = [{"$type": "appearanceAppearancePart", "resource": cr2w.res(MESH)}]
    override = ad["partsOverrides"][0]
    override["partResource"] = cr2w.res(None)
    co = override["componentsOverrides"][0]
    override["componentsOverrides"] = [co]
    co["componentName"] = cr2w.cname("deformations")
    co["meshAppearance"] = cr2w.cname("default")
    return cr2w.renumber_handles(doc)  # dropped appearances leave gaps


def make_mesh(doc):
    """Vanilla woman_base deformations entity, plus a "root" external component the animated component binds to."""
    rc = doc["Data"]["RootChunk"]
    root = {"$type": "entExternalComponent", "externalComponentName": cr2w.cname("root"),
            "id": ROOT_COMPONENT_ID, "isReplicable": 0, "name": cr2w.cname("Component")}
    binding = {"$type": "entAnimationControlBinding", "bindName": cr2w.cname("root"), "enabled": 1,
               "enableMask": {"$type": "entTagMask",
                              "excludedTags": {"$type": "redTagList", "tags": [cr2w.cname("NoBinding")]},
                              "hardTags": {"$type": "redTagList", "tags": []},
                              "softTags": {"$type": "redTagList", "tags": []}}}

    def patch(components, handle):
        deform = next(c for c in components if c["$type"] == "entAnimatedComponent")
        deform["controlBinding"] = handle
        deform["rig"] = cr2w.res(RIG, "Obligatory")
        deform["graph"] = cr2w.res(GRAPH, "Obligatory")
        components.insert(components.index(deform), copy.deepcopy(root))

    # Handle ids are shared across the whole file: compiledData defines the binding as handle 0,
    # the top-level component refers back to it, and the entity moves up to 1.
    pkg = rc["compiledData"]["Data"]
    patch(pkg["Chunks"], {"HandleId": "0", "Data": binding})
    ids = [c["id"] for c in pkg["Chunks"] if "id" in c]
    pkg["CruidDict"] = {str(i): v for i, v in enumerate(["0", *ids])}
    patch(rc["components"], {"HandleRefId": "0"})
    rc["entity"]["HandleId"] = "1"
    return doc


def make_factory(doc):
    rc = doc["Data"]["RootChunk"]
    rc["compiledData"] = []
    rc["data"] = []
    return doc


def generate(wk, game, out=None, keep_raw=None):
    out = Path(out) if out else (user_template_dir() if getattr(sys, "frozen", False) else TEMPLATE_DIR)
    work = Path(keep_raw) if keep_raw else Path(tempfile.mkdtemp(prefix="rigitems-tpl-"))
    try:
        for archive, files in VANILLA.items():
            regex = "^(" + "|".join(re.escape(p) for p in files.values()) + ")$"
            wk.extract(Path(game) / "archive/pc/content" / archive, work / "raw", regex)
        sources = {k: p for files in VANILLA.values() for k, p in files.items()}
        for kind, depot in sources.items():
            f = work / "raw" / depot.replace("\\", "/")
            if not f.is_file():
                raise FileNotFoundError(f"vanilla file not extracted: {depot}")
            wk.serialize(f, work / "json")
        made = {"root": make_root, "app": make_app, "mesh": make_mesh, "factory": make_factory}
        ext = {"root": "ent", "app": "app", "mesh": "ent", "factory": "csv"}
        out.mkdir(parents=True, exist_ok=True)
        for kind, fn in made.items():
            name = os.path.basename(sources[kind].replace("\\", "/"))
            doc = _strip_header(cr2w.load(work / "json" / f"{name}.json"))
            cr2w.dump(out / f"{kind}.{ext[kind]}.json", fn(doc))
        lines = ["Generated by `rigitems templates` from vanilla game files:", ""]
        lines += [f"- {k}: `{p}`" for k, p in sources.items()]
        lines += ["", f"WolvenKit CLI: {wk.version()}", f"Game: {game_version(game)}", ""]
        (out / "SOURCE.md").write_text("\n".join(lines), encoding="utf-8")
    finally:
        if not keep_raw:
            shutil.rmtree(work, ignore_errors=True)
    return out


def game_version(game):
    game = Path(game)
    parts = []
    exe = game / "bin/x64/Cyberpunk2077.exe"
    if exe.is_file():
        data = exe.read_bytes()
        key = "FileVersion".encode("utf-16-le") + b"\0\0"
        i = data.rfind(key)
        if i >= 0:
            j = i + len(key)
            j += j % 4                                       # value is 32-bit aligned
            end = data.find(b"\0\0", j)
            end += (end - j) % 2
            parts.append("Cyberpunk2077.exe " + data[j:end].decode("utf-16-le", "replace").strip("\0"))
    acf = game.parent.parent / "appmanifest_1091500.acf"
    if acf.is_file() and (m := re.search(r'"buildid"\s+"(\d+)"', acf.read_text())):
        parts.append(f"Steam build {m.group(1)}")
    return ", ".join(parts) or "unknown"
