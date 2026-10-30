"""Draw the item icon atlas (a rig skeleton plus each item's label) and encode it as BC3."""
import struct

from PIL import Image, ImageDraw, ImageFont

CELL = 160          # icon size on the 4K texture; the 1080p texture is half that
COLS = 8
SS = 4              # supersampling for antialiased lines

CYAN = (94, 246, 255, 255)
RED = (255, 97, 88, 255)
WHITE = (240, 240, 240, 255)
SHADOW = (0, 0, 0, 200)

# A standing figure as a deformation rig: joints (x, y in 0..1) and the bones between them.
JOINTS = {
    "head": (0.50, 0.11), "neck": (0.50, 0.20), "chest": (0.50, 0.30), "waist": (0.50, 0.42),
    "hips": (0.50, 0.50),
    "sh_l": (0.36, 0.23), "sh_r": (0.64, 0.23), "el_l": (0.31, 0.37), "el_r": (0.69, 0.37),
    "wr_l": (0.28, 0.50), "wr_r": (0.72, 0.50),
    "hip_l": (0.40, 0.52), "hip_r": (0.60, 0.52), "kn_l": (0.40, 0.68), "kn_r": (0.60, 0.68),
    "an_l": (0.41, 0.84), "an_r": (0.59, 0.84),
}
BONES = [("head", "neck"), ("neck", "chest"), ("chest", "waist"), ("waist", "hips"),
         ("neck", "sh_l"), ("neck", "sh_r"), ("sh_l", "el_l"), ("el_l", "wr_l"), ("sh_r", "el_r"),
         ("el_r", "wr_r"), ("hips", "hip_l"), ("hips", "hip_r"), ("hip_l", "kn_l"), ("kn_l", "an_l"),
         ("hip_r", "kn_r"), ("kn_r", "an_r")]
# Deformation volumes the rig drives, drawn as outlines around the skeleton.
VOLUMES = [(0.50, 0.31, 0.10, 0.05), (0.50, 0.53, 0.14, 0.07),
           (0.42, 0.63, 0.05, 0.07), (0.58, 0.63, 0.05, 0.07)]


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, OSError):    # Pillow without FreeType: fixed bitmap font
        return ImageFont.load_default()


def _wrap(text, font, width, draw, max_lines=2):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] += "…"
    while lines and draw.textlength(lines[-1], font=font) > width and len(lines[-1]) > 2:
        lines[-1] = lines[-1][:-2] + "…"
    return lines


def draw_icon(label):
    big = CELL * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fig = 0.82 * big        # figure scale; the bottom of the cell is left for the label
    pt = {k: (big / 2 + (x - 0.5) * fig, y * fig) for k, (x, y) in JOINTS.items()}
    for cx, cy, rx, ry in VOLUMES:
        cx = big / 2 + (cx - 0.5) * fig
        d.ellipse([cx - rx * fig, (cy - ry) * fig, cx + rx * fig, (cy + ry) * fig], outline=RED, width=2 * SS)
    for a, b in BONES:
        d.line([pt[a], pt[b]], fill=CYAN, width=3 * SS)
    hx, hy = pt["head"]
    d.ellipse([hx - 9 * SS, hy - 9 * SS, hx + 9 * SS, hy + 9 * SS], outline=CYAN, width=3 * SS)
    for k, (x, y) in pt.items():
        if k != "head":
            d.ellipse([x - 4 * SS, y - 4 * SS, x + 4 * SS, y + 4 * SS], fill=WHITE)
    img = img.resize((CELL, CELL), Image.Resampling.LANCZOS)

    d = ImageDraw.Draw(img)
    font = _font(15)
    lines = _wrap(label, font, CELL - 8, d)
    y = CELL - 4 - 17 * len(lines)
    for line in lines:
        x = (CELL - d.textlength(line, font=font)) / 2
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
            d.text((x + dx, y + dy), line, font=font, fill=SHADOW)
        d.text((x, y), line, font=font, fill=WHITE)
        y += 17
    return img


