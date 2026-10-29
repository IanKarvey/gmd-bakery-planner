"""The charts of the GMD Bakery program (Matplotlib), styled like the rest of the program.

bakery_lite.py works out the numbers and hands them to make(); this file only draws.

  BarChart    rounded bars with a gradient, one colour per product, the best one highlighted
  LineChart   a smooth curve with a soft gradient under it, the average marked, the best point called out
  DonutChart  a ring with the total in the middle (hover a slice to see its share)

Every chart:  - uses the current light/dark colours (ui_kit),
              - can grow in (frame / finish), played by ui_kit.play_chart,
              - shows a small tooltip when you point at a bar, a point or a slice (attach / detach).
"""
import numpy as np
import matplotlib
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.path import Path
from matplotlib.text import Annotation
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib.transforms import ScaledTranslation

import ui_kit as ui


def _pick_font():
    for name in ("Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            return name
        except ValueError:
            continue
    return "DejaVu Sans"


matplotlib.rcParams["font.family"] = _pick_font()


# ------------------------------------------------------------------ small drawing helpers
def gradient(top, bottom, alpha_top=1.0, alpha_bottom=1.0, rows=96):
    """A column of colour that fades from `top` to `bottom` (a picture one pixel wide)."""
    t = np.linspace(0, 1, rows)[:, None]
    image = np.zeros((rows, 1, 4))
    image[:, 0, :3] = (np.array(ui.rgb(top)) / 255) * (1 - t) + (np.array(ui.rgb(bottom)) / 255) * t
    image[:, 0, 3] = alpha_top * (1 - t[:, 0]) + alpha_bottom * t[:, 0]
    return image


def smooth(values, steps=10):
    """Points on a smooth curve that passes through every value (Catmull-Rom), as two arrays x and y."""
    points = np.asarray(values, float)
    n = len(points)
    if n < 3:
        return np.arange(n, dtype=float), points
    padded = np.concatenate([[2 * points[0] - points[1]], points, [2 * points[-1] - points[-2]]])
    xs, ys = [], []
    for i in range(n - 1):
        p0, p1, p2, p3 = padded[i:i + 4]
        for s in range(steps):
            t = s / steps
            ys.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                             + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
            xs.append(i + t)
    xs.append(n - 1)
    ys.append(points[-1])
    return np.array(xs), np.clip(np.array(ys), points.min() * 0.0, None)


def bar_path(x0, x1, height, rx, ry):
    """A bar whose top corners are rounded (rx and ry are the corner size in data units)."""
    height = max(height, 1e-9)
    ry, rx = min(ry, height / 2), min(rx, (x1 - x0) / 2)
    vertices = [(x0, 0), (x0, height - ry), (x0, height), (x0 + rx, height), (x1 - rx, height), (x1, height),
                (x1, height - ry), (x1, 0), (x0, 0)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO,
             Path.CLOSEPOLY]
    return Path(vertices, codes)


def tip(ax, size=9):
    """A dark rounded label for hovering (it is drawn separately, so moving it never redraws the chart)."""
    note = Annotation("", xy=(0, 0), xytext=(0, 16), textcoords="offset points", ha="center", va="bottom", fontsize=size,
                      multialignment="center", color=ui.ink(ui.PRIMARY), zorder=30, animated=True, visible=False,
                      annotation_clip=False, clip_on=False,  # (clip_on=False: it may reach outside the plot area)
                      bbox=dict(boxstyle="round,pad=0.55,rounding_size=0.7", fc=ui.PRIMARY, ec="none"))
    ax.add_artist(note)
    return note


def place_tip(note, fraction, gap, edge=0.14):
    """Keep a label inside the chart. `fraction` is where the point sits from left (0) to right (1): within `edge` of the
    left side the label grows to the right of the point, within `edge` of the right side to the left, otherwise it is centred."""
    if fraction < edge:
        note.set_ha("left")
        offset = -14
    elif fraction > 1 - edge:
        note.set_ha("right")
        offset = 14
    else:
        note.set_ha("center")
        offset = 0
    note.set_position((offset, gap))


class Chart:
    """Common to all charts: the clean look, the title, and the pointing (hover) machinery."""
    ms, animated = 800, True

    @staticmethod
    def ease(t):
        return ui.ease_out(t)

    def __init__(self, figure, scale, title, subtitle, margins=(0.07, 0.97, 0.13, 0.80)):
        self.figure, self.scale = figure, scale
        figure.clear()
        figure.patch.set_facecolor(ui.WHITE)
        self.ax = ax = figure.add_subplot(111)
        left, right, bottom, top = margins
        figure.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
        ax.set_facecolor(ui.WHITE)
        for name, spine in ax.spines.items():
            spine.set_visible(name == "bottom")
            spine.set_color(ui.LINE)
        ax.tick_params(length=0, colors=ui.MUTED, labelsize=9)
        ax.set_axisbelow(True)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=ui.TEXT, pad=38)
        figure.text(0, 1, subtitle, transform=ax.transAxes + ScaledTranslation(0, 17 / 72, figure.dpi_scale_trans),
                    fontsize=9.5, color=ui.MUTED, va="bottom", ha="left")
        self.canvas, self.bg, self.cids, self.busy, self.live = None, None, [], False, []

    # --- playing (growing in)
    def reset(self):
        """Put the chart in its starting state (nothing drawn yet)."""
        self.busy = True
        self.frame(0.0)

    def frame(self, t):
        return []

    def finish(self):
        self.busy = False

    # --- pointing
    def attach(self, canvas):
        self.canvas = canvas
        self.cids = [canvas.mpl_connect("draw_event", self._saved), canvas.mpl_connect("motion_notify_event", self._moved),
                     canvas.mpl_connect("axes_leave_event", self._left)]

    def detach(self):
        for cid in self.cids:
            self.canvas.mpl_disconnect(cid)
        self.cids = []

    def _saved(self, event):
        self.bg = self.canvas.copy_from_bbox(self.figure.bbox)

    def _moved(self, event):
        if self.busy or self.bg is None or event.inaxes is not self.ax:
            return
        if self.hover(event):
            self._paint()

    def _left(self, event):
        if not self.busy and self.bg is not None and self.hover(None):
            self._paint()

    def _paint(self):
        self.canvas.restore_region(self.bg)
        for artist in self.live:
            if artist.get_visible():
                self.ax.draw_artist(artist)
        self.canvas.blit(self.figure.bbox)

    def hover(self, event):
        """Show or hide the tooltip for the mouse position; returns True if anything changed."""
        return False


