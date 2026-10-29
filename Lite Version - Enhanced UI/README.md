# GMD Bakery — Order and Production Planner (enhanced UI)

A Python program for the bakery's orders, sales and baking plan. The data is kept in CSV files in `lite_data/`; this public copy ships with invented sample data
(the bakery's own data is not included). The charts are made with Matplotlib.

**This folder is the enhanced-UI copy.** It does the same things as the `Lite Version` folder (which is kept
unchanged as the simple backup); the look and the movement are new. There are three program files, keep them together:
- `bakery_lite.py` — **what the program does** (orders, sales, plan, inventory, reports)
- `ui_kit.py` — **how it looks and moves** (colours, pictures, cards, tabs, buttons, pop-ups, animations, light/dark)
- `charts.py` — **the three charts** (bars, line, donut), drawn with Matplotlib in the same style

It needs Python and `matplotlib`; Pillow and numpy are installed automatically together with it, so `run_lite.bat`
needs nothing extra.

## Light and dark
Press the round **sun/moon button** at the top right (or **Ctrl+D**). The whole window changes at once with a smooth
cross-fade (a picture of the old look dissolves into the new one), the title bar goes dark too, and the choice is
remembered in `lite_data/settings.json`. Every colour is a named role with a light and a dark value (see `THEMES` in
`ui_kit.py`); the text colours are checked for contrast in both.

## The look (inspired by phone home screens)
- **Overview** (opens first): a soft blue-grey gradient with a big *Today*, a progress ring (orders picked up), a
  **focus card** with the baking plan for the day you choose, three frosted-glass cards (total sales with a
  sparkline, orders waiting, ingredients to reorder) and a **7-day strip**. Click a day and the pill springs to it and the
  focus card shows that day's plan (a dot under a day means orders are waiting for pickup). The cards fly in one after
  another when the page opens, rise when you point at them, and a soft **spotlight follows the mouse** over them.
- **Clean and crisp ("HD")**: every rounded shape (cards, buttons, tabs, fields, icons, notes) is drawn as a smooth
  picture (drawn 4× bigger and shrunk, so no jagged edges) with a real blurred shadow.
- **Segmented tabs with line icons**: a pill springs under the tab you choose and the page slides in.
- **Pill buttons** that fade on hover and shrink a little when pressed; main buttons are black (white in dark mode).
  They work from the keyboard (Tab, then Space or Enter). Enter in the order form saves the order; Ctrl+1 … Ctrl+7 jump to a tab.
- **Rounded text fields** with a soft green ring while you type, and a red ring (with a message) when what you typed
  cannot be saved.
- **Pop-up dialogs** appear as a card over a blurred, dimmed copy of the window (like an iPhone alert) and spring into
  place; a success note slides up with a tick that draws itself; a newly saved order glows green for a moment.
- The line under the program name changes to say what the tab you are on is for. The bakery's logo (`GMD v2.jpg`) sits
  at the top left as a rounded tile (it stays white in dark mode, like an app icon).

## The charts
- **Bars** have rounded tops and a gradient, each product has its own colour (the same colour in every chart), the
  best seller is highlighted, and the bars spring up when the chart opens.
- **Line** is a smooth curve with a soft gradient under it, a dashed average, and the best day circled and labelled; it
  draws itself from left to right. Daily or weekly.
- **Donut** shows each product's share of the money with the total in the middle.
- Point at a bar, a day or a slice to see a tooltip (the donut swaps its middle to that product). A tooltip never gets
  cut off: near the first or last day of the line it opens to the right or the left of the point.
- Colours follow light/dark mode.

## About the speed
Animations run on a 60-frames-a-second timer that follows the clock (so each one always takes the same time) and the
program asks Windows for a 1 ms timer while it is open. Measured on a normal PC the animations ran at roughly 40-57
frames a second (tab slide, tab pill, card lift, chart growth, dialog and the light/dark cross-fade). Tkinter, the toolkit
the project is written in, cannot guarantee 60 on every screen.

To switch every animation off (the screens just snap and the plain Windows message boxes are used), set the
environment variable `GMD_NO_ANIMATION=1` before starting the program. `GMD_THEME=dark` starts in dark mode.

## How to run
1. Install Python from python.org (tick **Add python.exe to PATH**).
2. Double-click **run_lite.bat**. (The first time it installs `matplotlib`; that needs internet.)

Or, in a terminal: `pip install matplotlib` then `python bakery_lite.py`.

## Files
| File | What it is |
|---|---|
| `bakery_lite.py` | The program: the screens and all the calculations |
| `ui_kit.py` | The look and the animations (colours, light/dark, cards, buttons, tabs, pop-ups) |
| `charts.py` | The bar, line and donut charts |
| `GMD v2.jpg` | The bakery's logo, shown at the top left (keep it in this folder; without it a green "G" is shown instead) |
| `lite_data/products.csv` | Products: price, pieces per batch, recipe, max batches per day |
| `lite_data/ingredients.csv` | Ingredients on hand and reorder levels |
| `lite_data/daily_sales.csv` | 30 days of sales (1–30 September 2026); the last column, `order_id`, is empty for these and holds the order number for a sale that came from a completed order |
| `lite_data/orders.csv` | The customer orders |
| `lite_data/settings.json` | Made by the program: remembers light or dark |
| `excel_to_csv.py` | Made those four CSV files from the Excel file (needs `pip install openpyxl`) |

If Windows will not let Python save inside this folder, the program copies the four CSV files to
`C:\Users\<name>\AppData\Local\GMD-Bakery-Lite` and saves there instead.

## The tabs (and the requirement each one covers)
| Tab | What it does | Requirement |
|---|---|---|
| **Overview** | The bakery at a glance (see above) | — |
| **Orders** | Add an order: customer, product, quantity, **price** (fills in the product's usual price, but you can change it), **order date** and pickup date. Search by name or order number; filter by product, status and **order date or pickup date**; mark an order Completed or Cancelled (**Completed adds the order to today's sales**) | Add / View / Search orders |
| **Sales** | Total quantity and money per product, average per day, pending orders, **number of orders placed per product**, and sales for every day; record other sales by hand (completed orders are added by themselves) | Calculate sales, total orders, product quantities |
| **Production Plan** | For a date: pieces needed = usual daily sales + pending orders, then batches, a capacity check, and the ingredients needed. **Bake it** takes the ingredients out of the inventory | Production planning |
| **Inventory** | Ingredients on hand, Reorder / OK, days left; add stock | Inventory |
| **Reports** | A text summary, including the **most frequently ordered product**; can be saved as a `.txt` file | Generate reports |
| **Charts** | Bar (quantity sold per product), bar (**orders per product**), line (daily or weekly sales), donut (share of sales) with Matplotlib | Data visualization |

## How completed orders become sales
When the customer picks the order up and you press **Mark completed**, the order is added to the sales as one row
(its product, quantity and price, dated **today**) and the note on screen says how much was added. Every total, the
report, the Overview card and the charts use it straight away.
- It is counted **once**: pressing Mark completed again adds nothing.
- **Cancelled** (or back to **Pending**) takes that sale out again. Sales typed in by hand are never touched.
- Each such sale remembers its order number in the `order_id` column of `daily_sales.csv`, so it is still linked after
  the program is closed and opened again. An older `daily_sales.csv` without that column is upgraded automatically,
  with all its rows kept as they were.
- The orders that were already completed in the Excel file (before the program) are **not** added: the Excel sales
  already include them, so counting them again would double the money.
- If a file cannot be saved (for example it is open in Excel), a message says so and **nothing changes**: the order
  keeps its old status and no sale is added or removed.
- A completed order dated today is a new sales day, so the "usual daily sales" (total ÷ number of days) changes a little.

## How the production plan is worked out
- **Usual daily sales** = total pieces sold ÷ number of days, rounded up (for example Pandesal 9,745 ÷ 30 → 325).
- **Pieces needed** = usual daily sales + pending orders for that pickup date.
- **Batches** = pieces needed ÷ pieces per batch, rounded **up** (525 Pandesal ÷ 80 → 7 batches).
- **Capacity**: if the batches are more than the maximum per day, it says `OVER by …`.
- **Ingredients** = batches × the amount one batch uses. `Left after baking` below the reorder level shows
  *Reorder soon*, and below zero shows *NOT ENOUGH*.

## Where each part is in the code
| Part | File | Names to look for |
|---|---|---|
| Reading and saving CSV files | `bakery_lite.py` | `read`, `write`, `append`, `load_data`, `save_orders`, `save_sales`, `save_ingredients`, `upgrade_sales_file` |
| Calculations | `bakery_lite.py` | `sales_stats`, `order_counts`, `make_plan`, `ingredient_rows`, `focus_for` |
| Overview tab | `bakery_lite.py` | `build_overview`, `refresh_overview`, `pick_day`, `open_plan` |
| Orders tab | `bakery_lite.py` | `build_orders`, `fill_price`, `check_order_form`, `add_order`, `set_status`, `update_sales_for` (completed order → sale), `refresh_orders` |
| Sales tab | `bakery_lite.py` | `build_sales`, `add_sales`, `refresh_sales` |
| Production Plan tab | `bakery_lite.py` | `build_plan`, `refresh_plan`, `bake` |
| Inventory tab | `bakery_lite.py` | `build_inventory`, `restock`, `refresh_inventory` |
| Reports tab | `bakery_lite.py` | `report_text`, `save_report` |
| Charts tab | `bakery_lite.py` | `build_charts`, `draw_chart` |
| Light / dark | `bakery_lite.py`, `ui_kit.py` | `switch_theme`, `style_tables`; `THEMES`, `set_theme`, `recolor`, `restyle_all`, `Veil` |
| The three charts | `charts.py` | `BarChart`, `LineChart`, `DonutChart`, `EmptyChart` |
| Animation engine | `ui_kit.py` | `Motion` (every animation goes through it), `spring`, `ease_out` |
| Smooth pictures (shapes, shadows, glass, icons) | `ui_kit.py` | `mask`, `shape`, `card_picture`, `glass_picture`, `icon_picture`, `ring_picture` |
| Overview drawing | `ui_kit.py` | `Dashboard` |
| Cards, tabs, buttons, fields | `ui_kit.py` | `Surface`, `Panel`, `Tabs`, `Button`, `Entry`, `Combo`, `Header` |
| Pop-ups and notes | `ui_kit.py` | `Sheet`, `Messages`, `Toast`, `Tooltip` |
| Colours and fonts | `ui_kit.py` | `apply_style`, `font` |
