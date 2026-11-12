"""Energieaudit eines Bestandsgebäudes nach dem Aufbau der Audit-Werkzeuge im Weatherization
Assistance Program (WAP) und in einkommensabhängigen Utility-Programmen (USA).

Bausteine
- Abrechnungsanalyse: Gas-Monatsrechnungen gegen Gradtage (gewichtete Regression, PRISM-Prinzip
  mit fester Basis 65 °F), Normalisierung auf das Normaljahr, Trennung Grundlast / Heizung.
- Stündliches Einzonenmodell (synthetisches Wetterjahr aus usa.energy) für Heizen und Kühlen,
  kalibriert auf den normalisierten Heizverbrauch aus den Rechnungen.
- Maßnahmenbewertung: Barwert der Einsparung (modifizierter Barwertfaktor UPV* aus realem
  Diskontsatz und realer Energiepreisänderung oder aus den NIST-Tabellen) geteilt durch die
  Investition einschließlich Incidental Repairs = Savings-to-Investment Ratio (SIR).
  Rangfolge wie in NEAT: schrittweise jeweils die Maßnahme mit dem höchsten SIR im aktuellen
  Gebäudezustand (Wechselwirkungen), Abbruch, sobald keine Maßnahme SIR ≥ 1,0 erreicht.
- Gesundheit und Sicherheit: CAZ-Unterdruck, Abgasaustritt (Spillage), CO, Lüftung nach ASHRAE 62.2-2016.

Vereinfachungen: Einzonenmodell ohne Speichermasse, Keller innerhalb der thermischen Hülle,
Infiltration über den LBL-N-Faktor, Abluftventilator und Infiltration quadratisch überlagert.
Für Programmunterlagen ist das vom Grantee zugelassene Audit-Werkzeug (z. B. NEAT/MHEA oder eine
genehmigte Prioritätenliste) zu verwenden.
"""

import copy
import math
from dataclasses import dataclass, field

from usa.energy import MONTH_DAYS, weather

THERM = 100_000.0   # Btu je therm
KWH = 3412.14       # Btu je kWh
SHADE = 0.70        # pauschale Minderung solarer Gewinne (Vorhänge, Verschattung, Rahmen)
MONTH_OF_DAY = [m for m, n in enumerate(MONTH_DAYS) for _ in range(n)]


# ---------------------------------------------------------------- Gebäudezustand
@dataclass
class State:
    U: dict
    cfm50: float
    heat_eff: float
    dse: float
    shower_gpm: float
    dhw_factor: float
    lighting_kwh: float
    fridge_kwh: float
    q_fan: float = 0.0
    done: tuple = ()


def lamp_kwh(lamps, key="w"):
    return sum(x["n"] * x[key] * x["hours"] * 365 / 1000 for x in lamps)


def initial_state(p):
    h, w, b = p["heating"], p["dhw"], p["baseload"]
    return State(U={c["id"]: c["U"] for c in p["envelope"]}, cfm50=p["diagnostics"]["blower_door"]["pre_cfm50"],
                 heat_eff=h["efficiency"], dse=h["dse"], shower_gpm=w["shower_gpm"], dhw_factor=1.0,
                 lighting_kwh=lamp_kwh(b["lamps"]), fridge_kwh=b["refrigerator"]["metered_kwh_yr"])


def apply(s, m):
    """Gebäudezustand nach Einbau der Maßnahme m."""
    n = copy.deepcopy(s)
    k = m["type"]
    if k == "envelope":
        n.U[m["component"]] = m["U_new"]
    elif k == "dse":
        n.dse = m["dse_new"]
    elif k == "heating_eff":
        n.heat_eff = m["eff_new"]
    elif k == "showerhead":
        n.shower_gpm = m["gpm_new"]
    elif k == "dhw_factor":
        n.dhw_factor *= 1 - m["saving_fraction"]
    elif k == "lighting":
        n.lighting_kwh -= sum(x["n"] * (x["w_old"] - x["w_new"]) * x["hours"] * 365 / 1000 for x in m["lamps"])
    elif k == "refrigerator":
        n.fridge_kwh = m["kwh_new"]
    elif k != "air_sealing":
        raise ValueError(f"unbekannter Maßnahmentyp {k}")
    n.cfm50 -= m.get("cfm50_reduction", 0)
    n.done += (m["id"],)
    return n


# ---------------------------------------------------------------- Klima und Simulation
@dataclass
class Climate:
    hours: list          # (Monat, Außentemperatur °F, solare Gewinne Btu/h)
    hdd65: float
    cdd65: float
    monthly_hdd: list
    tmin: float


