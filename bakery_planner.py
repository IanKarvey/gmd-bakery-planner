"""GMD Bakery - Order and Production Planner.

Run:  python bakery_planner.py
Data is stored in orders.csv (created with sample data on first run).
"""
import csv
import io
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, timedelta
from tkinter import font as tkfont, messagebox, ttk

if __name__ == "__main__":  # (must come before the first window is created, or text looks blurry on scaled screens)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GMD.Bakery.Planner")
    except Exception:
        pass


def _make_splash():
    """A small 'starting up' window shown straight away: loading Matplotlib takes a few seconds."""
    try:
        root = tk.Tk()
        scale = max(1.0, root.winfo_fpixels("1i") / 96)
        root.overrideredirect(True)
        root.configure(bg="#175f27")
        w, h = int(380 * scale), int(160 * scale)
        root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
        card = tk.Frame(root, bg="white")
        card.pack(fill="both", expand=True, padx=3, pady=3)
        tk.Label(card, text="GMD Bakery", bg="white", fg="#175f27", font=("Georgia", 26, "bold")).pack(pady=(30, 2))
        tk.Label(card, text="Starting up…", bg="white", fg="#6b7568", font=("Segoe UI", 11)).pack()
        root.attributes("-topmost", True)
        root.update()
        tk._default_root = None  # the program's real window must become tkinter's default one, not this
        return root
    except Exception:
        return None


_SPLASH = _make_splash() if __name__ == "__main__" else None


def _pump_splash():
    """Keep the splash alive while the program builds its window."""
    if _SPLASH is not None:
        try:
            _SPLASH.update()
        except Exception:
            pass


def _close_splash():
    global _SPLASH
    if _SPLASH is not None:
        try:
            _SPLASH.destroy()
        except Exception:
            pass
        _SPLASH = None


try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ImportError:
    _close_splash()
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("Missing library",
                         "Matplotlib is not installed.\n\nOpen a terminal and run:\n"
                         "    python -m pip install matplotlib\n\n"
                         "Or double-click run.bat, which installs it for you.")
    raise SystemExit(1)

from PIL import Image, ImageDraw, ImageOps, ImageStat, ImageTk  # installed together with matplotlib


def _can_write(folder):
    """True only if a file can really be created here (os.access misses Windows folder protection)."""
    probe = os.path.join(folder, ".write_test")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(probe, "w") as f:
            f.write("ok")
    except OSError:
        return False
    try:
        os.remove(probe)
    except OSError:
        pass
    return True


def _app_dir():
    """The folder the program lives in (the folder holding the .exe when it is the packaged version)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_file():
    """orders.csv next to the program; if Windows/permissions block that folder, use another one."""
    here = _app_dir()
    home = os.path.expanduser("~")
    candidates = [here,
                  os.path.join(os.environ.get("LOCALAPPDATA", home), "GMD-Bakery"),
                  os.path.join(home, "GMD-Bakery")]
    for folder in candidates:  # keep using an existing data file so orders never seem to vanish
        if os.path.exists(os.path.join(folder, "orders.csv")) and _can_write(folder):
            return os.path.join(folder, "orders.csv")
    for folder in candidates:
        if _can_write(folder):
            return os.path.join(folder, "orders.csv")
    return os.path.join(here, "orders.csv")  # nothing writable; the app will show a clear error


CSV_FILE = _data_file()
FIELDS = ["order_id", "customer", "product", "quantity", "price", "order_date", "status"]
DATE_FMT = "%Y-%m-%d"
FORCE_DPI = None  # testing only: e.g. 144 simulates a 150% scaled screen
MAX_ROWS = 2000   # rows drawn in the Orders table at once (newest first); search/filters reach the rest
ADD_NOTE = "Record a customer order. Pick a product and the price fills in by itself."

# Product menu (name -> unit price in pesos). Edit freely.
PRODUCTS = {
    "Pandesal": 5.00,
    "Ensaymada": 25.00,
    "Spanish Bread": 12.00,
    "Cheese Bread": 15.00,
    "Pan de Coco": 12.00,
    "Monay": 8.00,
    "Cinnamon Roll": 35.00,
    "Chocolate Cake (slice)": 60.00,
    "Egg Pie (slice)": 40.00,
    "Brownies": 30.00,
}
CUSTOMERS = ["Maria Santos", "Juan Dela Cruz", "Ana Reyes", "Carlo Garcia", "Liza Mendoza",
             "Paolo Cruz", "Grace Bautista", "Mark Ramos", "Joy Villanueva", "Ben Aquino"]

# ---- design tokens (change colors here) ----
BG = "#f5f4ee"             # page background: a warm off-white
SURFACE = "#ffffff"        # cards, header, tab bar
BORDER = "#e4e2d8"
INK = "#15231a"            # main text
MUTED = "#6b7568"          # secondary text
LABEL = "#3f4d3f"          # form captions
PRIMARY = "#175f27"        # the logo's deep green: buttons, key numbers
PRIMARY_HOVER = "#114a1e"
ACCENT = "#63ab33"         # fresh green: highlights, tab underline, charts
SOFT = "#e7f1e1"           # pale green tint
SELECT_BG = "#dcebd2"
PENDING_BG = "#fff7e0"
DANGER = "#b3261e"
FONT = "Segoe UI"
SERIF = "Georgia"          # wordmark only, echoing the logo's serif lettering
CHART_COLORS = ["#175f27", "#63ab33", "#a8d27a", "#e9b44c", "#c8743a",
                "#8a5a3b", "#3b8ea5", "#7a6fb0", "#d9534f", "#8c9a8a"]

_SEMIBOLD = None           # set once Tk is running, if "Segoe UI Semibold" is installed


def font(size, bold=False):
    if bold and _SEMIBOLD:
        return (_SEMIBOLD, size)
    return (FONT, size, "bold" if bold else "normal")


def hex_to_rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def lerp_color(a, b, t):
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# ----------------------------------------------------------------- file handling
def seed_sample_data():
    """Create ~4 weeks of realistic sample orders so charts look good."""
    random.seed(7)
    rows, oid = [], 1
    weights = [10, 6, 6, 5, 4, 7, 3, 2, 2, 3]
    today = date.today()
    for back in range(27, -1, -1):  # 27 days ago .. today
        d = today - timedelta(days=back)
        n = random.randint(5, 9) + (3 if d.weekday() >= 5 else 0)
        for _ in range(n):
            prod = random.choices(list(PRODUCTS), weights)[0]
            price = PRODUCTS[prod]
            qty = random.randint(10, 40) if price <= 8 else random.randint(1, 12)
            status = "Completed" if d < today else random.choice(["Pending", "Completed"])
            rows.append({"order_id": oid, "customer": random.choice(CUSTOMERS), "product": prod,
                         "quantity": qty, "price": f"{price:.2f}",
                         "order_date": d.strftime(DATE_FMT), "status": status})
            oid += 1
    # a few upcoming orders to demo production planning
    for ahead in (1, 2):
        d = today + timedelta(days=ahead)
        for _ in range(4):
            prod = random.choices(list(PRODUCTS), weights)[0]
            price = PRODUCTS[prod]
            qty = random.randint(15, 50) if price <= 8 else random.randint(2, 15)
            rows.append({"order_id": oid, "customer": random.choice(CUSTOMERS), "product": prod,
                         "quantity": qty, "price": f"{price:.2f}",
                         "order_date": d.strftime(DATE_FMT), "status": "Pending"})
            oid += 1
    save_orders(rows)
    # a baking log that roughly matches what was sold, so the Inventory tab has something real to show
    need, stock, sid = defaultdict(lambda: defaultdict(int)), [], 1
    for r in rows:
        need[r["order_date"]][r["product"]] += r["quantity"]
    for back in range(20, -1, -1):
        d = (today - timedelta(days=back)).strftime(DATE_FMT)
        for prod, qty in sorted(need[d].items()):
            extra = random.randint(1, 8) if random.random() < 0.5 else 0
            stock.append({"entry_id": sid, "date": d, "product": prod, "quantity": qty + extra, "note": ""})
            sid += 1
    save_stock(stock)


def parse_date(s):
    """Return the date as YYYY-MM-DD, or None if it can't be read."""
    for fmt in (DATE_FMT, "%m/%d/%Y", "%Y/%m/%d"):  # the others appear when Excel reformats dates
        try:
            return datetime.strptime(str(s).strip(), fmt).strftime(DATE_FMT)
        except ValueError:
            pass
    return None