# ------------------------------------------------------------------ bars
class BarChart(Chart):
    ms = 850

    @staticmethod
    def ease(t):
        return ui.spring(t)  # the bars shoot up a little past their height and settle

    def __init__(self, figure, scale, title, subtitle, names, values, colors, details):
        super().__init__(figure, scale, title, subtitle)
        ax, n = self.ax, len(values)
        self.names, self.values, self.colors, self.details = list(names), list(values), list(colors), list(details)
        self.best = int(np.argmax(values))
        self.top, self.width, self.hot = max(values) * 1.24, 0.52, None
        ax.set_xlim(-0.6, n - 0.4)
        ax.set_ylim(0, self.top)
        # the invisible bars hold the numbers (and are what the mouse points at); the pretty bars are drawn over them
        self.rects = list(ax.bar(range(n), values, width=self.width, facecolor="none", edgecolor="none"))
        ax.set_xticks(range(n))
        ax.set_xticklabels(names, fontsize=10, color=ui.MUTED)
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.grid(True, color=ui.LINE, linewidth=1, linestyle=(0, (2, 4)))
        ax.tick_params(axis="y", labelleft=False)
        self.rx, self.ry = self._corner()
        self.images = []
        for i, value in enumerate(values):
            x0, x1 = i - self.width / 2, i + self.width / 2
            picture = ax.imshow(gradient(ui.mix(colors[i], ui.WHITE, 0.30), colors[i]), extent=(x0, x1, 0, value),
                                aspect="auto", origin="upper", zorder=3, alpha=1.0 if i == self.best else 0.72)
            picture.set_clip_path(bar_path(x0, x1, value, self.rx, self.ry), ax.transData)  # (cuts the picture to a rounded bar)
            self.images.append(picture)
        ax.set_xlim(-0.6, n - 0.4)
        ax.set_ylim(0, self.top)
        ax.set_aspect("auto")
        self.labels = []
        for i, value in enumerate(values):
            best = i == self.best
            self.labels.append(ax.annotate(
                f"{value:,}", (i, value), xytext=(0, 7), textcoords="offset points", ha="center", va="bottom",
                fontsize=10, fontweight="bold", color=ui.ink(ui.PRIMARY) if best else ui.TEXT, zorder=6,
                bbox=dict(boxstyle="round,pad=0.38,rounding_size=0.8", fc=ui.PRIMARY, ec="none") if best else None))
        self.glow = ax.imshow(gradient("#ffffff", "#ffffff", 0.34, 0.08), extent=(0, 1, 0, 1), aspect="auto", origin="upper",
                              zorder=4, animated=True, visible=False)
        self.glow.set_clip_path(bar_path(0, 1, 1, 0, 0), ax.transData)
        ax.set_xlim(-0.6, n - 0.4)
        ax.set_ylim(0, self.top)
        ax.set_aspect("auto")
        self.note = tip(ax)
        self.live = [self.glow, self.note]

    def attach(self, canvas):
        super().attach(canvas)
        self.cids.append(canvas.mpl_connect("resize_event", lambda event: self._rescale()))  # (the corners keep their shape)

    def _corner(self):
        """The size of a rounded corner in data units (about 9 pixels, whatever the shape of the chart)."""
        box = self.ax.get_window_extent()
        px = 9 * self.scale
        return px * (self.ax.get_xlim()[1] - self.ax.get_xlim()[0]) / max(1, box.width), px * self.top / max(1, box.height)

    def _rescale(self):
        self.rx, self.ry = self._corner()
        self._shape(self.last if hasattr(self, "last") else 1.0)

    def _shape(self, t):
        self.last = t
        for i, value in enumerate(self.values):
            height = max(value * t, 1e-9)
            x0, x1 = i - self.width / 2, i + self.width / 2
            self.rects[i].set_height(value * t)
            self.images[i].set_clip_path(bar_path(x0, x1, height, self.rx, self.ry), self.ax.transData)
            self.images[i].set_extent((x0, x1, 0, height))

    def frame(self, t):
        self._shape(t)
        for label in self.labels:
            label.set_visible(False)
        return self.images

    def finish(self):
        self._shape(1.0)
        for label in self.labels:
            label.set_visible(True)
        super().finish()

    def hover(self, event):
        hot = None
        if event is not None and event.xdata is not None:
            i = int(round(event.xdata))
            if 0 <= i < len(self.values) and abs(event.xdata - i) <= self.width / 2 and 0 <= event.ydata <= self.values[i] * 1.0:
                hot = i
        if hot == self.hot:
            return False
        self.hot = hot
        if hot is None:
            self.glow.set_visible(False)
            self.note.set_visible(False)
        else:
            x0, x1 = hot - self.width / 2, hot + self.width / 2
            self.glow.set_clip_path(bar_path(x0, x1, self.values[hot], self.rx, self.ry), self.ax.transData)
            self.glow.set_extent((x0, x1, 0, self.values[hot]))
            self.note.xy = (hot, self.values[hot])
            self.note.set_text("\n".join(self.details[hot]))
            place_tip(self.note, (hot + 0.5) / len(self.values), 34, edge=0.07)  # (a bar's label is short: it stays centred)
            self.glow.set_visible(True)
            self.note.set_visible(True)
        return True


