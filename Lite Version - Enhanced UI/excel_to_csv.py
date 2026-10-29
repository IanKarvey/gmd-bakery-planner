"""Turns the bakery's Excel file into the CSV files that bakery_lite.py uses.

Run:   python excel_to_csv.py
Needs: pip install openpyxl      (only for this one-time conversion; the program itself does not need it)

Excel sheet                       ->  CSV file
Product Recipes + Capacity        ->  lite_data/products.csv
Ingredient Inventory              ->  lite_data/ingredients.csv
Daily Sales                       ->  lite_data/daily_sales.csv
Orders                            ->  lite_data/orders.csv
(The 'Sales Summary' sheet is not copied: the program calculates it from the daily sales.)
"""
import csv
import datetime
import os
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
EXCEL = os.path.join(HERE, "GMDioknoBAKES_Data.xlsx")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "lite_data")


def clean(value):
    """Dates become YYYY-MM-DD, and 5.0 becomes 5."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 4)
    return "" if value is None else value


def read_sheet(book, name):
    """All the filled-in rows of a sheet, without the header row."""
    rows = book[name].iter_rows(min_row=2, values_only=True)
    return [[clean(v) for v in row] for row in rows if any(v is not None for v in row)]


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


# data_only=True gives the calculated values instead of the Excel formulas
book = openpyxl.load_workbook(EXCEL, data_only=True)
os.makedirs(OUT, exist_ok=True)
print("Reading", EXCEL)

recipes = read_sheet(book, "Product Recipes")
max_batches = {row[0]: row[1] for row in read_sheet(book, "Capacity")}
write_csv("products.csv",
          ["product", "flour", "sugar", "butter", "eggs", "yeast", "pieces_per_batch", "price", "max_batches"],
          [row[:8] + [max_batches[row[0]]] for row in recipes])
write_csv("ingredients.csv", ["ingredient", "qty_on_hand", "unit", "reorder_level"],
          [row[:4] for row in read_sheet(book, "Ingredient Inventory")])
write_csv("daily_sales.csv", ["date", "product", "qty_sold", "unit_price", "total_sales", "order_id"],
          [row + [""] for row in read_sheet(book, "Daily Sales")])  # order_id stays empty: these sales are not from orders
write_csv("orders.csv",
          ["order_id", "order_date", "customer", "product", "qty", "unit_price", "total", "pickup_date", "status"],
          read_sheet(book, "Orders"))
print("Done. Files are in", OUT)
