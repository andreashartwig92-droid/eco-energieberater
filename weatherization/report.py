"""Unterlagen eines Weatherization-Auftrags als HTML für den PDF-Druck (US Letter, englisch):
Home Energy Audit Report, Work Order für die ausführende Firma und Final-Inspection-Formular für den QCI."""

import datetime

from usa.style import info, n, page_start, t, table, tiles

from . import charts

EXTRA_CSS = """<style>
.st-pass { color: #166534; font-weight: bold; } .st-fail { color: #b91c1c; font-weight: bold; }
.st-warn { color: #b45309; font-weight: bold; }
.alert { border: 2px solid #b45309; background: #fffbeb; padding: 8px 10px; margin: 8px 0; break-inside: avoid; }
.blank { display: inline-block; min-width: 70px; border-bottom: 0.8px solid #1b1b1b; height: 11px; }
.box { font-size: 10pt; }
td.wide { width: 46%; }
table.ids td:first-child { white-space: nowrap; }
.sig3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; margin-top: 22px; break-inside: avoid; }
.sig3 div { border-top: 0.8px solid #1b1b1b; padding-top: 3px; font-size: 8pt; color: #444; }
</style>"""

STATUS = {"PASS": "st-pass", "WITHIN": "st-pass", "FAIL": "st-fail", "WAIVER REQUIRED": "st-warn", "ABOVE AVERAGE": "st-warn"}
DECISION = {"ECM": ("Install (ECM)", "st-pass"),
            "H&S": ("Install (H&S)", "st-warn"),
            "Not cost-effective": ("Not installed", "st-fail")}
BOX = '<span class="box">☐</span>'
BLANK = '<span class="blank"></span>'


def st(s):
    return f'<span class="{STATUS.get(s, "")}">{t(s)}</span>'


def pf(flag):
    return st("PASS" if flag else "FAIL")


def money(x):
    return f"${x:,.0f}"


def _date(p, key):
    return datetime.date.fromisoformat(p["project"][key])


def _start(p, doc, date):
    o = page_start(p, doc, date)
    o.append(EXTRA_CSS)
    return o


def _sample(p, o, text):
    if p["project"].get("sample"):
        o.append(f'<div class="sample">SAMPLE DOCUMENT – {t(p["project"]["note"])} {text}</div>')


def _ach50(p, cfm50):
    return cfm50 * 60 / p["dwelling"]["volume"]


def _lines(lines):
    return "<br>".join(f"{t(x['item'])}: {x['qty']:g} {t(x['unit'])} × ${x['unit_price']:,.2f}" + (" <i>(IRM)</i>" if x.get("irm") else "")
                       for x in lines)


