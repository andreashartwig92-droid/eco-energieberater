"""Raumweise Lasten nach dem Aufbau von ACCA Manual J (vereinfacht, IP-Einheiten),
Lüftung nach ASHRAE 62.2, Geräteauswahl nach Manual S und Kanalnetz nach Manual D.

Vereinfachungen: pauschale CLTD- und Solarfaktoren statt der HTM-Tabellen, keine AED-Prüfung,
Kanäle vollständig in der thermischen Hülle (keine Kanalverluste). Für Bauanträge sind die
Berechnungen mit ACCA-anerkannter Software zu erstellen.
"""

import math
from dataclasses import dataclass, field

ORIENT = ("N", "E", "S", "W")
NOMINAL_ROUND = (4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 22, 24)
GRILLES = ((10, 10), (12, 12), (14, 14), (16, 16), (20, 20), (20, 25), (20, 30), (24, 24), (24, 30))


def interp(table, x):
    """Lineare Interpolation in [[x, y], ...], außerhalb linear extrapoliert."""
    pts = sorted(table)
    if x <= pts[0][0]:
        (x0, y0), (x1, y1) = pts[0], pts[1]
    elif x >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
    else:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                break
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


# ---------------------------------------------------------------- Manual J
@dataclass
class RoomLoad:
    name: str
    floor: int
    area: float
    volume: float
    ext_wall_gross: dict
    glass: dict
    door: dict
    perimeter: float
    heat: dict = field(default_factory=dict)
    cool_s: dict = field(default_factory=dict)
    cool_l: dict = field(default_factory=dict)
    cfm_heat: float = 0.0
    cfm_cool: float = 0.0

    @property
    def heating(self):
        return sum(self.heat.values())

    @property
    def sensible(self):
        return sum(self.cool_s.values())

    @property
    def latent(self):
        return sum(self.cool_l.values())

    @property
    def cfm(self):
        return max(self.cfm_heat, self.cfm_cool)

    @property
    def mode(self):
        return "Htg" if self.cfm_heat >= self.cfm_cool else "Clg"


@dataclass
class Loads:
    rooms: list
    dT_heat: float
    dT_cool: float
    infil_cfm_heat: float
    infil_cfm_cool: float
    vent: dict
    vent_heat: float
    vent_sens: float
    vent_lat: float
    volume: float
    cfa: float

    @property
    def room_heating(self):
        return sum(r.heating for r in self.rooms)

    @property
    def room_sensible(self):
        return sum(r.sensible for r in self.rooms)

    @property
    def room_latent(self):
        return sum(r.latent for r in self.rooms)

    @property
    def heating(self):
        return self.room_heating + self.vent_heat

    @property
    def sensible(self):
        return self.room_sensible + self.vent_sens

    @property
    def latent(self):
        return self.room_latent + self.vent_lat

    @property
    def cooling(self):
        return self.sensible + self.latent


def ventilation_62_2(cfa, bedrooms):
    """ASHRAE 62.2: Q_tot = 0.03 · CFA + 7.5 · (N_br + 1), ohne Infiltrationsgutschrift."""
    q = 0.03 * cfa + 7.5 * (bedrooms + 1)
    return {"q_area": 0.03 * cfa, "q_occ": 7.5 * (bedrooms + 1), "q_tot": q, "q_fan": math.ceil(q / 5) * 5}


def exterior(room, house):
    """Außenwandlängen eines Raums aus seiner Lage im Grundriss (y von Norden gemessen)."""
    ext = {}
    if room["y"] == 0:
        ext["N"] = room["w"]
    if room["y"] + room["d"] == house["depth"]:
        ext["S"] = room["w"]
    if room["x"] == 0:
        ext["W"] = room["d"]
    if room["x"] + room["w"] == house["width"]:
        ext["E"] = room["d"]
    return ext


