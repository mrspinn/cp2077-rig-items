"""Locate and drive the user's own WolvenKit CLI (never bundled)."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import toolchain

EXE_NAMES = ("WolvenKit.CLI.exe", "WolvenKit.CLI") if os.name == "nt" else ("WolvenKit.CLI", "WolvenKit.CLI.exe")
TESTED_VERSION = "9.1.0"

# Keep the GUI app from flashing a console window for every WolvenKit call.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

# WolvenKit often exits 0 after logging an error, so the log is checked too.
_FAILED = re.compile(r"\b(Error|Critical)\s*\]|Unhandled exception")


class WolvenKitError(RuntimeError):
    pass


class RuntimeMissing(WolvenKitError):
    """WolvenKit is there but the .NET runtime it needs isn't (fix: toolchain.install_dotnet)."""


def _search_dirs():
    home = Path.home()
    dirs = [Path.cwd(), home / "Games/tools", home / "tools", home / ".local/share", home / "Downloads"]
    if os.name == "nt":
        for var in ("LOCALAPPDATA", "ProgramFiles", "USERPROFILE"):
            if os.environ.get(var):
                dirs.append(Path(os.environ[var]))
        dirs.append(Path("C:/tools"))
    return dirs


def _exe_in(folder):
    for name in EXE_NAMES:
        if (folder / name).is_file():
            return folder / name
    return None


def locate(explicit=None):
    """Find WolvenKit.CLI: --wolvenkit, then $WOLVENKIT_CLI, then PATH, then wolvenkit* folders in common places."""
    for given in (explicit, os.environ.get("WOLVENKIT_CLI")):
        if given:
            p = Path(given).expanduser()
            exe = _exe_in(p) if p.is_dir() else (p if p.is_file() else None)
            if not exe:
                raise WolvenKitError(f"WolvenKit CLI not found at {p}")
            return exe
    if exe := _exe_in(toolchain.wolvenkit_dir()):   # installed by `rigitems setup` / the app
        return exe
    for name in EXE_NAMES:
        if found := shutil.which(name):
            return Path(found)
    for d in _search_dirs():
        if not d.is_dir():
            continue
        for sub in sorted(d.glob("[Ww]olven[Kk]it*"), reverse=True):  # newest version name first
            if sub.is_dir() and (exe := _exe_in(sub)):
                return exe
    raise WolvenKitError(
        "WolvenKit CLI not found. Run `rigitems setup` to download it, or get the WolvenKit.Console build from "
        "https://github.com/WolvenKit/WolvenKit/releases and pass --wolvenkit PATH or set WOLVENKIT_CLI.")


class WolvenKit:
    def __init__(self, exe):
        self.exe = Path(exe)
        if os.name != "nt" and not os.access(self.exe, os.X_OK):
            raise WolvenKitError(f"{self.exe} is not executable (try: chmod +x '{self.exe}')")

    def run(self, *args):
        r = self._call(*args)
        if r.returncode != 0 or _FAILED.search(r.stdout):
            raise WolvenKitError(f"WolvenKit failed: {' '.join(map(str, args))}\n{r.stdout}\n{r.stderr}".rstrip())
        return r.stdout

    def _call(self, *args):
        r = subprocess.run([str(self.exe), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=toolchain.runtime_env(), **NO_WINDOW)
        if r.returncode != 0 and toolchain.missing_runtime(r.stdout + r.stderr):
            raise RuntimeMissing(f"WolvenKit needs the .NET {toolchain.DOTNET_CHANNEL} runtime. "
                                 "Run `rigitems setup` to download a private copy, or install it from "
                                 "https://dotnet.microsoft.com/download")
        return r

    def version(self):
        return self._call("--version").stdout.strip().split("+")[0]

    def list(self, archive):
        """Depot paths inside an .archive (unresolved hashes come back as numbers)."""
        return [ln.strip() for ln in self.run("archive", "-l", archive).splitlines()
                if ln.strip() and not ln.lstrip().startswith("[")]

    def extract(self, archive, out, regex):
        Path(out).mkdir(parents=True, exist_ok=True)
        self.run("extract", archive, "-o", out, "-r", regex)

    def serialize(self, path, out):
        Path(out).mkdir(parents=True, exist_ok=True)
        self.run("convert", "serialize", path, "-o", out)

    def deserialize(self, path, out):
        Path(out).mkdir(parents=True, exist_ok=True)
        self.run("convert", "deserialize", path, "-o", out)

    def pack(self, folder, out):
        Path(out).mkdir(parents=True, exist_ok=True)
        self.run("pack", folder, "-o", out)


def open_wolvenkit(explicit=None):
    wk = WolvenKit(locate(explicit))
    v = wk.version()
    if v and not v.startswith(TESTED_VERSION.rsplit(".", 1)[0]):
        print(f"note: WolvenKit {v} found; templates were made with {TESTED_VERSION}. "
              "If the build fails, regenerate them with `rigitems templates`.", file=sys.stderr)
    return wk