# ================================================================ Audit Report
def audit_html(p, A, date=None):
    date = date or datetime.date.today()
    pj, hh, dw, c, pr, pg = p["project"], p["household"], p["dwelling"], p["climate"], p["prices"], p["program"]
    dg = p["diagnostics"]
    doc = "Home Energy Audit Report – Weatherization"
    o = _start(p, doc, date)
    ecm = [x for x in A.measures if x.decision == "ECM"]
    cost_pre, cost_post = A.pre.cost(pr), A.post.cost(pr)
    caz_fail = [r for r in A.caz if not r[3]]

    o.append("<h1>Home Energy Audit Report</h1>")
    o.append('<div class="sub">Weatherization Assistance Program · energy audit with savings-to-investment ratio (10 CFR 440.21) · '
             "combustion safety and health &amp; safety (ANSI/BPI-1200, state H&amp;S plan) · ventilation (ASHRAE 62.2-2016)</div>")
    _sample(p, o, "Calculations use a simplified hourly model calibrated to the billing history. Program submittals are produced with "
                  "the DOE-approved audit tool of the grantee (e.g. NEAT/MHEA or an approved priority list).")
    o.append('<div class="verdict">'
             f'<div class="big">Recommended scope: {len(ecm)} energy measures · package SIR {A.package.sir:.2f} · '
             f'{money(A.package.dollars)} per year</div>'
             f"<div>Energy measures incl. incidental repairs {money(A.costs['ecm'])} · health &amp; safety {money(A.costs['hs'])} · "
             f"total {money(A.costs['total'])}. Predicted annual energy cost {money(cost_pre)} → {money(cost_post)} "
             f"(incl. new ventilation fan).</div></div>")
    if caz_fail or A.costs["hs"] > pg["hs_waiver_above"]:
        items = []
        if caz_fail:
            items.append(f"{len(caz_fail)} combustion safety / gas test(s) failed – must be corrected before or during weatherization "
                         "and re-tested before the crew leaves each day (section 2).")
        if A.costs["hs"] > pg["hs_waiver_above"]:
            items.append(f"H&amp;S cost {money(A.costs['hs'])} exceeds the per-unit threshold of {money(pg['hs_waiver_above'])}: "
                         "waiver from the state monitor required before the work order is released.")
        o.append('<div class="alert"><b>Action required</b><ul>' + "".join(f"<li>{x}</li>" for x in items) + "</ul></div>")

    o.append(info([
        ("Client", f"{t(pj['client'])} · {t(hh['tenure'])} · household of {hh['size']}"),
        ("Address", t(pj["address"])),
        ("Program", t(pj["program"])),
        ("Agency / job no.", f"{t(pj['agency'])} · {t(pj['job_no'])}"),
        ("Eligibility / priority", f"{t(hh['eligibility'])} · priority: {t(', '.join(hh['priority']))}"),
        ("Dwelling", f"{t(dw['type'])}, built {dw['year_built']}, {n(dw['cfa'])} ft² above grade + {n(dw['basement_area'])} ft² basement, "
                     f"{dw['bedrooms']} bedrooms"),
        ("Climate", f"IECC climate zone {t(c['climate_zone'])} · {t(c['location'])} · normal year {n(A.clim.hdd65)} HDD65 / "
                    f"{n(A.clim.cdd65)} CDD65"),
        ("Audit date", f"{_date(p, 'audit_date'):%m/%d/%Y} · report issued {date:%m/%d/%Y}"),
        ("Energy auditor", f"{t(pj['prepared_by']['name'])}, {t(pj['prepared_by']['credentials'])}"),
        ("Audit tool", "eco-energieberater sample model (hourly, single zone, bill-calibrated) – for illustration only"),
    ]))
    burden_pre = cost_pre / hh["income_annual"]
    burden_post = cost_post / hh["income_annual"]
    o.append(tiles([
        (f"{n(A.pre_state.cfm50)}", f"CFM50 before ({_ach50(p, A.pre_state.cfm50):.1f} ACH50)"),
        (f"≤ {n(A.post_state.cfm50)}", f"CFM50 target ({_ach50(p, A.post_state.cfm50):.1f} ACH50)"),
        (f"{A.package.sir:.2f}", "Package SIR (≥ 1.0 required)"),
        (money(A.package.dollars), f"Savings per year ({A.package.dollars / cost_pre:.0%} of energy cost)"),
        (f"{n(A.package.therms)} therms", "Gas savings per year"),
        (f"{n(A.package.kwh)} kWh", "Electricity savings per year"),
        (f"{burden_pre:.1%} → {burden_post:.1%}", "Energy burden (cost / income)"),
        (money(A.costs["total"]), "Total job cost (ECM + H&S)"),
    ]))
    o.append('<h2 class="pb">Program checks</h2>')
    o.append(table(["Check", "This unit", "Requirement", "Status"], [(t(a), t(b), t(cc), st(d)) for a, b, cc, d in A.checks], cls="s"))
    o.append(f'<p class="note">Limits: {t(pg["source"])}. The ACPU limit applies to the average of all units the agency completes in the '
             "program year, not to each unit. H&amp;S costs are budgeted separately and are not part of the SIR.</p>")

    # ------------------------------------------------------------ 1 Building and systems
    o.append("<h2>1 Building and systems as found</h2>")
    ua_tot = A.pre.ua_env + A.pre.ua_air
    rows = []
    for comp in p["envelope"]:
        ua = comp["area"] * comp["U"] * comp.get("b", 1.0)
        rows.append((t(comp["name"]), t(comp["desc"]), n(comp["area"]), f"{comp['U']:.3f}", f"{comp.get('b', 1.0):.1f}", n(ua, 1),
                     f"{ua / ua_tot:.0%}"))
    rows.append(("Air leakage", f"{n(A.pre_state.cfm50)} CFM50 ÷ N-factor {dg['blower_door']['n_factor']:g} = {A.pre.q_air:.0f} cfm natural",
                 "", "", "", n(A.pre.ua_air, 1), f"{A.pre.ua_air / ua_tot:.0%}"))
    rows.append(("Total", "", "", "", "", n(ua_tot, 1), "100%"))
    o.append(table(["Component", "Description", "Area ft²", "U Btu/h·ft²·°F", "ΔT factor", "UA Btu/h·°F", "Share"], rows, cls="s",
                   num=(2, 3, 4, 5, 6), row_cls=[""] * (len(rows) - 1) + ["sum"]))
    o.append(f'<p class="note">Basement inside the thermal and pressure boundary. Ground-coupled components with a reduced temperature '
             f"difference (factor b). Windows: {t(p['windows']['desc'])}, SHGC {p['windows']['shgc']}.</p>")
    o.append(table(["System", "As found", "Notes"], [
        ("Heating", t(p["heating"]["desc"]), f"{t(p['heating']['efficiency_note'])}; distribution efficiency {p['heating']['dse']:.2f}"),
        ("Cooling", t(p["cooling"]["desc"]), f"about {p['cooling']['fraction_cooled']:.0%} of the house cooled"),
        ("Water heating", t(p["dhw"]["desc"]), f"setpoint {p['dhw']['t_hot']} °F, showerhead {p['dhw']['shower_gpm']} gpm"),
        ("Refrigerator", t(p["baseload"]["refrigerator"]["desc"]),
         f"{n(p['baseload']['refrigerator']['metered_kwh_yr'])} kWh/yr metered – {t(p['baseload']['refrigerator']['metering'])}"),
        ("Lighting", f"{sum(x['n'] for x in p['baseload']['lamps'])} lamps inventoried, {n(A.pre_state.lighting_kwh)} kWh/yr",
         "; ".join(f"{t(x['location'])} {x['n']}×{x['w']} W" for x in p["baseload"]["lamps"])),
        ("Thermostat", f"heating {p['thermostat']['heating']} °F, cooling {p['thermostat']['cooling']} °F", t(p["thermostat"]["note"])),
    ], cls="s"))

    # ------------------------------------------------------------ 2 Diagnostics
    o.append("<h2>2 Diagnostic testing and combustion safety</h2>")
    bd = dg["blower_door"]
    o.append(table(["Test", "Result", "Notes"], [
        ("Blower door (pre)", f"{n(bd['pre_cfm50'])} CFM50 · {_ach50(p, bd['pre_cfm50']):.1f} ACH50 · volume {n(p['dwelling']['volume'])} ft³",
         f"{t(bd['setup'])}. Outdoor {bd['outdoor_f']} °F, {t(bd['wind'])}."),
        ("Duct diagnostics", t(dg["duct"]["pressure_pan"]), t(dg["duct"]["note"])),
        ("Radon", f"{dg['radon']['result_pci_l']} pCi/L", f"{t(dg['radon']['method'])}. {t(dg['radon']['consent'])}."),
    ], cls="s"))
    z = dg["caz"]
    o.append(f"<h3>Combustion appliance zone – {t(z['zone'])}</h3>")
    o.append(table(["Test", "Measured", "Action level", "Status"], [(t(a), t(b), t(cc), pf(d)) for a, b, cc, d in A.caz], cls="s"))
    o.append(f'<p class="note">Worst-case set-up: {t(z["worst_case_setup"])}. Cause of the depressurization: {t(z["cause"])} '
             f"{t(p['caz_limits']['source'])}.</p>")
    o.append('<p class="note">CAZ depressurization and spillage tests are repeated after the work and before the crew leaves on any day '
             "when air sealing, duct sealing or new exhaust fans could affect draft.</p>")

    # ------------------------------------------------------------ 3 Billing analysis
    b = A.bill
    o.append("<h2>3 Billing analysis and model calibration</h2>")
    rows = [(t(r["period"]), r["days"], n(r["hdd65"]), n(r["therms"]), f"{r['therms'] / r['days']:.2f}", n(r["kwh"])) for r in b.rows]
    rows.append(("12 months", sum(r["days"] for r in b.rows), n(b.actual_hdd), n(b.actual_therms), "", n(b.elec_annual)))
    o.append(table(["Billing period", "Days", "HDD65", "Gas therms", "therms/day", "Electric kWh"], rows, cls="s", num=(1, 2, 3, 4, 5),
                   row_cls=[""] * len(b.rows) + ["sum"]))
    o.append(f'<p class="note">{t(p["bills"]["source"])}.</p>')
    o.append('<div class="fig">' + charts.billing_scatter(A) + "</div>")
    o.append(table(["Item", "Gas, therms/yr", "Notes"], [
        ("Billed, actual year", n(b.actual_therms), f"{n(b.actual_hdd)} HDD65 – {(1 - b.actual_hdd / b.normal_hdd):.0%} warmer than normal"),
        ("Baseload (water heating, cooking)", n(b.base_annual), f"model: water heating {n(A.pre.dhw_therms)} + cooking {n(A.pre.cooking_therms)}"),
        ("Heating, weather-normalized", n(b.heat_normalized), f"{b.slope:.3f} therms per HDD × {n(b.normal_hdd)} HDD65"),
        ("Model heating before calibration", n(b.model_heat_raw), "hourly single-zone model, normal year"),
        ("Calibration factor", f"{b.calibration:.2f}", "applied to all heating results and savings"),
    ], cls="s", num=(1,)))
    o.append(table(["Electric end use", "kWh/yr", "Basis"], [
        ("Refrigerator", n(A.pre.fridge_kwh), "metered"),
        ("Lighting", n(A.pre.light_kwh), "lamp inventory × reported hours"),
        ("Window AC", n(A.pre.cool_kwh), "model, normal year"),
        ("Other plug loads, furnace blower", n(A.pre.other_kwh), "billed total minus identified end uses"),
        ("Total = billed", n(A.pre.elec), "12 months"),
    ], cls="s", num=(1,), row_cls=["", "", "", "", "sum"]))

    # ------------------------------------------------------------ 4 Measures
    o.append('<h2 class="pb">4 Energy conservation measures and SIR</h2>')
    o.append('<p>Each candidate measure is first evaluated alone. The package is then built step by step: in each round the measure with '
             "the highest SIR in the current state of the house is added, so that interactions (e.g. less heating after insulation "
             "reduces the value of a new furnace) are counted. Measures that no longer reach SIR 1.0 are not installed. Incidental "
             "repairs (IRM) needed to install a measure are part of its cost.</p>")
    ec = p["economics"]
    o.append(f'<div class="formula">SIR = Σ<sub>fuel</sub> (annual savings × price × UPV*<sub>fuel, life</sub>) ÷ installed cost · UPV* = '
             f"Σ<sub>t=1..N</sub> ((1+e)/(1+d))<sup>t</sup> with d = {ec['discount_rate']:.1%} real, e = "
             f"{ec['escalation']['gas']:+.1%} gas / {ec['escalation']['electric']:+.1%} electric</div>")
    rows, cls = [], []
    for x in sorted(A.measures, key=lambda z: (z.rank is None, z.rank or 0, -z.pkg.sir)):
        lab, c_ = DECISION[x.decision]
        rows.append((t(x.m["id"]), t(x.m["name"]), money(x.cost), x.m["life"], money(x.alone.dollars), f"{x.alone.sir:.2f}",
                     x.rank or "–", n(x.pkg.therms), n(x.pkg.kwh), money(x.pkg.dollars), f"<b>{x.pkg.sir:.2f}</b>",
                     f'<span class="{c_}">{lab}</span>'))
        cls.append("")
    rows.append(("", "ECM package (installed energy measures)", money(A.costs["ecm"]), "", "", "", "", n(A.package.therms), n(A.package.kwh),
                 money(A.package.dollars), f"<b>{A.package.sir:.2f}</b>", ""))
    cls.append("tot")
    o.append(table(["ID", "Measure", "Cost", "Life yr", "Alone $/yr", "Alone SIR", "Rank", "Pkg therms", "Pkg kWh", "Pkg $/yr", "Pkg SIR",
                    "Decision"], rows, cls="s ids", num=(2, 3, 4, 5, 6, 7, 8, 9, 10), row_cls=cls))
    o.append('<p class="note">Install (ECM): SIR ≥ 1.0 in package order, funded as energy measure. Install (H&amp;S): required to correct a '
             "health &amp; safety failure, funded from the H&amp;S budget and not part of the package SIR. Not installed: SIR below 1.0.</p>")
    o.append('<div class="fig">' + charts.sir_bars(A, pg["sir_min"]) + "</div>")
    o.append(f'<p class="note">Prices: gas ${pr["gas_per_therm"]:.2f}/therm, electricity ${pr["elec_per_kwh"]:.2f}/kWh ({t(pr["source"])}). '
             f"{t(ec['source'])}. Measure lives as applied in this sample; the state-approved audit procedure sets them. "
             f"Present value of package savings {money(A.package.pv)}.</p>")
    for x in A.measures:
        if x.decision != "ECM":
            why = x.m.get("hs_fallback") if x.decision == "H&S" else (
                f"SIR {x.pkg.sir:.2f} after the envelope measures (alone {x.alone.sir:.2f}). The existing equipment tested safe; "
                "replacement is reconsidered only if it fails or becomes a health & safety issue.")
            o.append(f"<p><b>{t(x.m['id'])} {t(x.m['name'])}:</b> {t(why)}</p>")

    # ------------------------------------------------------------ 5 Health and safety
    o.append("<h2>5 Health and safety</h2>")
    rows = [(t(h["id"]), t(h["item"]), t(h["finding"]), t(h["action"]), money(h["cost"]), t(h["funding"])) for h in A.hs]
    rows.append(("", "Total health &amp; safety", "", "", money(A.costs["hs"]), ""))
    o.append(table(["ID", "Item", "Finding", "Required action", "Cost", "Funding"], rows, cls="s ids", num=(4,),
                   row_cls=[""] * len(A.hs) + ["tot"]))
    o.append("<h3>Deferral screening</h3>")
    o.append(table(["Condition", "Finding"], [(t(a), t(b_)) for a, b_ in p["deferral_screen"]], cls="s"))
    o.append('<p class="note">Result: no condition requires deferral. A condition found later (hidden structural damage, asbestos, '
             "knob-and-tube wiring) stops the work until the auditor has reassessed the job.</p>")

    v0, v1, vs = A.vent_pre, A.vent_post, p["ventilation_62_2"]
    o.append("<h3>Ventilation – ASHRAE 62.2-2016 (existing building)</h3>")
    rows = [
        ("Floor area / bedrooms", f"{n(vs['floor_area'])} ft² / {p['dwelling']['bedrooms']}", "same"),
        ("Q_tot = 0.03 · A + 7.5 · (N_br + 1)", f"{v0['q_tot']:.1f} cfm", f"{v1['q_tot']:.1f} cfm"),
        ("Blower door Q50", f"{n(v0['cfm50'])} CFM50 (test)", f"{n(v1['cfm50'])} CFM50 (target)"),
        (f"Q_inf = 0.052 · Q50 · wsf ({vs['wsf']}) · (H/8.2)^0.4, H = {vs['height_ft']} ft", f"{v0['q_inf']:.1f} cfm", f"{v1['q_inf']:.1f} cfm"),
    ]
    for (room, req, have0, cr, d0), (_, _, have1, _, d1) in zip(v0["rows"], v1["rows"]):
        rows.append((f"Local exhaust {t(room)}: required {req} cfm, window credit {cr} cfm",
                     f"existing {have0} cfm → deficit {d0:.0f}", f"proposed {have1} cfm → deficit {d1:.0f}"))
    rows += [
        ("Q_tot,adj = Q_tot + 0.25 · Σ deficits", f"{v0['q_adj']:.1f} cfm", f"{v1['q_adj']:.1f} cfm"),
        ("Φ (unbalanced: Q_inf / Q_tot,adj)", f"{v0['phi']:.2f}", f"{v1['phi']:.2f}"),
        ("Required fan airflow Q_fan = Q_tot,adj − Φ · Q_inf", f"<b>{v0['q_fan']:.0f} cfm</b>", f"<b>{v1['q_fan']:.0f} cfm</b>"),
        ("Installed continuous fan", "none", f"<b>{vs['continuous_fan_cfm']} cfm</b> {pf(vs['continuous_fan_cfm'] >= v1['q_fan'])}"),
    ]
    o.append(table(["Step", "As found", "After weatherization"], rows, cls="s"))
    o.append(f'<p class="note">Fan: {t(vs["fan_desc"])}. {t(vs["source"])}. The calculation is updated with the final blower door result; '
             "if the house ends up tighter than the target, the fan rate is increased. ASHRAE 62.2 does not account for unusual "
             "pollutant sources and does not guarantee indoor air quality.</p>")

    # ------------------------------------------------------------ 6 Costs and results
    o.append("<h2>6 Cost summary and predicted results</h2>")
    o.append(table(["Budget category", "Cost", "Program reference"], [
        ("Energy conservation measures (incl. incidental repairs " + money(A.costs["irm"]) + ")", money(A.costs["ecm"]),
         f"counts toward ACPU average {money(A.costs['acpu'])}"),
        ("Health &amp; safety (separate budget)", money(A.costs["hs"]),
         f"average limit {money(A.costs['hs_avg'])} · unit waiver above {money(A.costs['hs_waiver'])}"),
        ("Total job cost", money(A.costs["total"]), ""),
    ], cls="s", num=(1,), row_cls=["", "", "tot"]))
    o.append('<p class="note">Program support, audit and inspection costs of the agency are not included.</p>')
    pre, pk, po = A.pre, A.pkg, A.post
    rows = [
        ("Space heating, therms", n(pre.heat_therms), n(pk.heat_therms), n(po.heat_therms)),
        ("Water heating, therms", n(pre.dhw_therms), n(pk.dhw_therms), n(po.dhw_therms)),
        ("Cooking, therms", n(pre.cooking_therms), n(pk.cooking_therms), n(po.cooking_therms)),
        ("Window AC, kWh", n(pre.cool_kwh), n(pk.cool_kwh), n(po.cool_kwh)),
        ("Lighting, kWh", n(pre.light_kwh), n(pk.light_kwh), n(po.light_kwh)),
        ("Refrigerator, kWh", n(pre.fridge_kwh), n(pk.fridge_kwh), n(po.fridge_kwh)),
        ("Other electric, kWh", n(pre.other_kwh), n(pk.other_kwh), n(po.other_kwh)),
        ("Total gas, therms", n(pre.gas), n(pk.gas), n(po.gas)),
        ("Total electricity, kWh", n(pre.elec), n(pk.elec), n(po.elec)),
        ("Site energy, MMBtu", n(pre.mmbtu(), 1), n(pk.mmbtu(), 1), n(po.mmbtu(), 1)),
        ("Annual energy cost", money(pre.cost(pr)), money(pk.cost(pr)), money(po.cost(pr))),
    ]
    o.append(table(["Normal-year energy use", "As found", "ECM package", "After all work (incl. H&S, ventilation)"], rows, cls="s",
                   num=(1, 2, 3), row_cls=[""] * 7 + ["sum", "sum", "sum", "tot"]))
    o.append('<div class="fig">' + charts.cost_bars(A, pr) + "</div>")
    o.append(f'<p class="note">The last column includes the H&amp;S duct sealing and the continuous {vs["continuous_fan_cfm"]} cfm exhaust fan '
             f"({n(po.q_air)} cfm combined air exchange). Predicted savings are engineering estimates; program evaluations often find "
             "realized savings below audit predictions. Calibration to the bills reduces, but does not remove, this gap.</p>")

    # ------------------------------------------------------------ 7 Method
    o.append("<h2>7 Method and limitations</h2>")
    o.append(f'<p class="note">Hourly heat balance of one thermal zone (basement included) over a synthetic normal weather year '
             f"({t(c['source'])}). Heating and cooling loads from UA, natural infiltration (CFM50 ÷ N-factor, combined in quadrature with "
             "exhaust fan airflow), internal gains and solar gains; no thermal mass. Heating results scaled to the weather-normalized "
             "billing history (fixed 65 °F base). Water heating from hot-water use and UEF; baseload measures from metering and "
             "inventories. Utility income-qualified programs use their own measure lists and cost tests; the SIR screen shown here "
             "follows 10 CFR 440 for the DOE program.</p>")
    # ------------------------------------------------------------ 8 Client
    o.append('<h2 class="pb">8 Client education and consent</h2>')
    items = ["Audit results, recommended measures and measures not recommended explained",
             "Combustion safety findings and CO risks explained; CO and smoke alarm operation shown",
             "Radon informed consent signed; EPA 'A Citizen's Guide to Radon' provided",
             "Lead-safe work practices and pre-renovation information ('Renovate Right') provided",
             "Ventilation fan: purpose, controls, service switch and cleaning explained; occupant agrees not to switch it off",
             "Thermostat settings and water heater temperature discussed",
             "Schedule, access and occupant protection during work agreed"]
    o.append(table(["Item", "Done"], [(t(x), BOX) for x in items], cls="s"))
    o.append('<div class="sig3"><div>Energy auditor: ' + t(pj["prepared_by"]["name"]) + "<br>signature / date</div>"
             "<div>Client: " + t(pj["client"]) + "<br>signature / date</div><div>Agency approval (work order release)<br>signature / date</div></div>")

    o.append("</body></html>")
    return "".join(o)