def manual_j(p):
    c, k, cf = p["climate"], p["construction"], p["cooling_factors"]
    inf, ig, house = p["infiltration"], p["internal"], p["house"]
    acf = c.get("acf", 1.0)
    dTh = c["indoor_heating"] - c["heating_db"]
    dTc = c["cooling_db"] - c["indoor_cooling"]
    gr = c["grains_diff"]

    rooms = []
    for r in p["rooms"]:
        fl = p["floors"][r["floor"]]
        ext = exterior(r, house)
        gross = {o: L * fl["wall_h"] for o, L in ext.items()}
        glass = {o: 0.0 for o in ORIENT}
        door = {o: 0.0 for o in ORIENT}
        for w in r.get("windows", []):
            glass[w["o"]] += w["area"]
        for d in r.get("doors", []):
            door[d["o"]] += d["area"]
        area = r["w"] * r["d"]
        rooms.append(RoomLoad(r["name"], r["floor"], area, area * fl["ceiling_h"], gross, glass, door,
                              sum(ext.values()) if fl["slab"] else 0.0))

    volume = sum(x.volume for x in rooms)
    cfa = sum(x.area for x in rooms)
    gross_total = sum(sum(x.ext_wall_gross.values()) for x in rooms)
    cfm_h = inf["ach50"] / inf["n_heating"] * volume / 60
    cfm_c = inf["ach50"] / inf["n_cooling"] * volume / 60

    for x, r in zip(rooms, p["rooms"]):
        fl = p["floors"][r["floor"]]
        glass_a = sum(x.glass.values())
        door_a = sum(x.door.values())
        wall_net = sum(x.ext_wall_gross.values()) - glass_a - door_a
        share = sum(x.ext_wall_gross.values()) / gross_total
        ceil_a = x.area if fl["attic"] else 0.0
        solar = sum(x.glass[o] * k["window"]["SHGC"] * cf["iac"] * cf["psf"][o] for o in ORIENT)

        x.heat = {
            "Walls": k["wall"]["U"] * wall_net * dTh,
            "Windows": k["window"]["U"] * glass_a * dTh,
            "Doors": k["door"]["U"] * door_a * dTh,
            "Ceiling": k["ceiling"]["U"] * ceil_a * dTh,
            "Slab edge": k["slab"]["F"] * x.perimeter * dTh,
            "Infiltration": 1.1 * acf * cfm_h * share * dTh,
        }
        x.cool_s = {
            "Walls": k["wall"]["U"] * wall_net * cf["wall_cltd"],
            "Windows (cond.)": k["window"]["U"] * glass_a * dTc,
            "Windows (solar)": solar,
            "Doors": k["door"]["U"] * door_a * cf["door_cltd"],
            "Ceiling": k["ceiling"]["U"] * ceil_a * cf["ceiling_cltd"],
            "Infiltration": 1.1 * acf * cfm_c * share * dTc,
            "People": r.get("people", 0) * ig["people_sensible"],
            "Appliances": r.get("appliances", 0),
        }
        x.cool_l = {
            "Infiltration": 0.68 * acf * cfm_c * share * gr,
            "People": r.get("people", 0) * ig["people_latent"],
        }

    v = p["ventilation"]
    vent = ventilation_62_2(cfa, house["bedrooms"])
    q = vent["q_fan"]
    loads = Loads(rooms, dTh, dTc, cfm_h, cfm_c, vent,
                  1.1 * acf * q * dTh * (1 - v["sre_heating"]),
                  1.1 * acf * q * dTc * (1 - v["se_cooling"]),
                  0.68 * acf * q * gr * (1 - v["le_cooling"]),
                  volume, cfa)

    eq = p["equipment"]
    for x in rooms:
        x.cfm_heat = x.heating / loads.room_heating * eq["blower_cfm_heating"]
        x.cfm_cool = x.sensible / loads.room_sensible * eq["blower_cfm_cooling"]
    return loads


