"""Prove a drawn sheet joins exactly the pins its source says it should."""
import collections, re, subprocess

from . import kicad
from .symbols import _close


def expected(L):
    """{net: ["REF.pin", ...]} the drawing must reproduce, over every part it placed.

    Nets carried by a hierarchical label are keyed by the label's name, which is what KiCad
    will call them.
    """
    nets = collections.defaultdict(list)
    for ref in {p[0] for p in L.placed}:
        for num, n in L.parts[ref]["pins"].items():
            if n:
                nets[L.interface.get(n, n)].append(f"{ref}.{num}")
    return nets


def netlist(sch, out):
    """Export `sch` with kicad-cli to `out` and read it back as {net name: {"REF.pin"}}."""
    r = subprocess.run([kicad.cli(), "sch", "export", "netlist", "-o", out, sch], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"netlist export failed: {(r.stdout + r.stderr).strip()[-300:]}")
    with open(out, encoding="utf-8") as f:
        txt = f.read()
    got = collections.defaultdict(set)
    # KiCad writes the netlist across lines, so slice each (net …) by paren depth
    for m in re.finditer(r'\(net\b', txt):
        blk = txt[m.start():_close(txt, m.start()) + 1]
        nm = re.search(r'\(name "([^"]*)"\)', blk)
        if not nm:
            continue
        for n in re.finditer(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk):
            got[nm.group(1).lstrip("/")].add(f"{n.group(1)}.{n.group(2)}")
    return got


def compare(want, got, named=(), source="the source"):
    """True when `got` joins exactly the pins `want` joins, printing every difference.

    Only rails and interface nets carry names in a drawn sheet; every other net is anonymous, so
    the check is on which pins are joined, plus the names in `named`. Pins KiCad reports as
    unconnected must be unconnected in `want` too, which is how floating pins are accounted for.
    """
    ok = True
    w = {frozenset(v) for v in want.values()}
    h = {frozenset(v) for n, v in got.items() if not n.startswith("unconnected-")}
    for s in sorted(w - h, key=sorted):
        print(f"  MISSING join {sorted(s)}"); ok = False
    for s in sorted(h - w, key=sorted):
        print(f"  EXTRA join {sorted(s)}"); ok = False
    for nm in sorted(named):
        if got.get(nm, set()) != set(want.get(nm, ())):
            print(f"  NAME {nm}: want {sorted(want.get(nm, ()))} got {sorted(got.get(nm, ()))}"); ok = False
    floating = sorted(n for n in got if n.startswith("unconnected-"))
    if floating:
        print(f"  pins left floating, as in {source}: {', '.join(f[13:-1] for f in floating)}")
    print(f"  {len(want)} nets, {sum(len(v) for v in want.values())} pin connections — "
          + (f"MATCHES {source}" if ok else f"DIFFERS from {source}"))
    return ok
