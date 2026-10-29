"""The look and the motion of the GMD Bakery program.

Nothing in this file knows about orders, sales or recipes - bakery_lite.py does that.

HOW THE "HD" LOOK IS MADE
  Tkinter draws plain shapes with jagged edges and has no shadows. So every rounded shape here (cards, buttons,
  tabs, fields, notes, icons) is drawn as a picture with Pillow: drawn 4x bigger and shrunk (that removes the jagged
  edges), with a real blurred shadow, then shown with transparency. Pillow is installed together with matplotlib.

LIGHT AND DARK
  Every colour is a named role (BG, WHITE for cards, TEXT, ...) with a light and a dark value (see THEMES).
  set_theme("dark") changes them all; the program then calls restyle_all() so everything is drawn again, and a
  see-through copy of the old look (Veil) fades away on top, so the change is one smooth cross-fade.

HOW THE MOTION IS MADE
  Everything that moves goes through `Motion`. It runs about 60 frames a second, follows the clock (an animation
  always takes the same time, even on a slow computer) and can be stopped when the window closes.
  Set the environment variable GMD_NO_ANIMATION=1 to switch all movement off; the screens then simply snap.
"""
import math
import os
import time
import weakref
import tkinter as tk
from datetime import timedelta
from functools import lru_cache
from tkinter import font as tkfont
from tkinter import messagebox as tkmessagebox
from tkinter import ttk

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

ANIMATE = os.environ.get("GMD_NO_ANIMATION") != "1"

# ------------------------------------------------------------------ colours: one set for light, one for dark
THEMES = {
    "light": dict(
        GREEN="#1b7a35", DARK_GREEN="#14602a", PALE_GREEN="#e8f3ea",      # the bakery's colour (ticks, charts, lines)
        BG="#f2f4f8", WHITE="#ffffff", LINE="#e4e7ec",                    # cool soft page, white cards, hairlines
        FIELD_BG="#fbfbfd", FIELD_LINE="#c9ccd2", PILL="#ffffff",
        TEXT="#1c1c1e", MUTED="#71767f", SHADOW="#1c2430",
        PRIMARY="#1c1c1e", PRIMARY_HOVER="#3b3b40",                       # the main button of a screen: black
        NEUTRAL="#eceef2", NEUTRAL_HOVER="#dfe2e8",                       # grey buttons and the tab track
        SKY_TOP="#c2d1e1", SKY_MID="#dde6ef", RED="#c4291f", AMBER="#a65f00",
        HEAD="#f7f7f9", SELECT="#d6ecdb", HOVER_ROW="#eef6f0", SOFT_PILL="#e3e8ef", BAD_FIELD="#fdecea",
        TRACK="#d6dce5", SCROLL="#c9c9ce", SCROLL_HOT="#a8a8ae", FLASH="#bfe3c5",
        GLASS="#ffffff", GLASS_ALPHA=178, RIM_ALPHA=235, SHADOW_GAIN=1.0, SPOT_ALPHA=95,
        CHART=("#1b7a35", "#f2a03d", "#e8604c", "#4f7cf0", "#8e5bd8")),  # one colour per product, in every chart
    "dark": dict(
        GREEN="#30d158", DARK_GREEN="#28b04a", PALE_GREEN="#14301e",
        BG="#0a0f17", WHITE="#161c26", LINE="#262e3b",
        FIELD_BG="#1d2531", FIELD_LINE="#3a4557", PILL="#3b4658",
        TEXT="#f2f3f5", MUTED="#8b93a1", SHADOW="#000000",
        PRIMARY="#f2f3f5", PRIMARY_HOVER="#d9dbe0",
        NEUTRAL="#232b37", NEUTRAL_HOVER="#2e3847",
        SKY_TOP="#1c3150", SKY_MID="#111d2f", RED="#ff6961", AMBER="#ffb340",
        HEAD="#1b222d", SELECT="#1f3a2a", HOVER_ROW="#1d2631", SOFT_PILL="#2a3342", BAD_FIELD="#3a1d1f",
        TRACK="#2c3646", SCROLL="#3a4558", SCROLL_HOT="#566176", FLASH="#1f4d2e",
        GLASS="#ffffff", GLASS_ALPHA=22, RIM_ALPHA=64, SHADOW_GAIN=2.4, SPOT_ALPHA=46,
        CHART=("#30d158", "#ffb340", "#ff7a6b", "#6e9bff", "#b48cf0")),
}
WIDGET_KEYS = ("BG", "WHITE", "LINE", "TEXT", "MUTED", "GREEN", "RED", "AMBER", "PALE_GREEN", "NEUTRAL", "PRIMARY")
THEME = {"name": "light"}
INK_DARK, INK_LIGHT = "#1c1c1e", "#ffffff"  # text on a light / on a dark fill (the same in both themes)
PURE_WHITE = "#ffffff"
globals().update(THEMES["light"])  # BG, WHITE, TEXT ... are module-level names that set_theme() changes
registry = weakref.WeakSet()  # everything that draws itself with pictures and must be redrawn after a theme change

SS = 4  # shapes are drawn this many times bigger, then shrunk: smooth edges
RESAMPLING = getattr(Image, "Resampling", Image)
SMOOTH, LINEAR = RESAMPLING.LANCZOS, RESAMPLING.BILINEAR
FAMILY = {"text": "Segoe UI", "display": "Segoe UI"}


def set_theme(name):
    """Switch every colour role to the 'light' or 'dark' value. (The program then calls restyle_all().)"""
    THEME["name"] = name
    globals().update(THEMES[name])
    for cached in (card_picture_cached, glass_picture, pill_picture, field_picture, sky_picture, spot_picture):
        cached.cache_clear()


def theme_map(old, new):
    """{old colour: new colour} for the colours that plain Tk widgets use, to recolour them after a switch."""
    return {THEMES[old][k].lower(): THEMES[new][k] for k in WIDGET_KEYS if THEMES[old][k].lower() != THEMES[new][k].lower()}


def recolor(root, mapping):
    """Recolour every plain Tk widget under `root` (ttk widgets follow their style instead)."""
    options = ("bg", "fg", "highlightbackground", "highlightcolor", "activebackground", "insertbackground",
               "selectbackground", "selectforeground")
    stack = [root]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if isinstance(widget, ttk.Widget):
            continue
        for option in options:
            try:
                value = str(widget.cget(option))
            except tk.TclError:
                continue
            try:
                r, g, b = (v // 257 for v in widget.winfo_rgb(value))
            except tk.TclError:
                continue
            new = mapping.get("#%02x%02x%02x" % (r, g, b))
            if new:
                widget.configure(**{option: new})


def restyle_all():
    for component in list(registry):
        try:
            component.restyle()
        except tk.TclError:
            pass


def native_theme(window, dark):
    """Windows: a dark (or light) title bar to match. On other systems this quietly does nothing."""
    try:
        import ctypes
        from ctypes import wintypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 11, and early Windows 10)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(value), 4)
    except Exception:
        pass


def pick_fonts(root):
    """Use the modern Windows 11 fonts when they exist (they look closest to Apple's), else Segoe UI."""
    names = set(tkfont.families(root))
    FAMILY["text"] = "Segoe UI Variable Text" if "Segoe UI Variable Text" in names else "Segoe UI"
    FAMILY["display"] = "Segoe UI Variable Display" if "Segoe UI Variable Display" in names else FAMILY["text"]


def font(size, weight="normal"):
    """A Tk font tuple. Big sizes use the 'display' font, small ones the 'text' font."""
    return (FAMILY["display" if size >= 14 else "text"], size, weight)


# ------------------------------------------------------------------ easing and colours
def ease_out(t):
    """Fast at first, slowing down gently at the end (feels natural)."""
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t):
    """Like ease_out but overshoots a little and settles back."""
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def spring(t):
    """A real spring: shoots a little past the goal and settles back, like iOS animations (a damped oscillation)."""
    return 1 - math.exp(-6.5 * t) * math.cos(8.5 * t)


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    """The colour a fraction t of the way from colour a to colour b (both '#rrggbb')."""
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x + (y - x) * t))) for x, y in zip(rgb(a), rgb(b)))


def ink(color):
    """Light text on dark colours, dark text on light ones."""
    r, g, b = rgb(color)
    return INK_LIGHT if 0.299 * r + 0.587 * g + 0.114 * b < 150 else INK_DARK


def contrast(a, b):
    """WCAG contrast ratio of two colours (4.5 or more reads comfortably)."""
    def luminance(color):
        parts = [(v / 255) for v in rgb(color)]
        r, g, bl = [p / 12.92 if p <= 0.03928 else ((p + 0.055) / 1.055) ** 2.4 for p in parts]
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def background_of(widget):
    """The colour behind a widget (so a canvas can match it)."""
    for option in ("bg", "background"):
        try:
            return widget.cget(option)
        except tk.TclError:
            pass
    style = ttk.Style(widget)
    return style.lookup(str(widget.cget("style")) or widget.winfo_class(), "background") or BG


def tags_of(tree, row):
    tags = tree.item(row, "tags")
    return (tags,) if isinstance(tags, str) and tags else tuple(tags)


# ------------------------------------------------------------------ pictures (Pillow): smooth shapes and shadows
@lru_cache(maxsize=512)
def mask(w, h, radius):
    """A smooth white rounded rectangle, as a grey-scale picture (drawn 4x big, then shrunk)."""
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=radius * SS, fill=255)
    return big.resize((w, h), SMOOTH)


