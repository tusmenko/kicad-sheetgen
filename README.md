# kicad-sheetgen

Readable KiCad schematics from code, **proven against a netlist**.

You describe a sheet the way you would draw it: put each part where it belongs, run wires between
pins, drop power symbols and labels. kicad-sheetgen writes the `.kicad_sch`, then exports it with
`kicad-cli` and checks that it joins exactly the pins your source connectivity says it should.
The drawing is yours; correctness is checked, not assumed.

The connectivity can come from anywhere: a netlist, a `.kicad_pcb` you are redrawing as clean
hierarchical sheets, or a table in your own script.

## Why it exists

As of KiCad 10 there is no way to script schematics from inside KiCad: the IPC API and
`kicad-python` cover the PCB editor only. The file-level libraries we tried fell short:

- **kicad-sch-api** (tested 0.5.6): mirroring a symbol is silently dropped, and its wire helper
  drew a diagonal wire to the wrong pin, which KiCad reported as unconnected.
- **kicad-skip**: symbols can only be cloned, not created; no junctions or sheets; inactive since 2024.
- **SKiDL**: circuit-as-code to netlist; KiCad schematic output is a stub in current releases.

None of them verify the result. Writing the file is the easy part; **not being wrong** is the
point, so verification is built in.

## What it does

- **Symbols straight from `.kicad_sym` files**, your own or the ones your KiCad installed. `extends` is
  flattened (a schematic's `lib_symbols` cannot inherit), and each pin is read on its own, so
  multi-unit parts don't pair pin positions with the wrong numbers.
- **Placement with intent**: `first="NET"` turns a two-pin part so that net sits on the left or
  top; `mirror="x"` puts an op-amp's inverting input on top, next to its feedback.
- **Wires by anchor**: `"R1.L"`, `"U1.2"` or `(x, y)`. Orthogonal only (a diagonal is an error).
  A wire that ends on another wire or a pin is split there, and a junction is added wherever three
  or more ends meet.
- **Rails as power symbols**, including rails KiCad has no symbol for (`+3V3_A`): they borrow a
  stock symbol and keep their own name as the value, which is what names the net.
- **Text that stays readable**: reference and value are placed from the symbol's drawn outline
  and kept centred, because KiCad mirrors left/right justification on flipped parts.
- **Verification**: `expected(L)` is what the parts' connectivity demands, `netlist()` is what
  KiCad actually sees, and `compare()` checks which pins are joined (internal nets are
  anonymous) plus the names that matter: rails and the sheet's interface.
- **Idioms** for recurring analog drawings: op-amp inverting chains, a quad op-amp's supply
  unit, spare sections tied off as followers.

## Install

```sh
pip install git+https://github.com/tusmenko/kicad-sheetgen
```

or put the checkout on `sys.path`: the package has no dependencies, so KiCad's bundled Python
can import it as it is.

## Example

[`examples/divider.py`](examples/divider.py) is a complete sheet that writes itself and checks the
result (`python examples/divider.py /tmp`). A larger one, using the op-amp idioms:

```python
import kicad_sheetgen as sg

lib = sg.SymbolLibrary({"MyLib": "lib/MyLib.kicad_sym"})     # Device, power, ... come from your KiCad
parts: dict[str, sg.Part] = {
    "U1": {"value": "TL074", "symbol": ("MyLib", "TL074"), "pins": {"1": "OUT", "2": "N1", "3": "GND", ...}},
    "R1": {"value": "10K", "symbol": ("Device", "R"), "pins": {"1": "IN", "2": "N1"}},
    ...
}
L = sg.Layout(parts, lib)
sg.idioms.two_stage(L, "U1", 71.12, [(1, "R1", "R2", "C1"), (4, "R3", "R4", "C2")],
                    ("label", "DAC_L"), ("jack", "J1"), "R5")
sg.idioms.supply(L, "U1", 205.74, 104.14)

version, gen = sg.sch_version()                              # match the installed KiCad
sg.write_sheet(L, "out.kicad_sch", version=version, generator_version=gen,
               project="myproject", root=sg.stable("myproject", "root"), title="Audio out")
ok = sg.compare(sg.expected(L), sg.netlist("out.kicad_sch", "out.net"), named={"GND", "DAC_L"})
```

`parts` pins are numbered as in the symbol. The package is fully typed (`py.typed`): `sg.Part`
describes one entry, so a type checker catches a misspelt key before KiCad does. Coordinates are schematic millimetres; keep them on
the 1.27 mm grid.

## Hierarchies

`Root` draws the top sheet as a block diagram: child sheets stand in columns, a net whose pins all
face one gap gets its own vertical track there, and a net that reaches both sides of a column is
labelled instead of wired across. `route()` lists nets that only one sheet carries in `problems`.

```python
R = sg.Root()
left, hub = R.column("Inputs"), R.column("Core")
R.sheet(left, "in_a", "input.kicad_sch", "Input A", right=["IN_A"])
R.sheet(left, "in_b", "input.kicad_sch", "Input B", right=["IN_B"])
R.sheet(hub, "core", "core.kicad_sch", "Core", left=["IN_A", "IN_B"], auto=True)
sg.write_root(R.route(), "project.kicad_sch", version=version, generator_version=gen,
              project="project", root_uuid=root, title="Project")
```

A file placed more than once, like `input.kicad_sch` above, is written once with every placement:
`write_sheet(..., instances=[(f"/{root}/{sg.sheet_uuid('in_a')}", same), (f"/{root}/{sg.sheet_uuid('in_b')}", renamed)])`,
where each renamer gives the references (power symbols included) that placement uses.

## Requirements

- Python 3.9+ with no third-party packages (KiCad's bundled interpreter works).
- KiCad 9 or 10 for `kicad-cli`: found via `$KICAD_CLI`, the macOS app bundle or `PATH`.
  Stock symbols via `$KICAD_SYMBOL_DIR` or the usual install locations.

## Symbols

kicad-sheetgen contains no symbols. It reads each symbol from a `.kicad_sym` file on your machine:
the libraries you name, or, for any other nickname (`Device`, `power`, ...), the library of that
name in your KiCad install. Written sheets carry copies of the symbols they use in their
`lib_symbols`, as every KiCad schematic does. KiCad's own libraries are CC-BY-SA 4.0 with an
[exception](https://www.kicad.org/libraries/license/) for designs and files generated from them.

The helpers assume a few common conventions, which you can ignore by drawing with `Layout`
directly: rails are placed as symbols from KiCad's `power` library, and `idioms` expects a quad
op-amp's standard pinout and a three-pin jack (tip 3, switch 2, sleeve 1).

## Development

```sh
pip install -e ".[dev]"
pytest              # or, with no dev tools: python -m unittest discover -s tests -t .
ruff check .
mypy                # strict, over the package, examples and tests
```

The tests that need `kicad-cli` are skipped when KiCad is not installed. The package itself has no
dependencies; pytest, ruff and mypy are only for development.

## Status

Early. It draws real multi-sheet projects, each sheet verified pin-for-pin, but the API is young
and will move; see [CHANGELOG.md](CHANGELOG.md).

## Licence

[MIT](LICENSE).

kicad-sheetgen is an independent project, not affiliated with or endorsed by the KiCad project.
KiCad is used only as an external program (`kicad-cli`), through its documented file formats.
