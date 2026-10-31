"""Turn what the user downloaded (mod zips/rars/7z, folders, loose .archive files) into rig sources."""
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .wolvenkit import NO_WINDOW

RIG_DIR = r"base\characters\base_entities\woman_base\deformations_rigs"
FRAMEWORK_RIG = RIG_DIR + r"\female_plr_deformations.rig"
FRAMEWORK_GRAPH = RIG_DIR + r"\female_plr_deformations.animgraph"
FPP_RIG = r"base\characters\entities\player\deformations_rigs_wa\player_woman_base_deformations.rig"
PACKED = {".zip", ".7z", ".rar"}
SEVEN_ZIP = ["7z", "7zz", "7za", "C:/Program Files/7-Zip/7z.exe", "C:/Program Files (x86)/7-Zip/7z.exe"]
KEY_RE = re.compile(r"^[a-z0-9_]{1,48}$")
NOISE = re.compile(r"(?:[ _-]+(?:with|w)?[ _-]*(?:uvf|unique[ _-]?v(?:[ _-]?framework)?|framework))+$", re.I)


class InputError(Exception):
    pass


@dataclass
class Rig:
    archive: Path       # the .archive holding the framework rig
    origin: Path        # the input the user passed
    has_fpp: bool       # also ships a first-person rig (ignored: items are third-person only)
    key: str = ""
    title: str = ""


def _seven_zip():
    for c in SEVEN_ZIP:
        if (p := shutil.which(c)) or (os.path.isabs(c) and os.path.isfile(p := c)):
            return p
    return None


def unpack(src, dest):
    dest.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            for m in z.infolist():
                target = (dest / m.filename).resolve()
                if not target.is_relative_to(dest.resolve()):
                    raise InputError(f"{src.name}: refusing unsafe path {m.filename!r}")
            z.extractall(dest)
        return
    tools = [[sz, "x", "-y", f"-o{dest}", str(src)]] if (sz := _seven_zip()) else []
    if src.suffix.lower() == ".rar" and shutil.which("unrar"):
        tools.append(["unrar", "x", "-o+", "-idq", str(src), f"{dest}{os.sep}"])
    # libarchive reads 7z and rar too; Windows 10+ ships it as tar.exe
    for tar in ("bsdtar", "tar") if os.name == "nt" else ("bsdtar",):
        if shutil.which(tar):
            tools.append([tar, "-xf", str(src), "-C", str(dest)])
    for cmd in tools:
        if subprocess.run(cmd, capture_output=True, **NO_WINDOW).returncode == 0:
            return
    raise InputError(f"{src.name}: can't unpack {src.suffix} (install 7-Zip, or extract it yourself and pass the folder)")


def _archives(path, work, n):
    if path.is_dir():
        return sorted(path.rglob("*.archive"))
    ext = path.suffix.lower()
    if ext == ".archive":
        return [path]
    if ext in PACKED:
        dest = work / f"{n:02d}_{path.stem}"
        unpack(path, dest)
        return sorted(dest.rglob("*.archive"))
    raise InputError(f"{path.name}: expected a mod .zip/.rar/.7z, a folder, or an .archive")


def collect(paths, wk, work, log=print):
    """One input yields one rig. Inputs without a framework rig are an error; other archives are skipped."""
    rigs, errors = [], []
    for n, p in enumerate(map(Path, paths)):
        if not p.exists():
            errors.append(f"{p}: not found")
            continue
        try:
            found = []
            for a in _archives(p, work, n):
                listing = {s.lower() for s in wk.list(a)}
                if FRAMEWORK_RIG in listing and FRAMEWORK_GRAPH in listing:
                    found.append(Rig(a, p, FPP_RIG in listing))
                elif any(s.endswith(".rig") for s in listing):
                    log(f"  skip {a.name}: its rigs aren't the Unique V framework rig (NPC/global rig)")
            if not found:
                raise InputError(f"{p.name}: no Unique V framework rig (female_plr_deformations.rig + .animgraph) inside")
            if len(found) > 1:
                names = "\n    ".join(str(r.archive) for r in found)
                raise InputError(f"{p.name}: holds {len(found)} framework rigs; pass the one you want directly:\n    {names}")
            rigs.append(found[0])
        except InputError as e:
            errors.append(str(e))
    if errors:
        raise InputError("\n".join(errors))
    return rigs


def path_hash(depot_path):
    """FNV-1a 64 of the lowercased depot path: how .archive indexes name their files."""
    h = 0xCBF29CE484222325
    for b in depot_path.lower().encode():
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def archive_hashes(path):
    """Path hashes in an .archive's file index, read directly: far faster than a WolvenKit call per archive."""
    with open(path, "rb") as f:
        head = f.read(20)
        if len(head) < 20 or head[:4] != b"RDAR":
            raise InputError(f"{Path(path).name}: not a Cyberpunk .archive")
        index_pos = struct.unpack_from("<Q", head, 8)[0]
        f.seek(index_pos)
        index = f.read(28)   # table offset, size, crc, file count, segment count, dependency count
        if len(index) < 28:
            raise InputError(f"{Path(path).name}: truncated .archive index")
        count = struct.unpack_from("<I", index, 16)[0]
        table = f.read(count * 56)   # 56-byte entries, path hash first
    return {struct.unpack_from("<Q", table, i * 56)[0] for i in range(len(table) // 56)}


def scan_mod_folder(folder, log=print):
    """Every installed framework rig in a game's archive/pc/mod (where Vortex deploys mods), one rig per archive."""
    rigs = []
    for a in sorted(Path(folder).rglob("*.archive")):
        try:
            hashes = archive_hashes(a)
        except (OSError, InputError) as e:
            log(f"  skip {a.name}: {e}")
            continue
        if path_hash(FRAMEWORK_RIG) in hashes and path_hash(FRAMEWORK_GRAPH) in hashes:
            rigs.append(Rig(a, a, path_hash(FPP_RIG) in hashes))
    return rigs


def default_title(stem):
    t = re.sub(r"^\d+[ _-]+", "", stem)            # load-order prefix like "06_"
    t = NOISE.sub("", t)
    t = re.sub(r"[ _]+", " ", t).strip(" -")
    return t or stem


def default_key(title):
    k = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return k[:48].rstrip("_") or "rig"


def load_overrides(path):
    """rigs.json: {"<archive or input file name, or its stem>": {"key": "...", "title": "..."}}."""
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InputError(f"{path}: expected an object mapping file names to {{key, title}}")
    for name, o in data.items():
        if "key" in o and not KEY_RE.match(o["key"]):
            raise InputError(f"{path}: key {o['key']!r} for {name!r} must be lowercase letters, digits, _ (max 48)")
    return {k.lower(): v for k, v in data.items()}


def name_rigs(rigs, overrides):
    used = set()
    for r in rigs:
        o = next((overrides[n.lower()] for n in (r.archive.name, r.archive.stem, r.origin.name, r.origin.stem)
                  if n.lower() in overrides), {})
        r.title = o.get("title") or default_title(r.archive.stem)
        key = o.get("key") or default_key(r.title)
        base, i = key, 2
        while key in used:
            key, i = f"{base}_{i}", i + 1
        used.add(key)
        r.key = key
    return rigs