def climate(p, seed=None):
    c = p["climate"]
    wx = c["weather"]
    raw = weather(c["latitude"], wx["seed"] if seed is None else seed, wx["mean"], wx["amp"], wx.get("daily", 10.0))
    win, shgc = p["windows"]["area"], p["windows"]["shgc"]
    hours, mh = [], [0.0] * 12
    for d, t, sol in raw:
        m = MONTH_OF_DAY[d]
        hours.append((m, t, sum(a * shgc * SHADE * sol[o] for o, a in win.items())))
        mh[m] += max(0.0, 65 - t) / 24
    return Climate(hours, sum(mh), sum(max(0.0, t - 65) for _, t, _ in raw) / 24, mh, min(t for _, t, _ in raw))


@dataclass
class Energy:
    heat_therms: float
    heat_monthly: list
    cool_kwh: float
    dhw_therms: float
    cooking_therms: float
    light_kwh: float
    fridge_kwh: float
    other_kwh: float
    ua_env: float
    ua_air: float
    q_air: float

    @property
    def gas(self):
        return self.heat_therms + self.dhw_therms + self.cooking_therms

    @property
    def elec(self):
        return self.cool_kwh + self.light_kwh + self.fridge_kwh + self.other_kwh

    def cost(self, prices):
        return self.gas * prices["gas_per_therm"] + self.elec * prices["elec_per_kwh"]

    def mmbtu(self):
        return (self.gas * THERM + self.elec * KWH) / 1e6


def ua_envelope(p, s):
    return sum(c["area"] * s.U[c["id"]] * c.get("b", 1.0) for c in p["envelope"])


def dhw_therms(p, s):
    w = p["dhw"]
    hot_frac = (w["t_shower"] - w["t_mains"]) / (w["t_hot"] - w["t_mains"])
    gpd = w["other_hot_gpd"] + s.shower_gpm * w["shower_minutes_per_day"] * hot_frac
    return gpd * 8.33 * (w["t_hot"] - w["t_mains"]) * 365 / (w["uef"] * THERM) * s.dhw_factor


def simulate(p, s, clim, cal=1.0, other_kwh=0.0):
    """Stündliche Bilanz: Heizen, wenn Verluste die Gewinne übersteigen; Kühlen ab einer Mindest-Außentemperatur."""
    th, tc = p["thermostat"]["heating"], p["thermostat"]["cooling"]
    gains = p["internal_gains_btuh"]
    cool = p["cooling"]
    q_air = math.hypot(s.cfm50 / p["diagnostics"]["blower_door"]["n_factor"], s.q_fan)
    ua_env = ua_envelope(p, s)
    ua = ua_env + 1.08 * q_air
    monthly = [0.0] * 12
    heat = cool_btu = 0.0
    for m, t, solar in clim.hours:
        q = ua * (th - t) - gains - solar
        if q > 0:
            heat += q
            monthly[m] += q
        elif t >= cool["min_outdoor_f"]:
            qc = ua * (t - tc) + gains + solar
            if qc > 0:
                cool_btu += qc
    f = cal / (s.heat_eff * s.dse) / THERM
    return Energy(heat * f, [x * f for x in monthly], cool_btu * cool["fraction_cooled"] / (cool["eer"] * 1000),
                  dhw_therms(p, s), p["dhw"].get("cooking_therms", 0.0), s.lighting_kwh, s.fridge_kwh, other_kwh,
                  ua_env, 1.08 * q_air, q_air)


# ---------------------------------------------------------------- Abrechnungsanalyse
@dataclass
class Billing:
    rows: list
    base_per_day: float
    slope: float
    r2: float
    actual_therms: float
    actual_hdd: float
    normal_hdd: float
    base_annual: float
    heat_normalized: float
    elec_annual: float
    calibration: float = 1.0
    model_heat_raw: float = 0.0

    @property
    def gas_normalized(self):
        return self.base_annual + self.heat_normalized


def regression(rows):
    """Gewichtete lineare Regression therms/Tag = a + b · HDD/Tag (Gewicht: Tage je Abrechnungszeitraum)."""
    w = [r["days"] for r in rows]
    x = [r["hdd65"] / r["days"] for r in rows]
    y = [r["therms"] / r["days"] for r in rows]
    sw = sum(w)
    mx = sum(wi * xi for wi, xi in zip(w, x)) / sw
    my = sum(wi * yi for wi, yi in zip(w, y)) / sw
    sxy = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y))
    sxx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x))
    b = sxy / sxx
    a = my - b * mx
    ss_res = sum(wi * (yi - a - b * xi) ** 2 for wi, xi, yi in zip(w, x, y))
    ss_tot = sum(wi * (yi - my) ** 2 for wi, yi in zip(w, y))
    return a, b, 1 - ss_res / ss_tot


