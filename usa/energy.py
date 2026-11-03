"""Jahresenergiebedarf nach dem Aufbau von IECC 2021 R405 (Simulated Building Performance):
Entwurf gegen Standard Reference Design, stündliche Bilanz über ein synthetisches Referenzjahr.

Vereinfachungen: Einzonenmodell ohne Speichermasse, synthetisches Wetter statt TMY3, Sonnenstand
nach Standardformeln mit pauschalem Bewölkungsfaktor. Für den Nachweis beim Bauamt ist eine vom
Code Official anerkannte Software mit Standortwetter zu verwenden.
"""

import math
import random
from dataclasses import dataclass, field

from .hvac import exterior, interp, ventilation_62_2

MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
AZIMUTH = {"S": 0.0, "E": -90.0, "W": 90.0, "N": 180.0}
W_M2_TO_BTU_FT2 = 0.317


def weather(lat, seed, mean=52.5, amp=22.0, daily=10.0):
    """Synthetisches Referenzjahr (8760 h): Jahresgang, Tagesgang, AR(1)-Wetterschwankung; Sonne je Fassade."""
    rng = random.Random(seed)
    anomaly, hours = 0.0, []
    phi = math.radians(lat)
    for d in range(365):
        season = math.cos(2 * math.pi * (d - 18) / 365)  # +1 im Januar
        anomaly = 0.72 * anomaly + rng.gauss(0, 5.0 + 2.2 * season)
        cloud = min(1.0, max(0.25, rng.gauss(0.58, 0.2)))
        t_day = mean - amp * math.cos(2 * math.pi * (d - 18) / 365) + anomaly
        dec = math.radians(23.45 * math.sin(2 * math.pi * (284 + d + 1) / 365))
        for h in range(24):
            t = t_day + daily * math.cos(2 * math.pi * (h - 15) / 24)
            w = math.radians(15 * (h + 0.5 - 12))
            sin_alt = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(w)
            sol = {o: 0.0 for o in AZIMUTH}
            if sin_alt > 0.02:
                alt = math.asin(sin_alt)
                cos_az = (math.sin(dec) - sin_alt * math.sin(phi)) / (math.cos(alt) * math.cos(phi))
                az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))  # 0 = Nord
                az_s = (az - 180) if w > 0 else (180 - az)  # 0 = Süd, + = West
                beam = 1000 * 0.7 ** ((1 / sin_alt) ** 0.678) * cloud
                diffuse = 0.1 * beam + 60 * (1 - cloud) * sin_alt
                for o, a in AZIMUTH.items():
                    inc = math.cos(alt) * math.cos(math.radians(az_s - a))
                    sol[o] = (beam * max(0.0, inc) + 0.5 * diffuse) * W_M2_TO_BTU_FT2
            hours.append((d, t, sol))
    return hours


@dataclass
class Design:
    label: str
    ua_env: float
    ua_inf: float
    ua_vent: float
    glass: dict
    shgc: float
    ua_parts: dict


@dataclass
class Result:
    label: str
    heat_load: float = 0.0
    cool_load: float = 0.0
    kwh: dict = field(default_factory=dict)
    monthly: list = field(default_factory=lambda: [0.0] * 12)
    aux_hours: int = 0
    unmet_hours: int = 0
    cost: float = 0.0

    @property
    def total(self):
        return sum(self.kwh.values())


def build(p, spec):
    house, floors = p["house"], p["floors"]
    gross, glass_by = {o: 0.0 for o in AZIMUTH}, {o: 0.0 for o in AZIMUTH}
    door_a, ceil_a, perim, vol, cfa = 0.0, 0.0, 0.0, 0.0, 0.0
    for r in p["rooms"]:
        fl = floors[r["floor"]]
        ext = exterior(r, house)
        for o, L in ext.items():
            gross[o] += L * fl["wall_h"]
        for w in r.get("windows", []):
            glass_by[w["o"]] += w["area"]
        door_a += sum(d["area"] for d in r.get("doors", []))
        a = r["w"] * r["d"]
        cfa += a
        vol += a * fl["ceiling_h"]
        ceil_a += a if fl["attic"] else 0.0
        perim += sum(ext.values()) if fl["slab"] else 0.0
    if spec["window_area"].startswith("15%"):
        glass_by = {o: 0.15 * cfa / 4 for o in AZIMUTH}
    glass = sum(glass_by.values())
    wall = sum(gross.values()) - glass - door_a
    parts = {
        "Walls": spec["wall_U"] * wall,
        "Windows": spec["window_U"] * glass,
        "Doors": spec["door_U"] * door_a,
        "Ceiling": spec["ceiling_U"] * ceil_a,
        "Slab edge": spec["slab_F"] * perim,
    }
    inf_cfm = spec["ach50"] * vol / 60 / 18.0
    q_vent = ventilation_62_2(cfa, house["bedrooms"])["q_fan"]
    return Design(spec["label"], sum(parts.values()), 1.08 * inf_cfm, 1.08 * q_vent * (1 - spec["vent_sre"]),
                  glass_by, spec["window_SHGC"], parts), cfa, q_vent