def render_atlas(labels):
    """labels: {partName: text}. Returns (image, image_1080, {partName: pixel box on image})."""
    names = list(labels)
    cols = min(COLS, len(names))
    rows = -(-len(names) // cols)
    atlas = Image.new("RGBA", (cols * CELL, rows * CELL), (0, 0, 0, 0))
    parts = {}
    for i, name in enumerate(names):
        x, y = i % cols * CELL, i // cols * CELL
        atlas.paste(draw_icon(labels[name]), (x, y))
        parts[name] = (x, y, x + CELL, y + CELL)
    small = atlas.resize((atlas.width // 2, atlas.height // 2), Image.Resampling.LANCZOS)
    return atlas, small, parts


def _rgb565(r, g, b):
    return (r * 31 + 127) // 255 << 11 | (g * 63 + 127) // 255 << 5 | (b * 31 + 127) // 255


def _unpack565(c):
    r, g, b = c >> 11 & 31, c >> 5 & 63, c & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def _alpha_block(alphas):
    a0, a1 = max(alphas), min(alphas)
    if a0 == a1:
        return bytes([a0, a1, 0, 0, 0, 0, 0, 0])
    pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    bits = 0
    for i, a in enumerate(alphas):
        idx = min(range(8), key=lambda j: abs(pal[j] - a))
        bits |= idx << (3 * i)
    return bytes([a0, a1]) + bits.to_bytes(6, "little")


def _palette(c0, c1):
    e0, e1 = _unpack565(c0), _unpack565(c1)
    return [e0, e1, tuple((2 * a + b) // 3 for a, b in zip(e0, e1)), tuple((a + 2 * b) // 3 for a, b in zip(e0, e1))]


def _dist(p, q):
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


def _color_block(pixels):
    # Colour under transparency is invisible, so weight each distinct colour by its total alpha.
    weight = {}
    for p in pixels:
        if p[3]:
            weight[p[:3]] = weight.get(p[:3], 0) + p[3]
    if not weight:
        return bytes(8)

    def error(pair):
        pal = _palette(*pair)
        return sum(w * min(_dist(c, q) for q in pal) for c, w in weight.items())

    # Try every pair of block colours as endpoints (c0 >= c1 keeps 4-colour mode) and keep the best.
    ends = [_rgb565(*c) for c in weight]
    c0, c1 = min({(max(a, b), min(a, b)) for a in ends for b in ends}, key=error)
    pal = _palette(c0, c1)
    bits = 0
    for i, p in enumerate(pixels):
        idx = min(range(4), key=lambda j: _dist(pal[j], p))
        bits |= idx << (2 * i)
    return struct.pack("<HHI", c0, c1, bits)


def encode_bc3(img):
    """Simple BC3 encoder (best pair of block colours as endpoints); plenty for flat UI art."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            block = [px[bx + i % 4, by + i // 4] for i in range(16)]
            out += _alpha_block([p[3] for p in block])
            out += _color_block(block)
    return bytes(out)


def xbm_bytes(img):
    """BC3 data as an .xbm stores it: rows bottom-up. Atlas UVs still refer to the upright image."""
    return encode_bc3(img.transpose(Image.Transpose.FLIP_TOP_BOTTOM))


def decode_bc3(data, w, h):
    """Inverse of encode_bc3, used by the tests and the preview."""
    img = Image.new("RGBA", (w, h))
    px = img.load()
    off = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            a0, a1 = data[off], data[off + 1]
            abits = int.from_bytes(data[off + 2:off + 8], "little")
            apal = [a0, a1] + ([((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)] if a0 > a1 else
                               [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255])
            c0, c1, cbits = struct.unpack_from("<HHI", data, off + 8)
            e0, e1 = _unpack565(c0), _unpack565(c1)
            cpal = [e0, e1, tuple((2 * a + b) // 3 for a, b in zip(e0, e1)),
                    tuple((a + 2 * b) // 3 for a, b in zip(e0, e1))]
            for i in range(16):
                px[bx + i % 4, by + i // 4] = (*cpal[cbits >> (2 * i) & 3], apal[abits >> (3 * i) & 7])
            off += 16
    return img
