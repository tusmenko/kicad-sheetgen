"""Recurring analog drawings: op-amp chains, supply units, spare sections."""

# quad op-amp (TL074, MCP6004, LM324 ...) section -> (inverting, non-inverting, output) pin
OPAMP = {1: ("2", "3", "1"), 2: ("6", "5", "7"), 3: ("9", "10", "8"), 4: ("13", "12", "14")}


def two_stage(L, u, y, stages, src, sink, rout, x0=50.8):
    """Op-amp chain, left to right: source -> inverting stages -> series R -> sink.

    stages: [(section, Rin, Rfb, Cfb or None)]. Each section is mirrored so its inverting input is
    on top, under its feedback. src/sink: ("label", name) or ("jack", ref); a jack is a three-pin
    symbol with tip "3", switch "2" and sleeve "1".
    Returns the jack-tip point of a jack source, so a caller can hang more on it.
    """
    xs, yi = x0, round(y - 2.54, 2)
    tip = None
    first_node = L.net(u, OPAMP[stages[0][0]][0])
    rin0 = stages[0][1]
    src_net = next(n for n in L.parts[rin0]["pins"].values() if n != first_node)
    if src[0] == "label":
        L.hlabel(src[1], (xs, yi), src_net)
    else:
        jack = src[1]
        L.place(jack, xs - 5.08, yi + 2.54, mirror="y")
        tip = (xs, yi)
        L.wire(f"{jack}.1", (xs + 2.54, yi + 5.08), (xs + 2.54, yi + 10.16))
        L.rail("GND", (xs + 2.54, yi + 10.16))
    for sec, rin, rfb, cfb in stages:
        inv, non, out = OPAMP[sec]
        node = L.net(u, inv)
        X, oy = round(xs + 38.1, 2), round(yi + 2.54, 2)
        L.place(u, X, oy, unit=sec, mirror="x")
        L.place(rin, xs + 12.7, yi, rot=90, first=next(n for n in L.parts[rin]["pins"].values() if n != node))
        L.place(rfb, X, yi - 10.16, rot=90, first=node)
        if cfb:
            L.place(cfb, X, yi - 20.32, rot=90, first=node)
        n, o = (round(xs + 22.86, 2), yi), (round(X + 12.7, 2), oy)
        L.wire((xs, yi), f"{rin}.L")
        L.wire(f"{rin}.R", n, f"{u}.{inv}")
        L.wire(n, (n[0], yi - 10.16), f"{rfb}.L")
        L.wire(f"{u}.{out}", o, (o[0], yi - 10.16), f"{rfb}.R")
        if cfb:
            L.wire((n[0], yi - 10.16), (n[0], yi - 20.32), f"{cfb}.L")
            L.wire((o[0], yi - 10.16), (o[0], yi - 20.32), f"{cfb}.R")
        L.wire(f"{u}.{non}", (n[0] + 5.08, oy + 2.54), (n[0] + 5.08, oy + 7.62))
        L.rail("GND", (n[0] + 5.08, oy + 7.62))
        xs, yi = o
    L.place(rout, xs + 10.16, yi, rot=90, first=L.net(u, OPAMP[stages[-1][0]][2]))
    L.wire((xs, yi), f"{rout}.L")
    if sink[0] == "jack":
        jack = sink[1]
        L.place(jack, xs + 30.48, yi + 2.54)
        L.wire(f"{rout}.R", f"{jack}.3")
        L.wire(f"{jack}.1", (xs + 22.86, yi + 5.08), (xs + 22.86, yi + 10.16))
        L.rail("GND", (xs + 22.86, yi + 10.16))
        L.no_connect(f"{jack}.2")
    else:
        end = next(n for n in L.parts[rout]["pins"].values() if n != L.net(u, OPAMP[stages[-1][0]][2]))
        L.wire(f"{rout}.R", (xs + 20.32, yi))
        L.hlabel(sink[1], (xs + 20.32, yi), end, shape="output", right=True)
    return tip


def supply(L, u, x, y, top="+12V", bot="-12V"):
    """The supply section (unit 5) of a quad op-amp, rails straight off its pins 4 and 11."""
    L.place(u, x, y, unit=5)
    L.wire(f"{u}.4", (x, y - 12.7)); L.rail(top, (x, y - 12.7))
    L.wire(f"{u}.11", (x, y + 12.7)); L.rail(bot, (x, y + 12.7), rot=0)


def spare(L, u, sec, x, y):
    """An unused section, tied off as a grounded follower."""
    inv, non, out = OPAMP[sec]
    L.place(u, x, y, unit=sec, mirror="x")
    L.wire(f"{u}.{out}", (x + 10.16, y), (x + 10.16, y - 7.62), (x - 10.16, y - 7.62),
           (x - 10.16, y - 2.54), f"{u}.{inv}")
    L.wire(f"{u}.{non}", (x - 10.16, y + 2.54), (x - 10.16, y + 7.62))
    L.rail("GND", (x - 10.16, y + 7.62))
