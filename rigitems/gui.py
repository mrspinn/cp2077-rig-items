"""The Rig Items window: add rig mods, name them, build the mod, copy the CET commands."""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import __version__, build, inputs, theme, toolchain
from .cli import setup
from .wolvenkit import RuntimeMissing, WolvenKit, WolvenKitError, locate

REQUIREMENTS = "Needs ArchiveXL, TweakXL, Equipment-EX and Cyber Engine Tweaks in the game."
FILETYPES = [("Rig mods", "*.zip *.7z *.rar *.archive"), ("All files", "*")]


def names_file():
    return toolchain.data_dir() / "names.json"


def load_names():
    try:
        return inputs.load_overrides(names_file())
    except (OSError, ValueError, inputs.InputError):
        return {}


def save_names(names):
    names_file().parent.mkdir(parents=True, exist_ok=True)
    names_file().write_text(json.dumps(names, indent=2), encoding="utf-8")


def default_output():
    downloads = Path.home() / "Downloads"
    return str((downloads if downloads.is_dir() else Path.home()) / "RigItems.zip")


def open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(path)])


class App:
    def __init__(self, root, paths):
        self.root = root
        self.q = queue.Queue()
        self.wk = None
        self.busy = False
        self.rigs = []
        self.names = load_names()
        self.session = Path(tempfile.mkdtemp(prefix="rigitems-gui-"))
        self.scans = 0
        self.pending = list(paths)

        root.title(f"Rig Items {__version__}")
        root.iconphoto(True, tk.PhotoImage(master=root, file=Path(__file__).resolve().parent / "data/icon.png"))
        root.minsize(640, 520)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._layout()
        self.root.after(50, self.poll)
        self.work(self._find_wolvenkit)

    # ---- layout ----
    def _layout(self):
        pad = {"padx": 12, "pady": (10, 0)}
        # Packed first so the growing log can never push it out of the window.
        ttk.Label(self.root, text=REQUIREMENTS, style="Dim.TLabel").pack(side="bottom", anchor="w", padx=12, pady=(0, 10))
        head = ttk.Frame(self.root)
        head.pack(fill="x", padx=12, pady=(8, 0))
        ttk.Label(head, text="RIG ITEMS", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=f"v{__version__}  //  EQUIPMENT-EX BODY RIGS", style="Dim.TLabel"
                  ).pack(side="left", padx=10, pady=(8, 0))
        ttk.Frame(self.root, style="Rule.TFrame", height=2).pack(fill="x", padx=12, pady=(2, 0))
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        self.wk_status = ttk.Label(top, text="Looking for WolvenKit...", style="Status.TLabel")
        self.wk_status.pack(side="left")
        self.locate_btn = ttk.Button(top, text="Locate...", command=self.locate)
        self.setup_btn = ttk.Button(top, text="Set up WolvenKit", command=self.setup)

        box = ttk.LabelFrame(self.root, text="RIGS  //  ONE ITEM EACH")
        box.pack(fill="both", expand=True, **pad)
        cols = ("title", "id", "source")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="extended", height=8)
        for c, label, w in zip(cols, ("In-game name", "Item ID", "From"), (220, 160, 220)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, stretch=True)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        self.tree.bind("<Double-1>", lambda e: self.rename())
        self.tree.bind("<Delete>", lambda e: self.remove())
        bar = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        bar.pack(side="left", fill="y", pady=8)
        self.tree.configure(yscrollcommand=bar.set)
        btns = ttk.Frame(box)
        btns.pack(side="left", fill="y", padx=8, pady=8)
        self.add_btn = ttk.Button(btns, text="Add files...", command=self.add_files)
        self.add_dir_btn = ttk.Button(btns, text="Add folder...", command=self.add_folder)
        self.rename_btn = ttk.Button(btns, text="Rename...", command=self.rename)
        self.remove_btn = ttk.Button(btns, text="Remove", command=self.remove)
        for b in (self.add_btn, self.add_dir_btn, self.rename_btn, self.remove_btn):
            b.pack(fill="x", pady=(0, 6))

        out = ttk.Frame(self.root)
        out.pack(fill="x", **pad)
        ttk.Label(out, text="Save mod as:").pack(side="left")
        self.output = tk.StringVar(value=default_output())
        ttk.Entry(out, textvariable=self.output).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Browse...", command=self.browse).pack(side="left")

        act = ttk.Frame(self.root)
        act.pack(fill="x", **pad)
        self.build_btn = ttk.Button(act, text="BUILD MOD", command=self.build, style="Accent.TButton")
        self.build_btn.pack(side="left")
        self.progress = ttk.Progressbar(act, mode="determinate", length=200)
        self.progress.pack(side="left", fill="x", expand=True, padx=(10, 0))

        self.log_text = tk.Text(self.root, height=9, wrap="word", state="disabled")
        theme.text(self.log_text, theme.CYAN)
        self.log_text.pack(fill="both", expand=True, padx=12, pady=10)

        self.done = ttk.LabelFrame(self.root, text="BUILD COMPLETE")
        ttk.Label(self.done, text="Install the zip with your mod manager, then paste this into the CET console:"
                  ).pack(anchor="w", padx=12, pady=(10, 0))
        self.cet = tk.Text(self.done, height=3, wrap="none")
        theme.text(self.cet, theme.YELLOW)
        self.cet.pack(fill="x", padx=12, pady=(6, 6))
        row = ttk.Frame(self.done)
        row.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(row, text="Copy commands", command=self.copy_cet).pack(side="left")
        ttk.Button(row, text="Open folder", command=lambda: open_folder(Path(self.output.get()).parent)
                   ).pack(side="left", padx=6)
        ttk.Label(row, text="Then equip a rig in Equipment-EX under Left Toes.", style="Dim.TLabel").pack(side="left", padx=6)

        self.refresh()

    # ---- background work: workers only talk to the UI through the queue ----
    def work(self, fn, *args):
        self.set_busy(True)

        def run():
            try:
                fn(*args)
            except Exception as e:   # surfaced in the window, never lost in a thread
                self.q.put(("error", str(e)))
            finally:
                self.q.put(("idle",))
        threading.Thread(target=run, daemon=True).start()

    def log(self, msg):
        self.q.put(("log", msg))

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind, rest = msg[0], msg[1:]
                if kind == "log":
                    self._append(rest[0])
                elif kind == "progress":
                    label, done, total = rest
                    self.progress.configure(mode="determinate", maximum=max(total, 1), value=done)
                    self.wk_status.configure(text=f"Downloading {label}... {done >> 20} / {total >> 20} MB")
                elif kind == "wk":
                    self.wk = rest[0]
                    self.wk_status.configure(text=rest[1])
                elif kind == "need_setup":
                    self.wk_status.configure(text=rest[0])
                    self.setup_btn.pack(side="right")
                    self.locate_btn.pack(side="right", padx=6)
                elif kind == "rigs":
                    self.rigs.extend(r for r in rest[0] if r.archive not in {x.archive for x in self.rigs})
                    self.apply_names()
                elif kind == "built":
                    self.show_done(rest[0])
                elif kind == "error":
                    self._append(f"Error: {rest[0]}", "error")
                    theme.error(self.root, "Error", rest[0])
                elif kind == "idle":
                    self.set_busy(False)
                    if self.pending and self.wk:
                        paths, self.pending = self.pending, []
                        self.scan(paths)
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def _append(self, text, tag=()):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_busy(self, busy):
        self.busy = busy
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
        self.refresh()

    def refresh(self):
        idle = not self.busy
        ready = idle and self.wk is not None
        for b in (self.add_btn, self.add_dir_btn):
            b.state(["!disabled"] if ready else ["disabled"])
        for b in (self.rename_btn, self.remove_btn):
            b.state(["!disabled"] if idle and self.rigs else ["disabled"])
        self.build_btn.state(["!disabled"] if ready and self.rigs else ["disabled"])
        for b in (self.setup_btn, self.locate_btn):
            b.state(["!disabled"] if idle else ["disabled"])

    # ---- WolvenKit ----
    def _find_wolvenkit(self, explicit=None):
        try:
            wk = WolvenKit(locate(explicit))
            version = wk.version()
        except RuntimeMissing:
            self.q.put(("need_setup", f"WolvenKit needs the .NET {toolchain.DOTNET_CHANNEL} runtime."))
            return
        except WolvenKitError:
            self.q.put(("need_setup", "WolvenKit isn't set up yet. It does the actual file conversion."))
            return
        self.q.put(("wk", wk, f"WolvenKit {version}: ready"))

    def setup(self):
        if not theme.confirm(
                self.root, "Set up WolvenKit",
                f"Download WolvenKit {toolchain.WK_VERSION} from github.com/WolvenKit (about 40 MB), plus "
                f"Microsoft's .NET {toolchain.DOTNET_CHANNEL} runtime if your PC doesn't have it (about 35 MB)?\n\n"
                f"They go in {toolchain.data_dir()} and nothing is installed system-wide.", ok="Download"):
            return

        def run():
            wk = setup(progress=lambda *p: self.q.put(("progress", *p)), log=self.log)
            self.q.put(("wk", wk, f"WolvenKit {wk.version()}: ready"))
        self.setup_btn.pack_forget()
        self.locate_btn.pack_forget()
        self.work(run)

    def locate(self):
        exe = filedialog.askopenfilename(title="Find WolvenKit.CLI", parent=self.root,
                                         filetypes=[("WolvenKit CLI", "WolvenKit.CLI*"), ("All files", "*")])
        if exe:
            self.setup_btn.pack_forget()
            self.locate_btn.pack_forget()
            self.work(self._find_wolvenkit, exe)

    # ---- rigs ----
    def add_files(self):
        paths = filedialog.askopenfilenames(title="Add rig mods", filetypes=FILETYPES, parent=self.root)
        if paths:
            self.scan(paths)

    def add_folder(self):
        path = filedialog.askdirectory(title="Add an unpacked rig mod folder", parent=self.root)
        if path:
            self.scan([path])

    def scan(self, paths):
        def run():
            found = []
            for p in paths:
                self.scans += 1
                self.log(f"Scanning {Path(p).name}...")
                try:
                    found += inputs.collect([p], self.wk, self.session / f"in{self.scans}", self.log)
                except inputs.InputError as e:
                    self.log(f"  {e}")
            self.q.put(("rigs", found))
            self.log(f"Found {len(found)} rig(s).")
        self.work(run)

    def apply_names(self):
        inputs.name_rigs(self.rigs, self.names)
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rigs):
            self.tree.insert("", "end", iid=str(i), values=(r.title, build.item_name(r.key), r.origin.name))
        self.refresh()

    def selected(self):
        return [self.rigs[int(i)] for i in self.tree.selection()]

    def rename(self):
        sel = self.selected()
        if len(sel) != 1:
            return
        r = sel[0]
        title = theme.ask_string(self.root, "Rename", "In-game name:", r.title)
        if title and title.strip():
            # Keep the item ID: changing it would make it a different item in the player's inventory.
            self.names[r.archive.name.lower()] = {"key": r.key, "title": title.strip()}
            save_names(self.names)
            self.apply_names()

    def remove(self):
        drop = {id(r) for r in self.selected()}
        self.rigs = [r for r in self.rigs if id(r) not in drop]
        self.apply_names()

    def browse(self):
        p = filedialog.asksaveasfilename(title="Save mod as", defaultextension=".zip", parent=self.root,
                                         initialfile=Path(self.output.get()).name,
                                         initialdir=str(Path(self.output.get()).parent),
                                         filetypes=[("Mod zip", "*.zip")])
        if p:
            self.output.set(p)

    # ---- build ----
    def build(self):
        rigs, output = list(self.rigs), self.output.get()
        self.done.pack_forget()

        def run():
            self.log(f"Building {len(rigs)} item(s)...")
            build.build_rigs(rigs, output, self.wk, log=self.log)
            self.log(f"Saved {output}")
            self.q.put(("built", rigs))
        self.work(run)

    def show_done(self, rigs):
        self.cet.delete("1.0", "end")
        self.cet.insert("1.0", build.cet_commands(rigs)[-1])  # the one-line "add all"
        self.done.pack(fill="x", padx=12, pady=(16, 0), before=self.log_text)

    def copy_cet(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.cet.get("1.0", "end").strip())

    def close(self):
        shutil.rmtree(self.session, ignore_errors=True)
        self.root.destroy()


def run(paths=()):
    if os.name == "nt":
        try:   # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    theme.apply(root)
    App(root, [str(p) for p in paths])
    theme.dark_title_bar(root)
    root.mainloop()


if __name__ == "__main__":
    run(sys.argv[1:])
