"""SVG-Grafiken für den Audit-Bericht (druckfertig, ohne externe Bibliotheken)."""

from usa.charts import BRAND, FONT, GRID, INK, MUTED, _t

ACCENT, REJECT, HS = "#c2410c", "#9ca3af", "#7c3aed"


def billing_scatter(A, w=640, h=270):
    """Gasverbrauch je Tag gegen Gradtage je Tag mit Regressionsgerade."""
    b = A.bill
    pts = [(r["hdd65"] / r["days"], r["therms"] / r["days"], r["period"]) for r in b.rows]
    xmax = max(x for x, _, _ in pts) * 1.1
    ymax = max(y for _, y, _ in pts) * 1.15
    L, R, T, B = 52, 16, 14, 40
    px = lambda x: L + x / xmax * (w - L - R)
    py = lambda y: h - B - y / ymax * (h - T - B)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" {FONT}>']
    for x in range(0, int(xmax) + 1, 5):
        o.append(f'<line x1="{px(x):.1f}" x2="{px(x):.1f}" y1="{T}" y2="{h - B}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(px(x), h - B + 14, f"{x}", 9, "middle", MUTED))
    for y in range(0, int(ymax) + 1, 1):
        o.append(f'<line x1="{L}" x2="{w - R}" y1="{py(y):.1f}" y2="{py(y):.1f}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(L - 6, py(y) + 3, f"{y}", 9, "end", MUTED))
    o.append(_t((L + w - R) / 2, h - 6, "Heating degree days (base 65 °F) per day", 9.5, "middle", MUTED))
    o.append(_t(12, (T + h - B) / 2, "therms per day", 9.5, "middle", MUTED, extra=f'transform="rotate(-90 12 {(T + h - B) / 2})"'))
    x1 = xmax / 1.1
    o.append(f'<line x1="{px(0):.1f}" y1="{py(b.base_per_day):.1f}" x2="{px(x1):.1f}" y2="{py(b.base_per_day + b.slope * x1):.1f}" '
             f'stroke="{BRAND}" stroke-width="2"/>')
    coldest = max(pts)
    for x, y, lab in pts:
        o.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="4" fill="#fff" stroke="{ACCENT}" stroke-width="1.8"/>')
    o.append(_t(px(coldest[0]) - 8, py(coldest[1]) + 16, coldest[2], 8.5, "end", MUTED))
    o.append(_t(L + 12, T + 14, f"therms/day = {b.base_per_day:.2f} + {b.slope:.3f} × HDD/day   (R² = {b.r2:.3f})", 10, color=BRAND,
                weight="bold"))
    o.append(_t(L + 12, T + 29, f"Baseload {b.base_annual:,.0f} therms/yr · heating {b.heat_normalized:,.0f} therms/yr at "
                                f"{b.normal_hdd:,.0f} normal HDD65", 9, color=MUTED))
    o.append("</svg>")
    return "".join(o)


def sir_bars(A, sir_min=1.0, w=640, h=None):
    """SIR je Maßnahme in Paketreihenfolge (eingebaut) bzw. im Endzustand (abgelehnt)."""
    ev = sorted(A.measures, key=lambda x: (x.rank is None, x.rank or 0, -x.pkg.sir))
    row = 22
    L, R, T, B = 230, 60, 8, 34
    h = h or T + B + row * len(ev)
    vmax = max(4.0, min(12.0, max(x.pkg.sir for x in ev) * 1.05))
    px = lambda v: L + min(v, vmax) / vmax * (w - L - R)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" {FONT}>']
    for v in range(0, int(vmax) + 1):
        o.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{T}" y2="{h - B}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(px(v), h - B + 13, f"{v}", 9, "middle", MUTED))
    o.append(_t((L + w - R) / 2, h - 6, f"Savings-to-investment ratio in package order · dashed line: SIR {sir_min:.1f}", 9.5, "middle",
                MUTED))
    for i, x in enumerate(ev):
        y = T + i * row
        col = {"ECM": BRAND, "H&S": HS}.get(x.decision, REJECT)
        lab = f"{x.m['id']} {x.m['name']}"
        o.append(_t(L - 8, y + 14, lab if len(lab) < 40 else lab[:38] + "…", 9, "end"))
        o.append(f'<rect x="{L}" y="{y + 4}" width="{px(x.pkg.sir) - L:.1f}" height="{row - 8}" fill="{col}"/>')
        o.append(_t(max(px(x.pkg.sir), px(sir_min)) + 5, y + 14, f"{x.pkg.sir:.2f}" + (" ▸" if x.pkg.sir > vmax else ""), 9,
                    weight="bold"))
    o.append(f'<line x1="{px(sir_min):.1f}" x2="{px(sir_min):.1f}" y1="{T}" y2="{h - B}" stroke="{ACCENT}" stroke-width="1.6" '
             'stroke-dasharray="4 3"/>')
    o.append("</svg>")
    return "".join(o)


def cost_bars(A, prices, w=640, h=150):
    """Jährliche Energiekosten vor und nach der Sanierung, getrennt nach Gas und Strom."""
    rows = (("Before weatherization", A.pre), ("After (incl. ventilation fan)", A.post))
    vmax = max(e.cost(prices) for _, e in rows) * 1.18
    L, R, T, B = 170, 20, 10, 32
    px = lambda v: L + v / vmax * (w - L - R)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" {FONT}>']
    for v in range(0, int(vmax) + 1, 500):
        o.append(f'<line x1="{px(v):.1f}" x2="{px(v):.1f}" y1="{T}" y2="{h - B}" stroke="{GRID}" stroke-width="0.6"/>')
        o.append(_t(px(v), h - B + 13, f"${v:,}", 9, "middle", MUTED))
    for i, (lab, e) in enumerate(rows):
        y = T + 8 + i * 46
        g, k = e.gas * prices["gas_per_therm"], e.elec * prices["elec_per_kwh"]
        o.append(_t(L - 8, y + 19, lab, 9.5, "end", weight="bold"))
        o.append(f'<rect x="{L}" y="{y}" width="{px(g) - L:.1f}" height="30" fill="{ACCENT}"/>')
        o.append(_t(L + (px(g) - L) / 2, y + 19, f"gas ${g:,.0f}", 9, "middle", "#fff", "bold"))
        o.append(f'<rect x="{px(g):.1f}" y="{y}" width="{px(g + k) - px(g):.1f}" height="30" fill="#0369a1"/>')
        o.append(_t((px(g) + px(g + k)) / 2, y + 19, f"electric ${k:,.0f}", 9, "middle", "#fff", "bold"))
        o.append(_t(px(g + k) + 6, y + 19, f"${g + k:,.0f}/yr", 10, weight="bold"))
    o.append("</svg>")
    return "".join(o)
