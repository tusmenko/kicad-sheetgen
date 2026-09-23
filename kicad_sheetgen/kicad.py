"""Where KiCad lives, and which file format it writes."""
from __future__ import annotations

import os, re, shutil, subprocess, tempfile

from .ids import uid

_MAC = "/Applications/KiCad/KiCad.app/Contents"


def cli() -> str:
    """kicad-cli: $KICAD_CLI, then the macOS bundle, then PATH."""
    for c in (os.environ.get("KICAD_CLI"), f"{_MAC}/MacOS/kicad-cli", shutil.which("kicad-cli")):
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError("kicad-cli not found; set KICAD_CLI")


def stock_symbols() -> str:
    """The installed KiCad's symbol library folder: $KICAD_SYMBOL_DIR, then the usual install places."""
    for d in (os.environ.get("KICAD_SYMBOL_DIR"), f"{_MAC}/SharedSupport/symbols",
              "/usr/share/kicad/symbols", "/usr/local/share/kicad/symbols"):
        if d and os.path.isdir(d):
            return d
    raise FileNotFoundError("KiCad symbol libraries not found; set KICAD_SYMBOL_DIR")


def sch_version() -> tuple[str, str]:
    """(file version, generator version) of the installed KiCad.

    Asked of kicad-cli by upgrading a stub, so the files we write match whatever KiCad is
    installed instead of a version number frozen in this code.
    """
    with tempfile.TemporaryDirectory() as d:
        stub = os.path.join(d, "_stub.kicad_sch")
        with open(stub, "w", encoding="utf-8") as f:
            f.write('(kicad_sch (version 20250114) (generator "x") (generator_version "9.0") '
                    f'(uuid "{uid()}") (paper "A4") (lib_symbols) (sheet_instances (path "/" (page "1"))))')
        r = subprocess.run([cli(), "sch", "upgrade", "--force", stub], capture_output=True, text=True)
        with open(stub, encoding="utf-8") as f:
            t = f.read()
    v, g = re.search(r"\(version (\d+)\)", t), re.search(r'\(generator_version "([^"]+)"\)', t)
    if r.returncode or not (v and g):
        raise RuntimeError(f"kicad-cli sch upgrade failed: {(r.stdout + r.stderr).strip()[-300:]}")
    return v.group(1), g.group(1)
