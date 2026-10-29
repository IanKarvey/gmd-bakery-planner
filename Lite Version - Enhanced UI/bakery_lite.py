"""GMD Bakery - Order and Production Planner (simple version, enhanced look)

Run:  python bakery_lite.py

What the program does (the features in the project requirements):
    Overview ....... the bakery at a glance: sales, orders waiting, what to bake next, what to reorder
    Orders ......... add, view, search/filter and update customer orders
    Sales .......... total sales per product and per day (from the daily sales records)
    Production ..... how many pieces and batches to bake for a date, and the ingredients needed
    Inventory ...... ingredients on hand, reorder status, restock
    Reports ........ a text summary that can be saved to a file
    Charts ......... bar, line and pie charts (Matplotlib)

All data is kept in CSV files (folder "lite_data"). This public copy ships with invented sample data;
excel_to_csv.py can import a bakery's own Excel workbook in the same layout.

The look and the movement (animated tabs, buttons, cards, charts) are in ui_kit.py, in the same folder.
"""
import csv
import json
import math
import os
import shutil
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, timedelta
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import charts  # the charts (Matplotlib), drawn in the same style
import ui_kit as ui  # the look and the motion (colours, animated tabs and buttons, cards, pop-up notes)

messagebox = ui.messages  # pop-up dialogs (the plain Windows ones when animation is off)

HERE = os.path.dirname(os.path.abspath(__file__))
STATUSES = ["Pending", "Completed", "Cancelled"]
ICONS = {"Overview": "home", "Orders": "list", "Sales": "bars", "Production Plan": "oven", "Inventory": "box",
         "Reports": "doc", "Charts": "pie"}  # the little line icon in each tab
HINTS = {  # the line under the program name changes to say what the tab you are on is for
    "Overview": "The bakery at a glance. Pick a day to see its baking plan; click a card to open it.",
    "Orders": "Write down every customer order. Amber = waiting, grey = cancelled. Completed orders count as sales.",
    "Sales": "Everything sold so far, by product and by day (completed orders are included). Pending = not picked up yet.",
    "Production Plan": "Pick a day to bake: usual daily sales + that day's orders = batches and ingredients.",
    "Inventory": "The ingredients in the kitchen. Reorder = time to buy more. Bake it uses them up.",
    "Reports": "A summary of orders and sales. Read it here or save it as a text file.",
    "Charts": "Pick a chart. The highlighted button is the one you are looking at.",
}
INGREDIENTS = ["flour", "sugar", "butter", "eggs", "yeast"]  # the order of the columns in products.csv

PRODUCT_FIELDS = ["product"] + INGREDIENTS + ["pieces_per_batch", "price", "max_batches"]
INGREDIENT_FIELDS = ["ingredient", "qty_on_hand", "unit", "reorder_level"]
SALES_FIELDS = ["date", "product", "qty_sold", "unit_price", "total_sales", "order_id"]  # order_id: the order it came from
ORDER_FIELDS = ["order_id", "order_date", "customer", "product", "qty", "unit_price", "total",
                "pickup_date", "status"]


# ------------------------------------------------------------------ small helpers
def parse_date(text):
    """'2026-09-30' -> a date, or None if it is not a valid YYYY-MM-DD date."""
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def peso(amount):
    return f"₱{amount:,.2f}"


def neat(number):
    """5.0 -> 5 (so the CSV files stay tidy)."""
    return int(number) if float(number).is_integer() else round(number, 4)


def show(number):
    """Text for a quantity on screen: 2.4 -> '2.4', 100.0 -> '100'."""
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def pick_data_folder(candidates=None):
    """Find a folder where the program can save. Normally that is lite_data next to the program.

    If Windows does not allow saving there (this happens in some protected folders), the starting
    files are copied to a folder inside AppData and that one is used instead.
    """
    seed = os.path.join(HERE, "lite_data")
    appdata = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "GMD-Bakery-Lite")
    for folder in candidates or [seed, appdata]:
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".write_test")
            with open(probe, "w") as f:  # a real test: can a file be created here?
                f.write("ok")
            os.remove(probe)
        except OSError:
            continue
        if folder != seed and os.path.isdir(seed):
            for name in os.listdir(seed):  # first time here: copy the starting data files
                target = os.path.join(folder, name)
                if name.endswith(".csv") and not os.path.exists(target):
                    shutil.copy(os.path.join(seed, name), target)
        return folder
    raise SystemExit("The program could not find a folder where it can save its data.")


