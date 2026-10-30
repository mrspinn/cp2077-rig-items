import argparse
import sys
from pathlib import Path

from . import __version__, build, inputs, templates, toolchain
from .wolvenkit import RuntimeMissing, WolvenKit, WolvenKitError, locate, open_wolvenkit

COMMANDS = {"build", "templates", "setup", "gui"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Double-clicked, or files dropped onto the app: open the window.
    if not argv or (argv[0] not in COMMANDS and not argv[0].startswith("-") and all(Path(a).exists() for a in argv)):
        return _gui(argv)

    ap = argparse.ArgumentParser(prog="rigitems",
                                 description="Turn Unique V framework body rigs into Equipment-EX items you can swap live. "
                                             "Run with no arguments to open the window.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--wolvenkit", metavar="PATH", help="WolvenKit.CLI executable or its folder (default: auto-detect)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="convert rig mods into one Rig Items mod")
    b.add_argument("inputs", nargs="+", help="rig mod .zip/.rar/.7z files, folders, or .archive files")
    b.add_argument("-o", "--output", default="RigItems.zip", help="output mod zip (default: %(default)s)")
    b.add_argument("--rigs", metavar="RIGS_JSON", help="names override file (see README)")
    b.add_argument("--templates", metavar="DIR", help="template folder (default: the bundled rigitems/data/)")
    b.add_argument("--work", metavar="DIR", help="keep intermediate files here (for debugging)")

    t = sub.add_parser("templates", help="regenerate the clean-room templates from your game files")
    t.add_argument("--game", metavar="PATH", help="Cyberpunk 2077 install folder (default: auto-detect)")
    t.add_argument("-o", "--output", metavar="DIR", help="where to write (default: the bundled rigitems/data/)")

    sub.add_parser("setup", help=f"download WolvenKit {toolchain.WK_VERSION} (and .NET if needed) into "
                                 f"{toolchain.data_dir()}")
    g = sub.add_parser("gui", help="open the window")
    g.add_argument("inputs", nargs="*", help="rig mods to start with")

    args = ap.parse_args(argv)
    if args.cmd == "gui":
        return _gui(args.inputs)
    try:
        if args.cmd == "setup":
            return setup(args.wolvenkit)
        wk = open_wolvenkit(args.wolvenkit)
        if args.cmd == "templates":
            game = templates.find_game(args.game)
            print(f"Extracting vanilla templates from {game}")
            print(f"Wrote {templates.generate(wk, game, args.output)}")
            return
        rigs = build.build(args.inputs, args.output, wk, args.rigs, args.templates, args.work)
        print(f"\nBuilt {args.output} with {len(rigs)} item(s). Install it with your mod manager, then in the CET console:\n")
        print("\n".join(build.cet_commands(rigs)))
        print("\nEquip them in Equipment-EX under Left Toes.")
    except (WolvenKitError, inputs.InputError, build.BuildError, toolchain.SetupError, FileNotFoundError) as e:
        sys.stdout.flush()  # keep progress lines ahead of the error when piped
        sys.exit(f"error: {e}")


def _progress(label, done, total):
    pct = f"{done * 100 // total:3d}%" if total else f"{done >> 20} MB"
    print(f"\r  {label}: {pct}", end="" if done < total or not total else "\n", flush=True)


def setup(explicit=None, progress=_progress, log=print):
    """Make sure a working WolvenKit is available, downloading what's missing. Returns the WolvenKit."""
    try:
        exe = locate(explicit)
        log(f"WolvenKit found: {exe}")
    except WolvenKitError:
        log(f"Downloading WolvenKit {toolchain.WK_VERSION} from github.com/WolvenKit...")
        exe = locate(toolchain.install_wolvenkit(progress))
    wk = WolvenKit(exe)
    try:
        version = wk.version()
    except RuntimeMissing:
        log(f"Downloading the .NET {toolchain.DOTNET_CHANNEL} runtime from Microsoft (private copy for WolvenKit)...")
        toolchain.install_dotnet(progress)
        version = wk.version()
    log(f"Ready: WolvenKit {version}")
    return wk


def _gui(paths):
    from . import gui   # tkinter only loads when the window is wanted
    gui.run(paths)
