# GMD Bakery — Order and Production Planner (simple version)

One Python file, `bakery_lite.py`. The data is kept in CSV files in `lite_data/`; this public copy ships with
invented sample data (the bakery's own data is not included). `excel_to_csv.py` can import an Excel workbook in the same layout.

## How to run
1. Install Python from python.org (tick **Add python.exe to PATH**).
2. Double-click **run_lite.bat**. (The first time it installs `matplotlib`; that needs internet.)

Or, in a terminal: `pip install matplotlib` then `python bakery_lite.py`.

## Files
| File | What it is |
|---|---|
| `bakery_lite.py` | The whole program |
| `lite_data/products.csv` | Products: price, pieces per batch, recipe, max batches per day |
| `lite_data/ingredients.csv` | Ingredients on hand and reorder levels |
| `lite_data/daily_sales.csv` | 30 days of sales (1–30 September 2026) |
| `lite_data/orders.csv` | The customer orders |
| `excel_to_csv.py` | Made those four CSV files from the Excel file (needs `pip install openpyxl`) |

If Windows will not let Python save inside this folder, the program copies the four CSV files to
`C:\Users\<name>\AppData\Local\GMD-Bakery-Lite` and saves there instead.

## The tabs (and the requirement each one covers)
| Tab | What it does | Requirement |
|---|---|---|
| **Orders** | Add an order: customer, product, quantity, **price** (fills in the product's usual price, but you can change it), **order date** and pickup date. Search by name or order number; filter by product, status and **order date or pickup date**; mark an order Completed or Cancelled | Add / View / Search orders |
| **Sales** | Total quantity and money per product, average per day, pending orders, **number of orders placed per product**, and sales for every day; record new sales | Calculate sales, total orders, product quantities |
| **Production Plan** | For a date: pieces needed = usual daily sales + pending orders, then batches, a capacity check, and the ingredients needed. **Bake it** takes the ingredients out of the inventory | Production planning |
| **Inventory** | Ingredients on hand, Reorder / OK, days left; add stock | Inventory |
| **Reports** | A text summary, including the **most frequently ordered product**; can be saved as a `.txt` file | Generate reports |
| **Charts** | Bar (quantity sold per product), bar (**orders per product**), line (daily or weekly sales), pie (share of sales) with Matplotlib | Data visualization |

## How the production plan is worked out
- **Usual daily sales** = total pieces sold ÷ number of days, rounded up (for example Pandesal 9,745 ÷ 30 → 325).
- **Pieces needed** = usual daily sales + pending orders for that pickup date.
- **Batches** = pieces needed ÷ pieces per batch, rounded **up** (525 Pandesal ÷ 80 → 7 batches).
- **Capacity**: if the batches are more than the maximum per day, it says `OVER by …`.
- **Ingredients** = batches × the amount one batch uses. `Left after baking` below the reorder level shows
  *Reorder soon*, and below zero shows *NOT ENOUGH*.

## Where each part is in the code
| Part | Names to look for |
|---|---|
| Reading and saving CSV files | `read`, `write`, `append`, `load_data`, `save_orders`, `save_ingredients` |
| Calculations | `sales_stats`, `order_counts`, `make_plan`, `ingredient_rows` |
| Orders tab | `build_orders`, `fill_price`, `add_order`, `set_status`, `refresh_orders` |
| Sales tab | `build_sales`, `add_sales`, `refresh_sales` |
| Production Plan tab | `build_plan`, `refresh_plan`, `bake` |
| Inventory tab | `build_inventory`, `restock`, `refresh_inventory` |
| Reports tab | `report_text`, `save_report` |
| Charts tab | `build_charts`, `draw_chart` |
