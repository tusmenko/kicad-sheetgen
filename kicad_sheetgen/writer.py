"""Write a Layout as a .kicad_sch file."""
from __future__ import annotations

import collections, os
from collections.abc import Mapping, Sequence

from .ids import stable
from .layout import Layout, Mirror, Part, Point, xform
from .symbols import SymbolLibrary, text_w


def _q(s: object) -> str:
    """A string as it goes between quotes in a KiCad file."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    if p in (a, b):
        return False
    if a[0] == b[0] == p[0]:
        return min(a[1], b[1]) < p[1] < max(a[1], b[1])
    if a[1] == b[1] == p[1]:
        return min(a[0], b[0]) < p[0] < max(a[0], b[0])
    return False


def _instances(project: str, root: str, ref: str, unit: int) -> str:
    return (f'\t\t(instances\n\t\t\t(project "{_q(project)}"\n\t\t\t\t(path "/{root}"\n\t\t\t\t\t(reference "{_q(ref)}")'
            f'\n\t\t\t\t\t(unit {unit})\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')


def symbol_instance(lib_: SymbolLibrary, ref: str, p: Part, lib: str, name: str, x: float, y: float, unit: int, rot: int,
                    mirror: Mirror, side: str | None, project: str, root: str, uuid: str) -> str:
    def prop(k: str, v: str, dx: float, dy: float, hide: bool = False) -> str:
        # a field's angle turns with its symbol, so a quarter-turned part needs its text turned back;
        # text stays centred because KiCad mirrors left / right justification on flipped parts
        return (f'\t\t(property "{k}" "{_q(v)}"\n\t\t\t(at {round(x + dx, 2)} {round(y + dy, 2)} {rot % 180})\n\t\t\t(effects (font (size 1.27 1.27))'
                + (" (hide yes)" if hide else "") + ")\n\t\t)")
    x0, y0, x1, y1 = lib_.bbox(lib, name, unit)
    cs = [xform(a, b, rot, mirror) for a in (x0, x1) for b in (y0, y1)]
    left, right = min(c[0] for c in cs), max(c[0] for c in cs)
    top, bot = min(c[1] for c in cs), max(c[1] for c in cs)
    cx, cy = (left + right) / 2, (top + bot) / 2
    val = p["value"]
    wide = max(text_w(ref), text_w(val))
    if side == "h":                             # horizontal two-pin part: name above, value below
        (rx, ry), (vx, vy) = (cx, min(top - 1.524, -2.54)), (cx, max(bot + 1.524, 2.54))
    elif side == "v" or side == "right":        # beside the body, on the right
        (rx, ry), (vx, vy) = (right + 1.27 + wide / 2, cy - 1.27), (right + 1.27 + wide / 2, cy + 1.27)
    elif side == "ne":                          # right of the body, level with its top
        (rx, ry), (vx, vy) = (right + 1.27 + wide / 2, top + 1.27), (right + 1.27 + wide / 2, top + 3.81)
    elif side == "left":
        (rx, ry), (vx, vy) = (left - 1.27 - wide / 2, cy - 1.27), (left - 1.27 - wide / 2, cy + 1.27)
    elif side == "below" or (rot == 0 and mirror == "x"):     # op-amp: feedback sits above
        (rx, ry), (vx, vy) = (cx + 1.27, bot + 2.54), (cx + 1.27, bot + 5.08)
    else:                                       # above the body
        (rx, ry), (vx, vy) = (cx, top - 5.08), (cx, top - 2.54)
    dnp = "yes" if p.get("dnp", val.upper().startswith("DNI")) else "no"
    return "\n".join([
        f'\t(symbol\n\t\t(lib_id "{lib}:{name}")\n\t\t(at {x} {y} {rot})' + (f"\n\t\t(mirror {mirror})" if mirror else "")
        + f'\n\t\t(unit {unit})'
        f'\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp {dnp})\n\t\t(uuid "{uuid}")',
        prop("Reference", ref, rx, ry), prop("Value", val, vx, vy),
        prop("Footprint", p.get("footprint", ""), 0, 0, True), prop("Datasheet", "~", 0, 0, True),
        _instances(project, root, ref, unit)])


def power_instance(net: str, x: float, y: float, n: int, rot: int, power_base: Mapping[str, str], project: str,
                   root: str, uuid: str) -> str:
    base = power_base.get(net, net)
    down = net == "GND" or net.startswith("-")
    # the value sits past the symbol's body, which points up for a supply and down for GND
    dx, dy = xform(0, -3.81 if down else 3.81, rot)
    if dx:
        dx += (1 if dx > 0 else -1) * text_w(net) / 2
    def prop(k: str, v: str, ox: float, oy: float, hide: bool = False) -> str:
        return (f'\t\t(property "{k}" "{_q(v)}"\n\t\t\t(at {round(x + ox, 2)} {round(y + oy, 2)} {rot % 180})\n\t\t\t(effects (font (size 1.27 1.27))'
                + (" (hide yes)" if hide else "") + ")\n\t\t)")
    ref = "#PWR%02d" % n
    return "\n".join([
        (f'\t(symbol\n\t\t(lib_id "power:{base}")\n\t\t(at {x} {y} {rot})\n\t\t(unit 1)'
        f'\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(uuid "{uuid}")'),
        prop("Reference", ref, 0, 0, True), prop("Value", net, dx, dy),
        prop("Footprint", "", 0, 0, True), prop("Datasheet", "~", 0, 0, True),
        _instances(project, root, ref, 1)])


def write_sheet(L: Layout, path: str, *, version: str, generator_version: str, project: str, root: str, title: str,
                company: str = "", comments: Sequence[str] = (), power_base: Mapping[str, str] | None = None,
                generator: str = "kicad-sheetgen") -> None:
    """Write layout `L` to `path`.

    version / generator_version: from `kicad_sheetgen.kicad.sch_version()`. project / root: the KiCad
    project name and root sheet uuid the symbol instances belong to. power_base maps a rail with
    no stock power symbol (say "+3V3_A") to the stock one it borrows ("+3V3").
    """
    power_base = power_base or {}
    lib = L.lib
    ns = os.path.basename(path)

    def key(*k: object) -> str:
        return stable(ns, *k)

    need = {L.parts[r]["symbol"] for r in {p[0] for p in L.placed}}
    need |= {("power", power_base.get(n, n)) for n, _, _ in L.power}
    rows = ["\t\t" + lib.definition(a, b) for a, b in sorted(need)]
    body: list[str] = []
    for ref, unit, lb, name, x, y, rot, mirror, side in L.placed:
        body.append(symbol_instance(lib, ref, L.parts[ref], lb, name, x, y, unit, rot, mirror, side, project, root,
                                    key("symbol", ref, unit)))
    for i, (net, (x, y), rot) in enumerate(L.power, 1):
        body.append(power_instance(net, x, y, i, rot, power_base, project, root, key("power", net, x, y)))
    # split every wire where another wire or a pin ends on it, so all joins are endpoint-to-endpoint
    ends = [pt for pl in L.paths for pt in pl] + list(L.pin.values())
    ends += [at for _, at, _ in L.locals] + [at for _, at, _, _ in L.labels]
    segs: list[tuple[Point, Point]] = []
    for pl in L.paths:
        for a, b in zip(pl, pl[1:]):
            cuts = sorted({a, b} | {e for e in ends if _on_segment(e, a, b)})
            segs += [(c, d) for c, d in zip(cuts, cuts[1:])]
    degree = collections.Counter(pt for s in segs for pt in s)
    for pt in set(L.pin.values()):
        if pt in degree:
            degree[pt] += 1
    for a, b in segs:
        body.append(f'\t(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid "{key("wire", a, b)}"))')
    for pt, d in sorted(degree.items()):
        if d >= 3:
            body.append(f'\t(junction (at {pt[0]} {pt[1]}) (diameter 0) (color 0 0 0 0) (uuid "{key("junction", pt)}"))')
    for name, (x, y), shape, right in L.labels:
        rot, just = (0, "left") if right else (180, "right")
        body.append(f'\t(hierarchical_label "{_q(name)}"\n\t\t(shape {shape})\n\t\t(at {x} {y} {rot})'
                    f'\n\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n\t\t(uuid "{key("hlabel", name, x, y)}")\n\t)')
    for name, (x, y), rot in L.locals:
        just = "left bottom" if rot in (0, 90) else "right bottom"
        body.append(f'\t(label "{_q(name)}"\n\t\t(at {x} {y} {rot})'
                    f'\n\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n\t\t(uuid "{key("label", name, x, y)}")\n\t)')
    for x, y in L.nc:
        body.append(f'\t(no_connect (at {x} {y}) (uuid "{key("nc", x, y)}"))')
    for s, x, y in L.texts:
        body.append(f'\t(text "{_q(s)}"\n\t\t(exclude_from_sim no)\n\t\t(at {x} {y} 0)'
                    f'\n\t\t(effects (font (size 1.27 1.27)) (justify left top))\n\t\t(uuid "{key("text", x, y)}")\n\t)')
    tb = f'\t(title_block\n\t\t(title "{_q(title)}")\n\t\t(company "{_q(company)}")'
    tb += "".join(f'\n\t\t(comment {i} "{_q(c)}")' for i, c in enumerate(comments, 1)) + "\n\t)"
    head = [f'(kicad_sch\n\t(version {version})\n\t(generator "{generator}")\n\t(generator_version "{generator_version}")',
            f'\t(uuid "{key("sheet")}")\n\t(paper "{L.paper}")', tb, "\t(lib_symbols"] + rows + ["\t)"]
    tail = ['\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)']
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + body + tail) + "\n")
