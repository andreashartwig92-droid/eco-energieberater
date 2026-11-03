"""SVG-Grafiken für die US-Musterunterlagen (druckfertig, ohne externe Bibliotheken)."""

from html import escape

from .hvac import interp, load_line

INK, MUTED, GRID = "#1b1b1b", "#555", "#d4d4d4"
BRAND, REF = "#14532d", "#9ca3af"
END_USE = {"Space heating": "#c2410c", "Space cooling": "#0369a1", "Ventilation fan": "#6b7280", "Water heating": "#7c3aed"}
FONT = "font-family=\"Liberation Sans, DejaVu Sans, Arial, sans-serif\""


def _t(x, y, s, size=10, anchor="start", color=INK, weight="normal", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" '
            f'font-weight="{weight}" {extra}>{escape(str(s))}</text>')


def balance_point(p, loads, sel, w=640, h=300):
    eq, c = p["equipment"], p["climate"]
    x0, x1, y1 = -10, 65, 40000
    L, R, T, B = 58, 18, 16, 40
    px = lambda t: L + (t - x0) / (x1 - x0) * (w - L - R)
    py = lambda q: h - B - q / y1 * (h - T - B)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" {FONT}>']
    for q in range(0, y1 + 1, 5000):
        o.append(f'<line x1="{L}" x2="{w - R}" y1="{py(q):.1f}" y2="{py(q):.1f}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(L - 6, py(q) + 3, f"{q:,}", 9, "end", MUTED))
    for t in range(x0, x1 + 1, 10):
        o.append(f'<line x1="{px(t):.1f}" x2="{px(t):.1f}" y1="{T}" y2="{h - B}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(px(t), h - B + 14, f"{t}", 9, "middle", MUTED))
    o.append(_t((L + w - R) / 2, h - 6, "Outdoor temperature (°F)", 9.5, "middle", MUTED))
    o.append(_t(12, (T + h - B) / 2, "Btu/h", 9.5, "middle", MUTED, extra=f'transform="rotate(-90 12 {(T + h - B) / 2})"'))
    ll = " ".join(f"{px(t):.1f},{py(load_line(loads, p, t)):.1f}" for t in range(x0, x1 + 1))
    cap = " ".join(f"{px(t):.1f},{py(interp(eq['heating_capacity'], t)):.1f}" for t in range(x0, x1 + 1))
    aux = " ".join(f"{px(t):.1f},{py(interp(eq['heating_capacity'], t) + sel.aux_selected):.1f}" for t in range(x0, 31))
    o.append(f'<polyline points="{aux}" fill="none" stroke="#c2410c" stroke-width="1.6" stroke-dasharray="5 3"/>')
    o.append(f'<polyline points="{ll}" fill="none" stroke="{INK}" stroke-width="2"/>')
    o.append(f'<polyline points="{cap}" fill="none" stroke="{BRAND}" stroke-width="2.4"/>')
    td = c["heating_db"]
    o.append(f'<line x1="{px(td):.1f}" x2="{px(td):.1f}" y1="{T}" y2="{h - B}" stroke="{INK}" stroke-width="0.8" stroke-dasharray="2 2"/>')
    o.append(_t(px(td) + 4, T + 10, f"Design {td} °F", 9, color=INK))
    if sel.balance_point is not None:
        bx, by = px(sel.balance_point), py(load_line(loads, p, sel.balance_point))
        o.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="4" fill="#fff" stroke="{BRAND}" stroke-width="2"/>')
        o.append(_t(bx + 10, by + 22, f"Thermal balance point ≈ {sel.balance_point:.0f} °F", 9.5, color=BRAND, weight="bold"))
    lx, ly = L + 14, h - B - 52
    for i, (col, dash, lab) in enumerate(((INK, "", "Building heating load line (Manual J)"),
                                          (BRAND, "", "Heat pump max. capacity (expanded data)"),
                                          ("#c2410c", "5 3", f"Heat pump + {p['equipment']['aux_heat_kw']:.0f} kW auxiliary heat"))):
        y = ly + i * 15
        o.append(f'<rect x="{lx - 6}" y="{y - 10}" width="236" height="15" fill="#fff" opacity="0.85"/>')
        o.append(f'<line x1="{lx}" x2="{lx + 22}" y1="{y - 3}" y2="{y - 3}" stroke="{col}" stroke-width="2" stroke-dasharray="{dash}"/>')
        o.append(_t(lx + 28, y, lab, 9))
    o.append("</svg>")
    return "".join(o)


def end_use_bars(ref, prop, w=640, h=230):
    L, R, T, B = 150, 20, 10, 34
    vmax = max(ref.total, prop.total) * 1.12
    px = lambda v: L + v / vmax * (w - L - R)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" {FONT}>']
    step = 2000 if vmax > 8000 else 1000
    for v in range(0, int(vmax) + 1, step):
        o.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{T}" y2="{h - B - 22}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(px(v), h - B - 10, f"{v:,}", 9, "middle", MUTED))
    o.append(_t((L + w - R) / 2, h - B + 4, "kWh per year", 9.5, "middle", MUTED))
    for i, r in enumerate((ref, prop)):
        y = T + 12 + i * 62
        x = L
        o.append(_t(L - 8, y + 24, r.label, 10, "end", weight="bold"))
        for k, v in r.kwh.items():
            o.append(f'<rect x="{x:.1f}" y="{y}" width="{px(v) - L:.1f}" height="36" fill="{END_USE[k]}"/>')
            if px(v) - L > 34:
                o.append(_t(x + (px(v) - L) / 2, y + 22, f"{v:,.0f}", 9, "middle", "#fff", "bold"))
            x += px(v) - L
        o.append(_t(x + 6, y + 22, f"{r.total:,.0f} kWh", 10, weight="bold"))
    lx = L
    for k, col in END_USE.items():
        o.append(f'<rect x="{lx}" y="{h - 14}" width="10" height="10" fill="{col}"/>')
        o.append(_t(lx + 14, h - 5, k, 9))
        lx += 120
    o.append("</svg>")
    return "".join(o)


def monthly(ref, prop, w=640, h=210):
    L, R, T, B = 50, 12, 10, 38
    vmax = max(max(ref.monthly), max(prop.monthly)) * 1.1
    bw = (w - L - R) / 12
    py = lambda v: h - B - v / vmax * (h - T - B)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" {FONT}>']
    step = 500 if vmax > 1500 else 250
    for v in range(0, int(vmax) + 1, step):
        o.append(f'<line x1="{L}" x2="{w - R}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(L - 6, py(v) + 3, f"{v:,}", 9, "end", MUTED))
    for m, name in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()):
        x = L + m * bw
        for j, (r, col) in enumerate(((ref, REF), (prop, BRAND))):
            v = r.monthly[m]
            o.append(f'<rect x="{x + 6 + j * (bw - 12) / 2:.1f}" y="{py(v):.1f}" width="{(bw - 12) / 2 - 1:.1f}" '
                     f'height="{h - B - py(v):.1f}" fill="{col}"/>')
        o.append(_t(x + bw / 2, h - B + 13, name, 9, "middle", MUTED))
    for i, (lab, col) in enumerate((("Standard reference design", REF), ("Proposed design", BRAND))):
        o.append(f'<rect x="{L + i * 190}" y="{h - 14}" width="10" height="10" fill="{col}"/>')
        o.append(_t(L + i * 190 + 14, h - 5, lab, 9))
    o.append(_t(w - R, h - 5, "kWh per month", 9, "end", MUTED))
    o.append("</svg>")
    return "".join(o)


def duct_layout(p, loads, dd, floor, s=12.0):
    """Grundriss eines Geschosses mit Zuluftauslässen, Stammkanal, Rückluft und Überströmern."""
    house, du = p["house"], p["ducts"]
    W, D = house["width"], house["depth"]
    ox, oy = 24, 26
    w, h = W * s + 2 * ox + 150, D * s + oy + 30
    X = lambda x: ox + x * s
    Y = lambda y: oy + y * s
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="86%" {FONT}>']
    sub = "" if floor == du["ahu"]["floor"] else " (trunk and AHU below, in floor-truss space / first floor)"
    o.append(_t(ox, 16, p["floors"][floor]["name"] + " – supply, return and transfer air" + sub, 11, weight="bold"))
    cfm = {x.name: x for x in loads.rooms}
    for r in p["rooms"]:
        if r["floor"] != floor:
            continue
        o.append(f'<rect x="{X(r["x"]):.1f}" y="{Y(r["y"]):.1f}" width="{r["w"] * s:.1f}" height="{r["d"] * s:.1f}" '
                 f'fill="#fafafa" stroke="#9ca3af" stroke-width="0.8"/>')
        o.append(_t(X(r["x"]) + 4, Y(r["y"]) + 12, r["name"], 8.5, weight="bold"))
        o.append(_t(X(r["x"]) + 4, Y(r["y"]) + 23, f"{cfm[r['name']].cfm:.0f} cfm ({cfm[r['name']].mode})", 8, color=MUTED))
    o.append(f'<rect x="{X(0)}" y="{Y(0)}" width="{W * s}" height="{D * s}" fill="none" stroke="{INK}" stroke-width="2.2"/>')

    ty = Y(du["trunk_y"])
    ahu = du["ahu"]
    x_end = max([ahu["x"]] + [r.x for r in dd.runs])
    o.append(f'<line x1="{X(0) + 6:.1f}" x2="{X(x_end) + 2:.1f}" y1="{ty:.1f}" y2="{ty:.1f}" stroke="#0369a1" '
             f'stroke-width="{7 if floor == ahu["floor"] else 4}" stroke-opacity="{1 if floor == ahu["floor"] else 0.35}"/>')
    if floor == ahu["floor"]:
        o.append(f'<line x1="{X(ahu["x"]):.1f}" x2="{X(ahu["x"]):.1f}" y1="{ty:.1f}" y2="{Y(ahu["y"]):.1f}" stroke="#0369a1" stroke-width="7"/>')

    tA, tB = dd.trunks
    o.append(_t(X(21), ty - 6, f'Trunk A {tA["w"]}"×{tA["h"]}"', 8, color="#0369a1", weight="bold"))
    o.append(_t(X(1), ty - 6, f'Trunk B {tB["w"]}"×{tB["h"]}"', 8, color="#0369a1", weight="bold"))
    if floor == ahu["floor"]:
        o.append(f'<rect x="{X(ahu["x"]) - 18:.1f}" y="{Y(ahu["y"]) - 14:.1f}" width="36" height="28" fill="#0369a1"/>')
        o.append(_t(X(ahu["x"]), Y(ahu["y"]) + 4, "AHU", 9, "middle", "#fff", "bold"))
        o.append(f'<rect x="{X(ahu["x"]) - 13:.1f}" y="{Y(ahu["y"]) - 40:.1f}" width="26" height="20" fill="#fff" stroke="#6b7280" stroke-width="1.2"/>')
        o.append(_t(X(ahu["x"]), Y(ahu["y"]) - 26, "ERV", 8, "middle", "#374151", "bold"))

    for r in dd.runs:
        if r.floor != floor:
            continue
        o.append(f'<line x1="{X(r.x):.1f}" x2="{X(r.x):.1f}" y1="{ty:.1f}" y2="{Y(r.y):.1f}" stroke="#0369a1" stroke-width="2"/>')
        o.append(f'<rect x="{X(r.x) - 7:.1f}" y="{Y(r.y) - 4:.1f}" width="14" height="8" fill="#fff" stroke="#0369a1" stroke-width="1.6"/>')
        o.append(f'<line x1="{X(r.x) - 7:.1f}" x2="{X(r.x) + 7:.1f}" y1="{Y(r.y) - 4:.1f}" y2="{Y(r.y) + 4:.1f}" stroke="#0369a1" stroke-width="0.8"/>')
        o.append(_t(X(r.x) + 10, Y(r.y) + 4, f'{r.id} {r.dia}" · {r.cfm:.0f}', 8, color="#0369a1", weight="bold"))

    for g in dd.returns:
        if g["floor"] != floor:
            continue
        gx, gy = X(g["x"]), Y(g["y"])
        o.append(f'<polyline points="{gx:.1f},{gy:.1f} {X(ahu["x"]) - 22:.1f},{gy:.1f} {X(ahu["x"]) - 22:.1f},{Y(ahu["y"]):.1f} {X(ahu["x"]) - 18:.1f},{Y(ahu["y"]):.1f}" '
                 f'fill="none" stroke="#b91c1c" stroke-width="3" stroke-dasharray="7 4"/>')
        o.append(f'<rect x="{gx - 10:.1f}" y="{gy - 10:.1f}" width="20" height="20" fill="#fff" stroke="#b91c1c" stroke-width="1.6"/>')
        for k in (-5, 0, 5):
            o.append(f'<line x1="{gx - 7:.1f}" x2="{gx + 7:.1f}" y1="{gy + k:.1f}" y2="{gy + k:.1f}" stroke="#b91c1c" stroke-width="0.8"/>')
        o.append(_t(gx, gy + 22, f'{g["name"].split()[0]} {g["grille"]} · {g["dia"]}" · {g["cfm"]:.0f} cfm', 8, "middle", "#b91c1c", "bold"))

    rooms = {r["name"]: r for r in p["rooms"]}
    for tr in dd.transfers:
        r = rooms[tr["room"]]
        if r["floor"] != floor:
            continue
        # Überströmer an der Innenwand zum Flur bzw. Nachbarraum, auf halber Raumtiefe
        inner_x = r["x"] + r["w"] if r["x"] == 0 else r["x"]
        tx, tyy = X(inner_x), Y(r["y"] + r["d"] * (0.8 if r["y"] == 0 else 0.5))
        o.append(f'<circle cx="{tx:.1f}" cy="{tyy:.1f}" r="5" fill="#fff" stroke="#b91c1c" stroke-width="1.4"/>')
        o.append(_t(tx + (-8 if r["x"] == 0 else 8), tyy + 3, f'TG {tr["dia"]}"', 7.5, "end" if r["x"] == 0 else "start", "#b91c1c"))

    lx = X(W) + 16
    items = (("#0369a1", "rect", "Supply register / ceiling diffuser"), ("#0369a1", "line", "Supply duct (run, size, cfm)"),
             ("#b91c1c", "rect", "Return grille + duct"), ("#b91c1c", "circle", "Transfer grille / jump duct (TG)"))
    for i, (col, kind, lab) in enumerate(items):
        y = Y(0) + 8 + i * 30
        if kind == "rect":
            o.append(f'<rect x="{lx}" y="{y - 5}" width="14" height="10" fill="#fff" stroke="{col}" stroke-width="1.6"/>')
        elif kind == "line":
            o.append(f'<line x1="{lx}" x2="{lx + 14}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="2.4"/>')
        else:
            o.append(f'<circle cx="{lx + 7}" cy="{y}" r="5" fill="#fff" stroke="{col}" stroke-width="1.4"/>')
        words = lab.split(" ")
        o.append(_t(lx + 20, y - 1, " ".join(words[:2]), 8))
        o.append(_t(lx + 20, y + 9, " ".join(words[2:]), 8))
    nx, ny = X(W) + 70, Y(D) - 40
    o.append(f'<polygon points="{nx},{ny - 18} {nx - 7},{ny + 4} {nx},{ny - 2} {nx + 7},{ny + 4}" fill="{INK}"/>')
    o.append(_t(nx, ny + 18, "N", 11, "middle", weight="bold"))
    o.append(_t(X(0), Y(D) + 18, f"Scale: grid 1 ft = {s:.0f} px · overall {W}' × {D}' · drawing schematic, not to construction tolerance", 8, color=MUTED))
    o.append("</svg>")
    return "".join(o)