def billing(p, clim):
    rows = p["bills"]["periods"]
    a, b, r2 = regression(rows)
    return Billing(rows, a, b, r2, sum(r["therms"] for r in rows), sum(r["hdd65"] for r in rows), clim.hdd65,
                   a * 365, b * clim.hdd65, sum(r["kwh"] for r in rows))


# ---------------------------------------------------------------- Wirtschaftlichkeit
def measure_cost(m):
    return sum(x["qty"] * x["unit_price"] for x in m["lines"])


def irm_cost(m):
    return sum(x["qty"] * x["unit_price"] for x in m["lines"] if x.get("irm"))


def upv(p, fuel, life):
    """Modifizierter Barwertfaktor UPV*: Tabellenwert, falls angegeben, sonst Σ ((1+e)/(1+d))^t."""
    ec = p["economics"]
    tab = (ec.get("upv_star") or {}).get(fuel, {})
    if str(life) in tab:
        return tab[str(life)]
    d, e = ec["discount_rate"], ec["escalation"][fuel]
    return sum(((1 + e) / (1 + d)) ** t for t in range(1, life + 1))


@dataclass
class Saving:
    therms: float
    kwh: float
    dollars: float
    pv: float
    sir: float


def saving(p, e0, e1, life, cost):
    pr = p["prices"]
    g, k = e0.gas - e1.gas, e0.elec - e1.elec
    pv = g * pr["gas_per_therm"] * upv(p, "gas", life) + k * pr["elec_per_kwh"] * upv(p, "electric", life)
    return Saving(g, k, g * pr["gas_per_therm"] + k * pr["elec_per_kwh"], pv, pv / cost if cost else float("inf"))


@dataclass
class Evaluated:
    m: dict
    cost: float
    alone: Saving
    pkg: Saving = None
    rank: int = None
    decision: str = ""

    @property
    def installed(self):
        return self.decision in ("ECM", "H&S")


@dataclass
class Audit:
    clim: Climate
    bill: Billing
    pre_state: State
    pre: Energy
    measures: list
    pkg_state: State
    pkg: Energy
    post_state: State
    post: Energy
    package: Saving
    vent_pre: dict
    vent_post: dict
    caz: list
    hs: list
    costs: dict
    checks: list
    materials: dict = field(default_factory=dict)


def rank_measures(p, s0, clim, cal, other):
    """NEAT-Prinzip: je Runde die Maßnahme mit dem höchsten SIR im aktuellen Zustand, bis kein SIR ≥ Grenze mehr."""
    sir_min = p["program"]["sir_min"]
    e0 = simulate(p, s0, clim, cal, other)
    ev = []
    for m in p["measures"]:
        c = measure_cost(m)
        ev.append(Evaluated(m, c, saving(p, e0, simulate(p, apply(s0, m), clim, cal, other), m["life"], c)))
    s, e, open_ = s0, e0, list(ev)
    rank = 0
    while open_:
        trial = []
        for x in open_:
            s1 = apply(s, x.m)
            e1 = simulate(p, s1, clim, cal, other)
            trial.append((saving(p, e, e1, x.m["life"], x.cost), x, s1, e1))
        best = max(trial, key=lambda z: z[0].sir)
        if best[0].sir < sir_min:
            for sv, x, _, _ in trial:
                x.pkg = sv
                x.decision = "H&S" if x.m.get("hs_fallback") else "Not cost-effective"
            break
        rank += 1
        sv, x, s, e = best
        x.pkg, x.rank, x.decision = sv, rank, "ECM"
        open_.remove(x)
    return ev, s, e


