"""A root sheet that reads as a block diagram: sheets in columns, wired to each other.

Sheets stand in columns; their pins face the gaps between columns. A net whose pins all face one
gap gets its own vertical track there and each pin runs straight across to it, so the wiring is
visible. A net whose pins face different gaps (a bus reaching both sides of a middle column) gets
a net label at each pin instead of a wire across the drawing.
"""
from __future__ import annotations

import collections, functools
from collections.abc import Mapping, Sequence
from typing import Literal

from .ids import stable
from .layout import Point
from .writer import _q, _wiring

PITCH = 2.54
Side = Literal["L", "R"]                    # which edge of the sheet a pin sits on


class Sheet:
    """One placement of a child sheet on the root."""

    def __init__(self, name: str, file: str, title: str, col: int, left: Sequence[str], right: Sequence[str],
                 nets: Mapping[str, str | None], auto: bool, page: int) -> None:
        self.name, self.file, self.title, self.col = name, file, title, col
        self.left, self.right = list(left), list(right)
        self.nets: dict[str, str | None] = dict(nets)
        self.auto, self.page = auto, page
        self.x = self.y = self.w = self.h = 0.0
        self.pin_at: dict[str, tuple[float, float, Side]] = {}

    def net(self, pin: str) -> str | None:
        """The design net a pin joins: as mapped, else the pin's own name; None leaves it unconnected."""
        return self.nets[pin] if pin in self.nets else pin

    def edges(self) -> tuple[tuple[Side, list[str]], tuple[Side, list[str]]]:
        return ("L", self.left), ("R", self.right)

    @property
    def uuid(self) -> str:
        return sheet_uuid(self.name)


class Column:
    def __init__(self, heading: str | None, width: float) -> None:
        self.heading, self.width = heading, width
        self.x = 0.0
        self.sheets: list[Sheet] = []


End = tuple[Sheet, str, Side]