def csv_safe(text):
    """Stop Excel running a name like '=1+1' as a formula: a leading quote makes it plain text."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def csv_unsafe(text):
    """Undo csv_safe() when reading the file back."""
    return text[1:] if text[:1] == "'" and text[1:2] in ("=", "+", "-", "@") else text


def load_orders():
    """Read orders.csv. Returns (rows, skipped) - unreadable rows are skipped, not fatal."""
    if not os.path.exists(CSV_FILE):
        seed_sample_data()
    rows, skipped, used_ids = [], 0, set()
    with open(CSV_FILE, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8-sig")  # utf-8-sig: Excel may add a BOM
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # Excel's plain "CSV" is Windows ANSI
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header_ok = set(FIELDS) <= set(reader.fieldnames or [])
    if raw.strip() and not header_ok:
        skipped += 1  # unusable header: nothing below it can be trusted
    else:
        for r in reader:
            try:
                d = parse_date(r["order_date"])
                qty = int(float(r["quantity"]))
                price = float(r["price"])
                prod = csv_unsafe(r["product"].strip())
                if not d or not prod or qty <= 0 or not math.isfinite(price) or price < 0:
                    raise ValueError
                oid = int(r["order_id"]) if (r.get("order_id") or "").strip() else 0
            except (ValueError, KeyError, TypeError, AttributeError):
                skipped += 1
                continue
            rows.append({"order_id": oid, "customer": csv_unsafe((r.get("customer") or "").strip()) or "Walk-in",
                         "product": prod, "quantity": qty, "price": price, "order_date": d,
                         "status": "Completed" if (r.get("status") or "").strip().lower() == "completed"
                         else "Pending"})
    next_id = max([r["order_id"] for r in rows], default=0) + 1
    for r in rows:  # give blank or duplicate IDs a fresh one so edit/delete hit the right row
        if r["order_id"] <= 0 or r["order_id"] in used_ids:
            r["order_id"] = next_id
            next_id += 1
        used_ids.add(r["order_id"])
    if skipped:  # keep the damaged original, then rewrite a clean file so later saves stay consistent
        try:
            shutil.copyfile(CSV_FILE, f"{CSV_FILE}.{datetime.now():%Y%m%d-%H%M%S}.bak")
            save_orders(rows)
        except OSError:
            pass
    return rows, skipped


def _file_row(row):
    return {**row, "customer": csv_safe(row["customer"]), "product": csv_safe(row["product"])}


def save_orders(rows):
    """Write the whole file safely: build a temporary copy, then swap it in, so a crash can't truncate it."""
    tmp = CSV_FILE + ".tmp"
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(_file_row(r) for r in rows)
        os.replace(tmp, CSV_FILE)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def append_order(row):
    size = os.path.getsize(CSV_FILE) if os.path.exists(CSV_FILE) else 0
    needs_newline = False
    if size:  # a file saved by Notepad/Excel may not end with a newline
        with open(CSV_FILE, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (b"\n", b"\r")
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\r\n")
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if size == 0:
            w.writeheader()
        w.writerow(_file_row(row))


def total(r):
    return r["quantity"] * r["price"]


def peso(x):
    return f"₱{x:,.2f}"


def plural(n, word):
    """'1 product', '2 products'."""
    return f"{n:,} {word}" + ("" if n == 1 else "s")


# ----------------------------------------------------------------- inventory (baking records)
STOCK_FIELDS = ["entry_id", "date", "product", "quantity", "note"]


def stock_file():
    """The baking records live next to the orders: orders.csv -> orders_stock.csv."""
    return (CSV_FILE[:-4] if CSV_FILE.lower().endswith(".csv") else CSV_FILE) + "_stock.csv"


def _stock_row(r):
    return {**r, "product": csv_safe(r["product"]), "note": csv_safe(r.get("note", ""))}


def load_stock():
    """Read the baking records. Unreadable lines are skipped (the original is kept as a .bak)."""
    path = stock_file()
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows, skipped = [], 0
    if raw.strip() and not set(STOCK_FIELDS) <= set(reader.fieldnames or []):
        skipped = 1
    else:
        for r in reader:
            try:
                d = parse_date(r["date"])
                qty = int(float(r["quantity"]))
                prod = csv_unsafe(r["product"].strip())
                if not d or not prod or qty == 0:
                    raise ValueError
                eid = int(r["entry_id"]) if (r.get("entry_id") or "").strip() else 0
            except (ValueError, KeyError, TypeError, AttributeError):
                skipped += 1
                continue
            rows.append({"entry_id": eid, "date": d, "product": prod, "quantity": qty,
                         "note": csv_unsafe((r.get("note") or "").strip())})
    next_id, used = max([r["entry_id"] for r in rows], default=0) + 1, set()
    for r in rows:  # blank or duplicate ids get a fresh one
        if r["entry_id"] <= 0 or r["entry_id"] in used:
            r["entry_id"], next_id = next_id, next_id + 1
        used.add(r["entry_id"])
    if skipped:
        try:
            shutil.copyfile(path, f"{path}.{datetime.now():%Y%m%d-%H%M%S}.bak")
            save_stock(rows)
        except OSError:
            pass
    return rows


def save_stock(rows):
    """Write all baking records safely (temporary copy, then swapped in)."""
    path = stock_file()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=STOCK_FIELDS)
            w.writeheader()
            w.writerows(_stock_row(r) for r in rows)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def append_stock(row):
    path = stock_file()
    size = os.path.getsize(path) if os.path.exists(path) else 0
    needs_newline = False
    if size:  # a file saved by Notepad/Excel may not end with a newline
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (b"\n", b"\r")
    with open(path, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\r\n")
        w = csv.DictWriter(f, fieldnames=STOCK_FIELDS)
        if size == 0:
            w.writeheader()
        w.writerow(_stock_row(row))


def stock_summary(orders, stock):
    """Per product: baked, sold, in stock (have), waiting (pending orders) and still-to-bake (short).

    Stock counts from the date of the first baking record: completed orders from that day on are
    'sold'. Returns (summary, date tracking started or None).
    """
    start = min((e["date"] for e in stock), default=None)
    baked, sold, waiting = defaultdict(int), defaultdict(int), defaultdict(int)
    for e in stock:
        baked[e["product"]] += e["quantity"]
    for o in orders:
        if o["status"] == "Pending":
            waiting[o["product"]] += o["quantity"]
        elif start is not None and o["order_date"] >= start:
            sold[o["product"]] += o["quantity"]
    out = {}
    for p in set(baked) | set(sold) | set(waiting):
        have = baked[p] - sold[p]
        out[p] = dict(baked=baked[p], sold=sold[p], have=have, waiting=waiting[p],
                      short=max(0, waiting[p] - max(have, 0)))
    return out, start


def open_file(path):
    """Open a file in the program the computer uses for it (Notepad for .txt on Windows)."""
    if hasattr(os, "startfile"):
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


# ----------------------------------------------------------------- images + custom widgets
_img_cache = {}


def round_img(w, h, r, fill, outline=None):
    """An anti-aliased rounded rectangle (drawn 4x bigger, then shrunk) as a Tk image."""
    key = (w, h, r, fill, outline)
    if key not in _img_cache:
        ss = 4
        big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        ImageDraw.Draw(big).rounded_rectangle(
            (0, 0, w * ss - 1, h * ss - 1), r * ss, fill=fill, outline=outline, width=ss if outline else 0)
        _img_cache[key] = ImageTk.PhotoImage(big.resize((w, h), Image.LANCZOS))
    return _img_cache[key]


LOGO_FILES = ("GMD v2", "GMD logo")  # tried in this order, any image extension: the newest design first


def find_logo():
    """The current logo ('GMD v2'); failing that, the first image here with 'logo' in its name."""
    exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
    # next to the program first (so the logo can be swapped), then the copy packed inside the .exe
    folders = [_app_dir()] + ([sys._MEIPASS] if getattr(sys, "_MEIPASS", None) else [])
    for here in folders:
        try:
            files = {n.lower(): n for n in os.listdir(here)}
        except OSError:
            continue
        for stem in LOGO_FILES:
            for ext in exts:
                if (stem + ext).lower() in files:
                    return os.path.join(here, files[(stem + ext).lower()])
        for lower, name in sorted(files.items()):
            if "logo" in lower and lower.endswith(exts):
                return os.path.join(here, name)
    return None


def load_logo():
    """Return (transparent RGBA logo, opaque square version) or (None, None).

    The supplied logo is green line art on a white background. Turning the ink darkness into
    transparency lets it sit cleanly on white, tinted or any other surface.
    """
    path = find_logo()
    if not path:
        return None, None
    try:
        rgb = Image.open(path).convert("RGB")
        gray = rgb.convert("L")
        ink = ImageOps.invert(gray)
        box = ink.point(lambda p: 255 if p > 60 else 0).getbbox()
        if box:
            rgb, gray, ink = rgb.crop(box), gray.crop(box), ink.crop(box)
        alpha = ink.point(lambda p: 0 if p < 16 else min(255, int((p - 16) * 1.45)))
        dark = gray.point(lambda p: 255 if p < 110 else 0)  # the solid parts of the drawing
        tint = tuple(int(v) for v in ImageStat.Stat(rgb, mask=dark).mean[:3]) if dark.getbbox() else hex_to_rgb(PRIMARY)
        out = Image.new("RGBA", rgb.size, tint + (0,))
        out.putalpha(alpha)
        side = max(out.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(out, ((side - out.width) // 2, (side - out.height) // 2))
        solid = Image.new("RGB", (side, side), "white")
        solid.paste(rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2))
        return square, solid
    except Exception:
        return None, None


class RoundButton(tk.Canvas):
    """A rounded button that eases between its normal and hover colours."""
    LOOKS = {
        "primary": dict(bg=PRIMARY, hover=PRIMARY_HOVER, fg="white", edge=None),
        "ghost": dict(bg="#eceee4", hover="#dde3d2", fg=INK, edge=None),
        "danger": dict(bg="#ffffff", hover="#fdeceb", fg=DANGER, edge="#e8b4b0"),
    }

    def __init__(self, app, parent, text, command, kind="primary", min_width=0, height=40):
        self.app, self.cmd, self.look, self.pos = app, command, self.LOOKS[kind], 0.0
        self.w = max(int(min_width * app.s), tkfont.Font(font=font(10, True)).measure(text) + int(44 * app.s))
        self.h = int(height * app.s)
        super().__init__(parent, width=self.w, height=self.h, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2")
        self.img = self.create_image(0, 0, anchor="nw")
        self.label = self.create_text(self.w // 2, self.h // 2, text=text, fill=self.look["fg"], font=font(10, True))
        self.paint()
        self.bind("<Enter>", lambda e: self.glide(1.0))
        self.bind("<Leave>", lambda e: self.glide(0.0))
        self.bind("<ButtonPress-1>", lambda e: self.move(self.label, 0, 1))
        self.bind("<ButtonRelease-1>", self.released)
        # keyboard: Tab reaches the button (a green ring shows where you are), Space or Enter presses it
        self.config(takefocus=1)
        self.ring = self.create_rectangle(1, 1, self.w - 2, self.h - 2, outline=ACCENT, width=2, state="hidden")
        self.bind("<FocusIn>", lambda e: self.itemconfigure(self.ring, state="normal"))
        self.bind("<FocusOut>", lambda e: self.itemconfigure(self.ring, state="hidden"))
        self.bind("<space>", lambda e: self.cmd())
        self.bind("<Return>", lambda e: self.cmd())

    def paint(self):
        t = round(self.pos * 8) / 8
        self.itemconfigure(self.img, image=round_img(
            self.w, self.h, int(9 * self.app.s), lerp_color(self.look["bg"], self.look["hover"], t), self.look["edge"]))

    def glide(self, target):
        start = self.pos

        def step(e):
            self.pos = start + (target - start) * e
            try:
                self.paint()
            except tk.TclError:  # the button was rebuilt/destroyed while it was animating
                self.app.cancel(("btn", id(self)))
        self.app.animate(("btn", id(self)), 140, step)

    def released(self, e):
        self.coords(self.label, self.w // 2, self.h // 2)
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h:
            self.cmd()

    def set_text(self, text):
        self.itemconfigure(self.label, text=text)


class Segmented(tk.Canvas):
    """A pill-shaped choice control; the highlight slides to the picked option."""

    def __init__(self, app, parent, options, value, command):
        self.app, self.options, self.cmd = app, list(options), command
        m = tkfont.Font(font=font(10, True))
        self.seg = max(m.measure(o) for o in options) + int(26 * app.s)
        self.pad = int(4 * app.s)
        self.h = int(40 * app.s)
        w = self.seg * len(options) + 2 * self.pad
        super().__init__(parent, width=w, height=self.h, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.create_image(0, 0, anchor="nw", image=round_img(w, self.h, int(10 * app.s), "#e9ebe0"))
        self.pill_img = round_img(self.seg, self.h - 2 * self.pad, int(8 * app.s), "white", "#d6dacb")
        self.pill = self.create_image(0, self.pad, anchor="nw", image=self.pill_img)
        self.texts = [self.create_text(self.pad + i * self.seg + self.seg // 2, self.h // 2, text=o,
                                       font=font(10, True), fill=MUTED) for i, o in enumerate(options)]
        self.pos = float(self.options.index(value))
        self.sel = self.options.index(value)
        self.draw()
        self.bind("<Button-1>", self.clicked)
        # keyboard: Tab reaches it (green ring), Left/Right change the choice
        self.config(takefocus=1)
        self.ring = self.create_rectangle(1, 1, w - 2, self.h - 2, outline=ACCENT, width=2, state="hidden")
        self.bind("<FocusIn>", lambda e: self.itemconfigure(self.ring, state="normal"))
        self.bind("<FocusOut>", lambda e: self.itemconfigure(self.ring, state="hidden"))
        self.bind("<Left>", lambda e: self.step_by(-1))
        self.bind("<Right>", lambda e: self.step_by(1))

    def step_by(self, delta):
        i = min(max(self.sel + delta, 0), len(self.options) - 1)
        if i != self.sel:
            self.glide_to(self.options[i])
            self.cmd(self.options[i])

    def draw(self):
        self.coords(self.pill, self.pad + self.pos * self.seg, self.pad)
        for i, t in enumerate(self.texts):
            self.itemconfigure(t, fill=lerp_color(MUTED, INK, max(0.0, 1 - abs(self.pos - i))))

    def glide_to(self, value, animate=True):
        target, start = float(self.options.index(value)), self.pos
        self.sel = self.options.index(value)
        if not animate:
            self.pos = target
            self.draw()
            return

        def step(e):
            self.pos = start + (target - start) * e
            self.draw()
        self.app.animate(("seg", id(self)), 260, step, ease=ease_in_out)

    def set(self, value):  # programmatic change: no callback
        if value in self.options:
            self.glide_to(value)

    def clicked(self, e):
        i = int((e.x - self.pad) // self.seg)
        if 0 <= i < len(self.options):
            self.glide_to(self.options[i])
            self.cmd(self.options[i])


class Pill(tk.Canvas):
    """A small rounded label (used for the pending-orders count in the header)."""

    def __init__(self, app, parent, fg=PRIMARY, fill=SOFT):
        self.app, self.fg, self.fill = app, fg, fill
        self.h = int(30 * app.s)
        super().__init__(parent, width=10, height=self.h, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.img = self.create_image(0, 0, anchor="nw")
        self.txt = self.create_text(0, self.h // 2, font=font(9, True), fill=fg)

    def set_text(self, text):
        w = tkfont.Font(font=font(9, True)).measure(text) + int(28 * self.app.s)
        self.config(width=w)
        self.itemconfigure(self.img, image=round_img(w, self.h, self.h // 2, self.fill))
        self.itemconfigure(self.txt, text=text)
        self.coords(self.txt, w // 2, self.h // 2)


class TabBar(tk.Canvas):
    """Top tabs with an underline that glides to the open tab."""

    def __init__(self, app, parent, on_pick):
        self.app, self.on_pick = app, on_pick
        self.h = int(46 * app.s)
        super().__init__(parent, height=self.h, bg=SURFACE, highlightthickness=0, bd=0)
        self.tabs, self.x_next, self.active, self.hover = [], int(28 * app.s), None, None
        self.line = self.create_rectangle(0, self.h - 3, 0, self.h, fill=ACCENT, width=0)
        self.line_x = (0.0, 0.0)
        self.measure = tkfont.Font(font=font(11, True))
        self.bind("<Button-1>", self.clicked)
        self.bind("<Motion>", self.moved)
        self.bind("<Leave>", lambda e: self.set_hover(None))
        self.config(cursor="arrow")

    def add(self, label, page):
        w = self.measure.measure(label) + int(40 * self.app.s)
        x0 = self.x_next
        text = self.create_text(x0 + w // 2, (self.h - 3) // 2, text=label, font=font(11, True), fill=MUTED)
        self.tabs.append(dict(page=page, x0=x0, x1=x0 + w, text=text, mix=0.0))
        self.x_next = x0 + w + int(2 * self.app.s)

    def index_of(self, page):
        return next(i for i, t in enumerate(self.tabs) if t["page"] is page)

    def at(self, x):
        return next((i for i, t in enumerate(self.tabs) if t["x0"] <= x <= t["x1"]), None)

    def clicked(self, e):
        i = self.at(e.x)
        if i is not None:
            self.on_pick(self.tabs[i]["page"])

    def moved(self, e):
        self.set_hover(self.at(e.x))

    def set_hover(self, i):
        if i == self.hover:
            return
        self.hover = i
        self.config(cursor="hand2" if i is not None else "arrow")
        self.recolor()

    def recolor(self):
        for i, t in enumerate(self.tabs):
            target = 1.0 if i == self.active else (0.55 if i == self.hover else 0.0)
            start = t["mix"]
            if abs(start - target) < 0.01:
                continue

            def step(e, t=t, start=start, target=target):
                t["mix"] = start + (target - start) * e
                self.itemconfigure(t["text"], fill=lerp_color(MUTED, INK, t["mix"]))
            self.app.animate(("tabcol", i), 160, step)

    def select(self, page, animate=True):
        self.active = self.index_of(page)
        t = self.tabs[self.active]
        target = (float(t["x0"] + int(10 * self.app.s)), float(t["x1"] - int(10 * self.app.s)))
        start = self.line_x
        self.recolor()
        if not animate or start == (0.0, 0.0):
            self.line_x = target
            self.coords(self.line, target[0], self.h - 3, target[1], self.h)
            return

        def step(e):
            self.line_x = (start[0] + (target[0] - start[0]) * e, start[1] + (target[1] - start[1]) * e)
            self.coords(self.line, self.line_x[0], self.h - 3, self.line_x[1], self.h)
        self.app.animate("tabline", 300, step, ease=ease_in_out)


NUM_RE = re.compile(r"^(\D*?)(\d[\d,]*(?:\.\d+)?)(\D*)$")


class Counter:
    """A number label that counts up to its value when a page is opened."""

    def __init__(self, app, var):
        self.app, self.var, self.target = app, var, ""

    def get(self):
        return self.target

    def set(self, text):
        self.target = text
        m = NUM_RE.match(text) if self.app.count_next else None
        if not m:
            self.app.cancel(("count", id(self)))
            self.var.set(text)
            return
        pre, num, suf = m.groups()
        decimals = len(num.split(".")[1]) if "." in num else 0
        end, comma = float(num.replace(",", "")), "," in num

        def fmt(v):
            return pre + (f"{v:,.{decimals}f}" if comma else f"{v:.{decimals}f}") + suf
        self.app.animate(("count", id(self)), 700, lambda e: self.var.set(fmt(end * e)),
                         lambda: self.var.set(text))


# ----------------------------------------------------------------- application
class _Nav:
    """Small stand-in for ttk.Notebook: lets the rest of the code select pages by widget."""

    def __init__(self, app):
        self.app = app

    def tabs(self):
        return [str(p) for p in self.app.page_order]

    def select(self, tab=None):
        if tab is None:
            return str(self.app.current_page)
        self.app.show_page(tab)


class App(tk.Tk):
    def __init__(self, intro=False, start_tab=None):
        super().__init__()
        global _SEMIBOLD
        self._closing = False
        _img_cache.clear()  # cached Tk images belong to one window; never reuse them in another
        _SEMIBOLD = "Segoe UI Semibold" if "Segoe UI Semibold" in tkfont.families(self) else None
        self.title("GMD Bakery - Order and Production Planner")
        if FORCE_DPI:  # testing hook: pretend to be a scaled (e.g. 150%) display
            self.tk.call("tk", "scaling", FORCE_DPI / 72)
        self.s = max(1.0, self.winfo_fpixels("1i") / 96)  # Windows display scaling (125%, 150%...)
        w = min(int(1140 * self.s), self.winfo_screenwidth() - 40)
        h = min(int(760 * self.s), self.winfo_screenheight() - 90)
        self.geometry(f"{w}x{h}")
        self.minsize(min(w, int(980 * self.s)), min(h, int(660 * self.s)))
        self.configure(bg=BG)
        self._anims, self.count_next, self.current_page = {}, False, None
        if intro:  # stay hidden while building, so there is never a blank grey window
            self.withdraw()
        try:
            self.orders, skipped = load_orders()
        except (OSError, csv.Error) as e:
            _close_splash()
            messagebox.showerror("Cannot open data file",
                                 f"The program could not create or read:\n{CSV_FILE}\n\n{e}\n\n"
                                 "Try moving the GMD-Bakery-Planner folder to your Desktop.")
            self.destroy()
            raise SystemExit(1)
        self.editing_id = None
        try:
            self.stock = load_stock()
        except (OSError, csv.Error):
            self.stock = []
        if skipped:
            self.later("warn", 300, lambda: messagebox.showwarning(
                "Some rows skipped",
                f"{skipped} row(s) in the CSV file could not be read and were ignored.\n\n"
                "A copy of the original file was saved next to it with the ending .bak"))
        else:  # keep last session's files, so one bad session can always be undone
            for path in (CSV_FILE, stock_file()):
                try:
                    if os.path.exists(path):
                        shutil.copyfile(path, path + ".last-session.bak")
                except OSError:
                    pass

        self._stamp = self.disk_stamp()
        self._stock_stamp = self.stock_stamp()
        self.logo_rgba, logo_solid = load_logo()
        self.logo_cache = {}
        if logo_solid is not None:
            try:
                self.icon_image = ImageTk.PhotoImage(logo_solid.resize((64, 64), Image.LANCZOS))
                self.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass

        _pump_splash()
        self.setup_style()
        self.build_shell()
        self.nb = _Nav(self)
        for build in (self.build_add, self.build_orders, self.build_sales, self.build_prod,
                      self.build_stock, self.build_report, self.build_charts):
            build()
            _pump_splash()
        self.bind_all("<Return>", self.on_enter_key)
        # keyboard shortcuts: Ctrl+1..7 open the tabs, Ctrl+N starts a new order, Ctrl+F searches the orders
        for i in range(len(self.page_order)):
            self.bind_all(f"<Control-Key-{i + 1}>", lambda e, i=i: self.show_page(self.page_order[i]))
        self.bind_all("<Control-n>", lambda e: (self.clear_form(), self.show_page(self.tab_add),
                                                self.ent_customer.focus_set()))
        self.bind_all("<Control-f>", lambda e: (self.show_page(self.tab_orders), self.ent_search.focus_set()))
        # coming back to the window (e.g. after editing the file in Excel) shows the latest orders
        self.bind("<FocusIn>", lambda e: e.widget is self and self.sync_from_disk() and self.refresh_all())
        self.show_page(self.tab_add, animate=False)
        if start_tab and 1 <= start_tab <= len(self.page_order):
            self.show_page(self.page_order[start_tab - 1], animate=False)
        _pump_splash()
        self.warm_up_charts()
        if intro:
            self.update_idletasks()
            self.deiconify()
            self.update()
            self.apply_icon()  # (after the window really exists, or Windows keeps the default feather)
            _close_splash()
            self.later("intro-wait", 30, self.intro_slide)
        else:
            _close_splash()

    def apply_icon(self):
        if getattr(self, "icon_image", None) is not None:
            try:
                self.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass

    def intro_slide(self):
        """On start-up the first page eases in, like every later page change (smooth, unlike a window fade)."""
        page, dx = self.current_page, int(36 * self.s)
        page.place_configure(x=dx)
        self.animate("intro", 380, lambda e: page.place_configure(x=int(dx * (1 - e))),
                     lambda: page.place_configure(x=0))

    def destroy(self):
        """Stop every pending animation timer first, so closing mid-animation never prints errors."""
        self._closing = True
        for key in list(getattr(self, "_anims", {})):
            self.cancel(key)
        super().destroy()

    @staticmethod
    def warm_up_charts():
        """Matplotlib spends ~0.8 s loading fonts the first time it draws; do that while the window is hidden."""
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            fig = Figure(figsize=(4, 3))
            ax = fig.add_subplot(111)
            ax.barh(["Pandesal", "Monay"], [3, 5])
            ax.set_title("Warm up", fontweight="bold")
            ax.set_xlabel("₱ Pieces (MM-DD)")
            ax.pie([1, 2], labels=["a", "b"], autopct="%1.1f%%")
            fig.tight_layout()
            FigureCanvasAgg(fig).draw()
        except Exception:
            pass

    # ------------------------------------------------------------ animation engine
    def animate(self, key, ms, step, done=None, ease=ease_out):
        """Run step(progress 0..1) about 60 times a second for `ms` milliseconds.

        Progress comes from the real clock, so a slow frame never makes the motion take longer.
        Starting an animation with the same key replaces the previous one.
        """
        self.cancel(key)
        t0 = time.perf_counter()

        def tick():
            if self._closing:
                return
            began = time.perf_counter()
            t = min(1.0, (began - t0) * 1000.0 / ms)
            step(ease(t))
            if t >= 1.0:
                self._anims.pop(key, None)
                if done:
                    done()
                return
            spent = (time.perf_counter() - began) * 1000.0
            self._anims[key] = self.after(max(1, int(16 - spent)), tick)
        tick()

    def later(self, key, ms, fn):
        self.cancel(key)
        self._anims[key] = self.after(ms, fn)

    def cancel(self, key):
        handle = self._anims.pop(key, None)
        if handle is not None:
            self.after_cancel(handle)

    def logo(self, size, fade=1.0):
        """The logo at a given pixel size (optionally faded) as a Tk image, or None."""
        if self.logo_rgba is None:
            return None
        key = (size, fade)
        if key not in self.logo_cache:
            img = self.logo_rgba.resize((size, size), Image.LANCZOS)
            boost = 2.2 if size < 160 else 1.6  # shrinking thins the fine lines, so strengthen them
            img.putalpha(img.getchannel("A").point(lambda p: min(255, int(p * boost))))
            if fade < 1.0:
                img.putalpha(img.getchannel("A").point(lambda p: int(p * fade)))
            self.logo_cache[key] = ImageTk.PhotoImage(img)
        return self.logo_cache[key]

    # ------------------------------------------------------------ look & feel
    def setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        px = lambda n: int(n * self.s)
        s.configure(".", font=font(10), background=BG, foreground=INK)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=SURFACE, foreground=INK)
        for name in ("TEntry", "TSpinbox", "TCombobox"):
            s.configure(name, fieldbackground="white", background="white", foreground=INK,
                        bordercolor="#d4d8c9", lightcolor="#d4d8c9", darkcolor="#d4d8c9",
                        insertcolor=INK, padding=px(10), arrowcolor=MUTED)
            s.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        s.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)],
              selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)])
        self.option_add("*TCombobox*Listbox.background", "white")
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)
        self.option_add("*TCombobox*Listbox.selectForeground", INK)
        self.option_add("*TCombobox*Listbox.font", font(10))

        s.configure("Treeview", background="white", fieldbackground="white", foreground=INK,
                    rowheight=px(30), borderwidth=0, font=font(10))
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", INK)])
        s.configure("Treeview.Heading", background="#f1f1e8", foreground=LABEL, font=font(10, True),
                    relief="flat", borderwidth=0, padding=(px(5), px(8)))
        s.map("Treeview.Heading", background=[("active", "#e8e8dd")])
        s.configure("Vertical.TScrollbar", background="#cfd3c4", troughcolor=BG, bordercolor=BG,
                    arrowcolor="#cfd3c4", lightcolor="#cfd3c4", darkcolor="#cfd3c4",
                    gripcount=0, width=px(10))
        s.map("Vertical.TScrollbar", background=[("active", "#b3b9a5")])

    # small building blocks ---------------------------------------------------
    def card(self, parent):
        return tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightcolor=BORDER,
                        highlightthickness=1)

    def btn(self, parent, text, command, kind="primary", min_width=0, height=40):
        return RoundButton(self, parent, text, command, kind, min_width, height)

    def stat_card(self, parent, title, col, cols):
        """A plain white box: a label, one number that counts up, and a short note underneath."""
        c = self.card(parent)
        c.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 7, 0 if col == cols - 1 else 7))
        parent.columnconfigure(col, weight=1, uniform="stat")
        tk.Label(c, text=title, bg=SURFACE, fg=LABEL, font=font(10)).pack(anchor="w", padx=18, pady=(10, 0))
        var, note = tk.StringVar(value="—"), tk.StringVar()
        tk.Label(c, textvariable=var, bg=SURFACE, fg=PRIMARY, font=font(19, True)).pack(anchor="w", padx=18)
        tk.Label(c, textvariable=note, bg=SURFACE, fg=MUTED, font=font(9)).pack(anchor="w", padx=18, pady=(0, 10))
        return Counter(self, var), note

    def table(self, parent, cols, heads, widths, left=(), scroll=True):
        """A card holding a clean Treeview. Returns (card, tree)."""
        c = self.card(parent)
        tree = ttk.Treeview(c, columns=cols, show="headings", selectmode="browse", height=4)
        for col, head, wd in zip(cols, heads, widths):
            anchor = "w" if col in left else ("e" if col in NUMERIC else "center")
            tree.heading(col, text=head, anchor=anchor)
            tree.column(col, width=int(wd * self.s), minwidth=int(40 * self.s), anchor=anchor)
        if scroll:
            sb = ttk.Scrollbar(c, orient="vertical", command=tree.yview)

            def on_scroll(lo, hi):  # show the scrollbar only when there is something to scroll
                sb.set(lo, hi)
                if float(lo) <= 0 and float(hi) >= 1:
                    sb.pack_forget()
                elif not sb.winfo_manager():
                    sb.pack(side="right", fill="y", before=tree)

            tree.configure(yscrollcommand=on_scroll)
            tree.pack(side="left", fill="both", expand=True)
        else:
            tree.pack(fill="both", expand=True)
        tree.tag_configure("even", background="white")
        tree.tag_configure("odd", background="#faf9f4")
        tree.tag_configure("pending", background=PENDING_BG)
        return c, tree

    def labeled(self, parent, text, row, col, span=1):
        """A caption above a form field. Returns the frame to put the field in."""
        cell = tk.Frame(parent, bg=SURFACE)
        cell.grid(row=row, column=col, columnspan=span, sticky="ew", padx=6, pady=(0, 14))
        tk.Label(cell, text=text, bg=SURFACE, fg=LABEL, font=font(10)).pack(anchor="w", pady=(0, 5))
        return cell

    def new_page(self, description):
        """A page = one line saying what it is for, then the content area."""
        page = tk.Frame(self.container, bg=BG)
        page.place(x=0, y=0, relwidth=1, relheight=1)
        page.note = tk.Label(page, text=description, bg=BG, fg=MUTED, font=font(10), anchor="w")
        page.note.pack(fill="x", padx=34, pady=(14, 8))
        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True, padx=34, pady=(0, 14))
        self.page_order.append(page)
        return page, body

    # ------------------------------------------------------------ shell + navigation
    def build_shell(self):
        self.page_order = []
        tk.Frame(self, bg=PRIMARY, height=4).pack(fill="x")
        head = tk.Frame(self, bg=SURFACE)
        head.pack(fill="x")
        pad = int(34 * self.s)
        mark = self.logo(int(64 * self.s))
        if mark is not None:
            tk.Label(head, image=mark, bg=SURFACE).pack(side="left", padx=(pad, 14), pady=int(5 * self.s))
        names = tk.Frame(head, bg=SURFACE)
        names.pack(side="left", pady=int(5 * self.s), padx=(0 if mark is not None else pad, 0))
        tk.Label(names, text="GMD Bakery", bg=SURFACE, fg=PRIMARY, font=(SERIF, 19, "bold")).pack(anchor="w")
        tk.Label(names, text="Order and Production Planner", bg=SURFACE, fg=MUTED, font=font(10)).pack(anchor="w")
        right = tk.Frame(head, bg=SURFACE)
        right.pack(side="right", padx=pad)
        self.lbl_date = tk.Label(right, text="", bg=SURFACE, fg=LABEL, font=font(10))
        self.lbl_date.pack(anchor="e", pady=(0, 6))
        self.pending_pill = Pill(self, right)
        self.pending_pill.pack(anchor="e")
        self.tabbar = TabBar(self, self, self.show_page)
        self.tabbar.pack(fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(self, bg=BG)
        foot.pack(side="bottom", fill="x")
        tk.Frame(foot, bg=BORDER, height=1).pack(fill="x")
        tk.Label(foot, text=f"Orders are saved in  {CSV_FILE}", bg=BG, fg=MUTED, font=font(8),
                 anchor="w").pack(fill="x", padx=34, pady=6)
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

    def add_nav(self, label, page):
        self.tabbar.add(label, page)

    def show_page(self, page, animate=True):
        page = next(p for p in self.page_order if p is page or str(p) == str(page))
        self.sync_from_disk()  # pick up edits made to the file elsewhere (the refresh below shows them)
        prev, self.current_page = self.current_page, page
        moving = animate and prev is not None and prev is not page
        self.tabbar.select(page, animate=moving)
        if page is self.tab_prod and not self.p_touched:  # open on a date that actually has orders
            self.p_date.set(self.default_prod_date())
        self.count_next = animate  # numbers count up and charts draw in when a page is opened
        self.refresh_all()
        self.count_next = False
        page.tkraise()
        if moving:  # the new page eases in from a short distance to the right
            dx = int(30 * self.s)
            page.place_configure(x=dx)
            self.animate("slide", 260, lambda e: page.place_configure(x=int(dx * (1 - e))),
                         lambda: page.place_configure(x=0))

    # ------------------------------------------------------------ Add / edit order
    def build_add(self):
        self.tab_add, body = self.new_page(ADD_NOTE)
        self.add_nav("Add Order", self.tab_add)
        body.columnconfigure(0, weight=7, uniform="add")
        body.columnconfigure(1, weight=4, uniform="add")
        body.rowconfigure(0, weight=1)

        form_card = self.card(body)
        form_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        form = tk.Frame(form_card, bg=SURFACE)
        form.pack(fill="x", padx=22, pady=(20, 16))
        form.columnconfigure((0, 1, 2, 3), weight=1, uniform="f")

        self.v_customer = tk.StringVar()
        self.v_product = tk.StringVar()
        self.v_qty = tk.StringVar(value="1")
        self.v_price = tk.StringVar()
        self.v_date = tk.StringVar(value=date.today().strftime(DATE_FMT))
        self.v_status = tk.StringVar(value="Pending")

        self.ent_customer = ttk.Entry(self.labeled(form, "Customer name", 0, 0, 2), textvariable=self.v_customer)
        self.ent_customer.pack(fill="x")
        self.cb_product = ttk.Combobox(
            self.labeled(form, "Product  (pick or type a new one)", 0, 2, 2),
            textvariable=self.v_product, values=list(PRODUCTS))
        self.cb_product.pack(fill="x")
        self.cb_product.bind("<<ComboboxSelected>>", lambda e: self.on_product(mode="force"))  # explicit pick
        self.cb_product.bind("<FocusOut>", lambda e: self.on_product())
        ttk.Spinbox(self.labeled(form, "Quantity", 1, 0), from_=1, to=1000, width=6,
                    textvariable=self.v_qty).pack(fill="x")
        ttk.Entry(self.labeled(form, "Unit price (₱)", 1, 1), textvariable=self.v_price, width=8).pack(fill="x")
        ttk.Entry(self.labeled(form, "Date needed", 1, 2), textvariable=self.v_date, width=8).pack(fill="x")
        ttk.Combobox(self.labeled(form, "Status", 1, 3), textvariable=self.v_status, state="readonly", width=8,
                     values=["Pending", "Completed"]).pack(fill="x")

        strip = tk.Frame(form, bg=SOFT)
        strip.grid(row=2, column=0, columnspan=4, sticky="ew", padx=6, pady=(2, 14))
        tk.Label(strip, text="Order total", bg=SOFT, fg=LABEL, font=font(11)).pack(side="left", padx=18, pady=12)
        self.lbl_total = tk.Label(strip, text="₱0.00", bg=SOFT, fg=PRIMARY, font=font(21, True))
        self.lbl_total.pack(side="right", padx=18)
        for v in (self.v_qty, self.v_price):
            v.trace_add("write", lambda *a: self.update_total())

        btns = tk.Frame(form, bg=SURFACE)
        btns.grid(row=3, column=0, columnspan=4, sticky="w", padx=6)
        self.btn_save = self.btn(btns, "Save order", self.save_order, "primary", min_width=150)
        self.btn_save.pack(side="left")
        self.btn(btns, "Clear", self.clear_form, "ghost", min_width=90).pack(side="left", padx=10)

        recent = self.card(body)
        recent.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        tk.Label(recent, text="Latest orders", bg=SURFACE, fg=INK, font=font(12, True)).pack(
            anchor="w", padx=20, pady=(16, 10))
        mark = self.logo(int(130 * self.s), fade=0.12)  # a faint brand mark in the empty space
        self.recent_mark = None
        if mark is not None:
            self.recent_mark = tk.Label(recent, image=mark, bg=SURFACE)
            self.recent_mark.pack(side="bottom", pady=12)
            # the mark is decoration: drop it when the card is too short, so the list gets the room
            recent.bind("<Configure>", lambda e: self.recent_mark.pack_forget() if e.height < int(480 * self.s)
                        else (None if self.recent_mark.winfo_manager() else
                              self.recent_mark.pack(side="bottom", pady=12, before=self.recent_tree.master)))
        _, self.recent_tree = self.table(recent, ("customer", "product", "quantity", "total"),
                                         ("Customer", "Product", "Qty", "Total"), (95, 95, 36, 64),
                                         left=("customer", "product"), scroll=False)
        self.recent_tree.master.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.recent_tree.master.config(highlightthickness=0)
        self.recent_tree.config(height=3)

    def on_enter_key(self, _event):
        """Enter saves the order, but only while the Add Order tab is showing."""
        try:
            kind = self.focus_get().winfo_class()
        except (KeyError, AttributeError):  # focus inside a dropdown popup, or nowhere
            return
        if kind in ("TEntry", "TSpinbox"):
            if self.current_page is self.tab_add:
                self.save_order()
            elif self.current_page is self.tab_stock:
                self.record_stock()

    def menu_prices(self):
        """Built-in PRODUCTS plus any product typed in earlier orders (with its most recent price)."""
        menu = dict(PRODUCTS)
        for o in sorted(self.orders, key=lambda o: (o["order_date"], o["order_id"])):
            if o["product"] not in PRODUCTS:
                menu[o["product"]] = o["price"]
        return menu

    def on_product(self, mode="empty"):
        """Match typed text to a menu item (any case) and fill its price.

        mode "force": always set the menu price (user just picked the item from the list).
        mode "empty": only if the price box is blank, so a typed price is never overwritten.
        """
        menu = self.menu_prices()
        typed = self.v_product.get().strip()
        match = next((p for p in menu if p.lower() == typed.lower()), None)
        if match:
            if match != self.v_product.get():
                self.v_product.set(match)
            if mode == "force" or self.v_price.get().strip() == "":
                self.v_price.set(f"{menu[match]:.2f}")

    def update_total(self):
        try:
            t = int(self.v_qty.get()) * float(self.v_price.get())
            self.lbl_total.config(text=peso(t))
        except ValueError:
            self.lbl_total.config(text="₱0.00")

    def set_add_heading(self, editing_id=None):
        """Top note + Save button text: plain instructions normally, a clear banner while editing."""
        if editing_id is None:
            self.tab_add.note.config(text=ADD_NOTE, fg=MUTED, font=font(10))
            self.btn_save.set_text("Save order")
        else:
            self.tab_add.note.config(text=f"Editing order #{editing_id}. Change what you need, then save.",
                                     fg=PRIMARY, font=font(10, True))
            self.btn_save.set_text("Save changes")

    def clear_form(self):
        self.editing_id = None
        self.set_add_heading()
        self.v_customer.set("")
        self.v_product.set("")
        self.v_qty.set("1")
        self.v_price.set("")
        self.v_date.set(date.today().strftime(DATE_FMT))
        self.v_status.set("Pending")

    def save_order(self):
        self.on_product()  # tidy the name; fills the menu price only if the price box is blank
        cust = self.v_customer.get().strip()
        prod = self.v_product.get().strip()
        if not cust:
            return messagebox.showerror("Missing info", "Please enter the customer name.")
        if not prod:
            return messagebox.showerror("Missing info", "Please choose or type a product.")
        if len(cust) > 80 or len(prod) > 60:
            return messagebox.showerror("Too long", "Customer names can be up to 80 characters "
                                                    "and product names up to 60.")
        try:
            qty = int(self.v_qty.get())
            price = float(self.v_price.get())
            if qty <= 0 or price < 0 or not math.isfinite(price):
                raise ValueError
        except ValueError:
            return messagebox.showerror("Invalid number",
                                        "Quantity must be a positive whole number and price a valid number.")
        if (qty > 10000 or price > 100000) and not messagebox.askyesno(
                "Check the amount", f"{qty:,} pieces at {peso(price)} each is unusually large. Is that correct?"):
            return
        d = parse_date(self.v_date.get())
        if not d:
            return messagebox.showerror("Invalid date", "Use the format YYYY-MM-DD (e.g. 2026-10-12).")
        gap = abs((datetime.strptime(d, DATE_FMT).date() - date.today()).days)
        if gap > 90 and not messagebox.askyesno(
                "Check the date", f"{d} is {gap} days from today. Is that correct?"):
            return

        if self.sync_from_disk():  # someone changed the file outside the program: start from what is really there
            self.refresh_all()
        if self.editing_id is not None and not any(o["order_id"] == self.editing_id for o in self.orders):
            self.clear_form()
            return messagebox.showerror("Order changed", "The order you were editing is no longer in the "
                                        "orders file (it was changed outside the program). Nothing was saved.")

        if self.editing_id is None:
            if any(o["customer"].lower() == cust.lower() and o["product"] == prod and o["quantity"] == qty
                   and o["price"] == price and o["order_date"] == d for o in self.orders) \
                    and not messagebox.askyesno(
                        "Possible duplicate",
                        "An identical order (same customer, product, quantity, price and date) "
                        "is already recorded.\n\nSave it again anyway?"):
                return
            new_id = max([o["order_id"] for o in self.orders], default=0) + 1
            row = {"order_id": new_id, "customer": cust, "product": prod, "quantity": qty,
                   "price": price, "order_date": d, "status": self.v_status.get()}
            try:
                if os.path.exists(CSV_FILE):
                    append_order({**row, "price": f"{price:.2f}"})
                else:  # the file was deleted while the program was open: write everything back, not just this row
                    save_orders([{**o, "price": f"{o['price']:.2f}"} for o in self.orders + [row]])
            except OSError as e:
                return self.file_error(e)
            self._stamp = self.disk_stamp()
            self.orders.append(row)
            messagebox.showinfo("Saved", f"Order #{new_id} saved.\nTotal: {peso(qty * price)}")
        else:
            old = [dict(o) for o in self.orders]
            for o in self.orders:
                if o["order_id"] == self.editing_id:
                    o.update(customer=cust, product=prod, quantity=qty, price=price,
                             order_date=d, status=self.v_status.get())
            if not self.persist(old):
                return
            messagebox.showinfo("Updated", f"Order #{self.editing_id} updated.")
        self.clear_form()
        self.refresh_all()

    def file_error(self, e, path=None):
        messagebox.showerror("Cannot save",
                             f"Could not write to:\n{path or CSV_FILE}\n\n{e}\n\n"
                             "If the file is open in Excel, close it and try again.")

    def persist(self, rollback=None):
        """Write all orders to CSV. On failure show an error, restore `rollback`, return False."""
        try:
            save_orders([{**o, "price": f"{o['price']:.2f}"} for o in self.orders])
            self._stamp = self.disk_stamp()
            return True
        except OSError as e:
            if rollback is not None:
                self.orders = rollback
            self.file_error(e)
            self.refresh_all()
            return False

    # ------------------------------------------------------------ Orders view/search
    def build_orders(self):
        self.tab_orders, body = self.new_page("Search, filter and manage every order.")
        self.add_nav("Orders", self.tab_orders)
        self.s_text = tk.StringVar()
        self.s_product = tk.StringVar(value="All")
        self.s_status = tk.StringVar(value="All")
        self.s_from = tk.StringVar()
        self.s_to = tk.StringVar()

        bar = self.card(body)
        bar.pack(fill="x", pady=(0, 14))
        row = tk.Frame(bar, bg=SURFACE)
        row.pack(fill="x", padx=16, pady=(12, 14))
        row.columnconfigure(0, weight=1)  # the search box takes up (or gives back) the spare width

        def field(text, col, widget_factory, grow=False):
            cell = tk.Frame(row, bg=SURFACE)
            cell.grid(row=0, column=col, sticky="sew" if grow else "s", padx=(0 if col == 0 else 10, 0))
            tk.Label(cell, text=text, bg=SURFACE, fg=LABEL, font=font(10)).pack(anchor="w", pady=(0, 4))
            w = widget_factory(cell)
            w.pack(fill="x" if grow else "none")
            return w

        self.ent_search = field("Search", 0, lambda p: ttk.Entry(p, textvariable=self.s_text, width=8), grow=True)
        self.cb_filter = field("Product", 1, lambda p: ttk.Combobox(
            p, textvariable=self.s_product, width=15, state="readonly", values=["All"] + list(PRODUCTS)))
        self.seg_status = field("Status", 2, lambda p: Segmented(
            self, p, ["All", "Pending", "Completed"], "All", lambda v: self.s_status.set(v)))
        for text, col, var in (("From date", 3, self.s_from), ("To date", 4, self.s_to)):
            ent = field(text, col, lambda p, v=var: ttk.Entry(p, textvariable=v, width=10))
            ent.bind("<Return>", lambda e: self.refresh_orders())
            ent.bind("<FocusOut>", lambda e: self.refresh_orders())  # leaving a half-typed date flags it
        # everything filters live: as you type, pick, or finish typing a date
        for var in (self.s_text, self.s_product, self.s_status):
            var.trace_add("write", lambda *a: self.refresh_orders())
        for var in (self.s_from, self.s_to):
            var.trace_add("write", lambda *a: self.live_dates())
        self.s_status.trace_add("write", lambda *a: self.seg_status.set(self.s_status.get()))
        reset = tk.Frame(row, bg=SURFACE)
        reset.grid(row=0, column=5, sticky="s", padx=(12, 0))
        self.btn(reset, "Reset", self.reset_filter, "ghost", min_width=72).pack()

        cols = ("order_id", "customer", "product", "quantity", "price", "total", "order_date", "status")
        heads = ("ID", "Customer", "Product", "Qty", "Unit price", "Total", "Date", "Status")
        widths = (55, 190, 200, 60, 100, 110, 110, 110)
        table_card, self.tree = self.table(body, cols, heads, widths, left=("customer", "product"))
        bot = tk.Frame(body, bg=BG)
        bot.pack(side="bottom", fill="x", pady=(14, 0))
        table_card.pack(fill="both", expand=True)
        self.lbl_count = tk.Label(bot, text="", bg=BG, fg=MUTED, font=font(10))
        self.lbl_count.pack(side="left")
        self.btn(bot, "Delete", self.delete_order, "danger", min_width=90).pack(side="right")
        self.btn(bot, "Edit", self.edit_order, "ghost", min_width=80).pack(side="right", padx=8)
        self.btn(bot, "Mark completed", self.complete_order, "primary", min_width=150).pack(side="right")

    def live_dates(self):
        """Apply the date filter once a date is complete (or cleared), not while it is half typed."""
        parts = (self.s_from.get().strip(), self.s_to.get().strip())
        if all(p == "" or (len(p) >= 10 and parse_date(p)) for p in parts):
            self.refresh_orders()

    def reset_filter(self):
        self.s_text.set("")
        self.s_product.set("All")
        self.s_status.set("All")
        self.s_from.set("")
        self.s_to.set("")
        self.refresh_orders()

    def filtered(self):
        txt = self.s_text.get().strip().lower()
        prod, status = self.s_product.get(), self.s_status.get()
        d1, d2 = self.s_from.get().strip(), self.s_to.get().strip()
        d1 = (parse_date(d1) or "") if d1 else ""  # an unreadable date is ignored, not compared as text
        d2 = (parse_date(d2) or "") if d2 else ""
        out = []
        for o in self.orders:
            if txt and txt not in o["customer"].lower() and txt not in str(o["order_id"]) \
                    and txt not in o["product"].lower():
                continue
            if prod != "All" and o["product"] != prod:
                continue
            if status != "All" and o["status"] != status:
                continue
            if d1 and o["order_date"] < d1:
                continue
            if d2 and o["order_date"] > d2:
                continue
            out.append(o)
        return sorted(out, key=lambda o: (o["order_date"], o["order_id"]), reverse=True)

    def refresh_orders(self):
        names = sorted(set(PRODUCTS) | {o["product"] for o in self.orders})
        self.cb_filter.config(values=["All"] + names)
        bad = [label for v, label in ((self.s_from.get(), "From"), (self.s_to.get(), "To"))
               if v.strip() and not parse_date(v)]
        self.tree.delete(*self.tree.get_children())
        rows = self.filtered()
        for i, o in enumerate(rows[:MAX_ROWS]):  # newest first; a huge history stays quick to draw
            tag = "pending" if o["status"] == "Pending" else ("odd" if i % 2 else "even")
            self.tree.insert("", "end", iid=str(o["order_id"]), tags=(tag,),
                             values=(o["order_id"], o["customer"], o["product"], o["quantity"],
                                     f"{o['price']:.2f}", f"{total(o):,.2f}", o["order_date"], o["status"]))
        if bad:
            self.lbl_count.config(text=f"'{bad[0]}' date not understood - use YYYY-MM-DD", fg=DANGER)
        elif len(rows) > MAX_ROWS:
            self.lbl_count.config(
                text=f"Showing the newest {MAX_ROWS:,} of {len(rows):,} orders   ·   "
                     f"{peso(sum(total(o) for o in rows))} in total   ·   use search or filters to narrow", fg=MUTED)
        else:
            self.lbl_count.config(
                text=f"{len(rows)} order(s)   ·   {peso(sum(total(o) for o in rows))}   ·   "
                     "yellow rows are still pending", fg=MUTED)

    def selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select an order", "Please select an order from the list first.")
            return None
        return int(sel[0])

    def action_id(self):
        """The selected order's id, after picking up any change made to the file outside the program."""
        oid = self.selected_id()
        if oid is None:
            return None
        if self.sync_from_disk():
            self.refresh_all()
            if not any(o["order_id"] == oid for o in self.orders):
                messagebox.showinfo("Order changed", "The orders file was changed outside the program and "
                                    "this order is no longer in it. The list has been refreshed.")
                return None
        return oid

    # --- keeping in step with the file on disk (e.g. someone saved it from Excel) -------------
    @staticmethod
    def disk_stamp():
        try:
            st = os.stat(CSV_FILE)
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    @staticmethod
    def stock_stamp():
        try:
            st = os.stat(stock_file())
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def sync_from_disk(self):
        """Reload orders / baking records if their files changed behind our back. True when something did."""
        changed = False
        stamp = self.disk_stamp()
        if stamp is not None and stamp != self._stamp:  # (a missing file is recreated by the next save)
            try:
                orders, skipped = load_orders()
            except (OSError, csv.Error):
                orders = None
            if orders is not None:
                self.orders, self._stamp, changed = orders, self.disk_stamp(), True
                if skipped:
                    messagebox.showwarning("Some rows skipped", f"{skipped} row(s) in the CSV file could not be "
                                           "read and were ignored. A copy of the original was saved with the ending .bak")
        stamp = self.stock_stamp()
        if stamp is not None and stamp != self._stock_stamp:
            try:
                self.stock, self._stock_stamp, changed = load_stock(), self.stock_stamp(), True
            except (OSError, csv.Error):
                pass
        return changed

    def complete_order(self):
        oid = self.action_id()
        if oid is None:
            return
        old = [dict(o) for o in self.orders]
        for o in self.orders:
            if o["order_id"] == oid:
                o["status"] = "Completed"
        if self.persist(old):
            self.refresh_all()

    def delete_order(self):
        oid = self.action_id()
        if oid is None:
            return
        if messagebox.askyesno("Delete order", f"Delete order #{oid}? This cannot be undone."):
            old = self.orders
            self.orders = [o for o in self.orders if o["order_id"] != oid]
            if not self.persist(old):
                return
            if self.editing_id == oid:
                self.clear_form()
            self.refresh_all()

    def edit_order(self):
        oid = self.action_id()
        if oid is None:
            return
        o = next(x for x in self.orders if x["order_id"] == oid)
        self.editing_id = oid
        self.set_add_heading(oid)
        self.v_customer.set(o["customer"])
        self.v_product.set(o["product"])
        self.v_qty.set(str(o["quantity"]))
        self.v_price.set(f"{o['price']:.2f}")
        self.v_date.set(o["order_date"])
        self.v_status.set(o["status"])
        self.show_page(self.tab_add)

    # ------------------------------------------------------------ Daily sales
    def build_sales(self):
        self.tab_sales, body = self.new_page("How much the bakery earned on each day.")
        self.add_nav("Daily Sales", self.tab_sales)
        cards = tk.Frame(body, bg=BG)
        cards.pack(fill="x", pady=(0, 16))
        self.sales_cards = [self.stat_card(cards, t, i, 3) for i, t in
                            enumerate(("Total sales", "Best day", "Average per day"))]
        table_card, self.sales_tree = self.table(
            body, ("date", "orders", "pieces", "sales"),
            ("Date", "Orders", "Pieces sold", "Total sales"), (200, 140, 160, 200), left=("date",))
        table_card.pack(fill="both", expand=True)

    def daily_totals(self):
        days = defaultdict(lambda: [0, 0, 0.0])
        for o in self.orders:
            d = days[o["order_date"]]
            d[0] += 1
            d[1] += o["quantity"]
            d[2] += total(o)
        return dict(sorted(days.items()))

    def most_ordered(self):
        """The most FREQUENTLY ordered product (the requirements' wording): the one that appears in the most orders.
        A tie goes to the product with more pieces. Returns (product, number of orders, pieces) or None."""
        count, pieces = defaultdict(int), defaultdict(int)
        for o in self.orders:
            count[o["product"]] += 1
            pieces[o["product"]] += o["quantity"]
        if not count:
            return None
        top = max(count, key=lambda p: (count[p], pieces[p]))
        return top, count[top], pieces[top]

    def refresh_sales(self):
        self.sales_tree.delete(*self.sales_tree.get_children())
        days = self.daily_totals()
        for i, (d, (n, pcs, amt)) in enumerate(reversed(list(days.items()))):
            self.sales_tree.insert("", "end", tags=("odd" if i % 2 else "even",),
                                   values=(d, n, f"{pcs:,}", peso(amt)))
        grand = sum(v[2] for v in days.values())
        (v1, n1), (v2, n2), (v3, n3) = self.sales_cards
        v1.set(peso(grand))
        pending_value = sum(total(o) for o in self.orders if o["status"] == "Pending")
        n1.set(f"{sum(v[0] for v in days.values()):,} orders · incl. {peso(pending_value)} pending")
        if days:
            best = max(days.items(), key=lambda kv: kv[1][2])
            v2.set(peso(best[1][2])); n2.set(best[0])
            v3.set(peso(grand / len(days))); n3.set(f"across {plural(len(days), 'day')}")
        else:
            v2.set("—"); n2.set("")
            v3.set("—"); n3.set("")

    # ------------------------------------------------------------ Production plan
    def build_prod(self):
        self.tab_prod, body = self.new_page(
            "The baker's to-do list: pick a date and the list updates by itself, showing how many pieces of each product to bake.")
        self.add_nav("Production Plan", self.tab_prod)
        self.p_touched = False  # turns True once the user picks a date themselves
        self.chip_dates = []
        ctl = self.card(body)
        ctl.pack(fill="x", pady=(0, 12))
        row = tk.Frame(ctl, bg=SURFACE)
        row.pack(fill="x", padx=18, pady=(12, 8))
        cell = tk.Frame(row, bg=SURFACE)
        cell.pack(side="left", padx=(0, 14), anchor="s")
        tk.Label(cell, text="Date to bake for", bg=SURFACE, fg=LABEL, font=font(10)).pack(anchor="w", pady=(0, 4))
        self.p_date = tk.StringVar(value=self.default_prod_date())
        e = ttk.Entry(cell, textvariable=self.p_date, width=13)
        e.pack()
        e.bind("<Return>", lambda _: self.refresh_prod())
        e.bind("<Key>", lambda _: setattr(self, "p_touched", True))
        self.p_date.trace_add("write", lambda *a: self.live_prod())  # the plan follows the date as you type
        quick = tk.Frame(row, bg=SURFACE)
        quick.pack(side="left", anchor="s", padx=(0, 18))
        for label, delta in (("Today", 0), ("Tomorrow", 1)):
            self.btn(quick, label, lambda d=delta: self.set_prod_date(d), "ghost", min_width=90).pack(
                side="left", padx=(0, 8))
        self.p_pending = tk.BooleanVar(value=True)
        self.seg_pending = Segmented(
            self, row, ["Pending only", "All orders"], "Pending only",
            lambda v: self.p_pending.set(v == "Pending only"))
        self.seg_pending.pack(side="left", anchor="s")
        # whatever changes the value (a click, or code) moves the switch and refreshes the plan
        self.p_pending.trace_add("write", lambda *a: (
            self.seg_pending.set("Pending only" if self.p_pending.get() else "All orders"), self.refresh_prod()))
        self.btn(row, "Print bake sheet", self.print_bake_sheet, "primary", min_width=150).pack(
            side="right", anchor="s")
        chips = tk.Frame(ctl, bg=SURFACE)
        chips.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(chips, text="Dates with orders to bake:", bg=SURFACE, fg=LABEL, font=font(10)).pack(
            side="left", padx=(0, 12))
        self.chip_box = tk.Frame(chips, bg=SURFACE)
        self.chip_box.pack(side="left")

        cards = tk.Frame(body, bg=BG)
        cards.pack(fill="x", pady=(0, 12))
        self.prod_cards = [self.stat_card(cards, t, i, 3) for i, t in
                           enumerate(("Pieces needed", "Already in stock", "Still to bake"))]
        self.lbl_prod = tk.Label(body, text="", bg=BG, fg=MUTED, font=font(10), anchor="w")
        self.lbl_prod.pack(side="bottom", fill="x", pady=(10, 0))  # packed first so it is never squeezed out
        table_card, self.prod_tree = self.table(
            body, ("product", "orders", "qty", "stock", "short"),
            ("Product", "Orders", "Pieces needed", "In stock", "Still to bake"), (240, 90, 140, 110, 140),
            left=("product",))
        table_card.pack(fill="both", expand=True)

    def default_prod_date(self):
        """The nearest date (today or later) that has pending orders; today if there are none."""
        today = date.today().strftime(DATE_FMT)
        pending = sorted({o["order_date"] for o in self.orders
                          if o["status"] == "Pending" and o["order_date"] >= today})
        return pending[0] if pending else today

    def set_prod_date(self, delta):
        self.p_touched = True
        self.p_date.set((date.today() + timedelta(days=delta)).strftime(DATE_FMT))
        self.refresh_prod()

    def pick_prod_date(self, day):
        self.p_touched = True
        self.p_date.set(day)
        self.refresh_prod()

    def plan_rows(self, d):
        """The plan for date d: (product, orders, needed, pending part, in stock or None, still to bake) rows.

        'Still to bake' = what is still pending minus what is already in stock (stock is shared across
        dates). Returns (rows, whether baking records exist).
        """
        agg = defaultdict(lambda: [0, 0, 0])
        for o in self.orders:
            if o["order_date"] == d and (not self.p_pending.get() or o["status"] == "Pending"):
                a = agg[o["product"]]
                a[0] += 1
                a[1] += o["quantity"]
                a[2] += o["quantity"] if o["status"] == "Pending" else 0
        summary, start = stock_summary(self.orders, self.stock)
        tracking = start is not None
        rows = []
        for prod, (n, qty, pend) in sorted(agg.items(), key=lambda kv: -kv[1][1]):
            have = max(0, summary.get(prod, {}).get("have", 0)) if tracking else None
            rows.append((prod, n, qty, pend, have, pend if have is None else max(0, pend - have)))
        return rows, tracking

    def live_prod(self):
        """Refresh the plan as soon as a full-length date has been typed (an invalid one shows a message)."""
        if len(self.p_date.get().strip()) >= 10:
            self.refresh_prod()

    def refresh_prod_chips(self, selected):
        """One-click buttons for the dates that have pending orders (the selected one is highlighted)."""
        for w in self.chip_box.winfo_children():
            w.destroy()
        today = date.today().strftime(DATE_FMT)
        pieces = defaultdict(int)
        for o in self.orders:
            if o["status"] == "Pending":
                pieces[o["order_date"]] += o["quantity"]
        upcoming = sorted(x for x in pieces if x >= today)[:4]
        overdue = sorted((x for x in pieces if x < today), reverse=True)[:max(0, 4 - len(upcoming))]
        self.chip_dates = upcoming + overdue
        if not self.chip_dates:
            tk.Label(self.chip_box, text="none yet. Add an order first.", bg=SURFACE, fg=MUTED,
                     font=font(10)).pack(side="left")
            return
        for x in self.chip_dates:
            dt = datetime.strptime(x, DATE_FMT).date()
            name = ("Today" if x == today else "Tomorrow" if dt == date.today() + timedelta(days=1)
                    else f"{dt:%a %d %b}")
            label = f"{name}  ·  {pieces[x]:,} pcs" + ("  (overdue)" if x < today else "")
            self.btn(self.chip_box, label, lambda v=x: self.pick_prod_date(v),
                     "primary" if x == selected else "ghost", height=32).pack(side="left", padx=(0, 8))

    def refresh_prod(self):
        self.prod_tree.delete(*self.prod_tree.get_children())
        (v1, n1), (v2, n2), (v3, n3) = self.prod_cards
        d = parse_date(self.p_date.get())
        if not d:
            self.lbl_prod.config(text="Invalid date — use YYYY-MM-DD", fg=DANGER)
            for v in (v1, v2, v3):
                v.set("—")
            return
        rows, tracking = self.plan_rows(d)
        for i, (prod, n, qty, pend, have, short) in enumerate(rows):
            tag = "pending" if short > 0 else ("odd" if i % 2 else "even")  # yellow = still needs baking
            self.prod_tree.insert("", "end", tags=(tag,), values=(
                prod, n, f"{qty:,}", "—" if have is None else f"{have:,}", f"{short:,}"))
        v1.set(f"{sum(r[2] for r in rows):,}")
        n1.set(f"{plural(len(rows), 'product')} · {plural(sum(r[1] for r in rows), 'order')}")
        v2.set(f"{sum(min(r[4], r[3]) for r in rows):,}" if tracking else "—")
        n2.set("covered by what you already baked" if tracking else "no baking records yet")
        v3.set(f"{sum(r[5] for r in rows):,}"); n3.set(f"for {d}")
        self.refresh_prod_chips(d)
        which = "pending orders" if self.p_pending.get() else "orders"
        if rows:
            text = (f"Showing {which} for {d}, biggest quantity first.  "
                    + ("Stock comes from the Inventory tab." if tracking else
                       "Record what you bake on the Inventory tab to see what is already in stock."))
        elif self.chip_dates:
            text = f"Nothing to bake for {d} yet. Click one of the dates above that has orders."
        else:
            text = "No pending orders yet. Add an order on the Add Order tab and it will appear here."
        self.lbl_prod.config(text=text, fg=MUTED)

    # ------------------------------------------------------------ Reports
    def build_report(self):
        self.tab_report, body = self.new_page("A summary of orders, pieces and sales.")
        self.add_nav("Reports", self.tab_report)
        row1 = tk.Frame(body, bg=BG)
        row1.pack(fill="x", pady=(0, 14))
        titles = ("Total orders", "Pieces sold", "Total sales", "Average per day")
        self.rep = dict(zip(("orders", "pieces", "sales", "avg"),
                            [self.stat_card(row1, t, i, 4) for i, t in enumerate(titles)]))
        row2 = tk.Frame(body, bg=BG)
        row2.pack(fill="x", pady=(0, 16))
        self.rep["top"] = self.stat_card(row2, "Most ordered product", 0, 3)
        self.rep["best"] = self.stat_card(row2, "Best sales day", 1, 3)
        self.rep["stock"] = self.stat_card(row2, "Pieces in stock", 2, 3)
        bot = tk.Frame(body, bg=BG)
        bot.pack(side="bottom", fill="x", pady=(12, 0))
        tk.Label(bot, text="Saves a plain-text copy of this report that you can print or send.", bg=BG,
                 fg=MUTED, font=font(10)).pack(side="left")
        self.btn(bot, "Save report", self.save_report, "ghost", min_width=130).pack(side="right")
        table_card, self.rep_tree = self.table(
            body, ("product", "pieces", "sales", "share"),
            ("Product", "Pieces", "Sales", "Share of sales"), (260, 120, 160, 140), left=("product",))
        table_card.pack(fill="both", expand=True)

    def refresh_report(self):
        o = self.orders
        qty, sales = defaultdict(int), defaultdict(float)
        for r in o:
            qty[r["product"]] += r["quantity"]
            sales[r["product"]] += total(r)
        days = self.daily_totals()
        grand = sum(sales.values())
        pending = sum(1 for r in o if r["status"] == "Pending")
        self.rep["orders"][0].set(f"{len(o):,}")
        self.rep["orders"][1].set(f"{pending} pending · {len(o) - pending} completed")
        self.rep["pieces"][0].set(f"{sum(qty.values()):,}")
        self.rep["pieces"][1].set(plural(len(qty), "product"))
        pending_value = sum(total(r) for r in o if r["status"] == "Pending")
        self.rep["sales"][0].set(peso(grand))
        self.rep["sales"][1].set(f"incl. {peso(pending_value)} pending")
        summary, start = stock_summary(self.orders, self.stock)
        if start is None:
            self.rep["stock"][0].set("—"); self.rep["stock"][1].set("no baking records yet")
        else:
            self.rep["stock"][0].set(f"{sum(max(0, v['have']) for v in summary.values()):,}")
            self.rep["stock"][1].set("baked minus completed orders")
        if days:
            best = max(days.items(), key=lambda kv: kv[1][2])
            self.rep["avg"][0].set(peso(grand / len(days))); self.rep["avg"][1].set(f"across {plural(len(days), 'day')}")
            self.rep["best"][0].set(best[0]); self.rep["best"][1].set(f"{peso(best[1][2])} in sales")
        else:
            for k in ("avg", "best"):
                self.rep[k][0].set("—"); self.rep[k][1].set("")
        best = self.most_ordered()
        if best:
            self.rep["top"][0].set(best[0]); self.rep["top"][1].set(f"{plural(best[1], 'order')} · {best[2]:,} pieces")
        else:
            self.rep["top"][0].set("—"); self.rep["top"][1].set("")
        self.rep_tree.delete(*self.rep_tree.get_children())
        for i, p in enumerate(sorted(qty, key=qty.get, reverse=True)):
            share = f"{sales[p] / grand * 100:.1f}%" if grand else "0.0%"
            self.rep_tree.insert("", "end", tags=("odd" if i % 2 else "even",),
                                 values=(p, f"{qty[p]:,}", peso(sales[p]), share))

    # ------------------------------------------------------------ Inventory
    def build_stock(self):
        self.tab_stock, body = self.new_page(
            "Keep count of what you bake. In stock = pieces baked minus orders marked Completed since your first record.")
        self.add_nav("Inventory", self.tab_stock)
        self.st_product, self.st_qty = tk.StringVar(), tk.StringVar(value="1")
        self.st_date = tk.StringVar(value=date.today().strftime(DATE_FMT))
        self.st_kind = "Baked"
        form = self.card(body)
        form.pack(fill="x", pady=(0, 12))
        row = tk.Frame(form, bg=SURFACE)
        row.pack(fill="x", padx=18, pady=(12, 14))

        def cell(label, factory):
            c = tk.Frame(row, bg=SURFACE)
            c.pack(side="left", anchor="s", padx=(0, 14))
            tk.Label(c, text=label, bg=SURFACE, fg=LABEL, font=font(10)).pack(anchor="w", pady=(0, 4))
            w = factory(c)
            w.pack()
            return w

        self.cb_stock_product = cell("Product", lambda p: ttk.Combobox(
            p, textvariable=self.st_product, width=20, values=list(PRODUCTS)))
        self.seg_stock_kind = cell("What happened", lambda p: Segmented(
            self, p, ["Baked", "Used / wasted"], "Baked", lambda v: setattr(self, "st_kind", v)))
        self.ent_stock_qty = cell("Pieces", lambda p: ttk.Spinbox(
            p, from_=1, to=10000, width=7, textvariable=self.st_qty))
        cell("Date", lambda p: ttk.Entry(p, textvariable=self.st_date, width=11))
        self.btn(row, "Record", self.record_stock, "primary", min_width=110).pack(side="right", anchor="s")

        cards = tk.Frame(body, bg=BG)
        cards.pack(fill="x", pady=(0, 12))
        self.stock_cards = [self.stat_card(cards, t, i, 3) for i, t in
                            enumerate(("Pieces in stock", "Still to bake", "Products running short"))]
        bot = tk.Frame(body, bg=BG)
        bot.pack(side="bottom", fill="x", pady=(10, 0))
        self.lbl_stock = tk.Label(bot, text="", bg=BG, fg=MUTED, font=font(10), anchor="w")
        self.lbl_stock.pack(side="left", fill="x", expand=True)
        self.btn(bot, "Undo last record", self.undo_stock, "ghost", min_width=150).pack(side="right")
        table_card, self.stock_tree = self.table(
            body, ("product", "baked", "sold", "have", "waiting", "short"),
            ("Product", "Baked", "Sold", "In stock", "Orders waiting", "Still to bake"),
            (220, 90, 90, 110, 130, 130), left=("product",))
        table_card.pack(fill="both", expand=True)

    def stock_say(self, text, error=False):
        """A one-line message under the stock table (fades from green to grey when it is good news)."""
        self.lbl_stock.config(text=text, fg=DANGER if error else PRIMARY)
        if error:
            self.cancel("stocknote")
        else:
            self.animate("stocknote", 2500, lambda e: self.lbl_stock.config(fg=lerp_color(PRIMARY, MUTED, e)),
                         ease=ease_in_out)

    def refresh_stock(self):
        self.cb_stock_product.config(values=list(self.menu_prices()))
        summary, start = stock_summary(self.orders, self.stock)
        self.stock_tree.delete(*self.stock_tree.get_children())
        rows = sorted(summary.items(), key=lambda kv: (-kv[1]["short"], kv[0]))
        for i, (prod, v) in enumerate(rows):
            tag = "pending" if v["short"] > 0 else ("odd" if i % 2 else "even")  # yellow = needs baking
            self.stock_tree.insert("", "end", tags=(tag,), values=(
                prod, f"{v['baked']:,}", f"{v['sold']:,}", f"{v['have']:,}", f"{v['waiting']:,}", f"{v['short']:,}"))
        (v1, n1), (v2, n2), (v3, n3) = self.stock_cards
        if start is None:
            for v, n in ((v1, n1), (v2, n2), (v3, n3)):
                v.set("—"); n.set("no baking records yet")
            self.lbl_stock.config(text="No baking records yet. Pick a product, enter how many you baked and press "
                                       "Record. The program keeps count from there.", fg=MUTED)
            return
        have = sum(max(0, v["have"]) for v in summary.values())
        short_rows = [v for v in summary.values() if v["short"] > 0]
        v1.set(f"{have:,}"); n1.set(f"across {plural(sum(1 for v in summary.values() if v['have'] > 0), 'product')}")
        v2.set(f"{sum(v['short'] for v in short_rows):,}"); n2.set("for the orders that are waiting")
        v3.set(str(len(short_rows))); n3.set(f"of {plural(len(summary), 'product')}")
        self.lbl_stock.config(text=f"{len(self.stock)} records since {start}.  Yellow rows still need baking "
                                   "for the orders that are waiting.", fg=MUTED)

    def record_stock(self):
        self.sync_from_disk()
        menu = self.menu_prices()
        typed = self.st_product.get().strip()
        prod = next((p for p in menu if p.lower() == typed.lower()), typed)
        if not prod:
            return self.stock_say("Please choose or type a product first.", error=True)
        if len(prod) > 60:
            return self.stock_say("Product names can be up to 60 characters.", error=True)
        try:
            qty = int(self.st_qty.get())
            if qty <= 0 or qty > 100000:
                raise ValueError
        except ValueError:
            return self.stock_say("Pieces must be a positive whole number.", error=True)
        d = parse_date(self.st_date.get())
        if not d:
            return self.stock_say("Use the date format YYYY-MM-DD (e.g. 2026-10-12).", error=True)
        gap = abs((datetime.strptime(d, DATE_FMT).date() - date.today()).days)
        if gap > 90 and not messagebox.askyesno("Check the date", f"{d} is {gap} days from today. Is that correct?"):
            return
        if qty > 10000 and not messagebox.askyesno("Check the amount", f"{qty:,} pieces is unusually large. Is that correct?"):
            return
        signed = qty if self.st_kind == "Baked" else -qty
        row = {"entry_id": max([e["entry_id"] for e in self.stock], default=0) + 1, "date": d,
               "product": prod, "quantity": signed, "note": ""}
        try:
            if os.path.exists(stock_file()):
                append_stock(row)
            else:  # first record, or the file was deleted: write everything back
                save_stock(self.stock + [row])
        except OSError as e:
            return self.file_error(e, stock_file())
        self._stock_stamp = self.stock_stamp()
        self.stock.append(row)
        self.st_qty.set("1")
        self.refresh_all()
        self.stock_say(f"Recorded {'+' if signed > 0 else '-'}{qty:,} {prod} on {d}.")

    def persist_stock(self, rollback):
        try:
            save_stock(self.stock)
            self._stock_stamp = self.stock_stamp()
            return True
        except OSError as e:
            self.stock = rollback
            self.file_error(e, stock_file())
            self.refresh_all()
            return False

    def undo_stock(self):
        self.sync_from_disk()
        if not self.stock:
            return self.stock_say("There are no records to undo yet.", error=True)
        last = max(self.stock, key=lambda e: e["entry_id"])
        if not messagebox.askyesno("Undo last record", f"Remove this record?\n\n{last['quantity']:+,} {last['product']} "
                                                       f"on {last['date']}"):
            return
        old = self.stock
        self.stock = [e for e in self.stock if e is not last]
        if self.persist_stock(old):
            self.refresh_all()
            self.stock_say("Last record removed.")

    # ------------------------------------------------------------ Saved reports / bake sheet
    @staticmethod
    def export_dir():
        return os.path.join(os.path.dirname(CSV_FILE), "exports")

    def write_export(self, stem, text):
        """Save text as a Notepad-friendly file in the exports folder and open it so it can be printed."""
        folder = self.export_dir()
        try:
            os.makedirs(folder, exist_ok=True)
            base = os.path.join(folder, f"{stem}-{datetime.now():%Y%m%d-%H%M%S}")
            path, n = base + ".txt", 1
            while os.path.exists(path):  # two saves in the same second must never overwrite each other
                n += 1
                path = f"{base}-{n}.txt"
            with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:  # BOM + CRLF: Notepad shows it properly
                f.write(text)
        except OSError as e:
            self.file_error(e, folder)
            return None
        try:
            open_file(path)
        except Exception:
            messagebox.showinfo("Saved", f"Saved to:\n{path}")
        return path

    def bake_sheet_text(self, d):
        rows, tracking = self.plan_rows(d)
        which = "pending orders only" if self.p_pending.get() else "all orders"
        width = 62
        lines = ["GMD BAKERY - BAKE SHEET", "=" * width,
                 f"Bake for : {datetime.strptime(d, DATE_FMT):%A, %d %B %Y}", f"Orders   : {which}",
                 f"Printed  : {datetime.now():%Y-%m-%d %H:%M}", "",
                 f"{'Product':<28}{'Needed':>8}{'In stock':>10}{'To bake':>10}", "-" * width]
        for prod, n, qty, pend, have, short in rows:
            lines.append(f"{prod[:27]:<28}{qty:>8,}{'-' if have is None else format(have, ','):>10}{short:>10,}")
        lines += ["-" * width, f"{'TOTAL':<28}{sum(r[2] for r in rows):>8,}"
                  f"{(format(sum(min(r[4], r[3]) for r in rows), ',') if tracking else '-'):>10}"
                  f"{sum(r[5] for r in rows):>10,}", "", "Orders for this day:"]
        for o in sorted((o for o in self.orders if o["order_date"] == d and
                         (not self.p_pending.get() or o["status"] == "Pending")), key=lambda o: o["order_id"]):
            lines.append(f"  #{o['order_id']:<5} {o['customer'][:24]:<25} {o['quantity']:>5,} x {o['product']}"
                         f"  [{o['status']}]")
        return "\n".join(lines) + "\n"

    def print_bake_sheet(self):
        d = parse_date(self.p_date.get())
        if not d:
            return messagebox.showerror("Invalid date", "Pick a valid date first (YYYY-MM-DD).")
        if not self.plan_rows(d)[0]:
            return messagebox.showinfo("Nothing to print", f"There is nothing to bake for {d}.")
        return self.write_export(f"bake-sheet-{d}", self.bake_sheet_text(d))

    def report_text(self):
        o = self.orders
        qty, sales = defaultdict(int), defaultdict(float)
        for r in o:
            qty[r["product"]] += r["quantity"]
            sales[r["product"]] += total(r)
        days = self.daily_totals()
        grand = sum(sales.values())
        pend = [r for r in o if r["status"] == "Pending"]
        pend_value = sum(total(r) for r in pend)
        summary, start = stock_summary(self.orders, self.stock)
        width = 62
        lines = ["GMD BAKERY - SUMMARY REPORT", "=" * width, f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
                 f"Total orders ........ {len(o):,}   ({len(pend)} pending, {len(o) - len(pend)} completed)",
                 f"Pieces ordered ...... {sum(qty.values()):,}",
                 f"Total sales ......... {peso(grand)}",
                 f"  completed ......... {peso(grand - pend_value)}",
                 f"  still pending ..... {peso(pend_value)}"]
        if days:
            best = max(days.items(), key=lambda kv: kv[1][2])
            lines += [f"Average per day ..... {peso(grand / len(days))}  (over {len(days)} days)",
                      f"Best sales day ...... {best[0]}  ({peso(best[1][2])})"]
        best = self.most_ordered()
        if best:
            lines.append(f"Most ordered ........ {best[0]}  ({plural(best[1], 'order')}, {best[2]:,} pieces)")
        lines.append("Pieces in stock ..... " + ("not tracked yet" if start is None else
                                                 f"{sum(max(0, v['have']) for v in summary.values()):,}"))
        lines += ["", f"{'Product':<28}{'Pieces':>8}{'Sales':>16}{'Share':>9}", "-" * width]
        for p in sorted(qty, key=qty.get, reverse=True):
            share = f"{sales[p] / grand * 100:.1f}%" if grand else "0.0%"
            lines.append(f"{p[:27]:<28}{qty[p]:>8,}{peso(sales[p]):>16}{share:>9}")
        lines += ["", "Daily sales (latest 14 days)", f"{'Date':<14}{'Orders':>8}{'Pieces':>9}{'Sales':>16}", "-" * width]
        for d, (n, pcs, amt) in list(reversed(list(days.items())))[:14]:
            lines.append(f"{d:<14}{n:>8}{pcs:>9,}{peso(amt):>16}")
        return "\n".join(lines) + "\n"

    def save_report(self):
        return self.write_export("report", self.report_text())

    # ------------------------------------------------------------ Charts
    def build_charts(self):
        self.tab_charts, body = self.new_page("See what sells best and how sales change over time.")
        self.add_nav("Charts", self.tab_charts)
        top = tk.Frame(body, bg=BG)
        top.pack(fill="x", pady=(0, 14))
        self.chart_kind = "bar"
        self.line_mode = tk.StringVar(value="Daily")
        kinds = {"Quantity per product": "bar", "Sales trend": "line", "Sales share": "pie"}
        self.seg_kind = Segmented(self, top, list(kinds), "Quantity per product",
                                  lambda v: self.pick_chart(kinds[v]))
        self.seg_kind.pack(side="left")
        self.trend_box = tk.Frame(top, bg=BG)
        self.seg_trend = Segmented(self, self.trend_box, ["Daily", "Weekly"], "Daily",
                                   lambda v: (self.line_mode.set(v), self.show_chart("line", animate=True)))
        self.seg_trend.pack()
        self.line_mode.trace_add("write", lambda *a: self.seg_trend.set(self.line_mode.get()))
        chart_card = self.card(body)
        chart_card.pack(fill="both", expand=True)
        self.fig = Figure(figsize=(8, 5), dpi=100, facecolor=SURFACE)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_card)
        chart_widget = self.canvas.get_tk_widget()
        chart_widget.config(highlightthickness=0, bg=SURFACE)
        chart_widget.pack(fill="both", expand=True, padx=14, pady=12)

    def pick_chart(self, kind):
        self.show_chart(kind, animate=True)

    @staticmethod
    def style_axes(ax, title):
        ax.set_facecolor("white")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(BORDER)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=16)

    def show_chart(self, kind, animate=False):
        self.chart_kind = kind
        self.seg_kind.set({"bar": "Quantity per product", "line": "Sales trend", "pie": "Sales share"}[kind])
        if kind == "line":
            self.trend_box.pack(side="right")
        else:
            self.trend_box.pack_forget()
        self.cancel("chart")
        self.cancel("chartwait")
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        qty, sales = defaultdict(int), defaultdict(float)
        for r in self.orders:
            qty[r["product"]] += r["quantity"]
            sales[r["product"]] += total(r)
        play = None  # (artists that move, per-frame update, final touch) when there is something to animate
        if not self.orders:
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center", fontsize=14, color=MUTED)
            ax.axis("off")
        elif kind == "bar":
            items = sorted(qty.items(), key=lambda kv: kv[1])
            top_v = max(v for _, v in items)
            colors = [lerp_color("#a8d27a", PRIMARY, v / top_v) for _, v in items]
            bars = ax.barh([k for k, _ in items], [v for _, v in items], color=colors, height=0.62)
            labels = ax.bar_label(bars, padding=4, color=INK, fontsize=9)
            self.style_axes(ax, "Quantity sold per product")
            ax.set_xlabel("Pieces", color=MUTED, fontsize=9)
            ax.xaxis.grid(True, color=BORDER, alpha=0.8)
            ax.set_axisbelow(True)
            ax.spines["left"].set_visible(False)
            ax.set_xlim(0, top_v * 1.12)
            final = [b.get_width() for b in bars]

            def upd(e, bars=bars, final=final):
                n = len(bars)
                for i, (b, w) in enumerate(zip(bars, final)):
                    b.set_width(w * max(0.0, min(1.0, e * 1.6 - 0.6 * i / n)))

            def fin(bars=bars, final=final, labels=labels):
                for b, w in zip(bars, final):
                    b.set_width(w)
                for t in labels:
                    t.set_visible(True)
            play = (list(bars), upd, fin, labels)
        elif kind == "line":
            days = self.daily_totals()
            multi_year = len({d[:4] for d in days}) > 1
            if self.line_mode.get() == "Weekly":
                wk = defaultdict(float)
                for d, v in days.items():
                    dt = datetime.strptime(d, DATE_FMT).date()
                    wk[dt - timedelta(days=dt.weekday())] += v[2]
                labels = [f"{k:%b %d, %Y}" if multi_year else f"{k:%b %d}" for k in sorted(wk)]
                ys = [wk[k] for k in sorted(wk)]
                ax.set_xlabel("Week starting", color=MUTED, fontsize=9)
            else:
                labels = [d if multi_year else d[5:] for d in days]
                ys = [v[2] for v in days.values()]
                ax.set_xlabel("Date" if multi_year else "Date (MM-DD)", color=MUTED, fontsize=9)
            xs = list(range(len(ys)))  # numeric positions so equal labels never merge
            (line,) = ax.plot(xs, ys, marker="o", markersize=5, color=ACCENT, linewidth=2.4)
            fill = ax.fill_between(xs, ys, alpha=0.14, color=ACCENT)
            self.style_axes(ax, f"{self.line_mode.get()} sales trend")
            ax.set_ylabel("Sales (₱)", color=MUTED, fontsize=9)
            ax.yaxis.grid(True, color=BORDER, alpha=0.8)
            ax.set_axisbelow(True)
            step = max(1, len(xs) // 12)
            ax.set_xticks(xs[::step])
            ax.set_xticklabels(labels[::step], rotation=45, ha="right")
            ax.set_xlim(-0.5, max(len(xs) - 0.5, 0.5))
            ax.set_ylim(0, max(ys) * 1.1 if ys and max(ys) > 0 else 1)
            state = {"fill": fill}

            def upd(e, line=line, xs=xs, ys=ys, state=state, ax=ax):
                reach = (len(xs) - 1) * e
                k = int(reach)
                px, py = xs[:k + 1], ys[:k + 1]
                if k < len(xs) - 1:
                    frac = reach - k
                    px = px + [xs[k] + frac]
                    py = py + [ys[k] + (ys[k + 1] - ys[k]) * frac]
                line.set_data(px, py)
                if state["fill"] is not None:
                    state["fill"].remove()
                state["fill"] = ax.fill_between(px, py, alpha=0.14, color=ACCENT, animated=True)

            def fin(line=line, xs=xs, ys=ys, state=state, ax=ax):
                line.set_data(xs, ys)
                if state["fill"] is not None:
                    state["fill"].remove()
                state["fill"] = ax.fill_between(xs, ys, alpha=0.14, color=ACCENT)

            play = ([line], upd, fin, [state])  # the fill is rebuilt every frame, so it lives in `state`
        else:
            items = [(k, v) for k, v in sorted(sales.items(), key=lambda kv: -kv[1]) if v > 0]
            if not items:
                ax.text(0.5, 0.5, "No sales to show", ha="center", va="center", fontsize=14, color=MUTED)
                ax.axis("off")
            else:
                colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(len(items))]
                wedges, texts, pct_texts = ax.pie(
                    [v for _, v in items], labels=[k for k, _ in items], autopct="%1.1f%%", startangle=90,
                    colors=colors, pctdistance=0.8, wedgeprops={"edgecolor": "white", "linewidth": 2})
                for t in texts:
                    t.set_color(INK); t.set_fontsize(9)
                for c, t in zip(colors, pct_texts):  # white text on dark slices
                    r, g, bl = hex_to_rgb(c)
                    t.set_fontsize(9)
                    if 0.299 * r + 0.587 * g + 0.114 * bl < 140:
                        t.set_color("white")
                ax.set_title("Share of total sales by product", loc="left", fontsize=13,
                             fontweight="bold", color=INK, pad=16)
                spans = [(w.theta1, w.theta2) for w in wedges]

                def upd(e, wedges=wedges, spans=spans):
                    for w, (a, b) in zip(wedges, spans):
                        w.set_theta1(90 + (a - 90) * e)
                        w.set_theta2(90 + (b - 90) * e)

                def fin(wedges=wedges, spans=spans, texts=texts, pct=pct_texts):
                    for w, (a, b) in zip(wedges, spans):
                        w.set_theta1(a); w.set_theta2(b)
                    for t in list(texts) + list(pct):
                        t.set_visible(True)
                play = (list(wedges), upd, fin, list(texts) + list(pct_texts))
        self.fig.tight_layout()
        if play and animate and self.current_page is self.tab_charts:
            self.play_chart(ax, kind, *play)
        else:
            self.canvas.draw()

    def play_chart(self, ax, kind, moving, upd, fin, extra):
        """Draw the chart in with blitting: only the moving shapes are redrawn each frame."""
        canvas = self.canvas
        hidden = [t for t in extra if hasattr(t, "set_visible")]
        try:
            for t in hidden:
                t.set_visible(False)
            for a in moving:
                a.set_animated(True)
            upd(0.0)  # for the line chart this also swaps the static fill for an animated one
            canvas.draw()
            backdrop = canvas.copy_from_bbox(ax.bbox)
            drawn = lambda: moving + ([extra[-1]["fill"]] if kind == "line" else [])

            def step(e):
                canvas.restore_region(backdrop)
                upd(e)
                for a in drawn():
                    ax.draw_artist(a)
                canvas.blit(ax.bbox)

            def done():
                for a in moving:
                    a.set_animated(False)
                fin()
                for t in hidden:
                    t.set_visible(True)
                canvas.draw()
            self.later("chartwait", 200, lambda: self.animate("chart", 750, step, done))
        except Exception:  # never let a drawing hiccup leave a blank chart
            if os.environ.get("GMD_DEBUG"):
                import traceback
                traceback.print_exc()
            for a in moving:
                a.set_animated(False)
            fin()
            for t in hidden:
                t.set_visible(True)
            canvas.draw()

    # ------------------------------------------------------------ refresh
    def refresh_all(self):
        self.cb_product.config(values=list(self.menu_prices()))
        self.refresh_orders()
        self.refresh_sales()
        self.refresh_prod()
        self.refresh_stock()
        self.refresh_report()
        self.refresh_recent()
        self.refresh_header()
        if self.current_page is self.tab_charts:  # the chart is only redrawn while it is on screen
            self.show_chart(self.chart_kind, animate=self.count_next)

    def refresh_header(self):
        self.lbl_date.config(text=f"{date.today():%A, %d %B %Y}")
        pending = sum(1 for o in self.orders if o["status"] == "Pending")
        self.pending_pill.set_text(f"{pending} pending order{'s' if pending != 1 else ''}")

    def refresh_recent(self):
        self.recent_tree.delete(*self.recent_tree.get_children())
        latest = sorted(self.orders, key=lambda o: o["order_id"], reverse=True)[:8]
        for i, o in enumerate(latest):
            self.recent_tree.insert("", "end", tags=("odd" if i % 2 else "even",),
                                    values=(o["customer"], o["product"], o["quantity"], f"{total(o):,.0f}"))


NUMERIC = {"quantity", "price", "total", "orders", "pieces", "sales", "qty", "value", "share",
           "stock", "short", "baked", "sold", "have", "waiting"}


if __name__ == "__main__":
    # optional: "GMD Bakery Planner.exe --tab 4" opens straight on tab 4 (handy for desktop shortcuts)
    wanted = None
    if "--tab" in sys.argv:
        try:
            wanted = int(sys.argv[sys.argv.index("--tab") + 1])
        except (ValueError, IndexError):
            pass
    App(intro=True, start_tab=wanted).mainloop()
