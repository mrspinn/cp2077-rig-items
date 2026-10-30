"""Night City look for the window: dark panels, neon yellow/cyan/red, cut-corner frames, condensed type."""
import base64
import io
import os
import tkinter as tk
from tkinter import font, ttk

from PIL import Image, ImageDraw

BG = "#0a0b10"
PANEL = "#12141c"
FIELD = "#06070a"
LINE = "#2a2f3d"
FG = "#e6e4d6"
DIM = "#5c6375"
YELLOW = "#fcee0a"
YELLOW_HOT = "#fff45c"
CYAN = "#02d7f2"
RED = "#ff003c"
HOVER = "#1c1d10"

# First installed family wins. Bahnschrift ships with Windows 10+ and is close to the game's UI face.
SANS = ("Bahnschrift", "Rajdhani", "Roboto Condensed", "DejaVu Sans Condensed", "Nimbus Sans Narrow", "Arial Narrow")
MONO = ("Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Courier New")

SUPERSAMPLE = 4


def _pick(root, choices):
    have = set(font.families(root))
    return next((f for f in choices if f in have), None)


def _chamfer(root, cut, line, fill, outline, notch=None):
    """A 9-sliceable box with its top-left and bottom-right corners cut off, as a Tk image.

    Drawn oversized and scaled down so the diagonals are antialiased. `notch` adds a solid tab
    along the top-left cut, the little accent the game puts on its panels.
    """
    edge = cut + line + 2              # the slice border: corners stay sharp however the widget stretches
    size = 2 * edge + 2
    k = SUPERSAMPLE
    img = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(inset, c):
        a, b = inset * k, (size - inset) * k - 1
        c *= k
        return [(a + c, a), (b, a), (b, b - c), (b - c, b), (a, b), (a, a + c)]
    d.polygon(box(0, cut), fill=outline)
    d.polygon(box(line, cut - line * 0.586), fill=fill)   # 2 - sqrt(2): keeps the diagonal stroke as thick as the sides
    if notch:
        t = cut + 3 * line
        d.polygon([(0, cut * k), (cut * k, 0), (t * k, 0), (0, t * k)], fill=notch)
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    photo = tk.PhotoImage(master=root, data=base64.b64encode(buf.getvalue()))
    root.theme_images.append(photo)    # Tk drops an image when its Python object is collected
    return photo, edge


def _element(style, root, name, states, cut, line=1):
    """Register an image element from {state spec: (fill, outline[, notch])}; the first entry is the default."""
    (_, default), *rest = [(spec, _chamfer(root, cut, line, *colors)) for spec, colors in states]
    style.element_create(name, "image", default[0], *[(spec, img) for spec, (img, _) in rest],
                         border=default[1], padding=line + 1, sticky="nsew")
    return default[1]


def _under_fill(layout):
    return [("Rig.background", {"sticky": "nsew", "children": layout})]