# ---------------------------------------------------------------- Manual S
@dataclass
class Selection:
    cool_total: float
    cool_sens: float
    cool_lat: float
    ratio_total: float
    ratio_sens: float
    ratio_lat: float
    limits: tuple
    cap_design: float
    cop_design: float
    aux_required: float
    aux_selected: float
    balance_point: float
    emergency_cover: float
    supply_temp: float
    checks: list


def load_line(loads, p, t):
    """Heizlastgerade: Auslegungslast bei θ_e, null bei der Nulllasttemperatur (Standard 65 °F)."""
    t0 = p["equipment"].get("heating_load_zero_f", 65)
    td = p["climate"]["heating_db"]
    return max(0.0, loads.heating * (t0 - t) / (t0 - td))


def manual_s(p, loads):
    eq, c = p["equipment"], p["climate"]
    cd = eq["cooling_at_design"]
    tot, sens = cd["total"], cd["sensible"]
    lat = tot - sens
    lo, hi = eq["cooling_limits"]
    cap = interp(eq["heating_capacity"], c["heating_db"])
    cop = interp(eq["heating_cop"], c["heating_db"])
    aux_req = max(0.0, loads.heating - cap)
    aux_sel = eq["aux_heat_kw"] * 3412.14

    # Bivalenzpunkt: Schnittpunkt Heizlastgerade / Wärmepumpenleistung
    t, bp = c["heating_db"] - 15, None
    while t <= 65:
        if interp(eq["heating_capacity"], t) >= load_line(loads, p, t):
            bp = t
            break
        t += 0.1
    sup_t = c["indoor_heating"] + cap / (1.08 * eq["blower_cfm_heating"])

    r_tot, r_sens, r_lat = tot / loads.cooling, sens / loads.sensible, lat / max(loads.latent, 1)
    checks = [
        (f"Total cooling capacity {lo:.0%}–{hi:.0%} of total cooling load", lo <= r_tot <= hi, f"{r_tot:.0%}"),
        ("Sensible capacity ≥ sensible load", r_sens >= 1.0, f"{r_sens:.0%}"),
        ("Latent capacity ≥ latent load", r_lat >= 1.0, f"{r_lat:.0%}"),
        ("Heat pump + auxiliary heat ≥ heating design load", cap + aux_sel >= loads.heating,
         f"{(cap + aux_sel) / loads.heating:.0%}"),
        ("Auxiliary heat locked out above balance point (outdoor sensor)", True, f"{bp:.0f} °F" if bp is not None else "–"),
    ]
    return Selection(tot, sens, lat, r_tot, r_sens, r_lat, (lo, hi), cap, cop, aux_req, aux_sel, bp,
                     aux_sel / loads.heating, sup_t, checks)


# ---------------------------------------------------------------- Manual D
def friction(q, d):
    """Reibungsdruckgefälle in in. w.c. je 100 ft, glattes Blech (Näherung des Reibungsdiagramms)."""
    return 0.109136 * q ** 1.9 / d ** 5.02


def velocity(q, d):
    return q / (math.pi * (d / 12) ** 2 / 4)


def size_round(q, fr, vmax):
    for d in NOMINAL_ROUND:
        if friction(q, d) <= fr and velocity(q, d) <= vmax:
            return d
    return NOMINAL_ROUND[-1]


def rect_equiv(a, b):
    """Gleichwertiger Durchmesser eines Rechteckkanals (Huebscher)."""
    return 1.30 * (a * b) ** 0.625 / (a + b) ** 0.25


def size_rect(q, fr, vmax, h=8):
    for w in range(6, 61, 2):
        de = rect_equiv(w, h)
        if friction(q, de) <= fr and q / (w * h / 144) <= vmax:
            return w, h, de
    return 60, h, rect_equiv(60, h)


@dataclass
class Run:
    id: str
    room: str
    floor: int
    x: float
    y: float
    cfm: float
    cfm_heat: float
    cfm_cool: float
    tel: float
    dia: int
    vel: float
    fr_actual: float