# ================================================================ Work Order
def workorder_html(p, A, date=None):
    date = date or datetime.date.today()
    pj = p["project"]
    doc = "Work Order – Scope of Work"
    o = _start(p, doc, date)
    o.append("<h1>Work Order – Scope of Work</h1>")
    o.append(f'<div class="sub">Job {t(pj["job_no"])} · issued by {t(pj["agency"])} to {t(pj["contractor"]["company"])} · '
             "performance requirements from the energy audit (WPN 22-4)</div>")
    _sample(p, o, "Prices follow an illustrative agency price list.")
    o.append(info([
        ("Job / client", f"{t(pj['job_no'])} · {t(pj['client'])}"),
        ("Address", t(pj["address"])),
        ("Scheduled", t(pj["work_scheduled"])),
        ("Contractor", f"{t(pj['contractor']['company'])} · {t(pj['contractor']['license'])}"),
        ("Crew lead", t(pj["contractor"]["crew_lead"])),
        ("Energy auditor (questions, change orders)", f"{t(pj['prepared_by']['name'])} · {t(pj['prepared_by']['email'])}"),
        ("Occupant", t(p["household"]["occupant_notes"])),
    ]))
    bd = p["diagnostics"]["blower_door"]
    z = p["diagnostics"]["caz"]
    o.append("<h2>Test targets and stop-work conditions</h2>")
    o.append(table(["Item", "Before", "Target / limit"], [
        ("Blower door", f"{n(bd['pre_cfm50'])} CFM50", f"≤ {n(A.post_state.cfm50)} CFM50 – if below {n(A.post_state.cfm50 * 0.85)} CFM50 "
                                                       "call the auditor (ventilation rate is recalculated)"),
        ("Worst-case CAZ depressurization", f"{z['worst_pa'] - z['base_pa']:+.1f} Pa"
         + (" (FAIL)" if z["worst_pa"] - z["base_pa"] < z["limit_pa"] else ""), f"≥ {z['limit_pa']:+.1f} Pa, tested at the end of every work day"),
        ("Spillage, each natural-draft appliance at worst case",
         ", ".join(f"{a['name']} {a['spillage_worst_s']} s" + (" (FAIL)" if a["spillage_worst_s"] > p["caz_limits"]["spillage_s"] else "")
                   for a in z["appliances"]), f"stops ≤ {p['caz_limits']['spillage_s']} s"),
        ("Ambient CO", f"{p['diagnostics']['ambient_co_max']} ppm", f"stop work and ventilate above {p['caz_limits']['ambient']} ppm"),
    ], cls="s"))
    o.append('<div class="alert"><b>Stop work and call the auditor</b> if: CAZ test fails after the day\'s work, a gas leak is found, '
             "suspected asbestos or vermiculite, knob-and-tube wiring, structural damage or moisture problems are uncovered, or the "
             "occupant asks to stop. No work outside this order without a signed change order.</div>")

    o.append("<h2>Scope of work</h2>")
    head = ["ID", "Measure / location", "Specification", "Line item", "Qty", "Unit", "Unit price", "Amount"]

    def block(items):
        rows, sub = [], 0.0
        for ident, name, loc, spec, sws, lines in items:
            for i, x in enumerate(lines):
                amt = x["qty"] * x["unit_price"]
                sub += amt
                first = i == 0
                rows.append((t(ident) if first else "", (f"<b>{t(name)}</b><br>{t(loc)}" if first else ""),
                             (f"{t(spec)}<br><i>{t(sws)}</i>" if first else ""),
                             t(x["item"]) + (" <i>(IRM)</i>" if x.get("irm") else ""), f"{x['qty']:g}", t(x["unit"]),
                             f"${x['unit_price']:,.2f}", money(amt)))
        rows.append(("", "Subtotal", "", "", "", "", "", money(sub)))
        return table(head, rows, cls="s ids", num=(4, 6, 7), row_cls=[""] * (len(rows) - 1) + ["sum"]), sub

    ecm_items = [(m["id"], m["name"], m["location"], m["spec"], m["sws"], m["lines"])
                 for m in (x.m for x in A.measures if x.decision == "ECM")]  # Reihenfolge der Projektdatei = Einbaureihenfolge
    hs_items = []
    for h in A.hs:
        m = next((x.m for x in A.measures if x.m["id"] == h["id"]), None)
        hs_items.append((m["id"], m["name"], m["location"], m["spec"], m["sws"], m["lines"]) if m else
                        (h["id"], h["item"], "", h["action"], h.get("sws", ""), h["lines"]))
    o.append("<h3>A – Energy conservation measures (DOE WAP program operations)</h3>")
    html_a, sub_a = block(ecm_items)
    o.append(html_a)
    o.append("<h3>B – Health &amp; safety (separate H&amp;S budget)</h3>")
    html_b, sub_b = block(hs_items)
    o.append(html_b)
    o.append(table(["Work order total", "Amount"], [("A – Energy conservation measures", money(sub_a)),
                                                    ("B – Health &amp; safety", money(sub_b)),
                                                    ("Total work order", money(sub_a + sub_b))],
                   cls="s", num=(1,), row_cls=["", "", "tot"]))
    o.append('<p class="note">SWS = DOE/NREL Standard Work Specifications as adopted in the state field guide. Measures evaluated in the audit '
             "but not cost-effective are not part of this order: "
             + t(", ".join(f"{x.m['id']} {x.m['name']}" for x in A.measures if x.decision == "Not cost-effective")) + ".</p>")

    o.append("<h2>Materials (estimate)</h2>")
    mat_rows = [(t(k), t(next(x.m["name"] for x in A.measures if x.m["id"] == k)), t(v["text"])) for k, v in A.materials.items()]
    o.append(table(["ID", "Measure", "Quantity"], mat_rows, cls="s ids"))
    o.append('<p class="note">Check coverage against the manufacturer\'s bag label (R-value, thickness and coverage per bag) and post the '
             "attic insulation certificate at the hatch.</p>")

    o.append("<h2>Daily combustion safety log</h2>")
    o.append(table(["Date", "Work done", "Worst-case CAZ Pa", "Spillage WH s", "Spillage furnace s", "Ambient CO ppm", "Pass", "Initials"],
                   [(BLANK, BLANK, BLANK, BLANK, BLANK, BLANK, BOX, BLANK) for _ in range(4)], cls="s"))
    o.append("<h2>Documentation to return with the invoice</h2>")
    docs = ["Before/after photos of every measure (attic depth rulers, hatch dam, baffles, wall plugs, rim joist, duct seams, fan, alarms)",
            "Attic insulation certificate, cellulose bag count and wall density check",
            "Final blower door reading and daily CAZ log (above)",
            "Fan flow measurement of the bath fan at continuous and boost speed",
            "EPA RRP records: certified renovator, containment, cleaning verification",
            "Refrigerator recycling receipt, product data of installed equipment",
            "Signed change orders (if any)"]
    o.append(table(["Document", "Attached"], [(t(x), BOX) for x in docs], cls="s"))
    o.append("<h2>Change orders</h2>")
    o.append(table(["No.", "Description / reason", "Amount", "Auditor approval", "Date"], [(BLANK, BLANK, BLANK, BLANK, BLANK) for _ in range(3)],
                   cls="s"))
    o.append('<div class="sig3"><div>Issued – energy auditor / agency<br>signature / date</div>'
             "<div>Accepted – contractor crew lead<br>signature / date</div><div>Work completed – contractor<br>signature / date</div></div>")
    o.append("</body></html>")
    return "".join(o)