@lru_cache(maxsize=512)
def shape(w, h, radius, fill, outline=None):
    """A smooth rounded rectangle with a fill colour and, if wanted, a 1 pixel outline."""
    radius = min(radius, h // 2, w // 2)
    image = Image.new("RGBA", (w, h), rgb(outline or fill) + (0,))
    image.putalpha(mask(w, h, radius))
    if outline:
        inner = Image.new("RGBA", (w - 2, h - 2), rgb(fill) + (0,))
        inner.putalpha(mask(w - 2, h - 2, max(radius - 1, 0)))
        image.alpha_composite(inner, (1, 1))
    return image


@lru_cache(maxsize=64)
def disc(size, color):
    return shape(size, size, size // 2, color)


def photo(image, owner):
    """Turn a Pillow picture into a Tk picture that belongs to the window of `owner` (a widget)."""
    return ImageTk.PhotoImage(image, master=owner)


LOGO_NAMES = ("GMD v2", "GMD logo")  # the logo file next to this program (tried in this order)


@lru_cache(maxsize=1)
def logo_source():
    """The bakery's logo as a square picture: the white margin is cut off, then a little white is added all round.
    None if there is no logo file (the header then shows a green G instead)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in LOGO_NAMES:
        for ext in (".png", ".jpg", ".jpeg"):
            path = os.path.join(here, name + ext)
            if not os.path.exists(path):
                continue
            try:
                picture = Image.open(path).convert("RGB")
            except (OSError, ValueError):
                continue
            ink = picture.convert("L").point(lambda v: 255 if v < 200 else 0)  # (anything that is not white)
            left, top, right, bottom = ink.getbbox() or (0, 0) + picture.size
            side = int(max(right - left, bottom - top) * 1.06)
            square = Image.new("RGB", (side, side), "white")
            square.paste(picture.crop((left, top, right, bottom)), ((side - (right - left)) // 2, (side - (bottom - top)) // 2))
            return square
    return None


@lru_cache(maxsize=16)
def logo_picture(size, line):
    """The logo as a smooth rounded tile (like an app icon) with a hairline edge; None if there is no logo file."""
    source = logo_source()
    if source is None:
        return None
    radius = round(size * 0.24)
    tile = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    tile.paste(source.resize((size, size), SMOOTH), (0, 0), mask(size, size, radius))
    inner = Image.new("L", (size, size), 0)
    inner.paste(mask(size - 2, size - 2, max(radius - 1, 0)), (1, 1))
    edge = Image.new("RGBA", (size, size), rgb(line) + (0,))
    edge.putalpha(ImageChops.subtract(mask(size, size, radius), inner))
    tile.alpha_composite(edge)
    return tile


def shadow_params(level, scale):
    """(blur, drop, strength) of a shadow. level 0 = resting, 1 = raised (points toward you)."""
    return (3.5 + 3.5 * level) * scale, (1.5 + 3.5 * level) * scale, (0.09 + 0.08 * level) * SHADOW_GAIN


def margin_for(raised, scale):
    """Room around a card for its shadow."""
    blur, drop, _ = shadow_params(1.0 if raised else 0.0, scale)
    return int(blur * 1.8 + drop) + 1


def soft_shadow(width, height, rect, radius, blur, strength, color=None):
    """A picture of a blurred rounded rectangle (the shadow). Blurred at half size: much faster, looks the same."""
    half = Image.new("L", (width // 2 + 2, height // 2 + 2), 0)
    ImageDraw.Draw(half).rounded_rectangle(tuple(v / 2 for v in rect), radius=radius / 2, fill=255)
    half = half.filter(ImageFilter.GaussianBlur(max(0.5, blur / 2)))
    alpha = half.resize((width, height), LINEAR).point(lambda v: min(255, int(v * strength)))
    image = Image.new("RGBA", (width, height), rgb(color or SHADOW) + (0,))
    image.putalpha(alpha)
    return image


@lru_cache(maxsize=192)
def card_picture_cached(w, h, radius, level10, margin, scale, fill, line):
    level = level10 / 10
    blur, drop, strength = shadow_params(level, scale)
    lift = round(level * 2 * scale)
    top = margin - lift
    image = soft_shadow(w + 2 * margin, h + 2 * margin, (margin, top + drop, margin + w, top + h + drop), radius,
                        blur, strength)
    image.alpha_composite(shape(w, h, radius, fill, line), (margin, top))
    return image


def card_picture(w, h, radius, level10, margin, scale, fill=None, line=None):
    """A card of size w x h (plus `margin` all round) with its shadow. level10 = 0..10 (resting .. raised)."""
    return card_picture_cached(w, h, radius, level10, margin, scale, fill or WHITE, line or LINE)


@lru_cache(maxsize=96)
def glass_picture(w, h, radius, level10, margin, scale):
    """A frosted-glass card: translucent with a bright rim. The shadow is removed under the glass (so it does not
    show through), and only falls outside. Meant to be put over the soft gradient."""
    level = level10 / 10
    blur, drop, strength = shadow_params(level, scale)
    lift = round(level * 2 * scale)
    top = margin - lift
    image = soft_shadow(w + 2 * margin, h + 2 * margin, (margin, top + drop, margin + w, top + h + drop), radius,
                        blur, strength * 0.85)
    card = Image.new("L", image.size, 0)
    card.paste(mask(w, h, radius), (margin, top))
    image.putalpha(ImageChops.multiply(image.getchannel("A"), ImageChops.invert(card)))
    tint = rgb(GLASS)
    glass = Image.new("RGBA", (w, h), tint + (0,))
    glass.putalpha(mask(w, h, radius).point(lambda v: v * GLASS_ALPHA // 255))
    image.alpha_composite(glass, (margin, top))
    inner = Image.new("L", (w, h), 0)
    inner.paste(mask(w - 2, h - 2, max(radius - 1, 0)), (1, 1))
    rim = Image.new("RGBA", (w, h), tint + (0,))
    rim.putalpha(ImageChops.subtract(mask(w, h, radius), inner).point(lambda v: v * RIM_ALPHA // 255))
    image.alpha_composite(rim, (margin, top))
    return image


@lru_cache(maxsize=48)
def blob(radius):
    """A soft round glow (white in the middle, fading to nothing), used for the spotlight."""
    glow = Image.radial_gradient("L").resize((radius * 2, radius * 2), LINEAR)
    return ImageChops.invert(glow).point(lambda v: int(255 * (v / 255) ** 1.6))


@lru_cache(maxsize=96)
def spot_picture(w, h, radius, margin, x, y, reach):
    """A spotlight inside a card: a soft white glow around the point (x, y), cut to the card's rounded shape."""
    layer = Image.new("L", (w, h), 0)
    layer.paste(blob(reach), (x - reach, y - reach))
    layer = ImageChops.multiply(layer, mask(w, h, radius)).point(lambda v: v * SPOT_ALPHA // 255)
    image = Image.new("RGBA", (w + 2 * margin, h + 2 * margin), (255, 255, 255, 0))
    glow = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    glow.putalpha(layer)
    image.alpha_composite(glow, (margin, margin))
    return image


@lru_cache(maxsize=96)
def ring_picture(size, progress100, color, track):
    """A progress ring (a circle outline that fills up clockwise from the top), smooth, with round ends."""
    big, thick = 4, max(3, size // 9)
    side = size * big
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = (thick * big / 2, thick * big / 2, side - thick * big / 2 - 1, side - thick * big / 2 - 1)
    draw.ellipse(box, outline=rgb(track) + (255,), width=thick * big)
    if progress100 > 0:
        draw.arc(box, -90, -90 + 360 * progress100 / 100, fill=rgb(color) + (255,), width=thick * big)
        centre, radius = side / 2, side / 2 - thick * big / 2
        for angle in (-90, -90 + 360 * progress100 / 100):  # round the two ends
            x, y = centre + radius * math.cos(math.radians(angle)), centre + radius * math.sin(math.radians(angle))
            draw.ellipse((x - thick * big / 2, y - thick * big / 2, x + thick * big / 2, y + thick * big / 2),
                         fill=rgb(color) + (255,))
    return image.resize((size, size), SMOOTH)


@lru_cache(maxsize=128)
def pill_picture(w, h):
    """The moving pill of the tab control (with a very light shadow)."""
    margin = 4
    image = soft_shadow(w + 2 * margin, h + 2 * margin, (margin, margin + 1, margin + w, margin + h + 1), h / 2, 2.2,
                        0.20 * SHADOW_GAIN)
    image.alpha_composite(shape(w, h, h // 2, PILL), (margin, margin))
    return image


@lru_cache(maxsize=256)
def field_picture(w, h, ring, ring_alpha10):
    """A rounded text field: its own colour, thin outline, and (when `ring`) a soft coloured ring around it."""
    pad = 3
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if ring and ring_alpha10 > 0:
        outer = mask(w, h, 9 + pad)
        inner = Image.new("L", (w, h), 0)
        inner.paste(mask(w - 2 * pad + 2, h - 2 * pad + 2, 9), (pad - 1, pad - 1))
        edge = Image.new("RGBA", (w, h), rgb(ring) + (0,))
        edge.putalpha(ImageChops.subtract(outer, inner).point(lambda v: v * ring_alpha10 // 10 * 7 // 10))
        image.alpha_composite(edge)
    image.alpha_composite(shape(w - 2 * pad, h - 2 * pad, 9, FIELD_BG, FIELD_LINE), (pad, pad))
    return image


# ------------------------------------------------------------------ line icons (drawn like the iPhone's)
def _line(draw, points, width, colour):
    draw.line(points, fill=colour, width=width, joint="curve")
    for x, y in (points[0], points[-1]):  # round caps
        draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=colour)


@lru_cache(maxsize=600)
def icon_picture(name, size, color):
    """A small line icon (home, list, bars, oven, box, doc, pie, sun, moon), smooth, in the given colour."""
    big = SS * 2
    k, w = size * big / 24, max(2, round(1.9 * size * big / 24))
    image = Image.new("RGBA", (size * big, size * big), (0, 0, 0, 0))
    draw, c = ImageDraw.Draw(image), rgb(color) + (255,)
    P = lambda *pts: [(x * k, y * k) for x, y in pts]
    R = lambda x1, y1, x2, y2: (x1 * k, y1 * k, x2 * k, y2 * k)
    if name == "home":
        _line(draw, P((3, 12), (12, 3.6), (21, 12)), w, c)
        _line(draw, P((5.6, 10.6), (5.6, 20.4), (18.4, 20.4), (18.4, 10.6)), w, c)
        _line(draw, P((10, 20.4), (10, 14.6), (14, 14.6), (14, 20.4)), w, c)
    elif name == "list":
        draw.rounded_rectangle(R(4.6, 3.6, 19.4, 20.4), radius=3.2 * k, outline=c, width=w)
        for y, x2 in ((9, 15.6), (13, 15.6), (17, 12.4)):
            _line(draw, P((8.4, y), (x2, y)), w, c)
    elif name == "bars":
        for x1, y1, x2 in ((4.4, 13, 8.4), (10, 8, 14), (15.6, 4, 19.6)):
            draw.rounded_rectangle(R(x1, y1, x2, 20.4), radius=1.9 * k, fill=c)
    elif name == "oven":
        draw.rounded_rectangle(R(3.6, 4.8, 20.4, 20.2), radius=3.2 * k, outline=c, width=w)
        _line(draw, P((3.6, 9.6), (20.4, 9.6)), w, c)
        for x in (7, 10.6):
            draw.ellipse(R(x - 0.95, 6.35, x + 0.95, 8.25), fill=c)
        draw.rounded_rectangle(R(7, 12.6, 17, 17.4), radius=1.6 * k, outline=c, width=w)
    elif name == "box":
        _line(draw, P((12, 3.6), (20, 8), (20, 16), (12, 20.4), (4, 16), (4, 8), (12, 3.6)), w, c)
        _line(draw, P((4, 8), (12, 12.6), (20, 8)), w, c)
        _line(draw, P((12, 12.6), (12, 20.4)), w, c)
    elif name == "doc":
        _line(draw, P((6, 3.6), (14, 3.6), (19, 8.6), (19, 20.4), (6, 20.4), (6, 3.6)), w, c)
        _line(draw, P((14, 3.6), (14, 8.6), (19, 8.6)), w, c)
        _line(draw, P((9.2, 13.2), (15.8, 13.2)), w, c)
        _line(draw, P((9.2, 16.6), (13.6, 16.6)), w, c)
    elif name == "pie":
        draw.ellipse(R(3.6, 3.6, 20.4, 20.4), outline=c, width=w)
        _line(draw, P((12, 12), (12, 3.6)), w, c)
        _line(draw, P((12, 12), (19.3, 16.2)), w, c)
    elif name == "sun":
        draw.ellipse(R(7.6, 7.6, 16.4, 16.4), outline=c, width=w)
        for i in range(8):
            a = math.radians(i * 45)
            _line(draw, P((12 + 7.4 * math.cos(a), 12 + 7.4 * math.sin(a)), (12 + 9.6 * math.cos(a), 12 + 9.6 * math.sin(a))), w, c)
    elif name == "moon":
        outer = Image.new("L", image.size, 0)
        ImageDraw.Draw(outer).ellipse(R(3.4, 3.4, 20.6, 20.6), fill=255)
        cut = Image.new("L", image.size, 0)
        ImageDraw.Draw(cut).ellipse(R(9.2, 0.6, 25.4, 16.8), fill=255)
        image.putalpha(ImageChops.subtract(outer, cut))
        image = Image.composite(Image.new("RGBA", image.size, c), image, image.getchannel("A"))
    return image.resize((size, size), SMOOTH)


def tick_picture(size, progress, color="#34c759"):
    """A green disc that grows, with a white tick that draws itself (progress 0..1). Smooth, drawn big then shrunk."""
    big = 4
    image = Image.new("RGBA", (size * big, size * big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    centre = size * big / 2
    radius = (centre - big) * (0.35 + 0.65 * min(1.0, progress * 2.0))
    draw.ellipse((centre - radius, centre - radius, centre + radius, centre + radius), fill=rgb(color) + (255,))
    reach = max(0.0, (progress - 0.35) / 0.65) * 2  # 0..1 for the short stroke, 1..2 for the long one
    a, b, c = (size * 0.28 * big, size * 0.52 * big), (size * 0.44 * big, size * 0.68 * big), (size * 0.74 * big, size * 0.34 * big)
    points = [a]
    if reach > 0:
        f = min(1.0, reach)
        points.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    if reach > 1:
        f = reach - 1
        points.append((b[0] + (c[0] - b[0]) * f, b[1] + (c[1] - b[1]) * f))
    if len(points) >= 2:
        draw.line(points, fill=(255, 255, 255, 255), width=int(2.6 * big), joint="curve")
        for x, y in (points[0], points[-1]):  # round ends
            draw.ellipse((x - 1.3 * big, y - 1.3 * big, x + 1.3 * big, y + 1.3 * big), fill=(255, 255, 255, 255))
    return image.resize((size, size), SMOOTH)


# ------------------------------------------------------------------ the animation engine
class Motion:
    """Runs animations for one window. Every animation has a key; starting a new one with the same key replaces it.

    On Windows the system clock normally ticks every 15.6 ms, which makes animations stutter. `timeBeginPeriod(1)`
    asks for 1 ms ticks while the window is open (it is switched back when the window closes).
    """
    FRAME_MS = 1000 / 60

    def __init__(self, root):
        self.root, self.running, self.stats, self.fine = root, {}, None, False
        if ANIMATE:
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
                self.fine = True
            except Exception:
                pass

    def run(self, key, ms, step, done=None, ease=ease_out):
        """Call step(progress) from 0 to 1 over `ms` milliseconds, then done()."""
        self.stop(key)
        if not ANIMATE or ms <= 0:
            step(1.0)
            if done:
                done()
            return
        start = time.perf_counter()
        label = key[1] if isinstance(key, tuple) and len(key) > 1 and isinstance(key[1], str) else str(key)

        def frame():
            began = time.perf_counter()
            progress = min(1.0, (began - start) * 1000 / ms)
            if self.stats is not None:
                self.stats.setdefault(label, []).append(began)
            try:
                step(1.0 if progress >= 1.0 else ease(progress))  # (the last frame is exactly the goal)
                # paint this frame now. (If a frame is slow, Tk's timer events would otherwise keep coming before its
                # own redraws and the window would look frozen until the animation ended.)
                self.root.update_idletasks()
            except tk.TclError:  # the widget was closed while it was moving
                self.running.pop(key, None)
                return
            if progress < 1.0:
                spent = (time.perf_counter() - began) * 1000
                self.running[key] = self.root.after(max(1, int(self.FRAME_MS - spent)), frame)
            else:
                self.running.pop(key, None)
                if done:
                    done()

        frame()

    def later(self, key, ms, function):
        """Call function() after `ms` milliseconds (can be cancelled like an animation)."""
        self.stop(key)

        def fire():
            self.running.pop(key, None)
            function()

        self.running[key] = self.root.after(ms, fire)

    def stop(self, key):
        pending = self.running.pop(key, None)
        if pending is not None:
            self.root.after_cancel(pending)

    def stop_group(self, group):
        """Stop every animation whose key starts with `group` (a widget stops all of its own)."""
        for key in list(self.running):
            if isinstance(key, tuple) and key and key[0] == group:
                self.stop(key)

    def stop_all(self):
        for key in list(self.running):
            self.stop(key)
        if self.fine:
            self.fine = False
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


# ------------------------------------------------------------------ colours, fonts and spacing for every widget
def apply_style(root, scale):
    """Only the appearance is set here; nothing in this function changes what the program does.
    (It reads the current theme, so it is called again after a light/dark switch.)"""
    pick_fonts(root)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        tkfont.nametofont(name).configure(family=FAMILY["text"], size=10)
    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", FIELD_BG)  # the list that drops down from a combo box
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                    troughcolor=BG, focuscolor=BG)
    # labels: on the page (BG) or inside a card (WHITE)
    style.configure("Hint.TLabel", foreground=MUTED)
    style.configure("Section.TLabel", foreground=TEXT, font=font(12, "bold"))
    style.configure("Note.TLabel", foreground=GREEN, font=font(10, "bold"))
    style.configure("Greeting.TLabel", foreground=TEXT, font=font(22, "bold"))
    style.configure("Field.TLabel", background=WHITE, foreground=MUTED, font=font(9))
    style.configure("Total.TLabel", background=WHITE, foreground=TEXT, font=font(13, "bold"))
    style.configure("Bad.TLabel", background=WHITE, foreground=RED, font=font(9))
    style.configure("Empty.TLabel", background=WHITE, foreground=MUTED, font=font(11))
    style.configure("Card.TLabel", background=WHITE)
    style.configure("Card.TCheckbutton", background=WHITE)
    style.map("Card.TCheckbutton", background=[("active", WHITE)], indicatorbackground=[("selected", GREEN)],
              indicatorforeground=[("selected", INK_LIGHT)])
    # text fields: the rounded outline and the focus ring belong to the picture behind (see Holder), so the
    # field itself is flat
    flat = dict(fieldbackground=FIELD_BG, background=FIELD_BG, bordercolor=FIELD_BG, lightcolor=FIELD_BG,
                darkcolor=FIELD_BG, borderwidth=0, foreground=TEXT, insertcolor=TEXT,
                padding=(int(6 * scale), int(4 * scale)))
    style.configure("TEntry", **flat)
    style.configure("TCombobox", arrowcolor=GREEN, arrowsize=int(14 * scale), **flat)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD_BG)], background=[("readonly", FIELD_BG)],
              selectbackground=[("readonly", FIELD_BG)], selectforeground=[("readonly", TEXT)])
    style.configure("Bad.TEntry", fieldbackground=BAD_FIELD, background=BAD_FIELD)
    # tables
    style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=TEXT, borderwidth=0,
                    rowheight=int(24 * scale))
    style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", background=HEAD, foreground=MUTED, relief="flat", font=font(9, "bold"),
                    padding=int(4 * scale))
    # thin scroll bars with no arrows (like on a phone)
    style.configure("TScrollbar", background=SCROLL, troughcolor=WHITE, bordercolor=WHITE, lightcolor=SCROLL,
                    darkcolor=SCROLL, arrowsize=int(9 * scale), gripcount=0, relief="flat")
    style.map("TScrollbar", background=[("active", SCROLL_HOT)], lightcolor=[("active", SCROLL_HOT)],
              darkcolor=[("active", SCROLL_HOT)])
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])


# ------------------------------------------------------------------ the bar at the top
class Header(tk.Canvas):
    """App name on the left, a one-line hint for the tab you are on (it fades when it changes), and on the right the
    date and a round light/dark switch (a sun or a moon that spins when you press it)."""

    def __init__(self, parent, motion, scale, title, subtitle, right, on_theme=None):
        self.h = int(56 * scale)
        super().__init__(parent, bg=WHITE, height=self.h, highlightthickness=0)
        self.motion, self.scale, self.on_theme, self.next_text = motion, scale, on_theme, subtitle
        self.title_text, self.date_text, self.hot, self.spin = title, right, 0.0, 1.0
        registry.add(self)
        self._draw()
        self.bind("<Configure>", lambda e: self._place(e.width))
        self.bind("<Motion>", self._moved)
        self.bind("<Leave>", lambda e: self._warm(0.0))
        self.bind("<Button-1>", self._clicked)

    def restyle(self):
        self._draw()

    def _icon_name(self):
        return "moon" if THEME["name"] == "light" else "sun"  # the icon shows what you would switch to

    def _draw(self):
        s, h = self.scale, self.h
        self.configure(bg=WHITE)
        self.delete("all")
        logo = logo_picture(int(44 * s), LINE)
        size = int(44 * s) if logo else int(32 * s)
        self.logo = photo(logo or disc(size, GREEN), self)
        self.create_image(18 * s, h / 2, image=self.logo, anchor="w")
        if not logo:  # (no logo file next to the program: a green G)
            self.create_text(18 * s + size / 2, h / 2, text="G", fill=PURE_WHITE, font=font(14, "bold"))
        left = 18 * s + size + 12 * s
        self.create_text(left, h / 2 - 9 * s, text=self.title_text, anchor="w", fill=TEXT, font=font(15, "bold"))
        self.hint = self.create_text(left, h / 2 + 11 * s, text=self.next_text, anchor="w", fill=MUTED, font=font(10))
        self.right = self.create_text(0, h / 2, text=self.date_text, anchor="e", fill=MUTED, font=font(10))
        self.button = int(36 * s)
        self.glow_item = self.create_image(0, h / 2, anchor="center")
        self.icon_item = self.create_image(0, h / 2, anchor="center")
        self._icon()
        if self.winfo_width() > 1:
            self._place(self.winfo_width())

    def _place(self, width):
        s = self.scale
        cx = width - 34 * s
        self.coords(self.glow_item, cx, self.h / 2)
        self.coords(self.icon_item, cx, self.h / 2)
        self.coords(self.right, cx - self.button / 2 - 12 * s, self.h / 2)
        self.centre = cx

    def _icon(self):
        """Draw the round button and its icon (the icon spins and pops when self.spin runs from 0 to 1)."""
        size = int(20 * self.scale)
        glow = disc(self.button, NEUTRAL).copy()
        glow.putalpha(glow.getchannel("A").point(lambda v: int(v * self.hot)))
        self._glow = photo(glow, self)
        self.itemconfigure(self.glow_item, image=self._glow)
        icon = icon_picture(self._icon_name(), size, TEXT)
        if self.spin < 1.0:
            scale = 0.35 + 0.65 * min(1.0, self.spin)
            icon = icon.rotate(-(1 - self.spin) * 140, resample=LINEAR).resize(
                (max(2, int(size * scale)), max(2, int(size * scale))), SMOOTH)
        self._icon_photo = photo(icon, self)
        self.itemconfigure(self.icon_item, image=self._icon_photo)

    def _over_button(self, x, y):
        return hasattr(self, "centre") and abs(x - self.centre) <= self.button / 2 and abs(y - self.h / 2) <= self.button / 2

    def _moved(self, event):
        over = self._over_button(event.x, event.y)
        self.configure(cursor="hand2" if over else "")
        self._warm(1.0 if over else 0.0)

    def _warm(self, target):
        start = self.hot
        if start != target:
            def step(t):
                self.hot = start + (target - start) * t
                self._icon()

            self.motion.run((id(self), "warm"), 140, step)

    def _clicked(self, event):
        if self._over_button(event.x, event.y) and self.on_theme:
            self.on_theme()

    def spin_icon(self):
        """The icon spins and pops into its new shape (played after a theme switch)."""
        def step(t):
            self.spin = t
            self._icon()

        self.spin = 0.0
        self.motion.run((id(self), "spin"), 520, step, ease=spring)

    def say(self, text):
        """Change the hint line: the old text fades out, the new one fades in."""
        if text == self.next_text:
            return
        self.next_text, swapped = text, [False]

        def step(t):
            if t < 0.4:
                self.itemconfigure(self.hint, fill=mix(MUTED, WHITE, t / 0.4))
            else:
                if not swapped[0]:
                    self.itemconfigure(self.hint, text=text)
                    swapped[0] = True
                self.itemconfigure(self.hint, fill=mix(WHITE, MUTED, (t - 0.4) / 0.6))

        self.motion.run(("header", id(self)), 300, step, ease=lambda t: t)

    def destroy(self):
        self.motion.stop_group(("header", id(self)))
        for name in ("warm", "spin"):
            self.motion.stop((id(self), name))
        super().destroy()


# ------------------------------------------------------------------ pill buttons
class Button(tk.Canvas):
    """A smooth pill button. Its colour fades when the mouse comes and goes, it shrinks a little when pressed, and
    it works from the keyboard (Tab to reach it, Space or Enter to press it). It answers invoke() and cget("text")
    like a normal button. `primary` buttons are black (white in dark mode); `highlight(True)` does the same to any button.
    """
    count = 0
    PAD = 3  # room around the pill for the focus ring

    def __init__(self, parent, motion, text, command, primary=False, tip=None, bg=None):
        Button.count += 1
        scale = max(1.0, parent.winfo_fpixels("1i") / 96)
        self.motion, self.key, self.on = motion, ("button", Button.count), primary
        self.hovering = self.pressed = self.focused = False
        self.text_value, self.command, self.fixed_bg = text, command, bg is not None
        self.label_font = tkfont.Font(font=font(10, "bold"))
        self.w = self.label_font.measure(text) + 2 * int(18 * scale)
        self.h = self.label_font.metrics("linespace") + 2 * int(6 * scale)
        pad = self.PAD
        super().__init__(parent, width=self.w + 2 * pad, height=self.h + 2 * pad, bg=bg or background_of(parent),
                         highlightthickness=0, cursor="hand2", takefocus=1)
        registry.add(self)
        self.shade = self._target()
        self.picture = self.create_image(0, 0, anchor="nw")
        self.label = self.create_text((self.w + 2 * pad) / 2, (self.h + 2 * pad) / 2, text=text, font=self.label_font)
        self._paint(self.shade)
        self.bind("<Enter>", lambda e: self._hover(True), add="+")
        self.bind("<Leave>", lambda e: self._hover(False), add="+")
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        self.bind("<space>", lambda e: self.invoke(), add="+")
        self.bind("<Return>", lambda e: self.invoke(), add="+")
        if tip:
            Tooltip(self, tip, motion)

    # --- the same calls as a normal button
    def invoke(self):
        return self.command() if self.command else None

    def cget(self, key):
        if key == "text":
            return self.text_value
        if key == "command":
            return self.command
        return super().cget(key)

    def configure(self, cnf=None, **options):
        if "text" in options:
            self.text_value = options.pop("text")
            self.itemconfigure(self.label, text=self.text_value)
        if "command" in options:
            self.command = options.pop("command")
        return super().configure(cnf, **options) if (cnf or options) else None

    config = configure

    def restyle(self):
        if not self.fixed_bg:
            super().configure(bg=background_of(self.master))
        self.shade = self._target()
        self._paint(self.shade)

    # --- colours and movement
    def _target(self):
        if self.on:
            return PRIMARY_HOVER if self.hovering else PRIMARY
        return NEUTRAL_HOVER if self.hovering else NEUTRAL

    def _paint(self, color, squeeze=0.0):
        self.shade = color
        pad, w, h = self.PAD, self.w, self.h
        shrink = round(squeeze)  # pressed: the pill is a little smaller
        image = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        if self.focused:
            ring = shape(w + 2 * pad, h + 2 * pad, (h + 2 * pad) // 2, MUTED).copy()
            ring.putalpha(ring.getchannel("A").point(lambda v: v * 4 // 10))
            image.alpha_composite(ring)
        width, height = w - 2 * shrink, h - 2 * shrink
        image.alpha_composite(shape(width, height, height // 2, color), (pad + shrink, pad + shrink))
        self._photo = photo(image, self)
        self.itemconfigure(self.picture, image=self._photo)
        self.itemconfigure(self.label, fill=ink(color))

    def _go(self, color, ms=140, squeeze=0.0):
        start = self.shade

        def step(t):
            self._paint(mix(start, color, t), squeeze)

        self.motion.run(self.key, ms, step)

    def _hover(self, inside):
        self.hovering = inside
        if not self.pressed:
            self._go(self._target())

    def _focus(self, focused):
        self.focused = focused
        self._paint(self.shade)

    def _press(self, event):
        self.pressed = True
        self.focus_set()
        self._go(mix(self._target(), "#000000", 0.18), 70, squeeze=1.0)

    def _release(self, event):
        was_pressed, self.pressed = self.pressed, False
        self._go(self._target(), 160)
        if was_pressed and 0 <= event.x <= self.w + 2 * self.PAD and 0 <= event.y <= self.h + 2 * self.PAD:
            self.invoke()

    def highlight(self, on):
        """Black (white in dark mode) when `on` (used to show which chart is on screen)."""
        self.on = on
        self._go(self._target(), 220)

    def destroy(self):
        self.motion.stop(self.key)
        super().destroy()


# ------------------------------------------------------------------ rounded text fields with a focus ring
class Holder(tk.Canvas):
    """The picture behind a text field: rounded box, thin outline, and a ring that fades in while you are in it
    (green) or stays on (red) when what you typed is wrong."""

    def __init__(self, parent, motion):
        super().__init__(parent, bg=background_of(parent), highlightthickness=0, bd=0)
        self.motion, self.key, self.alpha, self.bad = motion, ("field", id(self)), 0, False
        self.size, self.inner = (1, 1), None
        self.picture = self.create_image(0, 0, anchor="nw")
        registry.add(self)

    def attach(self, widget):
        widget.update_idletasks()
        edge = 3 + 2  # 3 for the focus ring, 2 for the outline and a little breathing room
        w, h = widget.winfo_reqwidth() + 2 * edge, widget.winfo_reqheight() + 2 * edge
        self.size, self.inner = (w, h), widget
        self.configure(width=w, height=h)
        self.create_window(edge, edge, window=widget, anchor="nw", width=w - 2 * edge, height=h - 2 * edge)
        self.draw()
        widget.bind("<FocusIn>", lambda e: self.glow(10), add="+")
        widget.bind("<FocusOut>", lambda e: self.glow(0), add="+")

    def restyle(self):
        self.configure(bg=background_of(self.master))
        self.draw()
        popdown = f"{self.inner}.popdown.f.l"  # the list of an already-opened combo box
        try:
            self.tk.call(popdown, "configure", "-background", FIELD_BG, "-foreground", TEXT, "-selectbackground", SELECT,
                         "-selectforeground", TEXT)
        except tk.TclError:
            pass

    def draw(self):
        ring = RED if self.bad else GREEN
        strength = 10 if self.bad else round(self.alpha)
        self._photo = photo(field_picture(*self.size, ring, strength), self)
        self.itemconfigure(self.picture, image=self._photo)

    def glow(self, target):
        start = self.alpha

        def step(t):
            self.alpha = start + (target - start) * t
            self.draw()

        self.motion.run(self.key, 180, step)

    def flag(self, bad):
        if bad != self.bad:
            self.bad = bad
            self.draw()

    def destroy(self):
        self.motion.stop(self.key)
        super().destroy()


def _forward(name):
    def method(self, *args, **options):
        return getattr(self.holder, name)(*args, **options)

    return method


class _Rounded:
    """Mixin for a ttk widget that lives on a Holder: placing it (grid, pack...) places the whole rounded field."""

    def configure(self, cnf=None, **options):
        if "style" in options:
            self.holder.flag(options["style"] == "Bad.TEntry")
        return super().configure(cnf, **options)

    config = configure


for _name in ("grid", "pack", "place", "grid_remove", "grid_forget", "pack_forget", "place_forget", "lift", "grid_info"):
    setattr(_Rounded, _name, _forward(_name))


class Entry(_Rounded, ttk.Entry):
    """A rounded text field. Use it like ttk.Entry."""

    def __init__(self, parent, motion, **options):
        self.holder = Holder(parent, motion)
        ttk.Entry.__init__(self, self.holder, **options)
        self.holder.attach(self)


class Combo(_Rounded, ttk.Combobox):
    """A rounded drop-down. Use it like ttk.Combobox."""

    def __init__(self, parent, motion, **options):
        self.holder = Holder(parent, motion)
        ttk.Combobox.__init__(self, self.holder, **options)
        self.holder.attach(self)


# ------------------------------------------------------------------ top tabs: a sliding segmented control
class Tabs(tk.Frame):
    """Tabs along the top, drawn like an iPhone segmented control: a pill glides under the chosen tab, each tab has a
    line icon, and the page slides in. It answers the same calls as ttk.Notebook (add, select, tab, tabs and the
    <<NotebookTabChanged>> event). <<TabShown>> is sent when a page has arrived."""

    ICON = 16  # icon size, in pixels at 100%

    def __init__(self, parent, motion, scale):
        super().__init__(parent, bg=BG)
        self.motion, self.scale = motion, scale
        self.font = tkfont.Font(font=font(10, "bold"))
        self.height = int(46 * scale)
        self.bar = tk.Canvas(self, bg=WHITE, height=self.height, highlightthickness=0)
        self.bar.pack(fill="x")
        tk.Frame(self, bg=LINE, height=1).pack(fill="x")  # hairline under the bar
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.pages, self.names, self.icons, self.spans, self.colors = [], [], [], [], []
        self.current, self.hover, self.pill_at, self.icon_photos = None, None, [0.0, 0.0], {}
        registry.add(self)
        self.bar.bind("<Button-1>", lambda e: self._click(e.x))
        self.bar.bind("<Motion>", lambda e: self._point(self._at(e.x)))
        self.bar.bind("<Leave>", lambda e: self._point(None))

    # --- the same calls as ttk.Notebook
    def page(self, padding=12):
        """A new empty page (give it to add())."""
        return ttk.Frame(self.body, padding=padding)

    def add(self, page, text="", icon=None):
        self.pages.append(page)
        self.names.append(text)
        self.icons.append(icon)
        self.colors.append(MUTED)
        self._draw()
        if self.current is None:
            self.select(0)

    def tabs(self):
        return tuple(str(page) for page in self.pages)

    def tab(self, which, option=None):
        name = self.names[self._index(which)]
        return name if option == "text" else {"text": name}

    def select(self, which=None):
        """With no argument: the current page (as a widget path). With a tab number: go there."""
        if which is None:
            return str(self.pages[self.current]) if self.current is not None else ""
        new = self._index(which)
        if new == self.current:
            return None
        old, self.current = self.current, new
        self.event_generate("<<NotebookTabChanged>>")  # the program refreshes the page first, before anything moves
        self._recolor()
        self._slide_pill()
        self._swap(old, new)
        return None

    def warm_up(self):
        """Lay out every page once (off screen) so the shadows are drawn before the first time you open a tab."""
        for page in self.pages:
            page.place(x=-20000, y=0, relwidth=1, relheight=1)
        self.update()
        for i, page in enumerate(self.pages):
            if i == self.current:
                page.place_configure(x=0)  # (the page on screen goes back where it belongs)
            else:
                page.place_forget()

    def restyle(self):
        self.configure(bg=BG)
        self.bar.configure(bg=WHITE)
        self.colors = [GREEN if i == self.current else MUTED for i in range(len(self.names))]
        self._draw()

    # --- helpers
    def _index(self, which):
        if isinstance(which, int):
            return which
        return [str(page) for page in self.pages].index(str(which))

    def _track(self):
        s = self.scale
        return (self.height - int(32 * s)) / 2, (self.height + int(32 * s)) / 2

    def _draw(self):
        s, gap = self.scale, int(3 * self.scale)
        icon, gap_icon, pad = int(self.ICON * s), int(6 * s), int(14 * s)
        self.bar.delete("all")
        top, bottom = self._track()
        x = start = int(16 * s)
        x += gap
        self.spans = []
        for name, symbol in zip(self.names, self.icons):
            width = self.font.measure(name) + 2 * pad + ((icon + gap_icon) if symbol else 0)
            self.spans.append((x, x + width))
            x += width
        end = x + gap
        pill_h = round(bottom - top) - 2 * int(2 * s)
        widths = [round(b - a) for a, b in self.spans] or [10]
        for w in range(min(widths), max(widths) + 1):  # draw every size the gliding pill will pass through, now
            pill_picture(w, pill_h)
        self._track_photo = photo(shape(int(end - start), int(bottom - top), int(bottom - top) // 2, NEUTRAL), self.bar)
        self.bar.create_image(start, top, image=self._track_photo, anchor="nw")
        self.pill = self.bar.create_image(0, 0, anchor="nw")
        if self.current is not None:
            self.pill_at = [float(v) for v in self.spans[self.current]]
        self._place_pill(*self.pill_at)
        for i, (name, symbol) in enumerate(zip(self.names, self.icons)):
            left, right = self.spans[i]
            body = self.font.measure(name) + ((icon + gap_icon) if symbol else 0)
            text_x = (left + right) / 2 - body / 2 + ((icon + gap_icon) if symbol else 0)
            if symbol:
                self.bar.create_image((left + right) / 2 - body / 2, self.height / 2, anchor="w", tags=(f"icon{i}",))
            self.bar.create_text(text_x, self.height / 2, text=name, font=self.font, fill=self.colors[i], anchor="w",
                                 tags=(f"tab{i}",))
            self._paint_tab(i)

    def _paint_tab(self, i):
        colour = self.colors[i]
        self.bar.itemconfigure(f"tab{i}", fill=colour)
        if self.icons[i]:
            picture = photo(icon_picture(self.icons[i], int(self.ICON * self.scale), colour), self.bar)
            self.icon_photos[i] = picture
            self.bar.itemconfigure(f"icon{i}", image=picture)

    def _place_pill(self, left, right):
        top, bottom = self._track()
        pad = int(2 * self.scale)
        width, height = max(10, round(right - left)), round(bottom - top) - 2 * pad
        self._pill_photo = photo(pill_picture(width, height), self.bar)
        self.bar.itemconfigure(self.pill, image=self._pill_photo)
        self.bar.coords(self.pill, left - 4, top + pad - 4)

    def _at(self, x):
        for i, (left, right) in enumerate(self.spans):
            if left <= x <= right:
                return i
        return None

    def _click(self, x):
        i = self._at(x)
        if i is not None:
            self.select(i)

    def _point(self, i):
        if i != self.hover:
            self.hover = i
            self.bar.configure(cursor="hand2" if i is not None else "")
            self._recolor()

    def _recolor(self):
        for i in range(len(self.names)):
            goal = GREEN if i == self.current else TEXT if i == self.hover else MUTED
            if goal != self.colors[i]:
                start = self.colors[i]

                def step(t, i=i, start=start, goal=goal):
                    self.colors[i] = mix(start, goal, round(t * 8) / 8)  # (8 shades is plenty for a tiny icon)
                    self._paint_tab(i)

                self.motion.run((id(self), "color", i), 170, step)

    def _slide_pill(self):
        left, right = self.spans[self.current]
        start = list(self.pill_at)

        def step(t):
            self.pill_at = [start[0] + (left - start[0]) * t, start[1] + (right - start[1]) * t]
            self._place_pill(*self.pill_at)

        self.motion.run((id(self), "pill"), 380, step, ease=spring)

    def _swap(self, old, new):
        key = (id(self), "page")
        self.motion.stop(key)
        if old is not None:
            self.pages[old].place_configure(x=0)  # in case it was still sliding in when we left it
        for i, page in enumerate(self.pages):
            if i not in (old, new):
                page.place_forget()
        page = self.pages[new]
        page.place(x=0, y=0, relwidth=1, relheight=1)
        page.lift()

        def settle():
            for i, other in enumerate(self.pages):
                if i != new:
                    other.place_forget()
            self.event_generate("<<TabShown>>")

        if old is None or not ANIMATE:
            settle()
            return
        shift = (1 if new > old else -1) * int(40 * self.scale)  # slides in from the side it belongs to
        page.place_configure(x=shift)
        page.update_idletasks()  # lay it out before the clock starts, so the slide does not stutter
        self.motion.run(key, 240, lambda t: page.place_configure(x=int(shift * (1 - t))), done=settle)

    def destroy(self):
        for name in ("page", "pill"):
            self.motion.stop((id(self), name))
        super().destroy()


# ------------------------------------------------------------------ rounded cards with a soft shadow
class Surface(tk.Canvas):
    """A smooth rounded card with a real blurred shadow. Put widgets in `.body`. The card grows to fit what is
    inside it, unless `stretch` is on: then it fills the space it is given (used for tables). With `hover` the card
    can be raised (`lift_to(1)`): it moves up a little and its shadow grows and deepens.
    """

    def __init__(self, parent, motion, scale, stretch=False, radius=12, inset=10, min_height=0, hover=False):
        self.margin = margin_for(hover, scale)
        super().__init__(parent, width=1, height=max(1, min_height), bg=background_of(parent), highlightthickness=0)
        self.motion, self.scale, self.stretch, self.level = motion, scale, stretch, 0.0
        self.radius, self.inset, self.size = int(radius * scale), int(inset * scale), None
        self.key = ("surface", id(self))
        self.picture = self.create_image(0, 0, anchor="nw")
        self.body = tk.Frame(self, bg=WHITE)
        self.window = self.create_window(0, 0, window=self.body, anchor="nw")
        registry.add(self)
        self.bind("<Configure>", lambda e: self._resized())
        if not stretch:
            self.body.bind("<Configure>", lambda e: self._fit())

    def restyle(self):
        self.configure(bg=background_of(self.master))
        if self.size is not None:
            self._render(self.level)

    def _fit(self):
        extra = 2 * (self.inset + self.margin)
        wanted = (self.body.winfo_reqwidth() + extra, self.body.winfo_reqheight() + extra)
        if wanted != (int(self.cget("width")), int(self.cget("height"))):
            self.configure(width=wanted[0], height=wanted[1])

    def _resized(self):
        size = (self.winfo_width(), self.winfo_height())
        if size == self.size or size[0] < 8 or size[1] < 8:
            return  # (moving a card, for example while a page slides, changes nothing: no redraw)
        if self.size is None:
            self._render(self.level)
        else:
            self.motion.later((self.key, "render"), 30, lambda: self._render(self.level))

    def _render(self, level):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            w, h = self.size or (w, h)
        self.size, self.level, m = (w, h), level, self.margin
        card_w, card_h = w - 2 * m, h - 2 * m
        self._photo = photo(card_picture(card_w, card_h, self.radius, round(level * 10), m, self.scale), self)
        self.itemconfigure(self.picture, image=self._photo)
        lift = round(level * 2 * self.scale)
        self.coords(self.window, m + self.inset, m + self.inset - lift)
        self.itemconfigure(self.window, width=max(1, card_w - 2 * self.inset),
                           height=max(1, card_h - 2 * self.inset) if self.stretch else 0)

    def chrome(self):
        """The height the card adds around what is inside it (padding and room for the shadow)."""
        return 2 * (self.inset + self.margin)

    def lift_to(self, target, ms=170):
        start = self.level
        self.motion.run((self.key, "lift"), ms, lambda t: self._render(start + (target - start) * t))

    def destroy(self):
        for name in ("lift", "render"):
            self.motion.stop((self.key, name))
        super().destroy()


class Panel(Surface):
    """A card with an optional title. Put widgets in `.content`."""

    def __init__(self, parent, motion, scale, title="", stretch=False, min_height=0, inset=10):
        super().__init__(parent, motion, scale, stretch=stretch, radius=16, inset=inset, min_height=min_height)
        if title:
            tk.Label(self.body, text=title, bg=WHITE, fg=TEXT, font=font(11, "bold"), anchor="w").pack(
                fill="x", pady=(0, int(4 * scale)))
        self.content = tk.Frame(self.body, bg=WHITE)
        self.content.pack(fill="both", expand=True)


# ------------------------------------------------------------------ the Overview: one canvas, drawn like a phone home screen
def sky_color(y, height):
    """The colour of the soft gradient at height y: blue-grey at the top, fading into the page colour."""
    t = y / max(1, height)
    if t < 0.38:
        return mix(SKY_TOP, SKY_MID, t / 0.38)
    return mix(SKY_MID, BG, min(1.0, (t - 0.38) / 0.45))


@lru_cache(maxsize=8)
def sky_picture(w, h):
    column = Image.new("RGB", (1, h))
    for y in range(h):
        column.putpixel((0, y), rgb(sky_color(y, h)))
    return column.resize((w, h))


def glass_tint(y, height):
    """What a frosted card looks like at height y (the gradient seen through the glass)."""
    return mix(sky_color(y, height), GLASS, GLASS_ALPHA / 255)


def money0(value):
    return f"₱{value:,.0f}"


def count0(value):
    return f"{value:,.0f}"


class Dashboard(tk.Canvas):
    """The Overview page, drawn as one canvas like a phone home screen: a soft gradient, a big 'Today' with a progress
    ring, a focus card (the plan for the day you choose), three frosted cards, and a 7-day strip whose pill glides to
    the day you pick. The cards fly in one after another when the page opens, rise when you point at them, and a soft
    spotlight follows the mouse over them.

    The program gives it numbers with show(data) and set_focus(focus); it reports clicks back through the three
    functions it was given: on_card(tab number), on_day(date) and on_open(date).
    """
    LETTERS = "MTWTFSS"
    CARDS = (("sales", "TOTAL SALES", 2), ("orders", "ORDERS WAITING", 1), ("stock", "TO REORDER", 4))
    GROUPS = ("head", "focus", "sales", "orders", "stock", "week")
    SPOTS = ("focus", "sales", "orders", "stock")

    def __init__(self, parent, motion, scale, today, on_card, on_day, on_open):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0)
        self.motion, self.scale, self.today = motion, scale, today
        self.on_card, self.on_day, self.on_open = on_card, on_day, on_open
        self.key = ("dashboard", id(self))
        self.data, self.focus, self.selected, self.values = None, None, today, []
        self.size, self.cards, self.text, self.days, self.ink = None, {}, {}, [], {}
        self.levels, self.lifted, self.shown, self.hover_day = {}, {}, {}, None
        self.offset, self.saved, self.revealing, self.last_spot = {}, {}, False, 0.0
        self.button = Button(self, motion, "Open production plan", self._open, primary=True)
        registry.add(self)
        self.bind("<Configure>", lambda e: self._resized())
        self.bind("<Motion>", self._moved)
        self.bind("<Leave>", lambda e: self._point(None, None, 0, 0))
        self.bind("<Button-1>", self._clicked)

    def restyle(self):
        self.configure(bg=BG)
        if self.size is not None:
            self._layout()

    # --- drawing the page (again, when the window changes size)
    def _resized(self):
        size = (self.winfo_width(), self.winfo_height())
        if size == self.size or size[0] < 300 or size[1] < 200:
            return
        if self.size is None:
            self._layout()
        else:
            self.motion.later((self.key, "layout"), 40, self._layout)

    def _glass(self, name, x, y, w, h, radius=22):
        s = self.scale
        m = margin_for(True, s)
        self.cards[name] = {"rect": (x, y, w, h), "radius": int(radius * s), "margin": m}
        self.levels[name], self.lifted[name], self.offset[name] = 0.0, 0, 0
        picture = photo(glass_picture(w, h, int(radius * s), 0, m, s), self)
        item = self.create_image(x - m, y - m, image=picture, anchor="nw")
        spot = self.create_image(x - m, y - m, anchor="nw", state="hidden")  # the spotlight (above the glass, below the text)
        self.cards[name].update(item=item, photo=picture, spot=spot)

    def _write(self, x, y, text, size, weight, fill, group, anchor="nw", **options):
        """Create a text and remember its colour (the entrance animation fades it in from the background)."""
        item = self.create_text(x, y, text=text, anchor=anchor, font=font(size, weight), fill=fill, tags=f"t_{group}",
                                **options)
        self.ink[item] = fill
        return item

    def _layout(self):
        s = self.scale
        W, H = self.winfo_width(), self.winfo_height()
        self.motion.stop_group(self.key)
        self.configure(bg=BG)
        self.size, self.revealing = (W, H), False
        self.delete("all")
        self.cards, self.text, self.days, self.ink, self.saved = {}, {}, [], {}, {}
        self._sky = photo(sky_picture(W, H), self)
        self.create_image(0, 0, image=self._sky, anchor="nw")
        pad, gap, top = int(28 * s), int(14 * s), int(20 * s)
        # --- "Today", the date, and the progress ring
        self._write(pad, top, "Today", 26, "bold", TEXT, "head")
        self._write(pad, top + int(42 * s), f"{self.today:%A, %d %B}", 11, "normal", MUTED, "head")
        ring = int(54 * s)
        self.ring_size, self.ring_at = ring, (W - pad - ring, top)
        self.ring_item = self.create_image(*self.ring_at, anchor="nw", tags="t_head")
        self.text["percent"] = self._write(self.ring_at[0] + ring / 2, top + ring / 2, "0%", 11, "bold", TEXT, "head",
                                           anchor="center")
        self._write(self.ring_at[0] - int(14 * s), top + ring / 2, "Orders\npicked up", 9, "normal", MUTED, "head",
                    anchor="e", justify="right")
        # --- the focus card
        y, fw, fh = top + int(76 * s), W - 2 * pad, int(140 * s)
        self._glass("focus", pad, y, fw, fh)
        ix = pad + int(26 * s)
        self.text["focus_caption"] = self._write(ix, y + int(18 * s), "", 9, "bold", MUTED, "focus")
        self.text["focus_title"] = self._write(ix, y + int(38 * s), "", 20, "bold", TEXT, "focus")
        button_w = self.button.w + 2 * self.button.PAD
        self.text["focus_text"] = self._write(ix, y + int(74 * s), "", 10, "normal", MUTED, "focus",
                                              width=fw - int(52 * s) - button_w - int(20 * s))
        self.button.configure(bg=glass_tint(y + fh / 2, H))  # the button sits at the right of the card, in the middle
        self.create_window(pad + fw - int(26 * s), y + fh / 2, window=self.button, anchor="e", tags="t_focus")
        # --- three frosted cards
        y2, rw, rh = y + fh + gap, (fw - 2 * gap) // 3, int(108 * s)
        for n, (name, caption, _) in enumerate(self.CARDS):
            x = pad + n * (rw + gap)
            self._glass(name, x, y2, rw, rh)
            inner = x + int(24 * s)
            self._write(inner, y2 + int(16 * s), caption, 9, "bold", MUTED, name)
            self.text[name] = self._write(inner, y2 + int(32 * s), "0", 24, "bold", TEXT, name)
            self.text[name + "_note"] = self._write(inner, y2 + int(72 * s), "", 9, "normal", MUTED, name, width=rw - int(48 * s))
        spark_w, spark_h = int(rw * 0.42), int(36 * s)
        self.spark_box = (pad + rw - int(24 * s) - spark_w, y2 + int(32 * s), spark_w, spark_h)
        self.spark_item = self.create_image(self.spark_box[0], self.spark_box[1], anchor="nw", tags="t_sales")
        # --- the 7-day strip
        y3, wh = y2 + rh + gap, int(108 * s)
        self._glass("week", pad, y3, fw, wh)
        self._write(ix, y3 + int(16 * s), "NEXT 7 DAYS", 9, "bold", MUTED, "week")
        first = self.today  # (the strip starts today)
        self._write(pad + fw - int(26 * s), y3 + int(16 * s), f"{first:%d %b} - {first + timedelta(days=6):%d %b}", 9,
                    "normal", MUTED, "week", anchor="ne")
        left, width = pad + int(26 * s), fw - int(52 * s)
        col, base = width / 7, y3 + int(40 * s)
        self.pill_size = (int(38 * s), int(58 * s))
        self._pill_photo = photo(shape(*self.pill_size, self.pill_size[0] // 2, PRIMARY), self)
        self._soft_photo = photo(shape(*self.pill_size, self.pill_size[0] // 2, SOFT_PILL), self)
        self.soft_item = self.create_image(0, 0, image=self._soft_photo, anchor="nw", state="hidden", tags="t_week")
        self.pill_item = self.create_image(0, 0, image=self._pill_photo, anchor="nw", state="hidden", tags="t_week")
        dot = int(6 * s)
        self._dots = {"off": photo(disc(dot, GREEN), self), "on": photo(disc(dot, ink(PRIMARY)), self)}
        for i in range(7):
            cx = left + col * (i + 0.5)
            day = first + timedelta(days=i)
            letter = self._write(cx, base + int(14 * s), self.LETTERS[day.weekday()], 9, "bold", MUTED, "week", anchor="center")
            number = self._write(cx, base + int(36 * s), str(day.day), 13, "bold", TEXT, "week", anchor="center")
            dot_item = self.create_image(cx, base + int(51 * s), image=self._dots["off"], state="hidden", tags="t_week")
            self.days.append({"date": day, "cx": cx, "box": (cx - col / 2, y3 + int(30 * s), cx + col / 2, y3 + wh),
                              "letter": letter, "number": number, "dot": dot_item, "pending": False,
                              "top": base - int(2 * s)})
        self._place_pill(self.selected)
        self._populate(False)

    # --- showing numbers
    def show(self, data, replay=False):
        """data: sales, days, best, spark, pending, pending_value, low, low_names, done (0..1), week (list of
        booleans: a pickup is waiting that day), selected (a date)."""
        self.data = data
        if data.get("selected") is not None:
            self.selected = data["selected"]
        if self.size is not None:
            self._populate(replay)

    def set_focus(self, focus, replay=True):
        """focus: day (date), pieces, batches, lines (list of text)."""
        self.focus = focus
        if self.size is not None:
            self._show_focus(replay)

    def _count(self, name, item, target, fmt, replay):
        start = 0 if replay else self.shown.get(name, 0)
        self.shown[name] = target
        self.motion.run((self.key, "count", name), 700 if start != target else 0,
                        lambda t: self.itemconfigure(item, text=fmt(start + (target - start) * t)))

    def _populate(self, replay):
        d = self.data
        if d is None:
            return
        self._count("sales", self.text["sales"], d["sales"], money0, replay)
        self.itemconfigure(self.text["sales_note"], text=f"{d['days']} days of sales" + (f"  -  top: {d['best']}" if d["best"] else ""))
        self._count("orders", self.text["orders"], d["pending"], count0, replay)
        self.itemconfigure(self.text["orders_note"], text=d["pending_value"])
        self._count("stock", self.text["stock"], d["low"], count0, replay)
        self.itemconfigure(self.text["stock_note"], text=d["low_names"])
        start = 0 if replay else self.shown.get("percent", 0)
        self.shown["percent"] = round(d["done"] * 100)

        def ring(t):
            value = start + (self.shown["percent"] - start) * t
            self._ring_photo = photo(ring_picture(self.ring_size, round(value), GREEN, TRACK), self)
            self.itemconfigure(self.ring_item, image=self._ring_photo)
            self.itemconfigure(self.text["percent"], text=f"{value:.0f}%")

        self.motion.run((self.key, "ring"), 900 if start != self.shown["percent"] else 0, ring)
        self._spark(d["spark"], replay)
        for i, day in enumerate(self.days):
            day["pending"] = d["week"][i]
            self.itemconfigure(day["dot"], state="normal" if day["pending"] else "hidden")
        self._paint_days()
        self._place_pill(self.selected)
        if self.focus is not None:
            self._show_focus(replay)
        if replay:
            self._stagger()

    def _show_focus(self, replay):
        f = self.focus
        label = "TODAY" if f["day"] == self.today else f"{f['day']:%A, %d %B}".upper()
        self.itemconfigure(self.text["focus_caption"], text=f"BAKING PLAN  -  {label}")
        self.itemconfigure(self.text["focus_text"], text="\n".join(f["lines"]))
        start = (0, 0) if replay else self.shown.get("focus", (0, 0))
        self.shown["focus"] = (f["pieces"], f["batches"])
        item = self.text["focus_title"]
        self.motion.run((self.key, "count", "focus"), 650 if start != self.shown["focus"] else 0, lambda t: self.itemconfigure(
            item, text=f"{round(start[0] + (f['pieces'] - start[0]) * t):,} pieces in "
                       f"{round(start[1] + (f['batches'] - start[1]) * t)} batches"))

    def _spark(self, values, replay):
        self.values = list(values)
        self.motion.run((self.key, "spark"), 900 if replay else 0, self._draw_spark, ease=ease_in_out)

    def _draw_spark(self, progress):
        _, _, width, height = self.spark_box
        values = self.values
        if len(values) < 2 or width < 20:
            self.itemconfigure(self.spark_item, image="")
            return
        big, pad = 3, 4
        image = Image.new("RGBA", (width * big, height * big), (0, 0, 0, 0))
        low, span = min(values), (max(values) - min(values)) or 1
        points = [((pad + i * (width - 2 * pad) / (len(values) - 1)) * big,
                   (height - pad - (v - low) / span * (height - 2 * pad)) * big) for i, v in enumerate(values)]
        reach = progress * (len(points) - 1)
        index, part = int(reach), reach - int(reach)
        shown = points[:index + 1]
        if index < len(points) - 1:
            (x1, y1), (x2, y2) = points[index], points[index + 1]
            shown.append((x1 + (x2 - x1) * part, y1 + (y2 - y1) * part))
        draw = ImageDraw.Draw(image)
        if len(shown) >= 2:
            draw.line(shown, fill=rgb(GREEN) + (255,), width=2 * big, joint="curve")
            x, y = shown[-1]
            draw.ellipse((x - 3.2 * big, y - 3.2 * big, x + 3.2 * big, y + 3.2 * big), fill=rgb(GREEN) + (255,),
                         outline=rgb(WHITE) + (255,), width=big)
        self._spark_photo = photo(image.resize((width, height), SMOOTH), self)
        self.itemconfigure(self.spark_item, image=self._spark_photo)

    # --- the cards fly in one after another
    def _stagger(self):
        if not ANIMATE or self.size is None:
            return
        self.revealing = True
        for i, name in enumerate(self.GROUPS):
            self._cover(name, 0.0)
            self.motion.later((self.key, "enter-wait", name), 40 + 85 * i, lambda n=name: self._enter(n))

    def _group_images(self, name):
        return {"head": [self.ring_item], "sales": [self.spark_item],
                "week": [self.pill_item] + [d["dot"] for d in self.days]}.get(name, [])

    def _cover(self, name, t):
        """Show group `name` at strength t (0 = invisible, 1 = normal). It also sits a little lower while t < 1."""
        shift = int(16 * self.scale)
        bg = None
        for item in self.find_withtag(f"t_{name}"):
            kind = self.type(item)
            if kind == "text":
                y = self.coords(item)[1]
                self.itemconfigure(item, fill=mix(sky_color(y, self.size[1]), self.ink.get(item, TEXT), t))
        for item in self._group_images(name):  # pictures simply appear once the group is mostly there
            if t <= 0:
                self.saved.setdefault(item, self.itemcget(item, "state"))
                self.itemconfigure(item, state="hidden")
            elif t >= 0.55 and item in self.saved:
                self.itemconfigure(item, state=self.saved.pop(item))
        card = self.cards.get(name)
        if card:
            x, y, w, h = card["rect"]
            image = glass_picture(w, h, card["radius"], 0, card["margin"], self.scale)
            if t < 1:
                image = image.copy()
                image.putalpha(image.getchannel("A").point(lambda v: int(v * max(0.0, t))))
            card["photo"] = photo(image, self)
            self.itemconfigure(card["item"], image=card["photo"])
        dy = round((1 - min(1.0, t)) * shift)
        delta = dy - self.offset.get(name, 0)
        if delta:
            self.move(f"t_{name}", 0, delta)
            if card:
                self.move(card["item"], 0, delta)
            self.offset[name] = dy

    def _enter(self, name):
        def done():
            self._cover(name, 1.0)
            if name == self.GROUPS[-1]:
                self.revealing = False

        self.motion.run((self.key, "enter", name), 520, lambda t: self._cover(name, min(1.0, t)), done=done, ease=ease_out)

    # --- the 7-day strip
    def _paint_days(self):
        light = ink(PRIMARY)
        for day in self.days:
            on = day["date"] == self.selected
            self.itemconfigure(day["number"], fill=light if on else TEXT)
            self.itemconfigure(day["letter"], fill=mix(PRIMARY, light, 0.62) if on else MUTED)
            self.itemconfigure(day["dot"], image=self._dots["on" if on else "off"])
            self.ink[day["number"]], self.ink[day["letter"]] = (light if on else TEXT), (mix(PRIMARY, light, 0.62) if on else MUTED)

    def _place_pill(self, date_):
        for day in self.days:
            if day["date"] == date_:
                x = day["cx"] - self.pill_size[0] / 2
                self.coords(self.pill_item, x, day["top"])
                self.itemconfigure(self.pill_item, state="normal")
                self.pill_x = x
                return
        self.itemconfigure(self.pill_item, state="hidden")

    def choose(self, date_):
        """Glide the pill to a day (with a little spring) and tell the program (it answers with that day's plan)."""
        old = next((d for d in self.days if d["date"] == self.selected), None)
        new = next((d for d in self.days if d["date"] == date_), None)
        if new is None or date_ == self.selected:
            return
        start_x = getattr(self, "pill_x", new["cx"] - self.pill_size[0] / 2)
        goal_x = new["cx"] - self.pill_size[0] / 2
        self.selected = date_
        self.itemconfigure(self.soft_item, state="hidden")
        light = ink(PRIMARY)

        def step(t):
            self.coords(self.pill_item, start_x + (goal_x - start_x) * t, new["top"])
            self.pill_x = start_x + (goal_x - start_x) * t
            k = max(0.0, min(1.0, t))
            for day, rising in ((old, False), (new, True)):
                if day is not None:
                    f = k if rising else 1 - k
                    self.itemconfigure(day["number"], fill=mix(TEXT, light, f))
                    self.itemconfigure(day["letter"], fill=mix(MUTED, mix(PRIMARY, light, 0.62), f))
                    self.itemconfigure(day["dot"], image=self._dots["on" if f > 0.5 else "off"])
            if k >= 1.0:
                self._paint_days()

        self.motion.run((self.key, "pill"), 420, step, ease=spring)
        self.on_day(date_)

    # --- the mouse
    def _hit(self, x, y):
        for name, card in self.cards.items():
            cx, cy, w, h = card["rect"]
            if cx <= x <= cx + w and cy <= y <= cy + h:
                if name == "week":
                    for day in self.days:
                        left, top, right, bottom = day["box"]
                        if left <= x <= right and y >= top:
                            return name, day
                return name, None
        return None, None

    def _moved(self, event):
        self._point(*self._hit(event.x, event.y), event.x, event.y)

    def _point(self, name, day, x, y):
        clickable = name in ("sales", "orders", "stock") or day is not None
        self.configure(cursor="hand2" if clickable else "")
        for card in self.cards:  # a card rises while the mouse is on it
            want = 1.0 if card == name and card in ("sales", "orders", "stock") else 0.0
            if self.levels.get(card, 0.0) != want and (want or self.levels.get(card, 0.0) > 0):
                self._lift(card, want)
        for card in self.SPOTS:
            if card != name and card in self.cards and self.itemcget(self.cards[card]["spot"], "state") != "hidden":
                self.itemconfigure(self.cards[card]["spot"], state="hidden")
        if name in self.SPOTS:
            self._spot(name, x, y)
        index = self.days.index(day) if day is not None else None
        if index != self.hover_day:
            self.hover_day = index
            show = index is not None and day["date"] != self.selected
            if show:
                self.coords(self.soft_item, day["cx"] - self.pill_size[0] / 2, day["top"])
            self.itemconfigure(self.soft_item, state="normal" if show else "hidden")

    def _spot(self, name, x, y):
        """A soft white glow that follows the mouse inside a card."""
        now = time.perf_counter()
        if now - self.last_spot < 0.025:
            return
        self.last_spot = now
        card = self.cards[name]
        cx, cy, w, h = card["rect"]
        lx, ly = int(max(0, min(w - 1, x - cx))) // 8 * 8, int(max(0, min(h - 1, y - cy))) // 8 * 8
        card["spot_photo"] = photo(spot_picture(w, h, card["radius"], card["margin"], lx, ly, int(150 * self.scale)), self)
        self.itemconfigure(card["spot"], image=card["spot_photo"], state="normal")

    def _clicked(self, event):
        name, day = self._hit(event.x, event.y)
        if day is not None:
            self.choose(day["date"])
        elif name in ("sales", "orders", "stock"):
            self.on_card(next(tab for key, _, tab in self.CARDS if key == name))

    def _lift(self, name, target, ms=170):
        card = self.cards[name]
        start, s = self.levels[name], self.scale
        x, y, w, h = card["rect"]

        def step(t):
            level = start + (target - start) * t
            self.levels[name] = level
            card["photo"] = photo(glass_picture(w, h, card["radius"], round(level * 10), card["margin"], s), self)
            self.itemconfigure(card["item"], image=card["photo"])
            dy = -round(level * 2 * s)
            self.move(f"t_{name}", 0, dy - self.lifted[name])
            self.lifted[name] = dy

        self.motion.run((self.key, "lift", name), ms, step)

    def _open(self):
        self.on_open(self.selected)

    def destroy(self):
        self.motion.stop_group(self.key)
        super().destroy()


# ------------------------------------------------------------------ the success note (toast)
class Toast:
    """A short note that slides up in the bottom-right corner (its tick draws itself), stays a moment, slides away."""

    def __init__(self, root, motion, scale):
        self.root, self.motion, self.scale, self.box, self.last = root, motion, scale, None, ""
        self.key = ("toast", id(self))

    def show(self, text):
        self.dismiss()
        s, dark, m = self.scale, "#1f2421", int(10 * self.scale)
        self.last = text
        label_font = tkfont.Font(font=font(10))
        size = int(26 * s)
        w, h = label_font.measure(text) + size + int(50 * s), int(48 * s)
        box = tk.Canvas(self.root, width=w + 2 * m, height=h + 2 * m, highlightthickness=0, bd=0, bg=background_of(self.root))
        box._card = photo(card_picture(w, h, h // 2, 6, m, s, dark, "#3a403c"), box)
        box.create_image(0, 0, image=box._card, anchor="nw")
        box.tick = box.create_image(m + int(14 * s), m + (h - size) // 2, anchor="nw")
        box.create_text(m + int(14 * s) + size + int(10 * s), m + h / 2, text=text, anchor="w", fill=PURE_WHITE, font=font(10))
        self.box = box
        hidden, shown = int(110 * s), -int(14 * s)
        box.place(relx=1.0, rely=1.0, anchor="se", x=-int(10 * s), y=hidden)
        tk.Misc.lift(box)  # raise the window (a canvas's own lift() raises its drawn items instead)

        def tick(t):
            box._tick = photo(tick_picture(size, t), box)
            box.itemconfigure(box.tick, image=box._tick)

        tick(0.0)
        self.motion.run(self.key, 420, lambda t: box.place_configure(y=int(hidden + (shown - hidden) * t)),
                        done=lambda: self.motion.later(self.key, 2600, self.leave), ease=spring)
        self.motion.run((self.key, "tick"), 560, tick, ease=ease_in_out)

    def leave(self):
        box = self.box
        if box is None:
            return
        shown, hidden = -int(14 * self.scale), int(110 * self.scale)
        self.motion.run(self.key, 220, lambda t: box.place_configure(y=int(shown + (hidden - shown) * t)),
                        done=self.dismiss)

    def dismiss(self):
        self.motion.stop(self.key)
        self.motion.stop((self.key, "tick"))
        if self.box is not None:
            self.box.destroy()
            self.box = None


class Tooltip:
    """A small label (dark on light pages, light on dark ones) that appears under a widget after the mouse rests on it."""

    def __init__(self, widget, text, motion):
        self.widget, self.text, self.motion, self.tip = widget, text, motion, None
        self.key = ("tip", id(self))
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _enter(self, event=None):
        self.hide()
        self.motion.later(self.key, 600, self.show)

    def show(self):
        if not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(tip, text=self.text, bg=PRIMARY, fg=ink(PRIMARY), font=font(9), padx=10, pady=5).pack()
        tip.geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 4}")
        self.tip = tip
        if ANIMATE:
            tip.attributes("-alpha", 0.0)
            self.motion.run((self.key, "fade"), 150, lambda t: tip.attributes("-alpha", 0.96 * t))

    def hide(self, event=None):
        self.motion.stop(self.key)
        self.motion.stop((self.key, "fade"))
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


# ------------------------------------------------------------------ photographing the window
class Unavailable(Exception):
    """The window cannot be photographed (not Windows, or minimised): the plain message box is used instead."""


def snapshot(window):
    """A picture (Pillow image) of what a Tk window shows in its client area, taken with PrintWindow."""
    try:
        import ctypes
        from ctypes import wintypes
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        if window.state() == "iconic":
            raise Unavailable
        window.update()
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top

        class BitmapInfo(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        hdc = user32.GetWindowDC(hwnd)
        memory = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(memory, bitmap)
        user32.PrintWindow(hwnd, memory, 2)  # 2 = PW_RENDERFULLCONTENT
        info = BitmapInfo(ctypes.sizeof(BitmapInfo), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(memory, bitmap, 0, h, buffer, ctypes.byref(info), 0)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(hwnd, hdc)
        full = Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1).convert("RGB")
        left, top = window.winfo_rootx() - rect.left, window.winfo_rooty() - rect.top
        return full.crop((left, top, left + window.winfo_width(), top + window.winfo_height()))
    except Unavailable:
        raise
    except Exception as error:
        raise Unavailable from error


class Veil:
    """A picture of the window, laid over it in a see-through window of its own. Change anything underneath (here: the
    whole theme), then fade() the picture away: the old look dissolves into the new one."""

    def __init__(self, app):
        self.app, self.win = app, None
        if not ANIMATE:
            return
        try:
            image = snapshot(app)
        except Unavailable:
            return
        self.win = tk.Toplevel(app)
        self.win.overrideredirect(True)
        self.win.transient(app)
        self.win.geometry(f"{image.width}x{image.height}+{app.winfo_rootx()}+{app.winfo_rooty()}")
        canvas = tk.Canvas(self.win, width=image.width, height=image.height, highlightthickness=0, bd=0)
        canvas.pack()
        canvas._photo = photo(image, canvas)
        canvas.create_image(0, 0, image=canvas._photo, anchor="nw")
        self.win.update()

    def fade(self, ms=420, done=None):
        win = self.win
        if win is None:
            if done:
                done()
            return

        def finish():
            try:
                win.destroy()
            except tk.TclError:
                pass
            self.win = None
            if done:
                done()

        self.app.motion.run(("veil", id(self)), ms, lambda t: win.attributes("-alpha", 1 - t), done=finish, ease=ease_in_out)


# ------------------------------------------------------------------ pop-up dialogs over a frosted window
class Sheet:
    """A message that pops up as a smooth card over a frosted, dimmed copy of the window (like an iPhone alert).
    The window blurs and dims, the card fades in and springs into place. It waits for an answer (modal).
    `.result` holds the answer; `.buttons` are its buttons."""

    ICONS = {"info": ("GREEN", "i"), "warn": ("AMBER", "!"), "error": ("RED", "!"), "ask": ("GREEN", "?")}
    current = None  # the dialog that is open right now (tests use this to press its buttons)

    def __init__(self, app, kind, title, text, labels):
        self.app, self.motion, s = app, app.motion, app.scale
        self.result = False if kind == "ask" else "ok"
        self.closing = False
        w, h = app.winfo_width(), app.winfo_height()
        base = snapshot(app).resize((w, h))
        small = base.resize((max(1, w // 2), max(1, h // 2)), SMOOTH).filter(ImageFilter.GaussianBlur(4))
        frosted = small.resize((w, h), SMOOTH).point(lambda v: int(v * 0.6))  # blurred and darker
        self.base, self.frosted = base, frosted
        self.overlay = tk.Canvas(app, bg="#222222", highlightthickness=0, bd=0, cursor="arrow")
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.backdrop = self.overlay.create_image(0, 0, anchor="nw")
        self.steps = [photo(Image.blend(base, frosted, k / 4), self.overlay) for k in range(5)]  # ready before it opens
        self._set_backdrop(0.0)
        tk.Misc.lift(self.overlay)
        # the card: a picture, with the real labels and buttons on top
        self.body = tk.Frame(self.overlay, bg=WHITE)
        colour = globals()[self.ICONS[kind][0]]
        symbol = self.ICONS[kind][1]
        icon = tk.Canvas(self.body, width=int(40 * s), height=int(40 * s), bg=WHITE, highlightthickness=0)
        icon._photo = photo(disc(int(40 * s), colour), icon)
        icon.create_image(0, 0, image=icon._photo, anchor="nw")
        icon.create_text(int(20 * s), int(20 * s), text=symbol, fill=PURE_WHITE, font=font(16, "bold"))
        icon.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, int(16 * s)))
        tk.Label(self.body, text=title, bg=WHITE, fg=TEXT, font=font(13, "bold"), anchor="w").grid(
            row=0, column=1, sticky="w")
        tk.Label(self.body, text=text, bg=WHITE, fg=MUTED, font=font(10), anchor="w", justify="left",
                 wraplength=int(330 * s)).grid(row=1, column=1, sticky="w", pady=(int(4 * s), 0))
        row = tk.Frame(self.body, bg=WHITE)
        row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(int(18 * s), 0))
        self.buttons = []
        for n, label in reversed(list(enumerate(labels))):
            last = n == len(labels) - 1
            button = Button(row, self.motion, label, lambda last=last: self.finish(last), primary=last)
            button.pack(side="right", padx=(int(6 * s), 0))
            self.buttons.append(button)
        self.body.update_idletasks()
        inset, margin = int(22 * s), margin_for(True, s)
        card_w, card_h = self.body.winfo_reqwidth() + 2 * inset, self.body.winfo_reqheight() + 2 * inset
        self.card = card_picture(card_w, card_h, int(16 * s), 6, margin, s)
        self.x, self.y = (w - card_w) // 2 - margin, (h - card_h) // 2 - margin - int(16 * s)
        self.inset, self.margin, self.rise = inset, margin, int(22 * s)
        self.card_item = self.overlay.create_image(self.x, self.y + self.rise, anchor="nw")
        self.body_item = self.overlay.create_window(self.x + margin + inset, self.y + margin + inset + self.rise,
                                                    window=self.body, anchor="nw", state="hidden")
        self.done = tk.IntVar(app)
        self.overlay.bind("<Escape>", lambda e: self.finish(False))
        self.overlay.bind("<Return>", lambda e: self.finish(True))
        self.overlay.focus_set()
        self.overlay.grab_set()
        Sheet.current = self
        self._pop(True)
        app.wait_variable(self.done)

    def _set_backdrop(self, t):
        self.overlay.itemconfigure(self.backdrop, image=self.steps[round(max(0.0, min(1.0, t)) * 4)])

    def _set_card(self, t):
        shown = self.card
        if t < 1:
            shown = self.card.copy()
            shown.putalpha(self.card.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, t)))))
        self._card_photo = photo(shown, self.overlay)
        self.overlay.itemconfigure(self.card_item, image=self._card_photo)
        lift = round(self.rise * (1 - t))  # (with the spring, t goes a little past 1: the card overshoots, then settles)
        self.overlay.coords(self.card_item, self.x, self.y + lift)
        self.overlay.coords(self.body_item, self.x + self.margin + self.inset, self.y + self.margin + self.inset + lift)
        self.overlay.itemconfigure(self.body_item, state="normal" if t >= 0.45 else "hidden")

    def _pop(self, opening):
        key = ("sheet", id(self))
        if opening:
            def step(t):
                self._set_backdrop(min(1.0, t * 1.4))
                self._set_card(t)

            self.motion.run(key, 380, step, ease=spring)
        else:
            def step(t):
                self._set_backdrop(1 - min(1.0, t * 1.2))
                self._set_card(1 - t)

            self.motion.run(key, 180, step, done=self.close, ease=lambda t: t)

    def finish(self, answer):
        if self.closing:
            return
        self.closing = True
        if isinstance(self.result, bool):
            self.result = answer
        self.overlay.grab_release()
        self._pop(False)

    def close(self):
        if Sheet.current is self:
            Sheet.current = None
        try:
            self.overlay.destroy()
        except tk.TclError:
            pass
        self.done.set(1)


class Messages:
    """Message boxes for the program. With animation they are Sheets (a pop-up card over a frosted window); without
    animation, before the main window exists, or if the window cannot be photographed, the plain Windows boxes."""

    def __init__(self):
        self.app = None

    def _show(self, kind, title, text, labels):
        app = self.app
        if ANIMATE and app is not None:
            try:
                if app.winfo_exists():
                    return Sheet(app, kind, title, text, labels).result
            except (tk.TclError, Unavailable):
                pass
        native = {"info": tkmessagebox.showinfo, "warn": tkmessagebox.showwarning, "error": tkmessagebox.showerror,
                  "ask": tkmessagebox.askyesno}[kind]
        return native(title, text)

    def showinfo(self, title, text):
        return self._show("info", title, text, ("OK",))

    def showwarning(self, title, text):
        return self._show("warn", title, text, ("OK",))

    def showerror(self, title, text):
        return self._show("error", title, text, ("OK",))

    def askyesno(self, title, text):
        return self._show("ask", title, text, ("No", "Yes"))


messages = Messages()


# ------------------------------------------------------------------ tables
def hover_rows(tree):
    """Light up the row under the mouse (the row keeps its own colour tags, such as Pending)."""
    last, made = [None], [False]

    def clear(event=None):
        row, last[0] = last[0], None
        if row and tree.exists(row):
            tree.item(row, tags=tuple(t for t in tags_of(tree, row) if t != "hover"))

    def move(event):
        row = tree.identify_row(event.y)
        if row != last[0]:
            clear()
            tree.tag_configure("hover", background=HOVER_ROW)  # (the current theme's colour)
            if row:
                tree.item(row, tags=tags_of(tree, row) + ("hover",))
                last[0] = row

    tree.bind("<Motion>", move, add="+")
    tree.bind("<Leave>", clear, add="+")


def flash_row(motion, tree, row, color=None):
    """Highlight a row that was just added; the colour fades away by itself."""
    if not tree.exists(row):
        return
    color = color or FLASH
    tree.tag_configure("flash", background=color)
    tree.item(row, tags=tags_of(tree, row) + ("flash",))

    def done():
        if tree.exists(row):
            tree.item(row, tags=tuple(t for t in tags_of(tree, row) if t != "flash"))

    shown = [color]

    def step(t):
        shade = mix(color, WHITE, round(t * 10) / 10)  # 10 steps: changing a table tag redraws the whole table
        if shade != shown[0]:
            shown[0] = shade
            tree.tag_configure("flash", background=shade)

    motion.run((id(tree), "flash"), 1600, step, done=done, ease=ease_in_out)


# ------------------------------------------------------------------ Matplotlib charts that grow in
def play_chart(motion, key, canvas, ax, frame, finish, ms=700, ease=ease_out):
    """Animate a chart quickly: the axes are drawn once, then only the moving parts are redrawn (blitting).

    frame(progress) changes the artists and returns the list to draw; finish() puts everything in its final state.
    """
    canvas.draw()
    background = canvas.copy_from_bbox(ax.bbox)

    def step(progress):
        canvas.restore_region(background)
        for artist in frame(progress):
            ax.draw_artist(artist)
        canvas.blit(ax.bbox)

    def done():
        finish()
        canvas.draw()

    motion.run(key, ms, step, done=done, ease=ease)
