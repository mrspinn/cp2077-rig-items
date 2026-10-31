"""Render the Nexus page images from packaging/logo.png: the 1920x1080 gallery image and the 1300x372 header."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BG, FG, YELLOW, RED = (10, 11, 16), (230, 228, 214), (252, 238, 10), (255, 0, 60)
BOLD = "/usr/share/fonts/gsfonts/NimbusSansNarrow-Bold.otf"
REGULAR = "/usr/share/fonts/gsfonts/NimbusSansNarrow-Regular.otf"
TAGLINE = "Swap body rigs in-game, no restart."


def render(w, h, logo_size, title_px, tag_px, path, right=None, top=None):
    """Centre the logo and text, or pin them `right` px from the right edge and `top` px from the top."""
    im = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(im)
    logo = Image.open(HERE / "logo.png").resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    big, small = ImageFont.truetype(BOLD, title_px), ImageFont.truetype(REGULAR, tag_px)
    gap = logo_size // 7
    title_h = big.getbbox("RIG ITEMS")[3]
    block_h = title_h + tag_px // 2 + 6 + tag_px // 2 + tag_px
    text_w = max(d.textlength("RIG ITEMS", font=big), d.textlength(TAGLINE, font=small))
    x0 = int(w - right - (logo_size + gap + text_w)) if right is not None else int((w - (logo_size + gap + text_w)) / 2)
    y0 = top if top is not None else (h - logo_size) // 2
    im.alpha_composite(logo, (x0, y0))
    x, y = x0 + logo_size + gap, y0 + (logo_size - block_h) // 2
    d.text((x, y), "RIG ITEMS", font=big, fill=YELLOW)
    y += title_h + tag_px // 2
    d.rectangle([x + 4, y, x + 4 + title_px, y + max(3, title_px // 30)], fill=RED)
    d.text((x + 4, y + tag_px // 2), TAGLINE, font=small, fill=FG)
    im.convert("RGB").save(path)


render(1920, 1080, 640, 220, 64, HERE / "nexus.png")
# Nexus overlays the title and stats on the header's bottom-left and buttons on its bottom-right.
render(1300, 372, 210, 110, 32, HERE / "nexus-header.png", right=90, top=36)
