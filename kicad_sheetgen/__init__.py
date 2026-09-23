"""Readable KiCad schematics from code, checked against a netlist.

    lib = SymbolLibrary({"MyLib": "path/MyLib.kicad_sym"})     # other nicknames: the installed KiCad's
    L = Layout(parts, lib)            # parts: {ref: {"value", "symbol": (lib, name), "pins": {n: net}}}
    L.place("R1", 63.5, 68.58, rot=90, first="IN")
    L.wire("R1.R", (73.66, 68.58), "U1.2")
    write_sheet(L, "amp.kicad_sch", version=v, generator_version=g, project="p", root=root_uuid, title="Amp")
    compare(expected(L), netlist("amp.kicad_sch", "amp.net"), named={"GND"})
"""
from .ids import stable, uid
from .kicad import cli, sch_version, stock_symbols
from .layout import Layout, xform
from .symbols import SymbolLibrary, text_w
from .verify import compare, expected, netlist
from .writer import write_sheet
from . import idioms

__all__ = ["stable", "uid", "cli", "sch_version", "stock_symbols", "Layout", "xform", "SymbolLibrary", "text_w",
           "compare", "expected", "netlist", "write_sheet", "idioms"]
