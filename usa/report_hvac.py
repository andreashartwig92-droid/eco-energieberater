"""HVAC Design Package (ACCA Manual J / S / D, ASHRAE 62.2) als HTML für den PDF-Druck."""

import datetime

from . import charts
from .style import info, n, ok, page_start, signature, t, table, tiles

DOC = "Residential HVAC Design Package"


def html(p, L, S, D, date=None):
    date = date or datetime.date.today()
    pj, c, k, eq, du, v = p["project"], p["climate"], p["construction"], p["equipment"], p["ducts"], p["ventilation"]
    o = page_start(p, DOC, date)

    # ------------------------------------------------------------ Cover / summary
    o.append(f"<h1>{DOC}</h1>")
    o.append('<div class="sub">Room-by-room load calculation (ACCA Manual J, 8th Ed. structure) · Equipment selection (ACCA Manual S) · '
             "Duct design (ACCA Manual D) · Whole-dwelling ventilation (ASHRAE 62.2)</div>")
    if pj.get("sample"):
        o.append(f'<div class="sample">SAMPLE DOCUMENT – {t(pj["note"])} Calculations use simplified factors that follow the '
                 "structure of the ACCA manuals. Permit submittals are produced with ACCA-approved software and site design data.</div>")
    o.append(info([
        ("Project", t(pj["title"])), ("Address", t(pj["address"])), ("Client / builder", t(pj["client"])),
        ("Description", t(pj["description"])), ("Energy code", t(pj["code"])),
        ("Prepared by", f'{t(pj["prepared_by"]["name"])}, {t(pj["prepared_by"]["company"])}'),
        ("Date / revision", f"{date:%m/%d/%Y} · Rev. 0 – issued for permit review"),
    ]))
    o.append(tiles([
        (f"{n(L.heating)} Btu/h", "Heating design load (incl. ventilation)"),
        (f"{n(L.cooling)} Btu/h", f"Total cooling load = {L.cooling / 12000:.2f} tons"),
        (f"{n(L.sensible)} / {n(L.latent)}", "Sensible / latent cooling, Btu/h"),
        (f"{L.heating / L.cfa:.1f} Btu/h·ft²", f"Heating per ft² ({n(L.cfa)} ft² CFA)"),
        ("2-ton class", "Variable-capacity cold-climate heat pump"),
        (f"{n(eq['blower_cfm_cooling'])} cfm", "Design blower airflow (heating and cooling)"),
        (f"{S.balance_point:.0f} °F", f"Thermal balance point · {eq['aux_heat_kw']:.0f} kW aux heat"),
        (f"{D.fr:.3f}", "Design friction rate, in. w.c. per 100 ft"),
    ]))

    o.append("<h2>Plans examiner summary</h2>")
    o.append('<p class="note">Layout follows the information requested on the ACCA Residential Plans Examiner Review Form (loads, equipment, ducts).</p>')
    rows = [
        ("<b>Design conditions</b>", "", ""),
        ("Outdoor heating / cooling design dry bulb", f"{c['heating_db']} °F / {c['cooling_db']} °F (coincident WB {c['cooling_wb']} °F)", ""),
        ("Indoor heating / cooling", f"{c['indoor_heating']} °F / {c['indoor_cooling']} °F at {c['indoor_rh']} % RH", ""),
        ("Grains difference · daily range · elevation", f"{c['grains_diff']} gr/lb · {c['daily_range']} · {n(c['elevation_ft'])} ft", ""),
        ("<b>Manual J loads</b>", "", ""),
        ("Heating load", f"{n(L.heating)} Btu/h", ""),
        ("Sensible / latent / total cooling load", f"{n(L.sensible)} / {n(L.latent)} / {n(L.cooling)} Btu/h", ""),
        ("Duct loads", "0 Btu/h – air handler and all ducts inside conditioned space", ""),
        ("<b>Manual S equipment</b>", "", ""),
        ("Cooling capacity at design (total / sensible / latent)", f"{n(S.cool_total)} / {n(S.cool_sens)} / {n(S.cool_lat)} Btu/h",
         f"{S.ratio_total:.0%} of total load"),
        ("Heat pump heating capacity at {0} °F".format(c["heating_db"]), f"{n(S.cap_design)} Btu/h", f"{S.cap_design / L.heating:.0%} of heating load"),
        ("Auxiliary heat", f"{eq['aux_heat_kw']:.1f} kW = {n(S.aux_selected)} Btu/h", f"required ≥ {n(S.aux_required)} Btu/h"),
        ("<b>Manual D ducts</b>", "", ""),
        ("Blower external static pressure / available static pressure", f"{D.esp:.2f} / {D.asp:.2f} in. w.c.", ""),
        ("Total effective length (supply + return)", f"{n(D.tel_supply)} + {n(D.tel_return)} = {n(D.tel_supply + D.tel_return)} ft", f"critical run {t(D.critical)}"),
        ("Design friction rate", f"{D.fr:.3f} in. w.c. / 100 ft", ok(0.06 <= D.fr <= 0.18) + " within 0.06–0.18"),
        ("<b>Ventilation</b>", "", ""),
        ("ASHRAE 62.2 whole-dwelling rate", f"{L.vent['q_tot']:.1f} cfm required · {L.vent['q_fan']} cfm provided by ERV",
         ok(L.vent["q_fan"] >= L.vent["q_tot"])),
    ]
    o.append(table(["Item", "Value", "Check"], rows, cls="s"))

    # ------------------------------------------------------------ 1 Design data
    o.append('<h2 class="pb">1 Design data and construction</h2>')
    o.append(table(["Parameter", "Value", "Source / remark"], [
        ("Location / climate zone", f"{t(c['location'])} · IECC climate zone {c['climate_zone']}", ""),
        ("Heating design (99 %)", f"{c['heating_db']} °F outdoor · {c['indoor_heating']} °F indoor · ΔT = {L.dT_heat:.0f} °F", t(c["source"])),
        ("Cooling design (1 %)", f"{c['cooling_db']} °F DB / {c['cooling_wb']} °F WB · {c['indoor_cooling']} °F indoor · ΔT = {L.dT_cool:.0f} °F", t(c["source"])),
        ("Grains difference", f"{c['grains_diff']} gr/lb", "outdoor minus indoor at 50 % RH"),
        ("Altitude correction factor", f"{c.get('acf', 1.0):.2f}", f"elevation {n(c['elevation_ft'])} ft"),
    ], cls="s"))
    o.append("<h3>Construction components</h3>")
    o.append(table(["Component", "Description", "U / F factor", "Cooling factor"], [
        ("Exterior walls", t(k["wall"]["desc"]), f"U-{k['wall']['U']:.3f}", f"CLTD {p['cooling_factors']['wall_cltd']} °F"),
        ("Ceiling", t(k["ceiling"]["desc"]), f"U-{k['ceiling']['U']:.3f}", f"CLTD {p['cooling_factors']['ceiling_cltd']} °F"),
        ("Windows", t(k["window"]["desc"]), f"U-{k['window']['U']:.2f} · SHGC {k['window']['SHGC']:.2f}",
         "PSF N/E/S/W " + "/".join(str(p["cooling_factors"]["psf"][o]) for o in "NESW") + f" · IAC {p['cooling_factors']['iac']}"),
        ("Doors", t(k["door"]["desc"]), f"U-{k['door']['U']:.2f}", f"CLTD {p['cooling_factors']['door_cltd']} °F"),
        ("Slab", t(k["slab"]["desc"]), f"F-{k['slab']['F']:.2f} Btu/h·ft·°F", "no cooling load"),
    ], cls="s"))
    inf = p["infiltration"]
    o.append(table(["Item", "Value", "Remark"], [
        ("Air leakage", f"{inf['ach50']} ACH50", t(inf["source"])),
        ("Natural infiltration", f"heating {inf['ach50'] / inf['n_heating']:.3f} ACH = {L.infil_cfm_heat:.0f} cfm · "
                                 f"cooling {inf['ach50'] / inf['n_cooling']:.3f} ACH = {L.infil_cfm_cool:.0f} cfm",
         f"ACH50 / N with N = {inf['n_heating']} (heating), {inf['n_cooling']} (cooling); allocated by exposed wall area"),
        ("Conditioned volume / floor area", f"{n(L.volume)} ft³ / {n(L.cfa)} ft²", ""),
        ("Occupants / internal gains", f"{p['house']['bedrooms'] + 1} persons · {p['internal']['people_sensible']} Btu/h sensible + "
                                       f"{p['internal']['people_latent']} Btu/h latent each", "kitchen appliances 1,200 Btu/h, study 300 Btu/h"),
        ("Ventilation", f"{t(v['type'])} · {L.vent['q_fan']} cfm", f"SRE {v['sre_heating']:.0%} heating · SE {v['se_cooling']:.0%} / LE {v['le_cooling']:.0%} cooling"),
    ], cls="s"))

    # ------------------------------------------------------------ 2 Manual J
    o.append("<h2>2 Room-by-room loads (Manual J)</h2>")
    rows, cls = [], []
    for fl in (0, 1):
        for x in (r for r in L.rooms if r.floor == fl):
            rows.append((t(x.name), p["floors"][fl]["name"].split()[0], n(x.area), n(x.heating), n(x.sensible), n(x.latent),
                         n(x.cfm_heat), n(x.cfm_cool), f"<b>{n(x.cfm)}</b> {x.mode}"))
            cls.append("")
    rows.append(("Room totals", "", n(L.cfa), n(L.room_heating), n(L.room_sensible), n(L.room_latent),
                 n(sum(r.cfm_heat for r in L.rooms)), n(sum(r.cfm_cool for r in L.rooms)), ""))
    cls.append("sum")
    rows.append((f"Ventilation (ERV, {L.vent['q_fan']} cfm)", "", "", n(L.vent_heat), n(L.vent_sens), n(L.vent_lat), "", "", ""))
    cls.append("")
    rows.append(("Duct gains / losses", "", "", "0", "0", "0", "", "", ""))
    cls.append("")
    rows.append(("Whole-house equipment load", "", "", n(L.heating), n(L.sensible), n(L.latent), "", "", ""))
    cls.append("tot")
    o.append(table(["Room", "Floor", "Area ft²", "Heating Btu/h", "Sens. clg Btu/h", "Lat. clg Btu/h", "Htg cfm", "Clg cfm", "Design cfm"],
                   rows, cls="s", num=(2, 3, 4, 5, 6, 7, 8), row_cls=cls))
    o.append('<p class="note">Room airflow = room load share × blower airflow in each mode. The larger value governs the branch size '
             "(Htg / Clg). Ventilation loads are carried by the equipment, not by room airflows (ERV ducted separately).</p>")
    comp_h, comp_c = {}, {}
    for x in L.rooms:
        for kk, vv in x.heat.items():
            comp_h[kk] = comp_h.get(kk, 0) + vv
        for kk, vv in x.cool_s.items():
            comp_c[kk] = comp_c.get(kk, 0) + vv
    comp_h["Ventilation (ERV)"] = L.vent_heat
    comp_c["Ventilation (ERV)"] = L.vent_sens
    keys = list(dict.fromkeys(list(comp_h) + list(comp_c)))
    o.append("<h3>Load components – whole house</h3>")
    o.append(table(["Component", "Heating Btu/h", "% ", "Sensible cooling Btu/h", "%"],
                   [(t(kk), n(comp_h.get(kk)) if kk in comp_h else "–", f"{comp_h[kk] / L.heating:.0%}" if kk in comp_h else "",
                     n(comp_c.get(kk)) if kk in comp_c else "–", f"{comp_c[kk] / L.sensible:.0%}" if kk in comp_c else "")
                    for kk in keys], cls="s", num=(1, 2, 3, 4)))

    # ------------------------------------------------------------ 3 Manual S
    o.append('<h2>3 Equipment selection (Manual S)</h2>')
    o.append(info([("Equipment", t(eq["type"])), ("Model / AHRI", f"{t(eq['model'])} · AHRI {t(eq['ahri_ref'])}"),
                   ("Rated efficiency", f"SEER2 {eq['rated']['SEER2']} · HSPF2 {eq['rated']['HSPF2']}"),
                   ("Cooling data basis", t(eq["cooling_at_design"]["conditions"]))]))
    o.append(table(["Cooling at design", "Load Btu/h", "Capacity Btu/h", "Capacity / load"], [
        ("Total", n(L.cooling), n(S.cool_total), f"{S.ratio_total:.0%}"),
        ("Sensible", n(L.sensible), n(S.cool_sens), f"{S.ratio_sens:.0%}"),
        ("Latent", n(L.latent), n(S.cool_lat), f"{S.ratio_lat:.0%}"),
    ], cls="s", num=(1, 2, 3)))
    o.append(table(["Heating", "Value"], [
        (f"Heating load at {c['heating_db']} °F", f"{n(L.heating)} Btu/h"),
        (f"Heat pump max. capacity at {c['heating_db']} °F (interpolated)", f"{n(S.cap_design)} Btu/h · COP {S.cop_design:.2f}"),
        ("Auxiliary heat required at design", f"{n(S.aux_required)} Btu/h"),
        ("Auxiliary heat selected", f"{eq['aux_heat_kw']:.1f} kW = {n(S.aux_selected)} Btu/h · covers {S.emergency_cover:.0%} of design load in emergency mode"),
        ("Thermal balance point", f"{S.balance_point:.1f} °F (load line zero at {eq['heating_load_zero_f']} °F)"),
        ("Supply air temperature at design, heat pump only", f"{S.supply_temp:.0f} °F"),
    ], cls="s", num=()))
    o.append(table(["Manual S check", "Result", "Status"], [(t(a), b, ok(f)) for a, f, b in S.checks], cls="s"))
    o.append(f'<p class="note">{t(eq["cooling_limits_note"])}</p>')
    o.append('<div class="fig">' + charts.balance_point(p, L, S) + "</div>")

    # ------------------------------------------------------------ 4 Manual D
    o.append("<h2>4 Duct design (Manual D)</h2>")
    o.append(f"<p>{t(du['material'])}.</p>")
    rows = [("Blower external static pressure (manufacturer, at design cfm)", f"{D.esp:.2f}")]
    rows += [(t(a), f"– {b:.2f}") for a, b in D.components]
    rows.append(("<b>Available static pressure (ASP)</b>", f"<b>{D.asp:.2f}</b>"))
    o.append(table(["Friction rate worksheet", "in. w.c."], rows, cls="s", num=(1,)))
    o.append(f'<div class="formula">FR = ASP × 100 / TEL = {D.asp:.2f} × 100 / ({n(D.tel_supply)} + {n(D.tel_return)}) = {D.fr:.3f} in. w.c. per 100 ft</div>')
    o.append('<p class="note">TEL = measured length + equivalent length of fittings (supply '
             f'{du["fitting_el_supply"]} ft, return {du["fitting_el_return"]} ft per circuit). Shorter runs are trimmed with balancing dampers.</p>')
    o.append("<h3>Supply branches</h3>")
    o.append(table(["Run", "Room", "Htg cfm", "Clg cfm", "Design cfm", "TEL ft", "Size", "Velocity fpm", "FR actual"],
                   [(r.id, t(r.room), n(r.cfm_heat), n(r.cfm_cool), n(r.cfm), n(r.tel), f'{r.dia}" round', n(r.vel), f"{r.fr_actual:.3f}")
                    for r in D.runs], cls="s", num=(2, 3, 4, 5, 7, 8)))
    o.append("<h3>Supply trunk, returns and transfer air</h3>")
    o.append(table(["Section", "cfm", "Size", "Equiv. dia.", "Velocity fpm", "FR"],
                   [(t(x["name"]), n(x["cfm"]), f'{x["w"]}" × {x["h"]}"', f'{x["de"]:.1f}"', n(x["vel"]), f'{x["fr"]:.3f}') for x in D.trunks] +
                   [(t(g["name"]), n(g["cfm"]), f'{g["dia"]}" round, grille {g["grille"]}', "", n(g["vel"]), "") for g in D.returns],
                   cls="s", num=(1, 4, 5)))
    o.append(table(["Room with door", "Return path cfm", "Transfer grille / jump duct"],
                   [(t(x["room"]), n(x["cfm"]), f'jump duct {x["dia"]}" or transfer grille, ≤ 3 Pa room pressure with door closed')
                    for x in D.transfers], cls="s", num=(1,)))
    o.append(f'<p class="note">Velocity limits applied: supply {du["v_max_supply"]} fpm, return {du["v_max_return"]} fpm. '
             "Return grille sized for ≤ 400 fpm face velocity at 70 % free area.</p>")

    # ------------------------------------------------------------ 5 Layout
    o.append('<h2 class="pb">5 Duct layout (schematic)</h2>')
    for fl in (0, 1):
        o.append('<div class="fig" style="text-align:center">' + charts.duct_layout(p, L, D, fl) + "</div>")

    # ------------------------------------------------------------ 6 Ventilation
    o.append('<h2 class="pb">6 Whole-dwelling ventilation (ASHRAE 62.2)</h2>')
    o.append(f'<div class="formula">Q_tot = 0.03 × CFA + 7.5 × (N_br + 1) = 0.03 × {n(L.cfa)} + 7.5 × ({p["house"]["bedrooms"]} + 1) = '
             f'{L.vent["q_area"]:.1f} + {L.vent["q_occ"]:.1f} = {L.vent["q_tot"]:.1f} cfm → {L.vent["q_fan"]} cfm continuous</div>')
    o.append('<p class="note">No infiltration credit taken (conservative). Balanced system: supply and exhaust airflows set equal at commissioning.</p>')
    sp, ex = v["supply_points"], v["exhaust_points"]
    rows = [(t(a), n(b), "", "") for a, b in sp.items()]
    for i, (a, b) in enumerate(ex.items()):
        if i < len(rows):
            rows[i] = rows[i][:2] + (t(a), n(b))
        else:
            rows.append(("", "", t(a), n(b)))
    rows.append(("<b>Total fresh air</b>", f"<b>{n(sum(sp.values()))}</b>", "<b>Total exhaust</b>", f"<b>{n(sum(ex.values()))}</b>"))
    o.append(table(["ERV supply to", "cfm", "ERV exhaust from", "cfm"], rows, cls="s", num=(1, 3)))
    o.append(table(["Space", "Local exhaust"], [(t(a), t(b)) for a, b in v["local_exhaust"]], cls="s"))

    # ------------------------------------------------------------ 7 Notes
    o.append("<h2>7 Installation and commissioning notes</h2>")
    o.append("<ul>"
             "<li>Set blower to the design airflow in heating and cooling. Verify total airflow and static pressure at start-up and record readings.</li>"
             "<li>Balance each supply run to the design cfm within ±10 %. Balancing dampers at every takeoff, accessible.</li>"
             "<li>Seal all duct seams and connections with mastic. Duct leakage testing per IECC R403.3 as required by the AHJ.</li>"
             "<li>Install outdoor temperature sensor; lock out auxiliary heat above the balance point except during defrost.</li>"
             "<li>Commission the ERV to the scheduled supply and exhaust airflows and verify continuous operation.</li>"
             "<li>Any change to windows, insulation, air leakage target or equipment requires a revised calculation.</li></ul>")
    o.append("<h3>Basis and limitations</h3>")
    o.append('<p class="note">Load method follows the procedure structure of ACCA Manual J 8th Edition with simplified CLTD and peak solar factors; '
             "adjusted excursion (AED) and orientation checks are not performed in this sample. Equipment data are illustrative. "
             "This document is a design calculation, not a sealed engineering document. Where the AHJ requires a design professional's "
             "seal, the package is reviewed and sealed by a licensed professional engineer in the project state.</p>")
    o.append(signature(p, "Designer"))
    o.append("</body></html>")
    return "".join(o)