class Root:
    """Build with column() and sheet(), then route(); write it with write_root()."""

    def __init__(self, paper: str = "A3", origin: Point = (25.4, 45.72), margin: float = 7.62, vgap: float = 12.7) -> None:
        self.paper, self.origin, self.margin, self.vgap = paper, origin, margin, vgap
        self.cols: list[Column] = []
        self.sheets: list[Sheet] = []
        self.texts: list[tuple[str, float, float, float]] = []
        self.paths: list[list[Point]] = []
        self.labels: list[tuple[str, Point, int]] = []
        self.nc: list[Point] = []
        self.problems: list[str] = []

    def column(self, heading: str | None = None, width: float = 63.5) -> int:
        self.cols.append(Column(heading, width))
        return len(self.cols) - 1

    def sheet(self, col: int, name: str, file: str, title: str, left: Sequence[str] = (), right: Sequence[str] = (),
              nets: Mapping[str, str | None] | None = None, auto: bool = False) -> Sheet:
        """Place a child sheet. `left` / `right` are its hierarchical label names, by edge.

        `nets` maps a pin to the design net it joins (default: its own name; None: no connect).
        `auto`: every pin goes to whichever edge its peers are on, ordered to run as straight as
        possible. For a hub, such as a processor module in the middle column.
        """
        s = Sheet(name, file, title, col, left, right, nets or {}, auto, len(self.sheets) + 2)
        self.sheets.append(s)
        self.cols[col].sheets.append(s)
        return s

    def text(self, s: str, x: float, y: float, size: float = 1.27) -> None:
        self.texts.append((s, x, y, size))

    def _ends(self) -> dict[str, list[End]]:
        ends: dict[str, list[End]] = collections.defaultdict(list)
        for s in self.sheets:
            for side, pins in s.edges():
                for p in pins:
                    n = s.net(p)
                    if n is not None:
                        ends[n].append((s, p, side))
        return ends

    def route(self) -> Root:
        # 1. hub sheets: each pin goes to the edge its peers are on
        ends = self._ends()
        for s in self.sheets:
            if s.auto:
                pins, s.left, s.right = s.left + s.right, [], []
                for p in pins:
                    n = s.net(p)
                    cols = {o.col for o, _, _ in ends.get(n, [])} - {s.col} if n is not None else set()
                    (s.right if cols and min(cols) > s.col else s.left).append(p)
        ends = self._ends()

        # 2. the gap each pin faces; one gap per net makes a track, more makes labels
        def gap(s: Sheet, side: Side) -> int:
            return s.col - 1 if side == "L" else s.col
        track: dict[int, list[str]] = collections.defaultdict(list)
        labelled: list[str] = []
        for net, es in ends.items():
            gaps = {gap(s, side) for s, _, side in es}
            if len(es) < 2:
                self.problems.append(f"{net}: only {es[0][0].name}.{es[0][1]} carries it")
                labelled.append(net)
            elif len(gaps) == 1:
                track[gaps.pop()].append(net)
            else:
                labelled.append(net)

        # 3. columns left to right, each gap as wide as its tracks and labels need
        label_gaps = {gap(s, side) for n in labelled for s, _, side in ends[n]}
        x = self.origin[0]
        for i, c in enumerate(self.cols):
            c.x = round(x / PITCH) * PITCH
            x = c.x + c.width + 2 * self.margin + max(len(track[i]) - 1, 0) * PITCH + (12.7 if i in label_gaps else 0)

        # 4. stack sheets. Pins sit on the 2.54 grid; odd columns are offset half a pitch so pins
        #    facing each other across a gap never share a row (a shared row would short two nets)
        def stack(ci: int) -> None:
            c, y = self.cols[ci], self.origin[1]
            for s in c.sheets:
                n = max(len(s.left), len(s.right), 1)
                s.x, s.y, s.w = c.x, round(y, 2), c.width
                s.h = round((n + 1) * PITCH + (PITCH if ci % 2 else 0), 2)
                off = PITCH * (1.5 if ci % 2 else 1)
                for side, pins in s.edges():
                    for i, p in enumerate(pins):
                        px = s.x if side == "L" else s.x + s.w
                        s.pin_at[p] = (round(px, 2), round(s.y + off + i * PITCH, 2), side)
                y = s.y + s.h + self.vgap

        def peer_y(s: Sheet, p: str) -> float:
            n = s.net(p)
            ys = [o.pin_at[q][1] for o, q, _ in ends.get(n, []) if o is not s and q in o.pin_at] if n is not None else []
            return min(ys, default=1e9)
        hubs = [i for i, c in enumerate(self.cols) if any(s.auto for s in c.sheets)]
        for ci in [i for i in range(len(self.cols)) if i not in hubs] + hubs:
            for s in self.cols[ci].sheets:
                if s.auto:                          # a hub's pins in the order of their peers
                    s.left.sort(key=functools.partial(peer_y, s))
                    s.right.sort(key=functools.partial(peer_y, s))
            stack(ci)

        # 5. tracks ordered by height, so wires cross as little as possible
        for g, nets in track.items():
            x0 = self.cols[g].x + self.cols[g].width + self.margin
            ys = {n: sorted(s.pin_at[p][1] for s, p, _ in ends[n]) for n in nets}
            for i, n in enumerate(sorted(nets, key=lambda n: (ys[n][0], ys[n][-1]))):
                tx = round(x0 + i * PITCH, 2)
                for s, p, _ in ends[n]:
                    px, py, _ = s.pin_at[p]
                    self.paths.append([(px, py), (tx, py)])
                self.paths.append([(tx, ys[n][0]), (tx, ys[n][-1])])
        for n in labelled:
            for s, p, side in ends[n]:
                px, py, _ = s.pin_at[p]
                ex = round(px + (5.08 if side == "R" else -5.08), 2)
                self.paths.append([(px, py), (ex, py)])
                self.labels.append((n, (ex, py), 0 if side == "R" else 180))
        for s in self.sheets:
            for p in s.left + s.right:
                if s.net(p) is None:
                    x, y, _ = s.pin_at[p]
                    self.nc.append((x, y))
        return self