# ------------------------------------------------------------------ line
class LineChart(Chart):
    ms = 1200

    @staticmethod
    def ease(t):
        return ui.ease_in_out(t)

    def __init__(self, figure, scale, title, subtitle, labels, values, details, average, y_title):
        super().__init__(figure, scale, title, subtitle, margins=(0.07, 0.97, 0.14, 0.80))
        ax, n = self.ax, len(values)
        self.labels, self.values, self.details = list(labels), list(values), list(details)
        color, self.hot = ui.GREEN, None
        top = max(values) * 1.25
        ax.set_xlim(-0.4, n - 0.6)
        ax.set_ylim(0, top)
        # lines[0] is the real data (small dots); lines[1] is the smooth curve through it
        self.dots = ax.plot(range(n), values, linestyle="none", marker="o", markersize=4, color=color, alpha=0.85, zorder=5)[0]
        self.sx, self.sy = smooth(values)
        self.curve = ax.plot(self.sx, self.sy, color=color, linewidth=2.6, solid_capstyle="round", zorder=4)[0]
        self.area = ax.imshow(gradient(color, color, 0.34, 0.0), extent=(-0.4, n - 0.6, 0, top), aspect="auto", origin="upper", zorder=2)
        ax.set_xlim(-0.4, n - 0.6)
        ax.set_ylim(0, top)
        ax.set_aspect("auto")
        ax.axhline(average, color=ui.MUTED, linewidth=1, linestyle=(0, (4, 4)), zorder=1, alpha=0.7)
        self.average = ax.add_artist(Annotation(f"average  {y_title(average)}", xy=(n - 0.6, average), xytext=(0, 5),
                                                textcoords="offset points", ha="right", va="bottom", fontsize=8.5,
                                                color=ui.MUTED, annotation_clip=False))
        best = int(np.argmax(values))
        self.peak = Line2D([best], [values[best]], marker="o", markersize=9, markerfacecolor=ui.WHITE, markeredgecolor=color,
                           markeredgewidth=2.4, zorder=7, linestyle="none")
        ax.add_line(self.peak)
        self.peak_label = ax.add_artist(Annotation(y_title(values[best]), xy=(best, values[best]), xytext=(0, 12),
                                                   textcoords="offset points", ha="center", va="bottom", fontsize=9.5,
                                                   fontweight="bold", color=ui.ink(ui.PRIMARY), zorder=8, annotation_clip=False,
                                                   clip_on=False,
                                                   bbox=dict(boxstyle="round,pad=0.38,rounding_size=0.8", fc=ui.PRIMARY, ec="none")))
        place_tip(self.peak_label, best / max(1, n - 1), 12)  # (even if the best day is the first or the last)
        step = max(1, n // 10)
        ax.set_xticks(range(0, n, step))
        ax.set_xticklabels([labels[i] for i in range(0, n, step)], fontsize=9, color=ui.MUTED)
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: y_title(v, short=True)))
        ax.yaxis.grid(True, color=ui.LINE, linewidth=1, linestyle=(0, (2, 4)))
        self.guide = Line2D([0, 0], [0, top], color=ui.MUTED, linewidth=1, linestyle=(0, (2, 3)), zorder=6, animated=True, visible=False)
        ax.add_line(self.guide)
        self.spot = Line2D([0], [0], marker="o", markersize=10, markerfacecolor=ui.WHITE, markeredgecolor=color, markeredgewidth=2.6,
                           linestyle="none", zorder=9, animated=True, visible=False)
        ax.add_line(self.spot)
        self.note = tip(ax)
        self.live = [self.guide, self.spot, self.note]
        self.y_title = y_title
        self.top = top
        self.finish()

    def _reveal(self, t):
        n = len(self.values)
        reach = t * (n - 1)
        index, part = int(reach), reach - int(reach)
        xs, ys = list(range(index + 1)), list(self.values[:index + 1])
        if index < n - 1:
            xs.append(index + part)
            ys.append(self.values[index] + (self.values[index + 1] - self.values[index]) * part)
        self.dots.set_data(xs, ys)
        cut = int(np.searchsorted(self.sx, reach, side="right"))
        cx, cy = list(self.sx[:cut]), list(self.sy[:cut])
        if cut < len(self.sx):
            frac = (reach - self.sx[cut - 1]) / max(1e-9, self.sx[cut] - self.sx[cut - 1]) if cut else 0
            cx.append(reach)
            cy.append((self.sy[cut - 1] + (self.sy[cut] - self.sy[cut - 1]) * frac) if cut else self.sy[0])
        self.curve.set_data(cx, cy)
        polygon = [(cx[0], 0)] + list(zip(cx, cy)) + [(cx[-1], 0)] if cx else [(0, 0)] * 3
        self.area.set_clip_path(Path(polygon + [polygon[0]], [Path.MOVETO] + [Path.LINETO] * (len(polygon) - 1) + [Path.CLOSEPOLY]),
                                self.ax.transData)  # (the gradient shows only under the part of the curve drawn so far)

    def frame(self, t):
        self._reveal(t)
        for artist in (self.peak, self.peak_label, self.average):
            artist.set_visible(False)
        return [self.area, self.curve, self.dots]

    def finish(self):
        self._reveal(1.0)
        for artist in (self.peak, self.peak_label, self.average):
            artist.set_visible(True)
        super().finish()

    def hover(self, event):
        hot = None
        if event is not None and event.xdata is not None:
            hot = min(max(int(round(event.xdata)), 0), len(self.values) - 1)
        if hot == self.hot:
            return False
        self.hot = hot
        if hot is None:
            for artist in self.live:
                artist.set_visible(False)
        else:
            value = self.values[hot]
            self.guide.set_data([hot, hot], [0, self.top])
            self.spot.set_data([hot], [value])
            self.note.xy = (hot, value)
            self.note.set_text("\n".join(self.details[hot]))
            place_tip(self.note, hot / max(1, len(self.values) - 1), 18)
            for artist in self.live:
                artist.set_visible(True)
        return True