def simulate(p, spec, hours, hp):
    en = p["energy"]
    d, cfa, q_vent = build(p, spec)
    nbr = p["house"]["bedrooms"]
    ig = (17900 + 23.8 * cfa + 4104 * nbr) / 24  # IECC R405 interne Gewinne, Btu/h
    shade = 0.92 - 0.21 * d.shgc  # Innenverschattung nach R405-Tabelle
    ua = d.ua_env + d.ua_inf + d.ua_vent
    th, tc = en["thermostat"]["heating"], en["thermostat"]["cooling"]
    cap_bldg = en.get("mass_btu_per_f_ft2", 4.0) * cfa  # wirksame Speicherkapazität, Btu/°F
    res = Result(spec["label"])
    heat_kwh = cool_kwh = 0.0
    t_in = th
    for day, t, sol in hours:
        month = next(i for i in range(12) if day < sum(MONTH_DAYS[: i + 1]))
        solar = sum(d.glass[o] * d.shgc * shade * sol[o] for o in AZIMUTH)
        t_free = t_in + (ig + solar - ua * (t_in - t)) / cap_bldg
        qh = qc = 0.0
        if t_free < th:
            qh, t_in = (th - t_free) * cap_bldg, th
        elif t_free > tc:
            qc, t_in = (t_free - tc) * cap_bldg, tc
        else:
            t_in = t_free
        e = 0.0
        if qh > 0:
            load = qh / spec["dse"]
            cap = interp(hp["heating_capacity"], t)
            cop = interp(hp["heating_cop"], t)
            hp_part = min(load, cap)
            e = hp_part / cop / 3412.14 + (load - hp_part) / 3412.14
            if load > cap:
                res.aux_hours += 1
            res.heat_load += qh
            heat_kwh += e
        elif qc > 0:
            load = qc / 0.80 / spec["dse"]  # gesamt inkl. latent, SHR 0,80
            e = load / interp(hp["cooling_eer"], t) / 1000
            res.cool_load += qc
            cool_kwh += e
        res.monthly[month] += e
    fan = q_vent * spec["vent_w_per_cfm"] * 8760 / 1000
    dhw = en["dhw"]
    gpd = 30 + 10 * nbr
    dhw_kwh = gpd * 8.33 * (dhw["t_hot"] - dhw["t_mains"]) * 365 / 3412.14 / spec["dhw_uef"]
    for m in range(12):
        res.monthly[m] += (fan + dhw_kwh) * MONTH_DAYS[m] / 365
    res.kwh = {"Space heating": heat_kwh, "Space cooling": cool_kwh, "Ventilation fan": fan, "Water heating": dhw_kwh}
    res.cost = res.total * en["price_per_kwh"]
    res.design = d
    res.cfa = cfa
    res.q_vent = q_vent
    res.gpd = gpd
    return res


def hp_tables(p, which):
    if which == "proposed":
        return p["equipment"]
    return p["energy"]["reference_heat_pump"]


def run_all(p):
    en = p["energy"]
    hours = weather(p["climate"]["latitude"], en.get("weather_seed", 1))
    hdd = sum(max(0.0, 65 - t) for _, t, _ in hours) / 24
    cdd = sum(max(0.0, t - 65) for _, t, _ in hours) / 24
    tmin = min(t for _, t, _ in hours)
    tmax = max(t for _, t, _ in hours)
    prop = simulate(p, en["proposed"], hours, hp_tables(p, "proposed"))
    ref = simulate(p, en["reference"], hours, hp_tables(p, "reference"))
    ups = []
    for u in en.get("upgrades", []):
        spec = dict(en["proposed"], **u["changes"])
        r = simulate(p, spec, hours, hp_tables(p, "proposed"))
        ups.append((u["name"], r))
    return {"hours": hours, "hdd": hdd, "cdd": cdd, "tmin": tmin, "tmax": tmax,
            "proposed": prop, "reference": ref, "upgrades": ups}
