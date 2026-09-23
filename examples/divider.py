"""A resistor divider with a filter cap, written and then checked against its own connectivity.

    python examples/divider.py [out_dir]

Needs KiCad 9 or 10 (kicad-cli and its symbol libraries).
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import kicad_sheetgen as sg

out = sys.argv[1] if len(sys.argv) > 1 else "."
parts: dict[str, sg.Part] = {
    "R1": {"value": "10k", "symbol": ("Device", "R"), "pins": {"1": "IN", "2": "MID"}},
    "R2": {"value": "10k", "symbol": ("Device", "R"), "pins": {"1": "MID", "2": "GND"}},
    "C1": {"value": "100n", "symbol": ("Device", "C"), "pins": {"1": "MID", "2": "GND"}},
}
L = sg.Layout(parts, sg.SymbolLibrary())         # Device and power come from the installed KiCad
L.place("R1", 63.5, 50.8, rot=90, first="IN")      # horizontal, IN on the left
L.place("R2", 76.2, 60.96, first="MID")            # vertical, MID on top
L.place("C1", 88.9, 60.96, first="MID")
L.hlabel("IN", (53.34, 50.8), "IN")
L.wire((53.34, 50.8), "R1.L")
L.wire("R1.R", (76.2, 50.8), (88.9, 50.8), (99.06, 50.8))
L.wire((76.2, 50.8), "R2.T")
L.wire((88.9, 50.8), "C1.T")
L.hlabel("OUT", (99.06, 50.8), "MID", shape="output", right=True)
L.wire("R2.B", (76.2, 71.12)); L.rail("GND", (76.2, 71.12))
L.wire("C1.B", (88.9, 71.12)); L.rail("GND", (88.9, 71.12))

sch = os.path.join(out, "divider.kicad_sch")
version, gen = sg.sch_version()
sg.write_sheet(L, sch, version=version, generator_version=gen, project="divider",
               root=sg.stable("divider", "root"), title="Divider")
ok = sg.compare(sg.expected(L), sg.netlist(sch, os.path.join(out, "divider.net")), named={"GND", "IN", "OUT"})
sys.exit(0 if ok else 1)