# ------------------------------------------------------------------ donut
class DonutChart(Chart):
    ms = 950

    def __init__(self, figure, scale, title, subtitle, names, values, colors, total_text, caption, details):
        super().__init__(figure, scale, title, subtitle, margins=(0.07, 0.66, 0.06, 0.80))
        ax = self.ax
        self.names, self.values, self.colors, self.details = list(names), list(values), list(colors), list(details)
        self.hot = None
        for spine in ax.spines.values():
            spine.set_visible(False)
        wedges, _, percents = ax.pie(values, colors=colors, startangle=90, autopct="%1.0f%%", pctdistance=0.82,
                                     wedgeprops={"width": 0.36, "linewidth": 3, "edgecolor": ui.WHITE},
                                     textprops={"fontsize": 9.5, "fontweight": "bold"})
        self.wedges, self.percents = list(wedges), list(percents)
        for text, color in zip(self.percents, colors):
            text.set_color(ui.ink(color))
        self.angles = [(w.theta1, w.theta2) for w in self.wedges]
        ax.set_aspect("equal")
        ax.set_anchor("W")  # the ring sits under the title, not in the middle of the empty space
        self.total = ax.add_artist(Annotation(total_text, xy=(0, 0.07), ha="center", va="center", fontsize=17, fontweight="bold",
                                              color=ui.TEXT, animated=True))
        self.caption = ax.add_artist(Annotation(caption, xy=(0, -0.2), ha="center", va="center", fontsize=9.5, color=ui.MUTED,
                                                animated=True))
        self.hot_name = ax.add_artist(Annotation("", xy=(0, 0.14), ha="center", va="center", fontsize=12, fontweight="bold",
                                                 color=ui.TEXT, animated=True, visible=False))
        self.hot_text = ax.add_artist(Annotation("", xy=(0, -0.14), ha="center", va="center", fontsize=10, color=ui.MUTED,
                                                 animated=True, visible=False))
        self.ring = Line2D([], [], linewidth=5, solid_capstyle="round", alpha=0.35, animated=True, visible=False)  # (an arc around the slice)
        ax.add_line(self.ring)
        handles = [Line2D([0], [0], marker="o", linestyle="none", markersize=10, markerfacecolor=c, markeredgecolor="none",
                          label=f"{name}    {detail[1]}") for name, c, detail in zip(names, colors, details)]
        legend = ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.12, 0.5), frameon=False, fontsize=10.5,
                           labelspacing=1.1, handletextpad=0.6, borderaxespad=0)
        for text in legend.get_texts():
            text.set_color(ui.TEXT)
        self.live = [self.total, self.caption, self.ring, self.hot_name, self.hot_text]
        self.finish()

    def frame(self, t):
        limit = self.angles[0][0] + 360 * t
        for wedge, (low, high) in zip(self.wedges, self.angles):
            wedge.set_theta2(max(low, min(high, limit)))
        for text in self.percents:
            text.set_visible(False)
        self.total.set_visible(False)
        self.caption.set_visible(False)
        return self.wedges

    def finish(self):
        for wedge, (low, high) in zip(self.wedges, self.angles):
            wedge.set_theta2(high)
        for text in self.percents:
            text.set_visible(True)
        self.total.set_visible(True)
        self.caption.set_visible(True)
        super().finish()

    def _saved(self, event):
        super()._saved(event)
        self._paint()  # (the centre text is drawn separately, so it has to be drawn once after every full redraw)

    def hover(self, event):
        hot = None
        if event is not None:
            for i, wedge in enumerate(self.wedges):
                if wedge.contains(event)[0]:
                    hot = i
                    break
        if hot == self.hot:
            return False
        self.hot = hot
        if hot is None:
            self.ring.set_visible(False)
            self.hot_name.set_visible(False)
            self.hot_text.set_visible(False)
            self.total.set_visible(True)
            self.caption.set_visible(True)
        else:
            low, high = self.angles[hot]
            angle = np.radians(np.linspace(low + 1.5, high - 1.5, 80))
            self.ring.set_data(1.1 * np.cos(angle), 1.1 * np.sin(angle))
            self.ring.set_color(self.colors[hot])
            self.hot_name.set_text(self.names[hot])
            self.hot_text.set_text("   ·   ".join(self.details[hot]))
            for artist in (self.ring, self.hot_name, self.hot_text):
                artist.set_visible(True)
            self.total.set_visible(False)
            self.caption.set_visible(False)
        return True


# ------------------------------------------------------------------ nothing to draw
class EmptyChart(Chart):
    animated = False

    def __init__(self, figure, scale, message):
        figure.clear()
        figure.patch.set_facecolor(ui.WHITE)
        self.figure, self.ax = figure, figure.add_subplot(111)
        self.ax.text(0.5, 0.5, message, ha="center", va="center", color=ui.MUTED, fontsize=12)
        self.ax.axis("off")
        self.canvas, self.bg, self.cids, self.busy, self.live = None, None, [], False, []

    def attach(self, canvas):
        self.canvas = canvas

    def detach(self):
        pass


def money(value, short=False):
    if short:
        return f"₱{value / 1000:,.0f}k" if value >= 1000 else f"₱{value:,.0f}"
    return f"₱{value:,.0f}"
