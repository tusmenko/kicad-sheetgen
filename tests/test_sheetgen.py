"""Tests that need no KiCad: symbols come from a fixture library written for these tests."""
from __future__ import annotations

import os, re, subprocess, sys, tempfile, unittest

import kicad_sheetgen as sg

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "Test.kicad_sym")


def lib() -> sg.SymbolLibrary:
    return sg.SymbolLibrary({"Test": FIX}, stock_dir="/nonexistent")


def parts() -> dict[str, sg.Part]:
    return {
        "R1": {"value": "10k", "symbol": ("Test", "R2"), "pins": {"1": "A", "2": "B"}},
        "R2": {"value": "10k", "symbol": ("Test", "R2"), "pins": {"1": "B", "2": "C"}},
        "R3": {"value": "1k", "symbol": ("Test", "R2"), "pins": {"1": "B", "2": "D"}},
    }


class Transform(unittest.TestCase):
    def test_library_y_points_up(self) -> None:
        self.assertEqual(sg.xform(0, 3.81, 0), (0, -3.81))

    def test_quarter_turn_is_counter_clockwise_on_screen(self) -> None:
        self.assertEqual(sg.xform(0, 3.81, 90), (-3.81, 0))

    def test_mirror(self) -> None:
        self.assertEqual(sg.xform(-5.08, 2.54, 0, "x"), (-5.08, 2.54))
        self.assertEqual(sg.xform(-5.08, 2.54, 0, "y"), (5.08, -2.54))


class Symbols(unittest.TestCase):
    def test_pins_keep_their_unit(self) -> None:
        pins = {num: unit for unit, num, *_ in lib().pins("Test", "DUAL")}
        self.assertEqual(pins, {"1": 1, "2": 1, "3": 1, "5": 2, "6": 2, "7": 2, "4": 3, "8": 3})

    def test_extends_is_flattened(self) -> None:
        blk = lib().block("Test", "R2X")
        self.assertNotIn("extends", blk)
        self.assertIn('(symbol "R2X_1_1"', blk)
        self.assertIn('(property "Value" "R2X"', blk)
        self.assertEqual(len(lib().pins("Test", "R2X")), 2)

    def test_missing_symbol(self) -> None:
        with self.assertRaises(KeyError):
            lib().block("Test", "NOPE")


class Placing(unittest.TestCase):
    def test_first_turns_part_end_for_end(self) -> None:
        L = sg.Layout(parts(), lib())
        L.place("R1", 50.8, 50.8, rot=90, first="B")
        self.assertEqual(L.pin["R1.L"], L.pin["R1.2"])
        L.place("R2", 50.8, 76.2, first="B")
        self.assertEqual(L.pin["R2.T"], L.pin["R2.1"])

    def test_first_on_a_net_the_part_lacks(self) -> None:
        with self.assertRaises(ValueError):
            sg.Layout(parts(), lib()).place("R1", 0, 0, first="Z")

    def test_diagonal_wire(self) -> None:
        with self.assertRaises(ValueError):
            sg.Layout(parts(), lib()).wire((0, 0), (2.54, 2.54))


def tee(title: str = "Tee") -> tuple[sg.Layout, str, str]:
    """R1 feeding a node that R2 and R3 hang off: one junction, with the wire split at it."""
    L = sg.Layout(parts(), lib())
    L.place("R1", 50.8, 50.8, rot=90, first="A")
    L.place("R2", 63.5, 60.96, first="B")
    L.place("R3", 76.2, 60.96, first="B")
    L.wire("R1.R", (63.5, 50.8), (76.2, 50.8), "R3.T")
    L.wire((63.5, 50.8), "R2.T")
    L.hlabel("A", "R1.L", "A")                  # free ends carry the sheet's interface, so none float
    L.hlabel("C", "R2.B", "C", shape="output")
    L.hlabel("D", "R3.B", "D", shape="output")
    d = tempfile.mkdtemp()
    path = os.path.join(d, "tee.kicad_sch")
    sg.write_sheet(L, path, version="20250114", generator_version="9.0", project="t",
                   root=sg.stable("t"), title=title)
    with open(path, encoding="utf-8") as f:
        return L, path, f.read()


class Writing(unittest.TestCase):
    def test_junction_where_three_meet(self) -> None:
        _, _, s = tee()
        self.assertEqual(re.findall(r"\(junction \(at ([\d.]+ [\d.]+)\)", s), ["63.5 50.8"])
        self.assertIn("(wire (pts (xy 54.61 50.8) (xy 63.5 50.8))", s)
        self.assertIn("(wire (pts (xy 63.5 50.8) (xy 76.2 50.8))", s)

    def test_regeneration_is_identical(self) -> None:
        self.assertEqual(tee()[2], tee()[2])

    def test_strings_are_escaped(self) -> None:
        _, _, s = tee(title='A "quoted" \\ title')
        self.assertIn(r'(title "A \"quoted\" \\ title")', s)

    def test_expected_nets(self) -> None:
        L = tee()[0]
        self.assertEqual({k: sorted(v) for k, v in sg.expected(L).items()},
                         {"A": ["R1.1"], "B": ["R1.2", "R2.1", "R3.1"], "C": ["R2.2"], "D": ["R3.2"]})


def _have_kicad() -> bool:
    try:
        sg.cli(); sg.stock_symbols()
        return True
    except FileNotFoundError:
        return False


@unittest.skipUnless(_have_kicad(), "KiCad not installed")
class WithKiCad(unittest.TestCase):
    def test_tee_matches_its_netlist(self) -> None:
        L, path, _ = tee()
        v, g = sg.sch_version()
        sg.write_sheet(L, path, version=v, generator_version=g, project="t", root=sg.stable("t"), title="Tee")
        self.assertTrue(sg.compare(sg.expected(L), sg.netlist(path, path + ".net")))

    def test_example(self) -> None:
        d = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "examples", "divider.py"), d],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
