"""One-click setup: download the official WolvenKit CLI (and a private .NET runtime if needed) into the app folder.

Nothing is bundled and nothing is installed system-wide: both come straight from their publishers, are checked
against pinned or published hashes, and live in data_dir().
"""
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

WK_VERSION = "9.1.0"
WK_ASSETS = {  # official WolvenKit release assets (sha256 from the GitHub release)
    "nt": ("WolvenKit.Console-9.1.0.zip", "7caf49cdf0f478b484b1a5a27e5aef261b879fabea7e72e33ca60eff3b834f4f"),
    "posix": ("WolvenKit.ConsoleLinux-9.1.0.zip", "5b3fbdfc7b0236939250ea9987a7ba0bb423c1e37d70c3ba91364c00057bf23b"),
}
WK_URL = "https://github.com/WolvenKit/WolvenKit/releases/download/{version}/{name}"
DOTNET_CHANNEL = "10.0"   # WolvenKit 9.1 targets net10.0
DOTNET_META = "https://builds.dotnet.microsoft.com/dotnet/release-metadata/{channel}/releases.json"
USER_AGENT = "rigitems-setup"


class SetupError(RuntimeError):
    pass


def data_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        return base / "RigItems"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "rigitems"


def wolvenkit_dir():
    return data_dir() / f"wolvenkit-{WK_VERSION}"


def dotnet_dir():
    return data_dir() / "dotnet"


def runtime_env():
    """Environment for running WolvenKit: points it at our private .NET runtime when we installed one."""
    env = dict(os.environ)
    if (dotnet_dir() / "shared/Microsoft.NETCore.App").is_dir():
        env["DOTNET_ROOT"] = str(dotnet_dir())
    return env


def _rid():
    import platform
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if not arch:
        raise SetupError(f"unsupported CPU architecture: {platform.machine()}")
    return ("win-" if os.name == "nt" else "linux-") + arch


def _download(url, dest, algo, digest, progress, label):
    """Stream url to dest, reporting progress(label, done, total); verify the hash before returning."""
    h = hashlib.new(algo)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                progress(label, done, total)
    except OSError as e:
        raise SetupError(f"download failed: {url}\n{e}") from e
    if h.hexdigest().lower() != digest.lower():
        raise SetupError(f"download of {url} is corrupt ({algo} mismatch); try again")


def _replace(staged, final):
    if final.exists():
        shutil.rmtree(final)
    staged.rename(final)


def install_wolvenkit(progress=lambda *a: None):
    name, sha = WK_ASSETS["nt" if os.name == "nt" else "posix"]
    final = wolvenkit_dir()
    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=final.parent) as tmp:
        tmp = Path(tmp)
        _download(WK_URL.format(version=WK_VERSION, name=name), tmp / name, "sha256", sha, progress, "WolvenKit")
        staged = tmp / "wk"
        with zipfile.ZipFile(tmp / name) as z:
            z.extractall(staged)
        if os.name != "nt":
            exe = staged / "WolvenKit.CLI"
            exe.chmod(exe.stat().st_mode | 0o111)
        _replace(staged, final)
    return final


def install_dotnet(progress=lambda *a: None):
    """Private .NET runtime (latest patch of the channel) from Microsoft's official builds."""
    rid = _rid()
    req = urllib.request.Request(DOTNET_META.format(channel=DOTNET_CHANNEL), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            meta = json.load(r)
    except OSError as e:
        raise SetupError(f"can't reach Microsoft's .NET release list\n{e}") from e
    release = next(rel for rel in meta["releases"] if rel["release-version"] == meta["latest-release"])
    ext = ".zip" if os.name == "nt" else ".tar.gz"
    f = next((f for f in release["runtime"]["files"]
              if f["rid"] == rid and f["name"] == f"dotnet-runtime-{rid}{ext}"), None)
    if not f:
        raise SetupError(f"no .NET {DOTNET_CHANNEL} runtime download for {rid}")
    final = dotnet_dir()
    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=final.parent) as tmp:
        tmp = Path(tmp)
        archive = tmp / ("runtime" + ext)
        _download(f["url"], archive, "sha512", f["hash"], progress, ".NET runtime")
        staged = tmp / "dotnet"
        if ext == ".zip":
            with zipfile.ZipFile(archive) as z:
                z.extractall(staged)
        else:
            with tarfile.open(archive) as t:
                t.extractall(staged, filter="data" if sys.version_info >= (3, 12) else None)
        _replace(staged, final)
    return final


def missing_runtime(output):
    """True when WolvenKit's launcher says the .NET runtime it needs isn't installed."""
    text = output.lower()
    return ("you must install .net" in text or "you must install or update .net" in text
            or "framework: 'microsoft.netcore.app'" in text or "the framework 'microsoft.netcore.app'" in text
            or "a fatal error occurred" in text and ".net" in text)