# ---------------------------------------------------------------- Gesundheit und Sicherheit
def ashrae_62_2(p, cfm50, fans):
    """ASHRAE 62.2-2016 für Bestandsgebäude: Q_tot, Infiltrationsgutschrift, Ausgleich fehlender Einzelabsaugung.

    Q_tot = 0,03 · A + 7,5 · (N_br + 1)
    Q_inf = 0,052 · Q50 · wsf · (H / 8,2 ft)^0,4
    Defizit je Raum = Bedarf − vorhandene Absaugung − Fenstergutschrift; Q_tot,adj = Q_tot + 0,25 · ΣDefizit
    Q_fan = Q_tot,adj − Φ · Q_inf, Φ = 1 (balanciert) bzw. Q_inf / Q_tot,adj (Abluft oder Zuluft)
    """
    v, d = p["ventilation_62_2"], p["dwelling"]
    q_tot = 0.03 * v["floor_area"] + 7.5 * (d["bedrooms"] + 1)
    q_inf = 0.052 * cfm50 * v["wsf"] * (v["height_ft"] / 8.2) ** 0.4
    rows, deficit = [], 0.0
    for r in v["local_exhaust"]:
        have = fans.get(r["room"], r.get("existing_cfm", 0))
        credit = v.get("window_credit_cfm", 20) if r.get("openable_window") else 0
        dfc = 0.0 if have >= r["required_cfm"] else max(0.0, r["required_cfm"] - have - credit)
        deficit += dfc
        rows.append((r["room"], r["required_cfm"], have, credit, dfc))
    q_adj = q_tot + 0.25 * deficit
    phi = 1.0 if v.get("balanced") else q_inf / q_adj
    q_fan = max(0.0, q_adj - phi * q_inf)
    return {"q_tot": q_tot, "q_inf": q_inf, "deficit": deficit, "q_adj": q_adj, "phi": phi, "q_fan": q_fan,
            "rows": rows, "cfm50": cfm50}


def caz_checks(p):
    """Prüfzeilen (Test, Messwert, Grenze, bestanden) für Verbrennungsgeräte, CO und Gaslecks."""
    dg, lim = p["diagnostics"], p["caz_limits"]
    z = dg["caz"]
    net = z["worst_pa"] - z["base_pa"]
    rows = [(f"Worst-case CAZ depressurization ({z['vent_group']})",
             f"{net:+.1f} Pa (worst {z['worst_pa']:+.1f} − baseline {z['base_pa']:+.1f})",
             f"≥ {z['limit_pa']:+.1f} Pa", net >= z["limit_pa"])]
    for a in z["appliances"]:
        for cond, key in (("natural conditions", "spillage_natural_s"), ("worst case", "spillage_worst_s")):
            rows.append((f"Spillage – {a['name']} – {cond}", f"{a[key]} s", f"stops ≤ {lim['spillage_s']} s",
                         a[key] <= lim["spillage_s"]))
        co_lim = lim["co_air_free"][a["type"]]
        rows.append((f"Flue CO, air-free – {a['name']}", f"{a['co_air_free']} ppm", f"≤ {co_lim} ppm", a["co_air_free"] <= co_lim))
    ov = dg["oven"]
    rows.append((f"Oven CO, as measured – {ov['name']}", f"{ov['co_ppm']} ppm", f"≤ {lim['oven_as_measured']} ppm",
                 ov["co_ppm"] <= lim["oven_as_measured"]))
    rows.append(("Ambient CO during inspection (maximum)", f"{dg['ambient_co_max']} ppm", f"≤ {lim['ambient']} ppm",
                 dg["ambient_co_max"] <= lim["ambient"]))
    for g in dg["gas_leaks"]:
        rows.append((f"Gas leak test – {g['location']}", g["reading"], "no leak", False))
    return rows


# ---------------------------------------------------------------- Material
def materials(m):
    """Materialmengen für die Work Order (Schüttdämmung, Einblasdämmung, Spritzschaum)."""
    x = m.get("materials")
    if not x:
        return None
    k = x["kind"]
    if k == "loose_fill":
        depth = x["added_R"] / x["r_per_inch"]
        lb = x["area"] * depth / 12 * x["density"] * (1 + x.get("waste", 0))
        return {"text": f"{depth:.1f} in. settled depth added (R-{x['added_R']} at R-{x['r_per_inch']}/in.), "
                        f"{x['density']} lb/ft³ → {lb:,.0f} lb ≈ {math.ceil(lb / x['bag_lb'])} bags of {x['bag_lb']} lb",
                "bags": math.ceil(lb / x["bag_lb"]), "depth": depth}
    if k == "dense_pack":
        vol = x["area"] * (1 - x["framing"]) * x["cavity_depth_in"] / 12
        lb = vol * x["density"] * (1 + x.get("waste", 0))
        return {"text": f"cavity volume {vol:,.0f} ft³ at {x['density']} lb/ft³ (+{x.get('waste', 0):.0%} waste) → {lb:,.0f} lb ≈ "
                        f"{math.ceil(lb / x['bag_lb'])} bags of {x['bag_lb']} lb", "bags": math.ceil(lb / x["bag_lb"])}
    if k == "spf":
        bf = x["area"] * x["thickness_in"]
        return {"text": f"{x['area']:,.0f} ft² × {x['thickness_in']} in. = {bf:,.0f} board feet closed-cell SPF", "bf": bf}
    raise ValueError(f"unbekannte Materialart {k}")


