"""A sheet described in code: parts placed by hand, joined by real wires."""


def xform(px, py, rot, mirror=None):
    """Symbol-library pin offset -> schematic offset. Library y points up, schematic y down."""
    x, y = px, -py
    for _ in range(int(rot) // 90 % 4):         # schematic rotation is counter-clockwise on screen
        x, y = y, -x
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    return round(x, 2), round(y, 2)


class Layout:
    """Everything one sheet holds, in schematic millimetres.

    `parts` maps a reference to {"value": str, "symbol": (lib, name), "pins": {number: net}}, with
    pins numbered as in the symbol. The nets are the connectivity the drawing must reproduce;
    `kicad_sheetgen.verify` checks that it does.

    Anchors are pins ("R1.2", "U1.OUT"), or for a two-pin part "R1.L" / "R1.R" (horizontal) and
    "R1.T" / "R1.B" (vertical), or plain (x, y) points.
    """

    def __init__(self, parts, library, paper="A4"):
        self.parts, self.lib, self.paper = parts, library, paper
        self.placed = []            # (ref, unit, lib, name, x, y, rot, mirror, label side)
        self.pin = {}               # "REF.num" -> (x, y)
        self.paths, self.labels, self.locals, self.power, self.nc, self.texts = [], [], [], [], [], []
        self.interface = {}         # net -> hierarchical label name

    def net(self, ref, num):
        return self.parts[ref]["pins"].get(num)

    def place(self, ref, x, y, unit=1, rot=0, mirror=None, first=None, side=None):
        """Put one unit of a part at (x, y).

        `first` names the net that goes on the left (or top) pin of a two-pin part; the part is
        turned end for end if needed. `side` puts the reference and value "above", "below",
        "left", "right" or "ne" (right, level with the top) of the body.
        """
        p = self.parts[ref]
        lib, name = p["symbol"]
        all_pins = self.lib.pins(lib, name)
        pins = [q for q in all_pins if q[0] in (unit, 0)]
        if first is not None:
            # try the given turn and its half-turn; keep the one that puts `first` left or on top
            for r in (rot, (rot + 180) % 360):
                pos = {num: xform(px, py, r, mirror) for _, num, px, py, _ in pins}
                if p["pins"].get(min(pos, key=lambda n: pos[n])) == first:
                    rot = r
                    break
            else:
                raise ValueError(f"{ref}: no end on net {first}")
        at = {}
        for _, num, px, py, _ in pins:
            dx, dy = xform(px, py, rot, mirror)
            at[num] = (round(x + dx, 2), round(y + dy, 2))
            self.pin[f"{ref}.{num}"] = at[num]
        orient = None
        if len(at) == 2 and len(all_pins) == 2:   # a two-pin unit of a bigger part keeps its names
            a, b = sorted(at.values())
            self.pin[f"{ref}.L"] = self.pin[f"{ref}.T"] = a
            self.pin[f"{ref}.R"] = self.pin[f"{ref}.B"] = b
            orient = "v" if a[0] == b[0] else "h"
        self.placed.append((ref, unit, lib, name, x, y, rot, mirror, side or orient))
        return self

    def pt(self, a):
        return self.pin[a] if isinstance(a, str) else (round(a[0], 2), round(a[1], 2))

    def wire(self, *anchors):
        """Orthogonal polyline through anchors. Joins are found for you: a wire that ends on
        another wire, or on a pin, is split there and gets a junction where three or more meet."""
        pts = [self.pt(a) for a in anchors]
        for a, b in zip(pts, pts[1:]):
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f"diagonal wire {a} -> {b}")
        self.paths.append(pts)

    def rail(self, net, at, rot=0):
        """A power symbol. A net with no stock symbol borrows one (see `power_base`) and keeps
        its own name as the value, which is what names the net."""
        self.power.append((net, self.pt(at), rot))

    def hlabel(self, name, at, net, shape="input", right=False):
        """Hierarchical label: the sheet's interface. `net` is the part-side net it carries."""
        self.interface[net] = name
        self.labels.append((name, self.pt(at), shape, right))

    def label(self, name, at, rot=0):
        """Local label; rot 0 reads to the right of the point, 180 left, 90 up, 270 down."""
        self.locals.append((name, self.pt(at), rot))

    def no_connect(self, at):
        self.nc.append(self.pt(at))

    def text(self, s, x, y):
        self.texts.append((s, x, y))