class App(tk.Tk):
    def __init__(self, folder=None):
        super().__init__()
        self.folder = folder or pick_data_folder()
        self.settings = self.load_settings()
        ui.set_theme(self.settings["theme"])  # (before any widget is made, so everything starts in the right colours)
        self.title("GMD Bakery - Order and Production Planner")
        # screen scaling (100%, 125%, 150%...): the fixed sizes below are multiplied by it so nothing is cut off
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96)
        width = min(int(1050 * self.scale), self.winfo_screenwidth() - 40)
        height = min(int(690 * self.scale), self.winfo_screenheight() - 90)
        self.geometry(f"{width}x{height}")
        self.minsize(min(width, int(950 * self.scale)), min(height, int(620 * self.scale)))

        self.motion = ui.Motion(self)  # runs every animation; stopped when the window closes
        self.toaster = ui.Toast(self, self.motion, self.scale)
        ui.apply_style(self, self.scale)
        if ui.ANIMATE:
            self.attributes("-alpha", 0.0)  # invisible until everything is built, then it fades in
        self.protocol("WM_DELETE_WINDOW", self.close)
        ui.messages.app = self  # pop-up dialogs open over this window
        self.header = ui.Header(self, self.motion, self.scale, "GMD Bakery", HINTS["Overview"], f"{date.today():%d %B %Y}",
                                on_theme=self.toggle_theme)
        self.header.pack(fill="x")
        self.tabs = ui.Tabs(self, self.motion, self.scale)
        self.tabs.pack(fill="both", expand=True)

        try:
            self.load_data()
        except (OSError, KeyError, ValueError) as error:  # a file is missing or was changed so it can't be read
            ui.messages.app = None  # the window is not ready yet, so use the plain Windows message box
            messagebox.showerror("Cannot read the data files",
                                 f"Folder: {self.folder}\n\nProblem: {error}\n\nCheck that products.csv and "
                                 "ingredients.csv are there and that no CSV file was changed by hand.")
            self.destroy()
            raise SystemExit(1)
        for name, build in [("Overview", self.build_overview), ("Orders", self.build_orders),
                            ("Sales", self.build_sales), ("Production Plan", self.build_plan),
                            ("Inventory", self.build_inventory), ("Reports", self.build_report),
                            ("Charts", self.build_charts)]:
            page = self.tabs.page(0 if name == "Overview" else 12)  # the Overview fills its whole page
            self.tabs.add(page, text=name, icon=ICONS[name])
            build(page)
        self.tabs.bind("<<NotebookTabChanged>>", lambda event: self.tab_changed())
        self.tabs.bind("<<TabShown>>", lambda event: self.tab_shown())
        for number in range(len(self.tabs.pages)):  # Ctrl+1 ... Ctrl+7 jump to a tab
            self.bind_all(f"<Control-Key-{number + 1}>", lambda event, n=number: self.tabs.select(n))
        for key in ("<Control-d>", "<Control-D>"):  # Ctrl+D: light / dark
            self.bind_all(key, lambda event: self.toggle_theme())
        self.style_tables()
        ui.native_theme(self, ui.THEME["name"] == "dark")  # a dark title bar in dark mode
        self.refresh_all()
        self.tabs.warm_up()  # draw every page's cards once, hidden, so opening a tab never has to wait
        self.refresh_overview(replay=True)
        self.motion.later("fade-start", 40, lambda: self.fade(0.0, 1.0, 320))  # after the first paint

    # ------------------------------------------------------------------ window and tab changes
    def fade(self, start, end, ms, done=None):
        """Fade the whole window from one opacity to another (does nothing when animation is off)."""
        if ui.ANIMATE:
            self.motion.run("fade", ms, lambda t: self.attributes("-alpha", start + (end - start) * t), done=done)
        elif done:
            done()

    def close(self):
        self.fade(1.0, 0.0, 160, done=self.destroy)

    def destroy(self):
        self.motion.stop_all()  # no animation may be left running on a window that is gone
        if ui.messages.app is self:
            ui.messages.app = None
        super().destroy()

    def tab_changed(self):
        """A tab was chosen: bring only that page up to date (it is not on screen yet). The other pages were
        already refreshed when the data last changed, so switching tabs stays quick."""
        name = self.tabs.names[self.tabs.current]
        {"Overview": lambda: self.refresh_overview(replay=True),  # the numbers count up again
         "Orders": self.refresh_orders, "Sales": self.refresh_sales, "Production Plan": self.refresh_plan,
         "Inventory": self.refresh_inventory, "Reports": self.refresh_report}.get(name, lambda: None)()
        self.header.say(HINTS[name])

    def tab_shown(self):
        """The page has finished sliding in: the chart grows in now."""
        if self.tabs.names[self.tabs.current] == "Charts":
            self.draw_chart(self.chart_kind, animate=True)

    def toast(self, text):
        """A short success note in the corner (errors and questions still use message boxes)."""
        self.toaster.show(text)

    # ------------------------------------------------------------------ light and dark
    def load_settings(self):
        settings = {}
        try:
            with open(self.path("settings.json"), encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, ValueError):
            pass  # (no settings yet: the light look)
        if os.environ.get("GMD_THEME") in ui.THEMES:  # (a way to start in a given theme, for tests and screenshots)
            settings["theme"] = os.environ["GMD_THEME"]
        if settings.get("theme") not in ui.THEMES:
            settings["theme"] = "light"
        return settings

    def save_settings(self):
        try:
            with open(self.path("settings.json"), "w", encoding="utf-8") as f:
                json.dump(self.settings, f)
        except OSError:
            pass  # (a theme that is not remembered is not worth an error message)

    def toggle_theme(self):
        self.switch_theme("dark" if ui.THEME["name"] == "light" else "light")

    def switch_theme(self, name):
        """Switch between the light and the dark look. The old look is photographed and laid over the window, everything
        underneath is redrawn in the new colours, then the photograph fades away: one smooth cross-fade."""
        if name == ui.THEME["name"] or name not in ui.THEMES:
            return
        old, veil = ui.THEME["name"], ui.Veil(self)
        self.veil = veil
        ui.set_theme(name)
        ui.apply_style(self, self.scale)
        ui.recolor(self, ui.theme_map(old, name))  # plain Tk widgets (frames, labels, the report text)
        ui.restyle_all()  # everything drawn with pictures: cards, buttons, tabs, fields, the Overview
        self.style_tables()
        self.report.configure(fg=ui.TEXT, insertbackground=ui.TEXT)
        self.refresh_plan()  # (its status note sets its own colour)
        self.draw_chart(self.chart_kind)
        ui.native_theme(self, name == "dark")
        self.update()
        self.settings["theme"] = name
        self.save_settings()
        veil.fade(420)
        self.header.spin_icon()

    def style_tables(self):
        """Colours of the status words and warning rows in the tables (set again after a light/dark switch)."""
        self.order_table.tag_configure("Pending", foreground=ui.AMBER)
        self.order_table.tag_configure("Completed", foreground=ui.TEXT)  # (done orders stay quiet)
        self.order_table.tag_configure("Cancelled", foreground=ui.MUTED)
        self.sales_table.tag_configure("total", background=ui.PALE_GREEN)
        for table in (self.plan_table, self.plan_ingredients):
            table.tag_configure("bad", foreground=ui.RED)
        self.plan_ingredients.tag_configure("warn", foreground=ui.AMBER)
        self.inv_table.tag_configure("warn", foreground=ui.AMBER)

    # ------------------------------------------------------------------ CSV files (read / write / append)
    def path(self, name):
        return os.path.join(self.folder, name)

    def read(self, name):
        with open(self.path(name), newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def write(self, name, fields, rows):
        """Write a whole file again (used when something is updated)."""
        with open(self.path(name), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            writer.writerows(rows)

    def append(self, name, row):
        """Add one new line at the end of a file (used for new orders and new sales records)."""
        with open(self.path(name), "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def load_data(self):
        # the files that hold the user's own records are created (with just a header row) if they do not exist yet
        for name, fields in (("orders.csv", ORDER_FIELDS), ("daily_sales.csv", SALES_FIELDS)):
            if not os.path.exists(self.path(name)):
                self.write(name, fields, [])
        self.upgrade_sales_file()
        self.products = {}  # name -> recipe, pieces per batch, price, max batches per day
        for r in self.read("products.csv"):
            self.products[r["product"]] = {
                "recipe": [float(r[i]) for i in INGREDIENTS], "pieces": int(float(r["pieces_per_batch"])),
                "price": float(r["price"]), "max_batches": int(float(r["max_batches"]))}
        self.ingredients = [{"name": r["ingredient"], "qty": float(r["qty_on_hand"]), "unit": r["unit"],
                             "reorder": float(r["reorder_level"])} for r in self.read("ingredients.csv")]
        self.sales = [{"date": parse_date(r["date"]), "product": r["product"], "qty": int(float(r["qty_sold"])),
                       "price": float(r["unit_price"]), "order": r.get("order_id") or ""}
                      for r in self.read("daily_sales.csv")]
        self.orders = [{"id": r["order_id"], "order_date": r["order_date"], "customer": r["customer"],
                        "product": r["product"], "qty": int(float(r["qty"])), "price": float(r["unit_price"]),
                        "pickup": r["pickup_date"], "status": r["status"]} for r in self.read("orders.csv")]

    def upgrade_sales_file(self):
        """Older data files have no order_id column in daily_sales.csv (it says which sales came from a completed
        order). Add the empty column once, keeping every row as it was."""
        with open(self.path("daily_sales.csv"), newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f), [])
        if "order_id" not in header:
            rows = self.read("daily_sales.csv")
            try:
                self.write("daily_sales.csv", SALES_FIELDS, [[r["date"], r["product"], r["qty_sold"], r["unit_price"],
                                                             r["total_sales"], ""] for r in rows])
            except OSError:
                pass  # (a folder that cannot be written to: the program still reads the old file)

    def save_sales(self):
        self.write("daily_sales.csv", SALES_FIELDS, [
            [x["date"], x["product"], x["qty"], neat(x["price"]), neat(x["qty"] * x["price"]), x["order"]]
            for x in self.sales])

    def save_orders(self):
        self.write("orders.csv", ORDER_FIELDS, [
            [o["id"], o["order_date"], o["customer"], o["product"], o["qty"], neat(o["price"]),
             neat(o["qty"] * o["price"]), o["pickup"], o["status"]] for o in self.orders])

    def save_ingredients(self):
        self.write("ingredients.csv", INGREDIENT_FIELDS, [
            [i["name"], neat(i["qty"]), i["unit"], neat(i["reorder"])] for i in self.ingredients])

    # ------------------------------------------------------------------ calculations
    def sales_stats(self):
        """Quantity and money sold per product, and the number of days that have sales records."""
        stats = {name: {"qty": 0, "money": 0.0} for name in self.products}
        days = set()
        for s in self.sales:
            if s["product"] in stats:
                stats[s["product"]]["qty"] += s["qty"]
                stats[s["product"]]["money"] += s["qty"] * s["price"]
            days.add(s["date"])
        return stats, len(days)

    def order_counts(self):
        """How many orders each product has (cancelled orders are not counted)."""
        counts = dict.fromkeys(self.products, 0)
        for o in self.orders:
            if o["status"] != "Cancelled" and o["product"] in counts:
                counts[o["product"]] += 1
        return counts

    def make_plan(self, day, include_usual):
        """What to bake on `day`.

        pieces needed = usual daily sales (the average) + pending orders to pick up that day
        batches       = pieces needed divided by the pieces one batch makes, rounded UP
        ingredients   = batches x the amount one batch uses
        """
        stats, days = self.sales_stats()
        pending = defaultdict(int)
        for o in self.orders:
            if o["status"] == "Pending" and o["pickup"] == day:
                pending[o["product"]] += o["qty"]
        rows, need = [], dict.fromkeys(INGREDIENTS, 0.0)
        for name, p in self.products.items():
            usual = math.ceil(stats[name]["qty"] / days) if include_usual and days else 0
            needed = usual + pending[name]
            batches = math.ceil(needed / p["pieces"]) if needed else 0
            for ingredient, amount in zip(INGREDIENTS, p["recipe"]):
                need[ingredient] += batches * amount
            rows.append({"product": name, "usual": usual, "pending": pending[name], "needed": needed,
                         "batches": batches, "max": p["max_batches"]})
        return rows, need

    def ingredient_rows(self, need):
        """Each ingredient with what is needed, what is left afterwards, and a status."""
        rows = []
        for i in self.ingredients:
            needed = need.get(i["name"].lower(), 0.0)
            left = i["qty"] - needed
            status = "NOT ENOUGH" if left < 0 else ("Reorder soon" if left <= i["reorder"] else "OK")
            rows.append({"name": i["name"], "unit": i["unit"], "needed": needed, "have": i["qty"], "left": left,
                         "reorder": i["reorder"], "status": status})
        return rows

    # ------------------------------------------------------------------ widget helpers
    def table(self, parent, columns, widths, height=8, left=(), empty=None):
        """A table (Treeview) with a scroll bar. `columns` is a list of (key, heading).

        Numbers line up on the right; the columns named in `left` (and the first one) are text, on the left.
        """
        card = ui.Panel(parent, self.motion, self.scale, stretch=True, inset=5)  # a rounded card with a soft shadow
        card.configure(height=(height + 1) * int(24 * self.scale) + card.chrome())  # room for `height` rows at least
        card.pack(fill="both", expand=True, pady=4)
        frame = card.content
        tree = ttk.Treeview(frame, columns=[key for key, _ in columns], show="headings", height=height)
        for n, ((key, heading), width) in enumerate(zip(columns, widths)):
            tree.heading(key, text=heading)
            tree.column(key, width=int(width * self.scale), anchor="w" if n == 0 or key in left else "e")
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ui.hover_rows(tree)  # the row under the mouse lights up
        tree.empty_note = ttk.Label(frame, text=empty, style="Empty.TLabel") if empty else None  # shown when no rows
        return tree

    @staticmethod
    def put(parent, label, widget, column):
        """A small label above a box, placed in the given column of a form."""
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=0, column=column, sticky="w", padx=8)
        widget.grid(row=1, column=column, sticky="w", padx=2, pady=(0, 2))
        return widget

    @staticmethod
    def fill(tree, rows, tags=None):
        tree.delete(*tree.get_children())
        for n, row in enumerate(rows):
            tree.insert("", "end", values=row, tags=(tags[n],) if tags and tags[n] else ())
        note = getattr(tree, "empty_note", None)
        if note is not None:
            if rows:
                note.place_forget()
            else:
                note.place(relx=0.5, rely=0.5, anchor="center")

    def refresh_all(self, draw=True):
        self.refresh_overview()
        self.refresh_orders()
        self.refresh_sales()
        self.refresh_plan()
        self.refresh_inventory()
        self.refresh_report()
        if draw:
            self.draw_chart(self.chart_kind)

    # ================================================================== OVERVIEW (the first tab)
    def build_overview(self, tab):
        self.dash = ui.Dashboard(tab, self.motion, self.scale, date.today(), on_card=self.tabs.select,
                                 on_day=self.pick_day, on_open=self.open_plan)
        self.dash.pack(fill="both", expand=True)

    def week_of(self, day):
        """Seven days starting today (the days you can still bake for)."""
        return [day + timedelta(days=i) for i in range(7)]

    def focus_for(self, day):
        """What to say about baking on `day`: pieces, batches and the things that need attention."""
        rows, need = self.make_plan(str(day), True)
        lines = [f"{r['product']}: {r['batches']} batches needed, only {r['max']} fit in a day."
                 for r in rows if r["batches"] > r["max"]]
        for i in self.ingredient_rows(need):
            if i["status"] == "NOT ENOUGH":
                lines.append(f"Not enough {i['name'].lower()}: need {show(i['needed'])} {i['unit']}, have {show(i['have'])}.")
            elif i["status"] == "Reorder soon":
                lines.append(f"{i['name']} will run low after baking. Reorder soon.")
        if not lines:
            lines = ["Everything fits in one day and the ingredients are enough."]
        if len(lines) > 3:
            lines = lines[:3] + [f"...and {len(lines) - 3} more (see Production Plan)."]
        return {"day": day, "pieces": sum(r["needed"] for r in rows), "batches": sum(r["batches"] for r in rows),
                "lines": lines}

    def pick_day(self, day):
        self.dash.set_focus(self.focus_for(day))

    def open_plan(self, day):
        self.p_date.set(str(day))
        self.tabs.select(3)

    def refresh_overview(self, replay=False):
        """Give the Overview its numbers. With replay they count up from zero again."""
        stats, days = self.sales_stats()
        per_day = defaultdict(float)
        for sale in self.sales:
            per_day[sale["date"]] += sale["qty"] * sale["price"]
        pending = [o for o in self.orders if o["status"] == "Pending"]
        value = sum(o["qty"] * o["price"] for o in pending)
        low = [i["name"] for i in self.ingredient_rows({}) if i["have"] <= i["reorder"]]
        live = [o for o in self.orders if o["status"] != "Cancelled"]
        week = self.week_of(date.today())
        waiting_days = {o["pickup"] for o in pending}
        planned = parse_date(self.default_plan_date())
        selected = self.dash.selected if self.dash.data is not None else (planned if planned in week else date.today())
        self.dash.show({
            "sales": sum(x["money"] for x in stats.values()), "days": days,
            "best": max(stats, key=lambda n: stats[n]["money"]) if days else None,
            "spark": [per_day[d] for d in sorted(per_day)], "pending": len(pending),
            "pending_value": f"worth {peso(value)}" if pending else "nothing is waiting",
            "low": len(low), "low_names": ", ".join(low) if low else "everything is stocked",
            "done": sum(1 for o in live if o["status"] == "Completed") / len(live) if live else 0.0,
            "week": [str(d) in waiting_days for d in week], "selected": selected}, replay)
        self.dash.set_focus(self.focus_for(selected), replay)

    # ================================================================== ORDERS
    def build_orders(self, tab):
        card = ui.Panel(tab, self.motion, self.scale, "Add a new order  (type dates like 2026-10-20)")
        card.pack(fill="x")
        form = card.content
        self.o_customer, self.o_product = tk.StringVar(), tk.StringVar(value=next(iter(self.products), ""))
        self.o_qty, self.o_price = tk.StringVar(value="1"), tk.StringVar()
        self.o_date = tk.StringVar(value=str(date.today()))
        self.o_pickup = tk.StringVar(value=str(date.today() + timedelta(days=1)))
        self.o_total = tk.StringVar(value="Total: ₱0.00")
        name_box = self.put(form, "Customer name", ui.Entry(form, self.motion, textvariable=self.o_customer, width=17), 0)
        self.put(form, "Product", ui.Combo(form, self.motion, textvariable=self.o_product, values=list(self.products),
                                               state="readonly", width=12), 1)
        self.box_qty = self.put(form, "Quantity", ui.Entry(form, self.motion, textvariable=self.o_qty, width=6), 2)
        self.box_price = self.put(form, "Price (₱)", ui.Entry(form, self.motion, textvariable=self.o_price, width=7), 3)
        self.box_order = self.put(form, "Order date", ui.Entry(form, self.motion, textvariable=self.o_date, width=11), 4)
        self.box_pickup = self.put(form, "Pickup date", ui.Entry(form, self.motion, textvariable=self.o_pickup, width=11), 5)
        ttk.Label(form, textvariable=self.o_total, style="Total.TLabel").grid(row=1, column=6, padx=10)
        ui.Button(form, self.motion, "Add order", self.add_order, primary=True,
                  tip="Save this order to orders.csv").grid(row=1, column=7, padx=4)
        self.o_hint = ttk.Label(form, text="", style="Bad.TLabel")  # says what is wrong while you type
        self.o_hint.grid(row=2, column=0, columnspan=8, sticky="w", padx=4)
        self.o_hint.grid_remove()
        for box in (name_box, self.box_qty, self.box_price, self.box_order, self.box_pickup):
            box.bind("<Return>", lambda event: self.add_order())  # Enter saves the order
        self.o_product.trace_add("write", lambda *args: self.fill_price())  # picking a product fills in its usual price
        for var in (self.o_qty, self.o_price):
            var.trace_add("write", lambda *args: self.update_order_total())
        for var in (self.o_qty, self.o_price, self.o_date, self.o_pickup):
            var.trace_add("write", lambda *args: self.check_order_form())
        self.fill_price()  # the first product is already chosen, so its price is shown from the start
        self.check_order_form()

        # search / filter row: the table below follows these boxes as you type
        card = ui.Panel(tab, self.motion, self.scale)  # the table below follows what you type here
        card.pack(fill="x", pady=(4, 0))
        bar = card.content
        self.f_text, self.f_product = tk.StringVar(), tk.StringVar(value="All")
        self.f_status, self.f_from, self.f_to = tk.StringVar(value="All"), tk.StringVar(), tk.StringVar()
        self.f_datetype = tk.StringVar(value="Pickup date")
        self.put(bar, "Customer / order no.", ui.Entry(bar, self.motion, textvariable=self.f_text, width=16), 0)
        self.put(bar, "Product", ui.Combo(bar, self.motion, textvariable=self.f_product, state="readonly", width=12,
                                              values=["All"] + list(self.products)), 1)
        self.put(bar, "Status", ui.Combo(bar, self.motion, textvariable=self.f_status, state="readonly", width=11,
                                             values=["All"] + STATUSES), 2)
        self.put(bar, "Date to filter by", ui.Combo(bar, self.motion, textvariable=self.f_datetype, state="readonly", width=12,
                                                        values=["Pickup date", "Order date"]), 3)
        self.put(bar, "From", ui.Entry(bar, self.motion, textvariable=self.f_from, width=10), 4)
        self.put(bar, "To", ui.Entry(bar, self.motion, textvariable=self.f_to, width=10), 5)
        ui.Button(bar, self.motion, "Clear", self.clear_filters).grid(row=1, column=6, padx=8)
        for var in (self.f_text, self.f_product, self.f_status, self.f_datetype, self.f_from, self.f_to):
            var.trace_add("write", lambda *args: self.refresh_orders())

        self.order_table = self.table(tab, [("id", "Order no."), ("date", "Order date"), ("customer", "Customer"),
                                            ("product", "Product"), ("qty", "Qty"), ("total", "Total"),
                                            ("pickup", "Pickup date"), ("status", "Status")],
                                      [80, 90, 200, 110, 60, 100, 100, 90], height=3,
                                      left=("date", "customer", "product", "pickup", "status"),
                                      empty="No orders match what you typed. Press Clear to see every order.")
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x")
        self.order_info = ttk.Label(buttons, text="")
        self.order_info.pack(side="left")
        ui.Button(buttons, self.motion, "Cancel order", lambda: self.set_status("Cancelled"),
                  tip="A cancelled order is left out of the plan and the order value").pack(side="right")
        ui.Button(buttons, self.motion, "Mark completed", lambda: self.set_status("Completed"),
                  tip="The customer picked it up: it is added to today's sales").pack(side="right", padx=6)

    def fill_price(self):
        product = self.products.get(self.o_product.get())
        if product:
            self.o_price.set(str(neat(product["price"])))

    def check_order_form(self):
        """Colour a box red, with a message under the form, while what is typed in it cannot be saved."""
        order_date, pickup = parse_date(self.o_date.get()), parse_date(self.o_pickup.get())
        try:
            qty_ok = int(self.o_qty.get()) > 0
        except ValueError:
            qty_ok = False
        try:
            price_ok = float(self.o_price.get()) > 0
        except ValueError:
            price_ok = False
        pickup_ok = pickup is not None and pickup >= date.today() and (order_date is None or pickup >= order_date)
        checks = [(self.box_qty, qty_ok, "Quantity must be a whole number above 0."),
                  (self.box_price, price_ok, "Price must be a number above 0."),
                  (self.box_order, order_date is not None, "Order date must be written like 2026-10-16."),
                  (self.box_pickup, pickup_ok, "Pickup date must be today or later, and not before the order date.")]
        for box, ok, _ in checks:
            box.configure(style="TEntry" if ok else "Bad.TEntry")
        problems = [text for _, ok, text in checks if not ok]
        if problems:
            self.o_hint.configure(text=problems[0])
            self.o_hint.grid()
        else:
            self.o_hint.grid_remove()

    def update_order_total(self):
        try:
            qty, price = int(self.o_qty.get()), float(self.o_price.get())
        except ValueError:
            qty = price = 0
        self.o_total.set(f"Total: {peso(qty * price)}" if qty > 0 and price > 0 else "Total: ₱0.00")

    def add_order(self):
        customer, product = self.o_customer.get().strip(), self.o_product.get()
        order_date, pickup = parse_date(self.o_date.get()), parse_date(self.o_pickup.get())
        try:
            qty, price = int(self.o_qty.get()), float(self.o_price.get())
        except ValueError:
            qty = price = 0
        if not customer:
            return messagebox.showerror("Check the form", "Please type the customer name.")
        if product not in self.products:
            return messagebox.showerror("Check the form", "Please choose a product.")
        if qty <= 0:
            return messagebox.showerror("Check the form", "Quantity must be a whole number above 0.")
        if price <= 0:
            return messagebox.showerror("Check the form", "Price must be a number above 0.")
        if order_date is None:
            return messagebox.showerror("Check the form", "Order date must be written like 2026-10-16.")
        if pickup is None or pickup < date.today() or pickup < order_date:
            return messagebox.showerror("Check the form", "Pickup date must be today or later, and not before "
                                                          "the order date (like 2026-10-20).")
        number = max([int(o["id"].split("-")[1]) for o in self.orders], default=0) + 1
        order = {"id": f"ORD-{number:03d}", "order_date": str(order_date), "customer": customer,
                 "product": product, "qty": qty, "price": price, "pickup": str(pickup), "status": "Pending"}
        try:
            self.append("orders.csv", [order["id"], order["order_date"], customer, product, qty,
                                       neat(order["price"]), neat(qty * order["price"]), order["pickup"], "Pending"])
        except OSError as error:
            return messagebox.showerror("Cannot save", f"The order was not saved:\n{error}\n\n"
                                                       "If the file is open in Excel, close it and try again.")
        self.orders.append(order)
        self.o_customer.set("")
        self.o_qty.set("1")
        self.fill_price()  # back to the product's usual price for the next order
        self.refresh_all()
        self.flash_order(order["id"])
        self.toast(f"{order['id']} saved. Total: {peso(qty * order['price'])}")

    def flash_order(self, number):
        """Make the row of a just-saved order glow green for a moment, so you can see where it went."""
        for row in self.order_table.get_children():
            if self.order_table.item(row)["values"][0] == number:
                ui.flash_row(self.motion, self.order_table, row)

    def set_status(self, status):
        chosen = self.order_table.selection()
        if not chosen:
            return messagebox.showinfo("Select an order", "Click an order in the table first.")
        number = self.order_table.item(chosen[0])["values"][0]
        order = next(o for o in self.orders if o["id"] == number)
        old_status, order["status"], sales_before = order["status"], status, self.sales
        try:
            self.save_orders()
            note = self.update_sales_for(order, old_status)
        except OSError as error:
            order["status"], self.sales = old_status, sales_before  # nothing was saved, so undo it on screen too
            try:
                self.save_orders()  # (and put the orders file back, if it had already been changed)
            except OSError:
                pass
            return messagebox.showerror("Cannot save", f"The change was not saved:\n{error}\n\n"
                                                       "If the file is open in Excel, close it and try again.")
        self.refresh_all()
        self.toast(f"{number} marked as {status.lower()}{note}")

    def update_sales_for(self, order, old_status):
        """A completed order is a sale: it is added to the sales (dated today) when you complete it, and taken out
        again if you undo that, so it is never counted twice. Returns a few words for the note on screen."""
        linked = [x for x in self.sales if x["order"] == order["id"]]
        if order["status"] == "Completed" and old_status != "Completed" and not linked:
            sale = {"date": date.today(), "product": order["product"], "qty": order["qty"], "price": order["price"],
                    "order": order["id"]}
            self.append("daily_sales.csv", [sale["date"], sale["product"], sale["qty"], neat(sale["price"]),
                                            neat(sale["qty"] * sale["price"]), sale["order"]])
            self.sales = self.sales + [sale]  # (a new list, so a failure can put the old one back)
            return f". {peso(sale['qty'] * sale['price'])} added to sales"
        if old_status == "Completed" and order["status"] != "Completed" and linked:
            self.sales = [x for x in self.sales if x["order"] != order["id"]]
            self.save_sales()
            return ". Taken out of sales"
        return ""

    def clear_filters(self):
        self.f_text.set("")
        for var in (self.f_product, self.f_status):
            var.set("All")
        self.f_datetype.set("Pickup date")
        self.f_from.set("")
        self.f_to.set("")

    def refresh_orders(self):
        text = self.f_text.get().strip().lower()
        start, end = parse_date(self.f_from.get()), parse_date(self.f_to.get())
        key = "pickup" if self.f_datetype.get() == "Pickup date" else "order_date"  # which date the From/To use
        shown = []
        for o in self.orders:
            if text and text not in o["customer"].lower() and text not in o["id"].lower():
                continue
            if self.f_product.get() not in ("All", o["product"]) or self.f_status.get() not in ("All", o["status"]):
                continue
            if (start and o[key] < str(start)) or (end and o[key] > str(end)):
                continue
            shown.append(o)
        shown.sort(key=lambda o: (o["order_date"], o["id"]), reverse=True)
        self.fill(self.order_table, [(o["id"], o["order_date"], o["customer"], o["product"], o["qty"],
                                      peso(o["qty"] * o["price"]), o["pickup"], o["status"]) for o in shown],
                  [o["status"] for o in shown])
        value = sum(o["qty"] * o["price"] for o in shown if o["status"] != "Cancelled")
        self.order_info.config(text=f"{len(shown)} order(s) shown.  Value (not counting cancelled): {peso(value)}")

    # ================================================================== SALES
    def build_sales(self, tab):
        self.sales_table = self.table(tab, [("product", "Product"), ("qty", "Total qty sold"),
                                            ("money", "Total sales"), ("avg", "Average qty per day"),
                                            ("pq", "Pending order qty"), ("pv", "Pending order value"),
                                            ("orders", "Orders placed")],
                                      [140, 110, 120, 140, 120, 140, 100], height=3)
        ttk.Label(tab, text="Sales per day", style="Section.TLabel").pack(anchor="w", pady=(4, 0))
        self.day_table = self.table(tab, [("date", "Date"), ("pieces", "Pieces sold"), ("money", "Total sales")],
                                    [160, 140, 160], height=3)  # (the date is the first column, so it is on the left)
        card = ui.Panel(tab, self.motion, self.scale, "Record other sales  (completed orders are added by themselves)")
        card.pack(fill="x")
        form = card.content
        self.s_date, self.s_product = tk.StringVar(value=str(date.today())), tk.StringVar(value=next(iter(self.products), ""))
        self.s_qty = tk.StringVar(value="1")
        self.put(form, "Date (YYYY-MM-DD)", ui.Entry(form, self.motion, textvariable=self.s_date, width=14), 0)
        self.put(form, "Product", ui.Combo(form, self.motion, textvariable=self.s_product, values=list(self.products),
                                               state="readonly", width=16), 1)
        qty_box = self.put(form, "Quantity sold", ui.Entry(form, self.motion, textvariable=self.s_qty, width=8), 2)
        qty_box.bind("<Return>", lambda event: self.add_sales())
        ui.Button(form, self.motion, "Add sales record", self.add_sales, primary=True,
                  tip="Save these sales to daily_sales.csv").grid(row=1, column=3, padx=8)

    def add_sales(self):
        day, product = parse_date(self.s_date.get()), self.s_product.get()
        try:
            qty = int(self.s_qty.get())
        except ValueError:
            qty = 0
        if day is None:
            return messagebox.showerror("Check the form", "Type the date like 2026-10-05.")
        if product not in self.products:
            return messagebox.showerror("Check the form", "Please choose a product.")
        if qty <= 0:
            return messagebox.showerror("Check the form", "Quantity must be a whole number above 0.")
        price = self.products[product]["price"]
        try:
            self.append("daily_sales.csv", [day, product, qty, neat(price), neat(qty * price), ""])
        except OSError as error:
            return messagebox.showerror("Cannot save", f"The record was not saved:\n{error}")
        self.sales.append({"date": day, "product": product, "qty": qty, "price": price, "order": ""})
        self.s_qty.set("1")
        self.refresh_all()
        self.toast(f"Sales record added: {qty} {product} on {day}")

    def refresh_sales(self):
        stats, days = self.sales_stats()
        pending_qty, pending_value = defaultdict(int), defaultdict(float)
        for o in self.orders:
            if o["status"] == "Pending":
                pending_qty[o["product"]] += o["qty"]
                pending_value[o["product"]] += o["qty"] * o["price"]
        counts = self.order_counts()
        rows = [(name, f"{s['qty']:,}", peso(s["money"]), f"{s['qty'] / days:,.1f}" if days else "0",
                 pending_qty[name], peso(pending_value[name]), counts[name]) for name, s in stats.items()]
        rows.append(("TOTAL", f"{sum(s['qty'] for s in stats.values()):,}",
                     peso(sum(s["money"] for s in stats.values())),
                     f"{sum(s['qty'] for s in stats.values()) / days:,.1f}" if days else "0",
                     sum(pending_qty.values()), peso(sum(pending_value.values())), sum(counts.values())))
        self.fill(self.sales_table, rows, ["" for _ in rows[:-1]] + ["total"])
        per_day = defaultdict(lambda: [0, 0.0])
        for s in self.sales:
            per_day[s["date"]][0] += s["qty"]
            per_day[s["date"]][1] += s["qty"] * s["price"]
        self.fill(self.day_table, [(str(d), f"{q:,}", peso(m)) for d, (q, m) in sorted(per_day.items(), reverse=True)])

    # ================================================================== PRODUCTION PLAN
    def build_plan(self, tab):
        card = ui.Panel(tab, self.motion, self.scale)
        card.pack(fill="x")
        bar = card.content
        self.p_date = tk.StringVar(value=self.default_plan_date())
        self.p_usual = tk.BooleanVar(value=True)
        ttk.Label(bar, text="Bake for (YYYY-MM-DD):", style="Card.TLabel").pack(side="left")
        ui.Entry(bar, self.motion, textvariable=self.p_date, width=14).pack(side="left", padx=6)
        ttk.Checkbutton(bar, text="Include usual daily sales (average)", variable=self.p_usual,
                        style="Card.TCheckbutton").pack(side="left", padx=10)
        for var in (self.p_date, self.p_usual):
            var.trace_add("write", lambda *args: self.refresh_plan())
        ui.Button(bar, self.motion, "Bake it (use up the ingredients)", self.bake, primary=True,
                  tip="Takes the ingredients for this plan out of the Inventory").pack(side="right")
        self.plan_note = ttk.Label(tab, text="", style="Note.TLabel")
        self.plan_note.pack(anchor="w", pady=(6, 0))
        self.plan_table = self.table(tab, [("product", "Product"), ("usual", "Usual daily sales"),
                                           ("pending", "Pending orders"), ("needed", "Pieces needed"),
                                           ("batches", "Batches"), ("max", "Max batches / day"),
                                           ("check", "Capacity")],
                                     [150, 130, 120, 120, 90, 130, 150], height=4, left=("check",))
        ttk.Label(tab, text="Ingredients for this plan", style="Section.TLabel").pack(anchor="w")
        self.plan_ingredients = self.table(tab, [("name", "Ingredient"), ("needed", "Needed"), ("have", "On hand"),
                                                 ("left", "Left after baking"), ("status", "Status")],
                                           [150, 120, 120, 150, 140], height=4, left=("status",))

    def default_plan_date(self):
        """The nearest pickup date (today or later) that has a pending order; tomorrow if there is none."""
        today = str(date.today())
        dates = sorted(o["pickup"] for o in self.orders if o["status"] == "Pending" and o["pickup"] >= today)
        return dates[0] if dates else str(date.today() + timedelta(days=1))

    def refresh_plan(self):
        day = parse_date(self.p_date.get())
        if day is None:
            self.plan_note.config(text="Type the date like 2026-10-05.", foreground=ui.RED)
            self.fill(self.plan_table, [])
            self.fill(self.plan_ingredients, [])
            return
        rows, need = self.make_plan(str(day), self.p_usual.get())
        self.fill(self.plan_table, [(r["product"], r["usual"], r["pending"], r["needed"], r["batches"], r["max"],
                                     "OK" if r["batches"] <= r["max"] else f"OVER by {r['batches'] - r['max']}")
                                    for r in rows],
                  ["bad" if r["batches"] > r["max"] else "" for r in rows])
        ing = self.ingredient_rows(need)
        self.fill(self.plan_ingredients, [(i["name"], f"{show(i['needed'])} {i['unit']}", f"{show(i['have'])} {i['unit']}",
                                           f"{show(i['left'])} {i['unit']}", i["status"]) for i in ing],
                  ["bad" if i["status"] == "NOT ENOUGH" else "warn" if i["status"] != "OK" else "" for i in ing])
        total = sum(r["needed"] for r in rows)
        self.plan_note.config(text=f"Plan for {day}: {total:,} pieces in {sum(r['batches'] for r in rows)} batches.",
                              foreground=ui.GREEN)

    def bake(self):
        day = parse_date(self.p_date.get())
        if day is None:
            return messagebox.showerror("Check the date", "Type the date like 2026-10-05.")
        rows, need = self.make_plan(str(day), self.p_usual.get())
        if not any(r["batches"] for r in rows):
            return messagebox.showinfo("Nothing to bake", "There is nothing to bake for that date.")
        short = [i for i in self.ingredient_rows(need) if i["status"] == "NOT ENOUGH"]
        if short:
            names = ", ".join(i["name"] for i in short)
            return messagebox.showerror("Not enough ingredients", f"There is not enough: {names}.\n"
                                                                  "Restock on the Inventory tab first.")
        if not messagebox.askyesno("Bake it", "Use up the ingredients for this plan?"):
            return
        for i in self.ingredients:
            i["qty"] -= need[i["name"].lower()]
        try:
            self.save_ingredients()
        except OSError as error:
            for i in self.ingredients:  # not saved, so put the amounts back
                i["qty"] += need[i["name"].lower()]
            return messagebox.showerror("Cannot save", f"The change was not saved:\n{error}")
        self.refresh_all()
        self.toast("Baked! The ingredients were taken out of the inventory.")

    # ================================================================== INVENTORY (ingredients)
    def build_inventory(self, tab):
        self.inv_table = self.table(tab, [("name", "Ingredient"), ("qty", "On hand"), ("unit", "Unit"),
                                          ("reorder", "Reorder level"), ("status", "Status"),
                                          ("days", "Days left (at usual use)")],
                                    [150, 110, 80, 120, 130, 170], height=6, left=("unit", "status"))
        ttk.Label(tab, text="Days left = what you have divided by what the usual daily sales use up.",
                  style="Hint.TLabel").pack(anchor="w")
        card = ui.Panel(tab, self.motion, self.scale, "Restock")
        card.pack(fill="x", pady=(4, 0))
        form = card.content
        self.r_name, self.r_qty = tk.StringVar(value=self.ingredients[0]["name"] if self.ingredients else ""), tk.StringVar(value="1")
        self.put(form, "Ingredient", ui.Combo(form, self.motion, textvariable=self.r_name, state="readonly", width=16,
                                                  values=[i["name"] for i in self.ingredients]), 0)
        self.put(form, "Quantity to add", ui.Entry(form, self.motion, textvariable=self.r_qty, width=10), 1)
        ui.Button(form, self.motion, "Add stock", self.restock, primary=True,
                  tip="Add this amount to the ingredient's stock").grid(row=1, column=2, padx=8)

    def restock(self):
        try:
            amount = float(self.r_qty.get())
        except ValueError:
            amount = 0
        match = [i for i in self.ingredients if i["name"] == self.r_name.get()]
        if not match:
            return messagebox.showerror("Check the form", "Please choose an ingredient.")
        if amount <= 0:
            return messagebox.showerror("Check the form", "Quantity must be a number above 0.")
        match[0]["qty"] += amount
        try:
            self.save_ingredients()
        except OSError as error:
            match[0]["qty"] -= amount
            return messagebox.showerror("Cannot save", f"The change was not saved:\n{error}")
        self.r_qty.set("1")
        self.refresh_all()
        self.toast(f"Added {show(amount)} {match[0]['unit']} of {match[0]['name'].lower()}")

    def refresh_inventory(self):
        _, daily_need = self.make_plan("", True)  # what a normal day uses (no pending orders)
        rows = self.ingredient_rows({})
        self.fill(self.inv_table, [
            (i["name"], show(i["have"]), i["unit"], show(i["reorder"]), "Reorder" if i["have"] <= i["reorder"] else "OK",
             f"{i['have'] / daily_need[i['name'].lower()]:,.1f}" if daily_need.get(i["name"].lower()) else "-")
            for i in rows], ["warn" if i["have"] <= i["reorder"] else "" for i in rows])

    # ================================================================== REPORT
    def build_report(self, tab):
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        ttk.Label(bar, text="A summary of the orders and sales. Read it here or save it as a text file.",
                  style="Hint.TLabel").pack(side="left")
        ui.Button(bar, self.motion, "Save report as a text file", self.save_report, primary=True,
                  tip="Writes this report to a .txt file next to the data").pack(side="right")
        card = ui.Panel(tab, self.motion, self.scale, stretch=True, inset=6)
        card.configure(height=int(200 * self.scale))
        card.pack(fill="both", expand=True, pady=(4, 0))
        self.report = tk.Text(card.content, font=("Consolas", 10), wrap="none", height=20, bg=ui.WHITE, fg=ui.TEXT,
                              insertbackground=ui.TEXT, relief="flat", highlightthickness=0, padx=8, pady=6)
        self.report.pack(fill="both", expand=True)

    def report_text(self):
        stats, days = self.sales_stats()
        qty_total = sum(s["qty"] for s in stats.values())
        money_total = sum(s["money"] for s in stats.values())
        counts = {status: sum(1 for o in self.orders if o["status"] == status) for status in STATUSES}
        pending_value = sum(o["qty"] * o["price"] for o in self.orders if o["status"] == "Pending")
        per_day = defaultdict(float)
        for s in self.sales:
            per_day[s["date"]] += s["qty"] * s["price"]
        by_product = self.order_counts()
        top_ordered = max(by_product, key=by_product.get) if any(by_product.values()) else None
        lines = ["GMD BAKERY - SUMMARY REPORT", "=" * 60, f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "",
                 f"Orders: {len(self.orders)}   (Pending {counts['Pending']}, Completed {counts['Completed']}, "
                 f"Cancelled {counts['Cancelled']})", f"Value of pending orders: {peso(pending_value)}",
                 f"Most frequently ordered: {top_ordered} ({by_product[top_ordered]} "
                 f"order{'s' if by_product[top_ordered] != 1 else ''})" if top_ordered
                 else "Most frequently ordered: no orders yet", ""]
        if days:
            first, last = min(per_day), max(per_day)
            best, worst = max(per_day, key=per_day.get), min(per_day, key=per_day.get)
            lines += [f"Sales records: {first} to {last} ({days} days)",
                      f"Pieces sold: {qty_total:,}", f"Total sales: {peso(money_total)}",
                      f"Average per day: {peso(money_total / days)}",
                      f"Best day: {best} ({peso(per_day[best])})", f"Lowest day: {worst} ({peso(per_day[worst])})", "",
                      f"Most pieces sold: {max(stats, key=lambda n: stats[n]['qty'])}",
                      f"Highest sales: {max(stats, key=lambda n: stats[n]['money'])}", "",
                      f"{'Product':<16}{'Pieces':>9}{'Sales':>16}{'Share':>9}", "-" * 50]
            for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["money"]):
                share = s["money"] / money_total * 100 if money_total else 0
                lines.append(f"{name:<16}{s['qty']:>9,}{peso(s['money']):>16}{share:>8.1f}%")
        else:
            lines.append("No sales records yet.")
        low = [i["name"] for i in self.ingredients if i["qty"] <= i["reorder"]]
        lines += ["", "Ingredients to reorder: " + (", ".join(low) if low else "none")]
        return "\n".join(lines) + "\n"

    def refresh_report(self):
        self.report.config(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", self.report_text())
        self.report.config(state="disabled")

    def save_report(self):
        name = f"report_{datetime.now():%Y-%m-%d_%H%M%S}.txt"
        try:
            with open(self.path(name), "w", encoding="utf-8") as f:
                f.write(self.report_text())
        except OSError as error:
            return messagebox.showerror("Cannot save", f"The report was not saved:\n{error}")
        messagebox.showinfo("Saved", f"Saved as:\n{self.path(name)}")

    # ================================================================== CHARTS (Matplotlib)
    def build_charts(self, tab):
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        self.chart_kind, self.chart = "bar", None
        self.c_mode = tk.StringVar(value="Daily")
        self.chart_buttons = {}
        for text, kind in (("Bar: quantity sold per product", "bar"), ("Bar: orders per product", "orders"),
                           ("Line: sales trend", "line"), ("Pie: share of sales", "pie")):
            self.chart_buttons[kind] = ui.Button(bar, self.motion, text, lambda k=kind: self.draw_chart(k, animate=True))
            self.chart_buttons[kind].pack(side="left", padx=(0, 6))
        self.mode_buttons = []  # Daily / Weekly only matter for the line chart, so they are switched off otherwise
        for choice in ("Daily", "Weekly"):
            button = ttk.Radiobutton(bar, text=choice, variable=self.c_mode, value=choice,
                                     command=lambda: self.draw_chart("line", animate=True))
            button.pack(side="right", padx=4)
            self.mode_buttons.append(button)
        self.mode_label = ttk.Label(bar, text="Line chart:")
        self.figure = Figure(figsize=(8, 4.6), dpi=int(100 * self.scale))  # sharp on big-scale screens
        card = ui.Panel(tab, self.motion, self.scale, stretch=True, inset=6)
        card.configure(height=int(240 * self.scale))
        card.pack(fill="both", expand=True, pady=(4, 0))
        self.canvas = FigureCanvasTkAgg(self.figure, master=card.content)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def draw_chart(self, kind, animate=False):
        """Draw a chart (see charts.py). With animate it grows in: bars spring up, the line draws itself, the ring sweeps round."""
        self.motion.stop("chart")  # a chart that is still growing is replaced
        self.chart_kind = kind
        for name, button in self.chart_buttons.items():  # the button of the chart on screen is highlighted
            button.highlight(name == kind)
        for button in self.mode_buttons:
            button.state(["!disabled"] if kind == "line" else ["disabled"])
            if kind == "line":
                button.pack(side="right", padx=4)
            else:
                button.pack_forget()
        if kind == "line":
            self.mode_label.pack(side="right")
        else:
            self.mode_label.pack_forget()
        if self.chart is not None:
            self.chart.detach()
        stats, days = self.sales_stats()
        names = list(stats)
        colors = [ui.CHART[i % len(ui.CHART)] for i in range(len(names))]  # a product keeps its colour in every chart
        total_money, total_qty = sum(x["money"] for x in stats.values()), sum(x["qty"] for x in stats.values())
        figure, scale = self.figure, self.scale
        if kind == "orders":  # this chart is about the orders, not the sales records
            counts = self.order_counts()
            if any(counts.values()):
                chart = charts.BarChart(
                    figure, scale, "Number of orders per product", "Cancelled orders are not counted", names,
                    [counts[n] for n in names], colors,
                    [[n, f"{counts[n]} order{'s' if counts[n] != 1 else ''}"] for n in names])
            else:
                chart = charts.EmptyChart(figure, scale, "No orders yet")
        elif not days:
            chart = charts.EmptyChart(figure, scale, "No sales records yet")
        elif kind == "bar":
            chart = charts.BarChart(
                figure, scale, "Quantity sold per product", f"{days} days of sales  -  {total_qty:,} pieces in all", names,
                [stats[n]["qty"] for n in names], colors,
                [[n, f"{stats[n]['qty']:,} pieces", charts.money(stats[n]["money"])] for n in names])
        elif kind == "line":
            per_day = defaultdict(float)
            weekly = self.c_mode.get() == "Weekly"
            for s in self.sales:
                # weekly: every date is moved back to the Monday of its week
                key = s["date"] - timedelta(days=s["date"].weekday()) if weekly else s["date"]
                per_day[key] += s["qty"] * s["price"]
            keys = sorted(per_day)
            values = [per_day[k] for k in keys]
            average = sum(values) / len(values)
            chart = charts.LineChart(
                figure, scale, "Weekly sales (weeks start on Monday)" if weekly else "Daily sales",
                f"{keys[0]:%d %b} to {keys[-1]:%d %b}  -  average {charts.money(average)} a {'week' if weekly else 'day'}",
                [k.strftime("%b %d") for k in keys], values, [[k.strftime("%A, %d %B"), charts.money(v)] for k, v in zip(keys, values)],
                average, charts.money)
        else:
            moneys = [stats[n]["money"] for n in names]
            chart = charts.DonutChart(
                figure, scale, "Share of total sales", "How much money each product brought in", names, moneys, colors,
                charts.money(total_money), "total sales",
                [[f"{m / total_money * 100:.1f}%", charts.money(m)] for m in moneys])
        self.chart = chart
        chart.attach(self.canvas)
        if animate and ui.ANIMATE and chart.animated:
            chart.reset()
            ui.play_chart(self.motion, "chart", self.canvas, chart.ax, chart.frame, chart.finish, ms=chart.ms, ease=chart.ease)
        else:
            chart.finish()
            if self.tabs.names[self.tabs.current] == "Charts":
                self.canvas.draw()  # (a chart nobody can see is only drawn when its tab is opened)


if __name__ == "__main__":
    try:  # sharper text on high-resolution Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()