def sheet_uuid(name: str) -> str:
    """The uuid of a placement on the root: what a child's instance path is built from."""
    return stable("root", "sheet", name)


def write_root(R: Root, path: str, *, version: str, generator_version: str, project: str, root_uuid: str, title: str,
               company: str = "", comments: Sequence[str] = (), generator: str = "kicad-sheetgen") -> None:
    """Write a routed Root. Child sheets are placed as `(path "/<root_uuid>/<sheet uuid>")`;
    pass the same paths to write_sheet(..., instances=...) for the symbols inside them."""
    def key(*k: object) -> str:
        return stable("root", *k)
    body: list[str] = []
    for s in R.sheets:
        pins: list[str] = []
        for p in s.left + s.right:
            x, y, side = s.pin_at[p]
            pins.append(f'\t\t(pin "{_q(p)}" passive\n\t\t\t(at {x} {y} {180 if side == "L" else 0})'
                        f'\n\t\t\t(effects (font (size 1.27 1.27)) (justify {"left" if side == "L" else "right"}))'
                        f'\n\t\t\t(uuid "{key("pin", s.name, p)}")\n\t\t)')
        body.append("\n".join([
            f'\t(sheet\n\t\t(at {s.x} {s.y})\n\t\t(size {s.w} {s.h})',
            '\t\t(stroke (width 0.1524) (type solid))\n\t\t(fill (color 0 0 0 0.0))',
            f'\t\t(uuid "{s.uuid}")',
            f'\t\t(property "Sheetname" "{_q(s.title)}"\n\t\t\t(at {s.x} {round(s.y - 0.71, 2)} 0)'
            '\n\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n\t\t)',
            f'\t\t(property "Sheetfile" "{_q(s.file)}"\n\t\t\t(at {s.x} {round(s.y + s.h + 0.6, 2)} 0)'
            '\n\t\t\t(effects (font (size 1.27 1.27)) (justify left top) (hide yes))\n\t\t)', *pins,
            f'\t\t(instances\n\t\t\t(project "{_q(project)}"\n\t\t\t\t(path "/{root_uuid}"\n\t\t\t\t\t(page "{s.page}")'
            '\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)']))
    pin_pts = [(s.pin_at[p][0], s.pin_at[p][1]) for s in R.sheets for p in s.left + s.right]
    body += _wiring(R.paths, pin_pts, [at for _, at, _ in R.labels], key)
    for n, (x, y), rot in R.labels:
        just = "left" if rot == 0 else "right"
        body.append(f'\t(label "{_q(n)}"\n\t\t(at {x} {y} {rot})\n\t\t(effects (font (size 1.27 1.27)) (justify {just} bottom))'
                    f'\n\t\t(uuid "{key("label", n, x, y)}")\n\t)')
    for x, y in R.nc:
        body.append(f'\t(no_connect (at {x} {y}) (uuid "{key("nc", x, y)}"))')
    for t, x, y, size in R.texts:
        body.append(f'\t(text "{_q(t)}"\n\t\t(exclude_from_sim no)\n\t\t(at {x} {y} 0)'
                    f'\n\t\t(effects (font (size {size} {size})) (justify left top))\n\t\t(uuid "{key("text", t, x, y)}")\n\t)')
    tb = f'\t(title_block\n\t\t(title "{_q(title)}")\n\t\t(company "{_q(company)}")'
    tb += "".join(f'\n\t\t(comment {i} "{_q(c)}")' for i, c in enumerate(comments, 1)) + "\n\t)"
    head = [f'(kicad_sch\n\t(version {version})\n\t(generator "{_q(generator)}")\n\t(generator_version "{_q(generator_version)}")',
            f'\t(uuid "{root_uuid}")\n\t(paper "{R.paper}")', tb, "\t(lib_symbols)"]
    tail = ['\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)']
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + body + tail) + "\n")