# ---------------------------------------------------------------- Gesamtablauf
def run(p):
    clim = climate(p)
    bill = billing(p, clim)
    s0 = initial_state(p)
    raw = simulate(p, s0, clim)
    cal = bill.heat_normalized / raw.heat_therms
    bill.calibration, bill.model_heat_raw = cal, raw.heat_therms
    known = raw.cool_kwh + raw.light_kwh + raw.fridge_kwh
    other = max(0.0, bill.elec_annual - known)
    pre = simulate(p, s0, clim, cal, other)

    ev, s_pkg, e_pkg = rank_measures(p, s0, clim, cal, other)
    ecm = [x for x in ev if x.decision == "ECM"]
    cost_ecm = sum(x.cost for x in ecm)
    life_pv = sum(x.pkg.pv for x in ecm)
    package = Saving(pre.gas - e_pkg.gas, pre.elec - e_pkg.elec, pre.cost(p["prices"]) - e_pkg.cost(p["prices"]),
                     life_pv, life_pv / cost_ecm if cost_ecm else 0.0)

    # H&S-Maßnahmen aus der Rangfolge (z. B. Kanalabdichtung zur CAZ-Sanierung) und Lüftungsventilator
    s_post = s_pkg
    for x in ev:
        if x.decision == "H&S":
            s_post = apply(s_post, x.m)
    v = p["ventilation_62_2"]
    vent_pre = ashrae_62_2(p, s0.cfm50, {})
    vent_post = ashrae_62_2(p, s_post.cfm50, v["proposed_fans"])
    s_post = copy.deepcopy(s_post)
    s_post.q_fan = v["continuous_fan_cfm"]
    post = simulate(p, s_post, clim, cal, other)

    hs = [dict(h, cost=sum(x["qty"] * x["unit_price"] for x in h["lines"])) for h in p["health_safety"]]
    hs += [{"id": x.m["id"], "item": x.m["name"], "finding": x.m["hs_fallback"], "action": x.m["spec"],
            "lines": x.m["lines"], "cost": x.cost, "funding": "DOE WAP H&S", "from_measure": True}
           for x in ev if x.decision == "H&S"]
    pg = p["program"]
    cost_hs = sum(h["cost"] for h in hs)
    hs_avg = pg["hs_limit_pct"] * pg["acpu_limit"]
    costs = {"ecm": cost_ecm, "irm": sum(irm_cost(x.m) for x in ecm), "hs": cost_hs, "total": cost_ecm + cost_hs,
             "acpu": pg["acpu_limit"], "hs_avg": hs_avg, "hs_waiver": pg["hs_waiver_above"]}
    ok = lambda f: "PASS" if f else "FAIL"
    checks = [
        ("Package SIR (ECMs incl. incidental repairs)", f"{package.sir:.2f}", f"≥ {pg['sir_min']:.1f}", ok(package.sir >= pg["sir_min"])),
        ("Every installed ECM has SIR ≥ 1 in package order", ", ".join(f"{x.m['id']} {x.pkg.sir:.2f}" for x in ecm),
         f"≥ {pg['sir_min']:.1f}", ok(all(x.pkg.sir >= pg["sir_min"] for x in ecm))),
        ("ECM + IRM cost of this unit compared with the program-year average (ACPU)", f"${cost_ecm:,.0f}",
         f"${pg['acpu_limit']:,.0f} average", "WITHIN" if cost_ecm <= pg["acpu_limit"] else "ABOVE AVERAGE"),
        (f"H&S cost of this unit (separate budget, average {pg['hs_limit_pct']:.0%} of ACPU)", f"${cost_hs:,.0f}",
         f"${hs_avg:,.0f} average · waiver above ${pg['hs_waiver_above']:,.0f}",
         "WITHIN" if cost_hs <= pg["hs_waiver_above"] else "WAIVER REQUIRED"),
        ("ASHRAE 62.2-2016: continuous fan airflow ≥ required Q_fan (at target CFM50)", f"{v['continuous_fan_cfm']} cfm",
         f"≥ {vent_post['q_fan']:.0f} cfm", ok(v["continuous_fan_cfm"] >= vent_post["q_fan"])),
        ("Calibration factor model → bills (heating)", f"{cal:.2f}", "0.70–1.30", ok(0.7 <= cal <= 1.3)),
        ("Billing regression fit (R²)", f"{bill.r2:.3f}", "≥ 0.90", ok(bill.r2 >= 0.9)),
    ]
    mats = {x.m["id"]: materials(x.m) for x in ev if x.installed and x.m.get("materials")}
    return Audit(clim, bill, s0, pre, ev, s_pkg, e_pkg, s_post, post, package, vent_pre, vent_post,
                 caz_checks(p), hs, costs, checks, mats)
