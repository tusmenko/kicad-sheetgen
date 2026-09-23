"""Symbols read straight out of .kicad_sym files: blocks, pins and outlines."""
import re

from . import kicad


def _close(s, i):
    """Index of the paren closing the one at s[i]."""
    d = 0
    for k in range(i, len(s)):
        d += s[k] == "("; d -= s[k] == ")"
        if d == 0:
            return k
    raise ValueError("unbalanced s-expression")


def _props(blk):
    """Top-level (property "K" "V" …) blocks, by key."""
    out = {}
    for m in re.finditer(r'\n\t\t\(property "([^"]+)"', blk):
        a = m.start() + 1
        out[m.group(1)] = blk[a:_close(blk, blk.index("(", a)) + 1]
    return out


def text_w(s):
    """Rough width of a 1.27 mm KiCad label, enough to keep text off a neighbour."""
    return 1.05 * len(s)


class SymbolLibrary:
    """Symbol lookup by (library nickname, symbol name).

    `libs` maps a nickname to a .kicad_sym file; any other nickname is looked up in the libraries
    of the installed KiCad as `<stock_dir>/<nickname>.kicad_sym`. No symbols ship with this
    package: every symbol is read from a file on the user's machine.
    """

    def __init__(self, libs=None, stock_dir=None):
        self.libs = dict(libs or {})
        self.stock_dir = stock_dir
        self._cache = {}

    def _path(self, lib):
        if lib in self.libs:
            return self.libs[lib]
        if self.stock_dir is None:
            self.stock_dir = kicad.stock_symbols()
        return f"{self.stock_dir}/{lib}.kicad_sym"

    def _raw(self, lib, name):
        path = self._path(lib)
        with open(path, encoding="utf-8") as f:
            s = f.read()
        i = s.find('(symbol "%s"' % name)
        if i < 0:
            raise KeyError(f"symbol {lib}:{name} not found in {path}")
        return s[i:_close(s, i) + 1]

    def block(self, lib, name):
        """A self-contained symbol. `extends` is flattened: a schematic's lib_symbols cannot inherit.

        The parent supplies the graphics, pins and unit sub-symbols; those sub-symbols are renamed
        to the child, and the child's own properties are laid over the parent's.
        """
        key = (lib, name)
        if key in self._cache:
            return self._cache[key]
        blk = self._raw(lib, name)
        ext = re.search(r'\(extends "([^"]+)"\)', blk)
        if ext:
            parent = self.block(lib, ext.group(1))
            merged = parent.replace('"%s' % ext.group(1), '"%s' % name)   # also renames NAME_0_1 etc.
            for k, v in _props(blk).items():
                pp = _props(merged)
                merged = merged.replace(pp[k], v) if k in pp else merged.replace('\n', '\n' + v + '\n', 1)
            blk = re.sub(r'\n\s*\(extends "[^"]+"\)', '', merged)
        self._cache[key] = blk
        return blk

    def _units(self, lib, name):
        """(start, end, unit) of every unit sub-symbol."""
        blk = self.block(lib, name)
        return [(sm.start(), _close(blk, sm.start()), int(sm.group(1)))
                for sm in re.finditer(r'\(symbol "%s_(\d+)_(\d+)"' % re.escape(name), blk)]

    def pins(self, lib, name):
        """[(unit, number, x, y, angle)] — `at` is the connection point wires attach to.

        Each (pin …) is sliced by paren depth and read on its own. Matching `at` to `number` with
        one regex across the whole symbol pairs them up wrongly on multi-unit parts.
        """
        blk = self.block(lib, name)
        units = self._units(lib, name)
        out = []
        for m in re.finditer(r'\(pin\s', blk):
            pin = blk[m.start():_close(blk, m.start()) + 1]
            at = re.search(r'\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', pin)
            num = re.search(r'\(number "([^"]+)"', pin)
            if at and num:
                unit = next((u for a, b, u in units if a <= m.start() <= b), 1)
                out.append((unit, num.group(1), float(at.group(1)), float(at.group(2)), float(at.group(3))))
        return out

    def bbox(self, lib, name, unit):
        """Library-frame (x0, y0, x1, y1) of a unit's drawing plus its pins' outer ends."""
        blk = self.block(lib, name)
        pts = []
        for a, b, u in self._units(lib, name):
            if u not in (0, unit):
                continue
            sub = blk[a:b + 1]
            for m in re.finditer(r'\((?:start|end|xy|mid) ([-\d.]+) ([-\d.]+)\)', sub):
                pts.append((float(m.group(1)), float(m.group(2))))
            for m in re.finditer(r'\(center ([-\d.]+) ([-\d.]+)\)\s*\(radius ([\d.]+)\)', sub):
                cx, cy, r = map(float, m.groups())
                pts += [(cx - r, cy - r), (cx + r, cy + r)]
        pts += [(px, py) for u, _, px, py, _ in self.pins(lib, name) if u in (0, unit)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def definition(self, lib, name):
        """The symbol block, renamed to `lib:name` for the sheet's lib_symbols."""
        return self.block(lib, name).replace('(symbol "%s"' % name, '(symbol "%s:%s"' % (lib, name), 1)
