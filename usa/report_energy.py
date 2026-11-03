"""Energy Code Compliance Report – IECC 2021 R405 Simulated Building Performance – als HTML für den PDF-Druck."""

import datetime

from . import charts
from .style import info, n, ok, page_start, signature, t, table, tiles

DOC = "Energy Code Compliance Report – IECC R405"

# 2009 IECC, Klimazone 5, vorgeschriebene Werte (Mindestniveau der Hülle bei R405)
BACKSTOP_2009_CZ5 = {"wall_U": 0.057, "ceiling_U": 0.030, "window_U": 0.35}


def u(x):
    return f"U-{x:.3f}" if x < 0.1 else f"U-{x:.2f}"


def html(p, R, date=None):
    date = date or datetime.date.today()
    pj, c, en = p["project"], p["climate"], p["energy"]
    prop, ref = R["proposed"], R["reference"]
    sp, sr = en["proposed"], en["reference"]
    passes = prop.cost <= ref.cost
    better = 1 - prop.cost / ref.cost
    o = page_start(p, DOC, date)

    o.append("<h1>Energy Code Compliance Report</h1>")
    o.append('<div class="sub">Simulated Building Performance alternative · 2021 IECC Section R405 · Proposed design compared with the '
             "Standard Reference Design (Table R405.4.2(1))</div>")
    if pj.get("sample"):
        o.append(f'<div class="sample">SAMPLE DOCUMENT – {t(pj["note"])} Results come from a simplified hourly single-zone model with a '
                 "synthetic weather year. Code submittals are produced with software approved by the code official and site weather data.</div>")
    o.append('<div class="verdict">'
             f'<div class="big">{"COMPLIES" if passes else "DOES NOT COMPLY"} – annual energy cost {better:.0%} below the standard reference design</div>'
             f"<div>Proposed design ${n(prop.cost)} per year · Standard reference design ${n(ref.cost)} per year · "
             f"electricity at ${en['price_per_kwh']:.2f}/kWh ({t(en['price_source'])})</div></div>")
    o.append(info([
        ("Project", t(pj["title"])), ("Address", t(pj["address"])), ("Builder", t(pj["client"])),
        ("Building", f"{t(pj['description'])}"),
        ("Climate", f"IECC climate zone {c['climate_zone']} · {t(c['location'])} · synthetic reference year: "
                    f"{n(R['hdd'])} HDD65 / {n(R['cdd'])} CDD65, min {R['tmin']:.0f} °F, max {R['tmax']:.0f} °F"),
        ("Conditioned floor area / bedrooms", f"{n(prop.cfa)} ft² / {p['house']['bedrooms']}"),
        ("Code", t(pj["code"])),
        ("Calculation tool", "eco-energieberater sample model (hourly, single zone) – for illustration only"),
        ("Prepared by", f'{t(pj["prepared_by"]["name"])}, {t(pj["prepared_by"]["credentials"])}'),
        ("Date", f"{date:%m/%d/%Y} · Rev. 0"),
    ]))
    o.append(tiles([
        (f"{n(prop.total)} kWh", "Proposed design, annual"),
        (f"{n(ref.total)} kWh", "Standard reference design, annual"),
        (f"{better:.0%}", "Lower energy cost than reference"),
        (f"{prop.total / prop.cfa:.1f} kWh/ft²", "Proposed energy intensity (regulated uses)"),
    ]))
    o.append("<h2>Compliance criteria</h2>")
    bs = BACKSTOP_2009_CZ5
    backstop = sp["wall_U"] <= bs["wall_U"] and sp["ceiling_U"] <= bs["ceiling_U"] and sp["window_U"] <= bs["window_U"]
    o.append(table(["Requirement", "Proposed", "Limit / reference", "Status"], [
        ("Annual energy cost ≤ standard reference design (R405.3)", f"${n(prop.cost)}", f"${n(ref.cost)}", ok(passes)),
        ("Envelope at or better than 2009 IECC prescriptive levels (R405.2)",
         f"wall {u(sp['wall_U'])} · ceiling {u(sp['ceiling_U'])} · window {u(sp['window_U'])}",
         f"wall {u(bs['wall_U'])} · ceiling {u(bs['ceiling_U'])} · window {u(bs['window_U'])}", ok(backstop)),
        ("Mandatory provisions (Table R405.2)", "see inspection checklist, section 4", "all listed items", "to be verified"),
    ], cls="s"))

    # ------------------------------------------------------------ 1 Inputs
    o.append('<h2 class="pb">1 Proposed design and standard reference design</h2>')
    hp_ref = en["reference_heat_pump"]["desc"]
    eq = p["equipment"]
    rows = [
        ("Exterior walls", u(sr["wall_U"]), f"{u(sp['wall_U'])} · {t(p['construction']['wall']['desc'])}"),
        ("Ceiling", u(sr["ceiling_U"]), f"{u(sp['ceiling_U'])} · {t(p['construction']['ceiling']['desc'])}"),
        ("Window area", f"{n(sum(ref.design.glass.values()))} ft² ({t(sr['window_area'])})", f"{n(sum(prop.design.glass.values()))} ft² as designed"),
        ("Window U / SHGC", f"{u(sr['window_U'])} / {sr['window_SHGC']:.2f}", f"{u(sp['window_U'])} / {sp['window_SHGC']:.2f}"),
        ("Doors", u(sr["door_U"]), u(sp["door_U"])),
        ("Slab edge", f"F-{sr['slab_F']:.2f}", f"F-{sp['slab_F']:.2f} · {t(p['construction']['slab']['desc'])}"),
        ("Air leakage", f"{sr['ach50']} ACH50", f"{sp['ach50']} ACH50 (blower door test required)"),
        ("Mechanical ventilation", f"{prop.q_vent} cfm balanced, no heat recovery, {sr['vent_w_per_cfm']:.2f} W/cfm",
         f"{prop.q_vent} cfm ERV, {sp['vent_sre']:.0%} sensible recovery, {sp['vent_w_per_cfm']:.2f} W/cfm"),
        ("Heating / cooling", t(hp_ref), f"{t(eq['type'])} · SEER2 {eq['rated']['SEER2']} / HSPF2 {eq['rated']['HSPF2']}"),
        ("Distribution system efficiency", f"{sr['dse']:.2f}", f"{sp['dse']:.2f} · ducts and air handler inside conditioned space"),
        ("Water heating", f"{t(sr['dhw_desc'])}", f"{t(sp['dhw_desc'])}"),
        ("Hot water use", f"{prop.gpd} gal/day (30 + 10 × N_br)", "same"),
        ("Thermostat", f"heating {en['thermostat']['heating']} °F / cooling {en['thermostat']['cooling']} °F", "same"),
        ("Internal gains", "17,900 + 23.8 × CFA + 4,104 × N_br Btu/day", "same"),
        ("Interior shade fraction", "0.92 − 0.21 × SHGC", "same"),
    ]
    o.append(table(["Building component", "Standard reference design", "Proposed design"], rows, cls="s"))
    o.append('<p class="note">Reference values as applied in this sample per Table R405.4.2(1); confirm against the code edition adopted by the AHJ.</p>')
    o.append("<h3>Envelope heat loss coefficient (UA)</h3>")
    keys = list(prop.design.ua_parts)
    o.append(table(["Component", "Reference UA Btu/h·°F", "Proposed UA Btu/h·°F"],
                   [(t(kk), n(ref.design.ua_parts[kk], 1), n(prop.design.ua_parts[kk], 1)) for kk in keys] +
                   [("Infiltration", n(ref.design.ua_inf, 1), n(prop.design.ua_inf, 1)),
                    ("Ventilation (net of heat recovery)", n(ref.design.ua_vent, 1), n(prop.design.ua_vent, 1)),
                    ("Total", n(ref.design.ua_env + ref.design.ua_inf + ref.design.ua_vent, 1),
                     n(prop.design.ua_env + prop.design.ua_inf + prop.design.ua_vent, 1))],
                   cls="s", num=(1, 2), row_cls=[""] * (len(keys) + 2) + ["sum"]))

    # ------------------------------------------------------------ 2 Results
    o.append('<h2 class="pb">2 Annual energy use and cost</h2>')
    rows = []
    for kk in prop.kwh:
        rows.append((t(kk), n(ref.kwh[kk]), n(prop.kwh[kk]), n(ref.kwh[kk] - prop.kwh[kk]),
                     f"${n(ref.kwh[kk] * en['price_per_kwh'])}", f"${n(prop.kwh[kk] * en['price_per_kwh'])}"))
    rows.append(("Total", n(ref.total), n(prop.total), n(ref.total - prop.total), f"${n(ref.cost)}", f"${n(prop.cost)}"))
    o.append(table(["End use", "Reference kWh", "Proposed kWh", "Savings kWh", "Reference cost", "Proposed cost"],
                   rows, cls="s", num=(1, 2, 3, 4, 5), row_cls=[""] * len(prop.kwh) + ["tot"]))
    o.append('<div class="fig">' + charts.end_use_bars(ref, prop) + "</div>")
    o.append('<div class="fig">' + charts.monthly(ref, prop) + "</div>")
    o.append(f'<p class="note">Hours with auxiliary resistance heat: proposed {prop.aux_hours} h, reference {ref.aux_hours} h. '
             "Lighting and plug loads are identical in both designs and not part of the comparison.</p>")

    # ------------------------------------------------------------ 3 Upgrades
    o.append("<h2>3 Beyond code – upgrade options for the builder</h2>")
    rows = []
    for name, r in R["upgrades"]:
        rows.append((t(name), n(r.total), n(prop.total - r.total), f"${n(prop.cost - r.cost)}", f"{1 - r.cost / ref.cost:.0%}"))
    pv = en["pv"]
    pv_kwh = pv["kw"] * pv["kwh_per_kw"]
    best = R["upgrades"][-1][1] if R["upgrades"] else prop
    net = best.total - pv_kwh
    rows.append((f"All envelope upgrades + rooftop PV {pv['kw']:.1f} kW", f"{n(net)} (net)", n(prop.total - net),
                 f"${n((prop.total - net) * en['price_per_kwh'])}", "net producer" if net < 0 else f"{1 - net * en['price_per_kwh'] / ref.cost:.0%}"))
    o.append(table(["Option (each compared with the proposed design)", "Annual kWh", "Savings kWh", "Savings per year", "Cost below reference"],
                   rows, cls="s", num=(1, 2, 3, 4)))
    o.append(f'<p class="note">PV yield {pv["kwh_per_kw"]:,} kWh per kW ({t(pv["source"])}). Installed costs are not included and are to be '
             "priced by the builder. A net-negative result means the home produces more than its regulated uses over a year.</p>")

    # ------------------------------------------------------------ 4 Checklist
    o.append('<h2 class="pb">4 Inspection checklist – component characteristics to verify</h2>')
    items = [
        ("Wall insulation", "R-21 cavity + R-5 continuous exterior", "Insulation inspection"),
        ("Ceiling insulation", "R-60 blown, depth markers, raised-heel trusses", "Final inspection"),
        ("Windows / doors", f"NFRC labels U ≤ {sp['window_U']}, SHGC ≤ {sp['window_SHGC']}; doors U ≤ {sp['door_U']}", "Rough-in"),
        ("Slab edge insulation", "R-10, 4 ft vertical", "Foundation"),
        ("Air leakage (R402.4)", f"Blower door ≤ {sp['ach50']} ACH50 (model input; code maximum 3.0)", "Final, test report"),
        ("Ducts (R403.3)", "Air handler and all ducts inside conditioned space, sealed; leakage test as required", "Rough-in / final"),
        ("Equipment sizing (R403.7)", "ACCA Manual J / S calculation on file – see HVAC Design Package", "Permit"),
        ("Heat pump", f"{t(eq['type'])}, AHRI {t(eq['ahri_ref'])}, SEER2 ≥ {eq['rated']['SEER2']}, HSPF2 ≥ {eq['rated']['HSPF2']}", "Final"),
        ("Controls (R403.1)", "Programmable thermostat; aux heat lockout via outdoor sensor", "Final"),
        ("Mechanical ventilation (R403.6)", f"ERV {prop.q_vent} cfm continuous, balanced, efficacy ≥ 1.2 cfm/W", "Final, airflow test"),
        ("Water heater (R403.5)", t(sp["dhw_desc"]), "Final"),
        ("Hot water pipe insulation (R403.5)", "R-3 where required", "Rough-in"),
        ("Lighting (R404)", "All permanently installed fixtures high-efficacy", "Final"),
    ]
    o.append(table(["Item", "Required value", "Phase", "Verified"], [(t(a), b, t(cc), "☐") for a, b, cc in items], cls="s"))

    o.append("<h2>5 Method and limitations</h2>")
    o.append('<p class="note">Hourly heat balance of a single thermal zone with an effective building capacitance of '
             f'{en.get("mass_btu_per_f_ft2", 4.0)} Btu/°F per ft². Weather: synthetic year with seasonal and daily cycles and random weather '
             "variation (fixed seed), solar gains from sun position for each façade. Heat pump capacity and COP from performance tables; "
             "load beyond heat pump capacity met by resistance heat. Cooling energy assumes a sensible heat ratio of 0.80. "
             "The model shows the structure and content of an R405 report. It is not approved compliance software.</p>")
    o.append(signature(p, "Energy analyst"))
    o.append("</body></html>")
    return "".join(o)
