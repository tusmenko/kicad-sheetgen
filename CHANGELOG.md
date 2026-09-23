# Changelog

The API is young and may change between 0.x releases.

## 0.1.0 (unreleased)

First public version: `SymbolLibrary`, `Layout`, `write_sheet`, `expected` / `netlist` / `compare`,
`sch_version`, and the op-amp `idioms`. Element uuids are derived from content, so regenerating an
unchanged sheet gives an identical file. Fully typed (`py.typed`, checked with `mypy --strict`), with
`Part` (a `TypedDict`) for the `parts` entries and `Placed` (a `NamedTuple`) for placed units.