def apply(root):
    root.theme_images = []
    px = max(1, round(root.winfo_fpixels("1i") / 96))   # 1 on a normal screen, 2 at 200% scaling

    sans, mono = _pick(root, SANS), _pick(root, MONO)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkCaptionFont", "TkHeadingFont"):
        f = font.nametofont(name, root)
        f.configure(size=10)
        if sans:
            f.configure(family=sans)
    font.nametofont("TkHeadingFont", root).configure(weight="bold")
    # Kept on root: a tkinter Font deletes its Tk font when the Python object is collected.
    family = font.nametofont("TkDefaultFont", root).actual("family")
    bold = font.Font(root, name="RigBold", family=family, size=10, weight="bold")
    title = font.Font(root, name="RigTitle", family=family, size=20, weight="bold")
    root.theme_fonts = (bold, title)
    if mono:
        font.nametofont("TkFixedFont", root).configure(family=mono, size=10)

    root.configure(background=BG)
    # Plain tk widgets, including the tk-drawn file picker on Linux.
    for pattern, value in (("*Background", BG), ("*Foreground", FG), ("*activeBackground", HOVER),
                           ("*activeForeground", YELLOW), ("*selectBackground", YELLOW),
                           ("*selectForeground", BG), ("*insertBackground", YELLOW),
                           ("*highlightBackground", BG), ("*highlightColor", CYAN),
                           ("*Entry.Background", FIELD), ("*Listbox.Background", FIELD),
                           ("*Button.Background", PANEL), ("*Button.Foreground", YELLOW)):
        root.option_add(pattern, value)

    style = ttk.Style(root)
    style.theme_use("clam")   # the native Windows/macOS themes ignore most colors
    style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, troughcolor=FIELD,
                    bordercolor=LINE, lightcolor=BG, darkcolor=BG, focuscolor=CYAN,
                    selectbackground=YELLOW, selectforeground=BG, insertcolor=YELLOW)
    style.map(".", foreground=[("disabled", DIM)])

    style.configure("Dim.TLabel", foreground=DIM)
    style.configure("Status.TLabel", foreground=CYAN)
    style.configure("Title.TLabel", foreground=YELLOW, font=title)
    style.configure("Header.TLabel", foreground=RED, font=bold)
    style.configure("Rule.TFrame", background=RED)

    # Buttons: cut-corner image instead of clam's bevel. Pressed before active: a pressed button is also active.
    _element(style, root, "Rig.Button.border", [
        ((), (PANEL, YELLOW)),
        (("disabled",), (BG, LINE)),
        (("pressed",), (YELLOW, YELLOW)),
        (("active",), (HOVER, CYAN)),
    ], cut=6 * px, line=px)
    _element(style, root, "Rig.Accent.border", [
        ((), (YELLOW, YELLOW)),
        (("disabled",), (PANEL, LINE)),
        (("pressed",), (CYAN, CYAN)),
        (("active",), (YELLOW_HOT, CYAN)),
    ], cut=8 * px, line=px)
    for name, element in (("TButton", "Rig.Button.border"), ("Accent.TButton", "Rig.Accent.border")):
        style.layout(name, _under_fill([(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]))
    style.configure("TButton", background=BG, foreground=YELLOW, padding=(12, 3))
    # Override clam's own state colors, which would show through the cut corners.
    style.map("TButton", background=[("disabled", BG), ("pressed", BG), ("active", BG)],
              foreground=[("disabled", DIM), ("pressed", BG), ("active", CYAN)])
    style.configure("Accent.TButton", foreground=BG, font=bold, padding=(20, 5))
    style.map("Accent.TButton", foreground=[("disabled", DIM), ("!disabled", BG)])

    # Panels: label sits above the box (clam's labeloutside), box has a cut corner and a red notch.
    _element(style, root, "Rig.Labelframe.border", [((), (BG, RED, RED))], cut=12 * px, line=px)
    style.layout("TLabelframe", _under_fill([("Rig.Labelframe.border", {"sticky": "nsew"})]))
    style.configure("TLabelframe.Label", background=BG, foreground=RED, font=bold)

    _element(style, root, "Rig.Entry.field", [
        ((), (FIELD, LINE)),
        (("focus",), (FIELD, CYAN)),
        (("disabled",), (BG, LINE)),
    ], cut=5 * px, line=px)
    style.layout("TEntry", _under_fill([("Rig.Entry.field", {"sticky": "nsew", "children": [
        ("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]})]))
    style.map("TEntry", background=[("disabled", BG), ("focus", BG)])
    style.configure("TEntry", foreground=FG, padding=(8, 4))

    style.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, bordercolor=LINE,
                    lightcolor=FIELD, darkcolor=FIELD, rowheight=24 * px)
    style.map("Treeview", background=[("selected", YELLOW)], foreground=[("selected", BG)])
    style.configure("Treeview.Heading", background=PANEL, foreground=CYAN, bordercolor=LINE,
                    lightcolor=PANEL, darkcolor=PANEL, relief="flat", padding=(6, 4), font=bold)
    style.map("Treeview.Heading", background=[("active", HOVER)])

    style.configure("TScrollbar", background=PANEL, troughcolor=FIELD, bordercolor=FIELD,
                    lightcolor=PANEL, darkcolor=PANEL, arrowcolor=CYAN, gripcount=0)
    style.map("TScrollbar", background=[("active", LINE)], arrowcolor=[("disabled", DIM)])

    # The bar is an image too: as a plain element its color would also be the widget background.
    _element(style, root, "Rig.Progressbar.trough", [((), (FIELD, LINE))], cut=4 * px, line=px)
    _element(style, root, "Rig.Progressbar.pbar", [((), (YELLOW, YELLOW))], cut=3 * px, line=px)
    style.layout("Horizontal.TProgressbar", _under_fill([("Rig.Progressbar.trough", {"sticky": "nsew", "children": [
        ("Rig.Progressbar.pbar", {"side": "left", "sticky": "ns"})]})]))
    style.configure("Horizontal.TProgressbar", background=BG)


def text(widget, color=FG):
    """Style a tk.Text, which ttk themes don't reach."""
    widget.configure(background=FIELD, foreground=color, insertbackground=YELLOW, selectbackground=YELLOW,
                     selectforeground=BG, relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=LINE, highlightcolor=CYAN, font="TkFixedFont", padx=8, pady=6)
    widget.tag_configure("error", foreground=RED)


def dark_title_bar(window):
    """Windows 10 (20H1+) and 11: ask for the dark title bar. Silently does nothing elsewhere."""
    if os.name != "nt":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except (AttributeError, OSError):
        pass


# ---- dialogs: tk's messagebox and simpledialog are native on Windows and can't be themed ----
class Dialog(tk.Toplevel):
    def __init__(self, parent, title, message, buttons=("OK",), header=YELLOW, initial=None):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(background=BG, highlightthickness=1, highlightbackground=header, highlightcolor=header)
        self.transient(parent)
        self.resizable(False, False)
        self.result = self.text = None

        body = ttk.Frame(self, padding=(20, 16))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"// {title.upper()}", style="Header.TLabel", foreground=header).pack(anchor="w")
        ttk.Frame(body, style="Rule.TFrame", height=1).pack(fill="x", pady=(4, 12))
        ttk.Label(body, text=message, wraplength=440, justify="left").pack(anchor="w")
        self.value = None
        if initial is not None:
            self.value = tk.StringVar(self, initial)
            entry = ttk.Entry(body, textvariable=self.value, width=48)
            entry.pack(fill="x", pady=(10, 0))
            entry.select_range(0, "end")
            entry.focus_set()

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(18, 0))
        *others, primary = buttons
        ok = ttk.Button(row, text=primary, style="Accent.TButton", command=lambda: self.close(primary))
        ok.pack(side="right")
        for label in reversed(others):
            ttk.Button(row, text=label, command=lambda l=label: self.close(l)).pack(side="right", padx=(0, 8))
        if self.value is None:
            ok.focus_set()

        self.bind("<Return>", lambda e: self.close(primary))
        self.bind("<Escape>", lambda e: self.close(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self.close(None))

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        dark_title_bar(self)
        self.grab_set()
        self.wait_window()

    def close(self, choice):
        self.result = choice
        if self.value is not None:
            self.text = self.value.get()
        self.grab_release()
        self.destroy()


def error(parent, title, message):
    Dialog(parent, title, message, header=RED)


def confirm(parent, title, message, ok="OK"):
    return Dialog(parent, title, message, buttons=("Cancel", ok)).result == ok


def ask_string(parent, title, prompt, initial=""):
    d = Dialog(parent, title, prompt, buttons=("Cancel", "OK"), initial=initial)
    return d.text if d.result == "OK" else None