# ================================================================ Final Inspection
VERIFY = {
    "air_sealing": "Bypasses sealed as specified (photos); chimney chase sealed with non-combustible material and clearance kept",
    "envelope": "Coverage, thickness/density and finish as specified; photo record matches",
    "dse": "All listed seams sealed with mastic; filter slot covered; pressure pan at returns improved",
    "heating_eff": "Equipment installed per specification",
    "showerhead": "Low-flow showerhead installed, no leaks",
    "dhw_factor": "Pipe insulation installed, clearance to draft hood kept",
    "lighting": "LED lamps installed as listed, old lamps removed",
    "refrigerator": "New unit label kWh/yr as specified; recycling receipt for the old unit",
}


def inspection_html(p, A, date=None):
    date = date or datetime.date.today()
    pj = p["project"]
    doc = "Final Inspection – Quality Control"
    o = _start(p, doc, date)
    o.append("<h1>Final Inspection – Quality Control Inspection</h1>")
    o.append('<div class="sub">Every unit reported as complete receives a final inspection led by a certified Quality Control Inspector, '
             "including an assessment of the energy audit (DOE WAP Quality Work Plan, WPN 22-4)</div>")
    _sample(p, o, "Form pre-filled from the work order; fields are completed on site by the QCI.")
    o.append(info([
        ("Job / client", f"{t(pj['job_no'])} · {t(pj['client'])} · {t(pj['address'])}"),
        ("Contractor", t(pj["contractor"]["company"])),
        ("Energy auditor", t(pj["prepared_by"]["name"])),
        ("Quality control inspector", t(pj["qci"])),
        ("Inspection date", BLANK),
    ]))

    o.append("<h2>1 Assessment of the energy audit</h2>")
    items = ["Field data match the audit inputs (areas, existing R-values, equipment, lamp and appliance inventory)",
             "Audit tool inputs and outputs reviewed (billing data, calibration, measure costs and lives)",
             "Measures on the work order are those called for by the approved audit procedure (SIR ≥ 1 or H&S)",
             "H&S items are allowable and documented (incl. waiver where required)"]
    o.append(table(["Item", "Yes", "No", "Comment"], [(t(x), BOX, BOX, BLANK) for x in items], cls="s"))

    o.append("<h2>2 Installed measures</h2>")
    rows = []
    for x in (x for x in A.measures if x.installed):
        m = x.m
        req = m["spec"]
        if m["type"] == "envelope":
            mt = A.materials.get(m["id"])
            req = f"{m['name']}: U ≤ {m['U_new']:.3f}" + (f"; {mt['text']}" if mt else "")
        rows.append((t(m["id"]), t(m["name"]), t(req), t(VERIFY[m["type"]]), BOX, BOX))
    for h in A.hs:
        if not h.get("from_measure"):
            rows.append((t(h["id"]), t(h["item"]), t(h["action"]), "Installed and functional as specified", BOX, BOX))
    o.append(table(["ID", "Measure", "Performance requirement", "Verify", "Pass", "Fail"], rows, cls="s ids"))

    o.append('<h2 class="pb">3 Post-work testing</h2>')
    z, lim = p["diagnostics"]["caz"], p["caz_limits"]
    rows = [
        ("Blower door", f"≤ {n(A.post_state.cfm50)} CFM50 (pre {n(A.pre_state.cfm50)})", BLANK + " CFM50"),
        ("Worst-case CAZ depressurization", f"≥ {z['limit_pa']:+.1f} Pa", BLANK + " Pa"),
    ]
    for a in z["appliances"]:
        rows.append((f"Spillage at worst case – {t(a['name'])}", f"stops ≤ {lim['spillage_s']} s", BLANK + " s"))
        rows.append((f"Flue CO, air-free – {t(a['name'])}", f"≤ {lim['co_air_free'][a['type']]} ppm", BLANK + " ppm"))
    rows += [
        ("Oven CO, as measured", f"≤ {lim['oven_as_measured']} ppm", BLANK + " ppm"),
        ("Ambient CO", f"≤ {lim['ambient']} ppm", BLANK + " ppm"),
        ("Gas leak re-test (all connections)", "no leak", BLANK),
        ("Bath fan airflow, continuous / boost", f"≥ {p['ventilation_62_2']['continuous_fan_cfm']} cfm / ≥ 50 cfm", BLANK + " / " + BLANK + " cfm"),
        ("ASHRAE 62.2 calculation updated with final CFM50", f"required Q_fan ≤ installed {p['ventilation_62_2']['continuous_fan_cfm']} cfm",
         BLANK + " cfm"),
        ("Smoke/CO alarms test", "operating", BOX),
    ]
    o.append(table(["Test", "Requirement", "Result", "Pass"], [(a, b, c, BOX) for a, b, c in rows], cls="s"))

    o.append("<h2>4 Client</h2>")
    o.append(table(["Item", "Done"], [(t(x), BOX) for x in (
        "Occupant shown fan controls, alarms and any new equipment; manuals left",
        "Work area clean; lead-safe cleaning verification passed",
        "Occupant satisfied / complaints recorded below")], cls="s"))
    o.append("<h2>5 Result</h2>")
    o.append(table(["Result", ""], [
        (f"{BOX} PASS – all work meets the field guide; unit may be reported complete", ""),
        (f"{BOX} FAIL – return to contractor; items: {BLANK}{BLANK}{BLANK}", f"re-inspection {BLANK}"),
    ], cls="s"))
    o.append('<div class="sig3"><div>Quality control inspector – printed name<br><br>certification no.</div>'
             "<div>QCI signature / date</div><div>Client signature / date</div></div>")
    o.append("</body></html>")
    return "".join(o)
