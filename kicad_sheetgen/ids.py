"""UUIDs for the elements a sheet is built from."""
import uuid

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/kicad-sheetgen")


def uid(seed=[0]):
    """Sequential: for hand-built elements outside a Layout (a root sheet, a placeholder)."""
    seed[0] += 1
    return "00000000-0000-4000-8000-%012d" % seed[0]


def stable(*key):
    """Derived from what the element is (file, kind, reference or position), so an element that
    has not changed keeps its uuid across regenerations and a diff shows only real edits."""
    return str(uuid.uuid5(_NS, "\x1f".join(map(str, key))))
