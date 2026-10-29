"""GMD Bakery - Order and Production Planner (simple version)

Run:  python bakery_lite.py

What the program does (the features in the project requirements):
    Orders ......... add, view, search/filter and update customer orders
    Sales .......... total sales per product and per day (from the daily sales records)
    Production ..... how many pieces and batches to bake for a date, and the ingredients needed
    Inventory ...... ingredients on hand, reorder status, restock
    Reports ........ a text summary that can be saved to a file
    Charts ......... bar, line and pie charts (Matplotlib)

All data is kept in CSV files (folder "lite_data"). This public copy ships with invented sample data;
excel_to_csv.py can import a bakery's own Excel workbook in the same layout.
"""
import csv
import math
import os
import shutil
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

HERE = os.path.dirname(os.path.abspath(__file__))
GREEN = "#175f27"
STATUSES = ["Pending", "Completed", "Cancelled"]
INGREDIENTS = ["flour", "sugar", "butter", "eggs", "yeast"]  # the order of the columns in products.csv

PRODUCT_FIELDS = ["product"] + INGREDIENTS + ["pieces_per_batch", "price", "max_batches"]
INGREDIENT_FIELDS = ["ingredient", "qty_on_hand", "unit", "reorder_level"]
SALES_FIELDS = ["date", "product", "qty_sold", "unit_price", "total_sales"]
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
        self.title("GMD Bakery - Order and Production Planner")
        # screen scaling (100%, 125%, 150%...): the fixed sizes below are multiplied by it so nothing is cut off
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96)
        width = min(int(1050 * self.scale), self.winfo_screenwidth() - 40)
        height = min(int(690 * self.scale), self.winfo_screenheight() - 90)
        self.geometry(f"{width}x{height}")
        self.minsize(min(width, int(950 * self.scale)), min(height, int(620 * self.scale)))

        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(bg=style.lookup("TFrame", "background"))  # same grey as the tabs, so the title blends in
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground=GREEN)
        style.configure("Treeview", rowheight=int(24 * self.scale))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        ttk.Label(self, text="GMD Bakery - Order and Production Planner", style="Title.TLabel").pack(
            anchor="w", padx=12, pady=(10, 4))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        try:
            self.load_data()
        except (OSError, KeyError, ValueError) as error:  # a file is missing or was changed so it can't be read
            messagebox.showerror("Cannot read the data files",
                                 f"Folder: {self.folder}\n\nProblem: {error}\n\nCheck that products.csv and "
                                 "ingredients.csv are there and that no CSV file was changed by hand.")
            self.destroy()
            raise SystemExit(1)
        for name, build in [("Orders", self.build_orders), ("Sales", self.build_sales),
                            ("Production Plan", self.build_plan), ("Inventory", self.build_inventory),
                            ("Reports", self.build_report), ("Charts", self.build_charts)]:
            page = ttk.Frame(self.tabs, padding=10)
            self.tabs.add(page, text=name)
            build(page)
        self.tabs.bind("<<NotebookTabChanged>>", lambda event: self.refresh_all())
        self.refresh_all()

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
        self.products = {}  # name -> recipe, pieces per batch, price, max batches per day
        for r in self.read("products.csv"):
            self.products[r["product"]] = {
                "recipe": [float(r[i]) for i in INGREDIENTS], "pieces": int(float(r["pieces_per_batch"])),
                "price": float(r["price"]), "max_batches": int(float(r["max_batches"]))}
        self.ingredients = [{"name": r["ingredient"], "qty": float(r["qty_on_hand"]), "unit": r["unit"],
                             "reorder": float(r["reorder_level"])} for r in self.read("ingredients.csv")]
        self.sales = [{"date": parse_date(r["date"]), "product": r["product"], "qty": int(float(r["qty_sold"])),
                       "price": float(r["unit_price"])} for r in self.read("daily_sales.csv")]
        self.orders = [{"id": r["order_id"], "order_date": r["order_date"], "customer": r["customer"],
                        "product": r["product"], "qty": int(float(r["qty"])), "price": float(r["unit_price"]),
                        "pickup": r["pickup_date"], "status": r["status"]} for r in self.read("orders.csv")]

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
    def table(self, parent, columns, widths, height=8, left=()):
        """A table (Treeview) with a scroll bar. `columns` is a list of (key, heading).

        Numbers line up on the right; the columns named in `left` (and the first one) are text, on the left.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=6)
        tree = ttk.Treeview(frame, columns=[key for key, _ in columns], show="headings", height=height)
        for n, ((key, heading), width) in enumerate(zip(columns, widths)):
            tree.heading(key, text=heading)
            tree.column(key, width=int(width * self.scale), anchor="w" if n == 0 or key in left else "e")
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    @staticmethod
    def put(parent, label, widget, column):
        """A small label above a box, placed in the given column of a form."""
        ttk.Label(parent, text=label).grid(row=0, column=column, sticky="w", padx=4)
        widget.grid(row=1, column=column, sticky="w", padx=4, pady=(0, 2))

    @staticmethod
    def fill(tree, rows, tags=None):
        tree.delete(*tree.get_children())
        for n, row in enumerate(rows):
            tree.insert("", "end", values=row, tags=(tags[n],) if tags and tags[n] else ())

    def refresh_all(self):
        self.refresh_orders()
        self.refresh_sales()
        self.refresh_plan()
        self.refresh_inventory()
        self.refresh_report()
        self.draw_chart(self.chart_kind)

    # ================================================================== ORDERS
    def build_orders(self, tab):
        form = ttk.LabelFrame(tab, text="New order  (dates are written YYYY-MM-DD)", padding=8)
        form.pack(fill="x")
        self.o_customer, self.o_product = tk.StringVar(), tk.StringVar()
        self.o_qty, self.o_price = tk.StringVar(value="1"), tk.StringVar()
        self.o_date = tk.StringVar(value=str(date.today()))
        self.o_pickup = tk.StringVar(value=str(date.today() + timedelta(days=1)))
        self.o_total = tk.StringVar(value="Total: ₱0.00")
        self.put(form, "Customer name", ttk.Entry(form, textvariable=self.o_customer, width=22), 0)
        self.put(form, "Product", ttk.Combobox(form, textvariable=self.o_product, values=list(self.products),
                                               state="readonly", width=14), 1)
        self.put(form, "Quantity", ttk.Entry(form, textvariable=self.o_qty, width=7), 2)
        self.put(form, "Price (₱)", ttk.Entry(form, textvariable=self.o_price, width=8), 3)
        self.put(form, "Order date", ttk.Entry(form, textvariable=self.o_date, width=12), 4)
        self.put(form, "Pickup date", ttk.Entry(form, textvariable=self.o_pickup, width=12), 5)
        ttk.Label(form, textvariable=self.o_total, font=("Segoe UI", 10, "bold")).grid(row=1, column=6, padx=10)
        ttk.Button(form, text="Add order", command=self.add_order).grid(row=1, column=7, padx=4)
        self.o_product.trace_add("write", lambda *args: self.fill_price())  # picking a product fills in its usual price
        for var in (self.o_qty, self.o_price):
            var.trace_add("write", lambda *args: self.update_order_total())

        # search / filter row: the table below follows these boxes as you type
        bar = ttk.LabelFrame(tab, text="Search", padding=8)
        bar.pack(fill="x", pady=(8, 0))
        self.f_text, self.f_product = tk.StringVar(), tk.StringVar(value="All")
        self.f_status, self.f_from, self.f_to = tk.StringVar(value="All"), tk.StringVar(), tk.StringVar()
        self.f_datetype = tk.StringVar(value="Pickup date")
        self.put(bar, "Customer / order no.", ttk.Entry(bar, textvariable=self.f_text, width=20), 0)
        self.put(bar, "Product", ttk.Combobox(bar, textvariable=self.f_product, state="readonly", width=14,
                                              values=["All"] + list(self.products)), 1)
        self.put(bar, "Status", ttk.Combobox(bar, textvariable=self.f_status, state="readonly", width=11,
                                             values=["All"] + STATUSES), 2)
        self.put(bar, "Date to filter by", ttk.Combobox(bar, textvariable=self.f_datetype, state="readonly", width=12,
                                                        values=["Pickup date", "Order date"]), 3)
        self.put(bar, "From", ttk.Entry(bar, textvariable=self.f_from, width=11), 4)
        self.put(bar, "To", ttk.Entry(bar, textvariable=self.f_to, width=11), 5)
        ttk.Button(bar, text="Clear", command=self.clear_filters).grid(row=1, column=6, padx=8)
        for var in (self.f_text, self.f_product, self.f_status, self.f_datetype, self.f_from, self.f_to):
            var.trace_add("write", lambda *args: self.refresh_orders())

        self.order_table = self.table(tab, [("id", "Order no."), ("date", "Order date"), ("customer", "Customer"),
                                            ("product", "Product"), ("qty", "Qty"), ("total", "Total"),
                                            ("pickup", "Pickup date"), ("status", "Status")],
                                      [80, 90, 200, 110, 60, 100, 100, 90], height=9,
                                      left=("date", "customer", "product", "pickup", "status"))
        self.order_table.tag_configure("Pending", background="#fff6d6")
        self.order_table.tag_configure("Cancelled", foreground="#999999")
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x")
        self.order_info = ttk.Label(buttons, text="")
        self.order_info.pack(side="left")
        ttk.Button(buttons, text="Cancel order", command=lambda: self.set_status("Cancelled")).pack(side="right")
        ttk.Button(buttons, text="Mark completed", command=lambda: self.set_status("Completed")).pack(
            side="right", padx=6)

    def fill_price(self):
        product = self.products.get(self.o_product.get())
        if product:
            self.o_price.set(str(neat(product["price"])))

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
        messagebox.showinfo("Saved", f"{order['id']} saved. Total: {peso(qty * order['price'])}")

    def set_status(self, status):
        chosen = self.order_table.selection()
        if not chosen:
            return messagebox.showinfo("Select an order", "Click an order in the table first.")
        number = self.order_table.item(chosen[0])["values"][0]
        order = next(o for o in self.orders if o["id"] == number)
        old_status, order["status"] = order["status"], status
        try:
            self.save_orders()
        except OSError as error:
            order["status"] = old_status  # the file was not changed, so undo it on screen too
            return messagebox.showerror("Cannot save", f"The change was not saved:\n{error}\n\n"
                                                       "If the file is open in Excel, close it and try again.")
        self.refresh_all()

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
                                      [140, 110, 120, 140, 120, 140, 100], height=5)
        self.sales_table.tag_configure("total", background="#e7f1e1")
        ttk.Label(tab, text="Sales per day", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.day_table = self.table(tab, [("date", "Date"), ("pieces", "Pieces sold"), ("money", "Total sales")],
                                    [160, 140, 160], height=5)  # (the date is the first column, so it is on the left)
        form = ttk.LabelFrame(tab, text="Record sales", padding=8)
        form.pack(fill="x")
        self.s_date, self.s_product = tk.StringVar(value=str(date.today())), tk.StringVar()
        self.s_qty = tk.StringVar(value="1")
        self.put(form, "Date (YYYY-MM-DD)", ttk.Entry(form, textvariable=self.s_date, width=14), 0)
        self.put(form, "Product", ttk.Combobox(form, textvariable=self.s_product, values=list(self.products),
                                               state="readonly", width=16), 1)
        self.put(form, "Quantity sold", ttk.Entry(form, textvariable=self.s_qty, width=8), 2)
        ttk.Button(form, text="Add sales record", command=self.add_sales).grid(row=1, column=3, padx=8)

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
            self.append("daily_sales.csv", [day, product, qty, neat(price), neat(qty * price)])
        except OSError as error:
            return messagebox.showerror("Cannot save", f"The record was not saved:\n{error}")
        self.sales.append({"date": day, "product": product, "qty": qty, "price": price})
        self.s_qty.set("1")
        self.refresh_all()

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
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        self.p_date = tk.StringVar(value=self.default_plan_date())
        self.p_usual = tk.BooleanVar(value=True)
        ttk.Label(bar, text="Bake for (YYYY-MM-DD):").pack(side="left")
        ttk.Entry(bar, textvariable=self.p_date, width=14).pack(side="left", padx=6)
        ttk.Checkbutton(bar, text="Include usual daily sales (average)", variable=self.p_usual).pack(
            side="left", padx=10)
        for var in (self.p_date, self.p_usual):
            var.trace_add("write", lambda *args: self.refresh_plan())
        ttk.Button(bar, text="Bake it (use up the ingredients)", command=self.bake).pack(side="right")
        self.plan_note = ttk.Label(tab, text="", foreground=GREEN)
        self.plan_note.pack(anchor="w", pady=(6, 0))
        self.plan_table = self.table(tab, [("product", "Product"), ("usual", "Usual daily sales"),
                                           ("pending", "Pending orders"), ("needed", "Pieces needed"),
                                           ("batches", "Batches"), ("max", "Max batches / day"),
                                           ("check", "Capacity")],
                                     [150, 130, 120, 120, 90, 130, 150], height=6, left=("check",))
        self.plan_table.tag_configure("bad", foreground="#b3261e")
        ttk.Label(tab, text="Ingredients for this plan", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.plan_ingredients = self.table(tab, [("name", "Ingredient"), ("needed", "Needed"), ("have", "On hand"),
                                                 ("left", "Left after baking"), ("status", "Status")],
                                           [150, 120, 120, 150, 140], height=6, left=("status",))
        self.plan_ingredients.tag_configure("bad", foreground="#b3261e")
        self.plan_ingredients.tag_configure("warn", foreground="#9a6200")

    def default_plan_date(self):
        """The nearest pickup date (today or later) that has a pending order; tomorrow if there is none."""
        today = str(date.today())
        dates = sorted(o["pickup"] for o in self.orders if o["status"] == "Pending" and o["pickup"] >= today)
        return dates[0] if dates else str(date.today() + timedelta(days=1))

    def refresh_plan(self):
        day = parse_date(self.p_date.get())
        if day is None:
            self.plan_note.config(text="Type the date like 2026-10-05.", foreground="#b3261e")
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
                              foreground=GREEN)

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
        messagebox.showinfo("Done", "The ingredients were taken out of the inventory.")

    # ================================================================== INVENTORY (ingredients)
    def build_inventory(self, tab):
        self.inv_table = self.table(tab, [("name", "Ingredient"), ("qty", "On hand"), ("unit", "Unit"),
                                          ("reorder", "Reorder level"), ("status", "Status"),
                                          ("days", "Days left (at usual use)")],
                                    [150, 110, 80, 120, 130, 170], height=8, left=("unit", "status"))
        self.inv_table.tag_configure("warn", foreground="#9a6200")
        ttk.Label(tab, text="Days left = what you have divided by what the usual daily sales use up.").pack(anchor="w")
        form = ttk.LabelFrame(tab, text="Restock", padding=8)
        form.pack(fill="x", pady=10)
        self.r_name, self.r_qty = tk.StringVar(), tk.StringVar(value="1")
        self.put(form, "Ingredient", ttk.Combobox(form, textvariable=self.r_name, state="readonly", width=16,
                                                  values=[i["name"] for i in self.ingredients]), 0)
        self.put(form, "Quantity to add", ttk.Entry(form, textvariable=self.r_qty, width=10), 1)
        ttk.Button(form, text="Add stock", command=self.restock).grid(row=1, column=2, padx=8)

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
        ttk.Button(bar, text="Save report as a text file", command=self.save_report).pack(side="right")
        self.report = tk.Text(tab, font=("Consolas", 10), wrap="none", height=20)
        self.report.pack(fill="both", expand=True, pady=(8, 0))

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
        self.chart_kind = "bar"
        self.c_mode = tk.StringVar(value="Daily")
        for text, kind in (("Bar: quantity sold per product", "bar"), ("Bar: orders per product", "orders"),
                           ("Line: sales trend", "line"), ("Pie: share of sales", "pie")):
            ttk.Button(bar, text=text, command=lambda k=kind: self.draw_chart(k)).pack(side="left", padx=(0, 6))
        self.mode_buttons = []  # Daily / Weekly only matter for the line chart, so they are switched off otherwise
        for choice in ("Daily", "Weekly"):
            button = ttk.Radiobutton(bar, text=choice, variable=self.c_mode, value=choice,
                                     command=lambda: self.draw_chart("line"))
            button.pack(side="right", padx=4)
            self.mode_buttons.append(button)
        ttk.Label(bar, text="Line chart:").pack(side="right")
        self.figure = Figure(figsize=(8, 4.6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=8)

    def draw_chart(self, kind):
        self.chart_kind = kind
        for button in self.mode_buttons:
            button.state(["!disabled"] if kind == "line" else ["disabled"])
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        stats, days = self.sales_stats()
        names = list(stats)
        if kind == "orders":  # this chart is about the orders, not the sales records
            counts = self.order_counts()
            if any(counts.values()):
                bars = ax.bar(list(counts), list(counts.values()), color=GREEN)
                ax.bar_label(bars, padding=3)
                ax.set_title("Number of orders per product (cancelled orders not counted)")
                ax.set_ylabel("Orders")
            else:
                ax.text(0.5, 0.5, "No orders yet", ha="center", va="center")
                ax.axis("off")
        elif not days:
            ax.text(0.5, 0.5, "No sales records yet", ha="center", va="center")
            ax.axis("off")
        elif kind == "bar":
            bars = ax.bar(names, [stats[n]["qty"] for n in names], color=GREEN)
            ax.bar_label(bars, padding=3)
            ax.set_title("Quantity sold per product")
            ax.set_ylabel("Pieces")
        elif kind == "line":
            per_day = defaultdict(float)
            for s in self.sales:
                # weekly: every date is moved back to the Monday of its week
                key = s["date"] - timedelta(days=s["date"].weekday()) if self.c_mode.get() == "Weekly" else s["date"]
                per_day[key] += s["qty"] * s["price"]
            keys = sorted(per_day)
            ax.plot([k.strftime("%b %d") for k in keys], [per_day[k] for k in keys], marker="o", color=GREEN)
            ax.set_title(f"{self.c_mode.get()} sales (week starts on Monday)" if self.c_mode.get() == "Weekly"
                         else "Daily sales")
            ax.set_ylabel("Sales (PHP)")
            ax.grid(alpha=0.3)
            ax.tick_params(axis="x", rotation=60)
            step = max(1, len(keys) // 12)
            for n, label in enumerate(ax.get_xticklabels()):
                label.set_visible(n % step == 0)
        else:
            ax.pie([stats[n]["money"] for n in names], labels=names, autopct="%1.1f%%", startangle=90)
            ax.set_title("Share of total sales")
        self.figure.tight_layout()
        self.canvas.draw()


if __name__ == "__main__":
    try:  # sharper text on high-resolution Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()