@dataclass
class DuctDesign:
    esp: float
    components: list
    asp: float
    tel_supply: float
    tel_return: float
    fr: float
    runs: list
    trunks: list
    returns: list
    transfers: list
    critical: str


def manual_d(p, loads):
    du, eq = p["ducts"], p["equipment"]
    ahu = du["ahu"]
    comp = sum(v for _, v in du["components"])
    asp = du["blower_esp"] - comp
    rooms = {r["name"]: r for r in p["rooms"]}

    runs, n = [], 1
    for x in loads.rooms:
        r = rooms[x.name]
        k = max(1, math.ceil(x.cfm / du["max_cfm_per_run"]))
        for i in range(k):
            # Auslässe gleichmäßig entlang der Raumbreite, nahe der Außenwand
            rx = r["x"] + r["w"] * (i + 1) / (k + 1)
            ry = r["y"] + (r["d"] * 0.75 if r["y"] > 0 else r["d"] * 0.25)
            length = abs(rx - ahu["x"]) + abs(du["trunk_y"] - ahu["y"]) + abs(ry - du["trunk_y"])
            length += du["riser_ft"] * abs(x.floor - ahu["floor"])
            runs.append(Run(f"S{n}", x.name, x.floor, rx, ry, x.cfm / k, x.cfm_heat / k, x.cfm_cool / k,
                            length + du["fitting_el_supply"], 0, 0, 0))
            n += 1

    def peak(sel):
        # Kanalabschnitte führen den größeren Volumenstrom aus Heiz- oder Kühlbetrieb (Gebläse je Modus konstant)
        return max(sum(r.cfm_heat for r in runs if sel(r)), sum(r.cfm_cool for r in runs if sel(r)))

    ret = []
    total = peak(lambda r: True)
    for g in du["returns"]:
        q = peak(lambda r, f=g["serves"]: r.floor == f)
        length = abs(g["x"] - ahu["x"]) + abs(g["y"] - ahu["y"]) + du["riser_ft"] * abs(g["floor"] - ahu["floor"])
        ret.append({"name": g["name"], "floor": g["floor"], "x": g["x"], "y": g["y"], "cfm": q,
                    "tel": length + du["fitting_el_return"]})

    crit = max(runs, key=lambda r: r.tel)
    tel_s = crit.tel
    tel_r = max(g["tel"] for g in ret)
    fr = asp * 100 / (tel_s + tel_r)

    for r in runs:
        r.dia = size_round(r.cfm, fr, du["v_max_supply"])
        r.vel = velocity(r.cfm, r.dia)
        r.fr_actual = friction(r.cfm, r.dia)
    for g in ret:
        g["dia"] = size_round(g["cfm"], fr, du["v_max_return"])
        g["vel"] = velocity(g["cfm"], g["dia"])
        need = g["cfm"] / 400 * 144 / 0.70  # Nennfläche bei 400 fpm Stirnfläche, 70 % freier Querschnitt
        g["grille"] = next((f"{a}\"×{b}\"" for a, b in GRILLES if a * b >= need), "2 grilles")

    west = peak(lambda r: r.x < 20)
    trunks = []
    for name, q in (("Trunk A – plenum to x = 20 ft (all runs)", total), ("Trunk B – x = 20 ft to west end", west)):
        w, h, de = size_rect(q, fr, du["v_max_supply"])
        trunks.append({"name": name, "cfm": q, "w": w, "h": h, "de": de, "vel": q / (w * h / 144),
                       "fr": friction(q, de)})

    transfers = []
    for name in du["transfer_rooms"]:
        q = next(x.cfm for x in loads.rooms if x.name == name)
        d = size_round(q, 0.05, 600)
        transfers.append({"room": name, "cfm": q, "dia": d})
    return DuctDesign(du["blower_esp"], du["components"], asp, tel_s, tel_r, fr, runs, trunks, ret, transfers,
                      f"{crit.id} ({crit.room})")
