"""HTML-Bericht (für den PDF-Druck) zu Heizlast und hydraulischem Abgleich."""

import datetime
from html import escape

from .abgleich import DT_LOG_N
from .zahlen import de

GRENZFALL_K = 2.0  # Heizkörper bis zu 2 K über Ziel-Vorlauf: Vorlauf anheben statt tauschen prüfen

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm;
  @bottom-left { content: "__FUSS__"; font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
  @bottom-right { content: "Seite " counter(page) " von " counter(pages); font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
}
* { box-sizing: border-box; }
body { font-family: 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif; font-size: 9pt; color: #1b1b1b; line-height: 1.35; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 2px; color: #14532d; }
h2 { font-size: 12pt; margin: 18px 0 6px; color: #14532d; border-bottom: 1.5px solid #14532d; padding-bottom: 2px; break-after: avoid; }
h3 { font-size: 10pt; margin: 12px 0 4px; break-after: avoid; }
p { margin: 4px 0; }
.untertitel { color: #444; margin-bottom: 10px; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 8px; }
th, td { border: 0.6px solid #b8b8b8; padding: 2.5px 4px; vertical-align: top; }
th { background: #eef4ef; font-weight: bold; text-align: left; font-size: 8pt; }
td.z, th.z { text-align: right; white-space: nowrap; }
tr.summe td { font-weight: bold; background: #f4f4f4; }
tr.tausch td { background: #fff4e5; }
table.klein td, table.klein th { font-size: 7.8pt; padding: 2px 3px; }
table.klein td:first-child { white-space: nowrap; }
table.info td:first-child { width: 28%; color: #444; }
.muster { border: 2px solid #b91c1c; color: #b91c1c; padding: 6px 10px; margin: 8px 0 10px; font-weight: bold; }
.wasserzeichen { position: fixed; top: 38%; left: 0; width: 100%; text-align: center; font-size: 110pt; font-weight: bold;
  color: rgba(185, 28, 28, 0.07); transform: rotate(-28deg); z-index: -1; letter-spacing: 8px; }
.kacheln { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 6px 0 4px; }
.kachel { border: 0.8px solid #b8b8b8; border-radius: 4px; padding: 6px 8px; break-inside: avoid; }
.kachel .wert { font-size: 14pt; font-weight: bold; color: #14532d; }
.kachel .lbl { font-size: 7.8pt; color: #444; }
.hinweis { font-size: 7.8pt; color: #444; }
.warn { color: #9a3412; }
ul { margin: 4px 0 4px 18px; padding: 0; }
li { margin: 2px 0; }
.raumblatt { break-inside: avoid; }
.seitenumbruch { break-before: page; }
.formel { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; background: #f6f6f6; padding: 4px 6px; margin: 4px 0; }
"""


def _t(x):
    return escape(str(x))


def _tabelle(kopf, zeilen, klasse="", zahlspalten=(), zeilenklassen=None):
    h = [f'<table class="{klasse}"><thead><tr>']
    for i, k in enumerate(kopf):
        h.append(f'<th class="{"z" if i in zahlspalten else ""}">{k}</th>')
    h.append("</tr></thead><tbody>")
    for j, z in enumerate(zeilen):
        kl = zeilenklassen[j] if zeilenklassen else ""
        h.append(f'<tr class="{kl}">')
        for i, c in enumerate(z):
            h.append(f'<td class="{"z" if i in zahlspalten else ""}">{c}</td>')
        h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def erzeuge_html(projekt, geb, abg, datum=None):
    datum = datum or datetime.date.today()
    pj = projekt["projekt"]
    klima = projekt["klima"]
    lue = projekt.get("lueftung", {})
    wb = projekt.get("waermebruecken", {})
    hyd = projekt["hydraulik"]
    muster = pj.get("muster", False)
    fuss = f"{pj['titel']} · Stand {datum:%d.%m.%Y} · Entwurf zur Prüfung"
    o = []
    o.append(f"<!doctype html><html lang='de'><head><meta charset='utf-8'><title>{_t(pj['titel'])}</title>")
    o.append(f"<style>{CSS.replace('__FUSS__', fuss.replace(chr(34), ''))}</style></head><body>")
    if muster:
        o.append('<div class="wasserzeichen">MUSTER</div>')

    # Kopf
    o.append("<h1>Heizlastberechnung und hydraulischer Abgleich</h1>")
    o.append('<div class="untertitel">Raumweise Norm-Heizlast in Anlehnung an DIN EN 12831-1 / DIN/TS 12831-1 (vereinfachtes Verfahren) · '
             "Hydraulischer Abgleich nach Verfahren B</div>")
    if muster:
        o.append(f'<div class="muster">MUSTERBERECHNUNG – {_t(pj.get("hinweis", ""))}</div>')
    if pj.get("warnung"):
        o.append(f'<div class="muster">{_t(pj["warnung"])}</div>')
    info = [
        ("Objekt", pj["titel"]),
        ("Adresse", pj.get("adresse", "–")),
        ("Baujahr", pj.get("baujahr", "–")),
        ("Beschreibung", pj.get("beschreibung", "–")),
        ("Stand", f"{datum:%d.%m.%Y} – Entwurf, Prüfung und Freigabe durch den Energieberater erforderlich"),
    ]
    o.append('<table class="info">' + "".join(f"<tr><td>{_t(a)}</td><td>{_t(b)}</td></tr>" for a, b in info) + "</table>")

    # Ergebnis-Kacheln
    getauscht = [h for h in abg.heizkoerper if h.getauscht]
    kacheln = [
        (f"{de(geb.phi_HL / 1000, 1)} kW", "Gebäude-Heizlast"),
        (f"{de(geb.spez)} W/m²", f"spezifisch, bezogen auf {de(geb.A, 1)} m² beheizte Fläche"),
        (f"{de(abg.theta_V, 1)} / {de(abg.theta_R_misch, 1)} °C", "Auslegung Vorlauf / Rücklauf (Mischtemperatur)"),
        (f"{de(abg.theta_V_bestand, 1)} °C", "nötiger Vorlauf mit allen Bestandsheizkörpern"),
        (f"{len(getauscht)} von {len(abg.heizkoerper)}", f"Heizkörper zu tauschen für ≤ {de(abg.theta_V_ziel)} °C Vorlauf"),
        (f"{de(abg.m_gesamt)} l/h", "Volumenstrom gesamt"),
        (f"{de(abg.foerderhoehe_m, 2)} m", f"Förderhöhe Heizkreispumpe ({de(abg.dp_verfuegbar / 100 + abg.dp_erzeuger / 100)} mbar)"),
        (f"{de(geb.summe_raumheizlasten / 1000, 1)} kW", "Summe der Raumheizlasten (für Heizflächen)"),
    ]
    o.append('<div class="kacheln">' + "".join(
        f'<div class="kachel"><div class="wert">{w}</div><div class="lbl">{_t(l)}</div></div>' for w, l in kacheln) + "</div>")
    o.append('<p class="hinweis">Nicht enthalten: Zuschläge für Warmwasserbereitung und EVU-Sperrzeiten bei der Auslegung des Wärmeerzeugers. '
             "Aufheizzuschlag: " + ("keiner (Betrieb ohne Nachtabsenkung)" if not projekt.get("aufheizzuschlag_W_m2") else
                                    f"{de(projekt['aufheizzuschlag_W_m2'])} W/m²") + ".</p>")

    # 1 Randbedingungen
    o.append("<h2>1 Randbedingungen</h2>")
    rb = [
        ("Norm-Außentemperatur θ<sub>e</sub>", f"{de(klima['theta_e'], 1)} °C" if "theta_e" in klima else "–", klima.get("quelle", "")),
        ("Jahresmittel Außentemperatur θ<sub>m,e</sub>", f"{de(klima['theta_m_e'], 1)} °C" if "theta_m_e" in klima else "–", "nur für erdberührte Bauteile"),
        ("Lüftung", _t(lue.get("art", "freie Lüftung")), ""),
        ("Luftwechsel n<sub>50</sub>", f"{de(lue.get('n50', 4.0), 1)} h⁻¹", _t(lue.get("n50_quelle", ""))),
        ("Mindestluftwechsel n<sub>min</sub>", f"{de(lue.get('n_min_standard', 0.5), 1)} h⁻¹", "je Raum, sofern nicht abweichend angegeben"),
        ("Wärmebrückenzuschlag ΔU<sub>WB</sub>", f"{de(wb.get('delta_U', 0.10), 2)} W/(m²K)", _t(wb.get("quelle", ""))),
    ]
    o.append(_tabelle(["Größe", "Wert", "Quelle / Bemerkung"], [(a, b, _t(c)) for a, b, c in rb], klasse="klein"))

    if projekt.get("bauteile"):
        o.append("<h3>Bauteilkatalog</h3>")
        o.append(_tabelle(
            ["Kürzel", "Bauteil", "U-Wert W/(m²K)"],
            [(_t(k), _t(v["bezeichnung"]), de(v["U"], 2)) for k, v in projekt["bauteile"].items()],
            klasse="klein", zahlspalten=(2,)))
    if projekt.get("angrenzend"):
        o.append("<h3>Angrenzende unbeheizte Bereiche</h3>")
        o.append(_tabelle(
            ["Bereich", "Beschreibung", "Temperatur-Korrekturfaktor b<sub>u</sub>"],
            [(_t(k), _t(v.get("hinweis", "")), de(v["b_u"], 2)) for k, v in projekt["angrenzend"].items()],
            klasse="klein", zahlspalten=(2,)))

    # 2 Raumweise Heizlast
    o.append("<h2>2 Raumweise Norm-Heizlast</h2>")
    zeilen = []
    for r in geb.raeume:
        zeilen.append((_t(r.geschoss), _t(r.name), de(r.theta_i), de(r.A, 1), de(r.V, 1),
                       "–" if r.vorgabe else de(r.phi_T), "–" if r.vorgabe else de(r.phi_V),
                       de(r.phi_HL) + (" *" if r.vorgabe else ""), de(r.spez)))
    teilweise = any(r.vorgabe for r in geb.raeume)
    zeilen.append(("", "Summe Raumheizlasten", "", de(geb.A, 1), de(sum(r.V for r in geb.raeume), 1),
                   "–" if teilweise else de(sum(r.phi_T for r in geb.raeume)),
                   "–" if teilweise else de(sum(r.phi_V for r in geb.raeume)),
                   de(geb.summe_raumheizlasten), de(geb.summe_raumheizlasten / geb.A)))
    zeilen.append(("", "Gebäude-Heizlast", "", de(geb.A, 1), "", "–" if teilweise else de(geb.phi_T),
                   "–" if teilweise else de(geb.phi_V), de(geb.phi_HL), de(geb.spez)))
    o.append(_tabelle(
        ["Geschoss", "Raum", "θ<sub>i</sub> °C", "A m²", "V m³", "Φ<sub>T</sub> W", "Φ<sub>V</sub> W", "Φ<sub>HL</sub> W", "W/m²"],
        zeilen, klasse="klein", zahlspalten=(2, 3, 4, 5, 6, 7, 8),
        zeilenklassen=[""] * len(geb.raeume) + ["summe", "summe"]))
    if teilweise:
        o.append('<p class="hinweis">* Raumheizlast vorgegeben (nicht aus Bauteilen berechnet), Quelle siehe Anhang A. '
                 "Die Gebäude-Heizlast ist hier die einfache Summe der Raumheizlasten.</p>")
    o.append('<p class="hinweis">Die Summe der Raumheizlasten dient der Heizflächenauslegung. Die Gebäude-Heizlast (Wärmeerzeuger) '
             "ist kleiner: Wärmeströme zwischen beheizten Räumen entfallen, und die Infiltration wird nur zur Hälfte angesetzt "
             "(Wind wirkt nicht auf alle Fassaden gleichzeitig). Wärmegewinne aus wärmeren Nachbarräumen (z. B. Bad) sind "
             "auf der sicheren Seite vernachlässigt.</p>")

    # 3 Hydraulischer Abgleich
    o.append("<h2>3 Hydraulischer Abgleich (Verfahren B)</h2>")
    ab = [
        ("System", _t(hyd.get("system", "Zweirohrheizung"))),
        ("Ziel-Vorlauftemperatur (Wärmepumpe)", f"{de(abg.theta_V_ziel, 1)} °C"),
        ("Auslegungsspreizung maßgebender Heizkörper", f"{de(abg.spreizung_ausl, 1)} K"),
        ("Heizkörper-Kennlinie", f"Φ = Φ<sub>N</sub> · (ΔT<sub>log</sub> / {de(DT_LOG_N, 2)} K)<sup>n</sup>, Φ<sub>N</sub> bei 75/65/20 °C (DIN EN 442)"),
        ("Rohrnetz (Abschätzung)", f"R = {de(hyd.get('R_Pa_pro_m', 100))} Pa/m, Einzelwiderstände +{de(100 * hyd.get('zuschlag_einzelwiderstaende', 0.3))} %, "
                                   "Vor- und Rücklauf (2 × Leitungslänge)"),
        ("Mindest-Differenzdruck am Thermostatventil (ungünstigster Heizkörper)", f"{de(hyd.get('dp_ventil_min_mbar', 50))} mbar"),
        ("Druckverlust Wärmeerzeuger", f"{de(hyd.get('dp_erzeuger_mbar', 0))} mbar – {_t(hyd.get('dp_erzeuger_hinweis', ''))}"),
        ("Ventiltyp", _t(hyd.get("ventiltyp", "nicht angegeben"))),
    ]
    o.append('<table class="info klein">' + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in ab) + "</table>")

    if getauscht:
        o.append(f"<p>Mit allen Bestandsheizkörpern wären <b>{de(abg.theta_V_bestand, 1)} °C</b> Vorlauf nötig. "
                 f"Damit die Wärmepumpe mit höchstens {de(abg.theta_V_ziel)} °C auskommt, sind {len(getauscht)} Heizkörper zu tauschen "
                 f"(orange markiert). Der Abgleich ist für <b>{de(abg.theta_V, 1)} °C</b> Vorlauf mit den neuen Heizkörpern gerechnet.</p>")
    else:
        o.append(f"<p>Alle Bestandsheizkörper reichen bei <b>{de(abg.theta_V, 1)} °C</b> Vorlauf aus.</p>")

    o.append("<h3>3.1 Heizkörper – Leistung und Temperaturen</h3>")
    zeilen, kl = [], []
    for h in abg.heizkoerper:
        zeilen.append((_t(h.id), _t(h.raum), _t(h.beschreibung), de(h.phi_N), de(h.phi_soll), de(h.theta_V_erf, 1),
                       de(h.phi_N_ausl) + (" neu" if h.getauscht else ""), de(h.theta_R, 1), de(h.spreizung, 1), de(h.m)))
        kl.append("tausch" if h.getauscht else "")
    o.append(_tabelle(
        ["HK", "Raum", "Heizkörper Bestand", "Φ<sub>N</sub> Bestand W", "Φ<sub>soll</sub> W",
         f"VL nötig °C (σ = {de(abg.spreizung_ausl)} K)", "Φ<sub>N</sub> Auslegung W", "RL °C", "Spreizung K", "V̇ l/h"],
        zeilen, klasse="klein", zahlspalten=(3, 4, 5, 6, 7, 8, 9), zeilenklassen=kl))

    katalog = projekt.get("ventile", {})
    o.append("<h3>3.2 Druckverluste, Ventile und Voreinstellung</h3>")
    zeilen, kl = [], []
    for h in abg.heizkoerper:
        hinweise = list(h.hinweise)
        if h.getauscht and h.theta_V_erf - abg.theta_V_ziel <= GRENZFALL_K:
            hinweise.append(f"Grenzfall: alternativ Vorlauf auf {de(h.theta_V_erf, 1)} °C anheben statt tauschen")
        bez = katalog.get(h.ventil, {}).get("kurz", h.ventil)
        zeilen.append((_t(h.id), _t(h.raum), de(h.m), de(h.L, 1), de(h.dp_rohr / 100, 1), de(h.dp_ventil / 100, 1),
                       de(h.kv, 3), _t(bez), f"<b>{_t(h.einstellung)}</b>", de(h.m_ist),
                       "<br>".join(_t(x) for x in hinweise) or "–"))
        kl.append("tausch" if h.getauscht else "")
    o.append(_tabelle(
        ["HK", "Raum", "V̇ Soll l/h", "Leitung einfach m", "Δp Rohr mbar", "Δp Ventil mbar", "k<sub>v</sub> erf. m³/h",
         "Ventil", "Voreinstellung", "V̇ mit Einst. l/h", "Hinweise"],
        zeilen, klasse="klein", zahlspalten=(2, 3, 4, 5, 6, 9), zeilenklassen=kl))
    o.append('<div class="formel">V̇ = Φ<sub>soll</sub> / (1,163 · (θ<sub>V</sub> − θ<sub>R</sub>))  ·  '
             "Δp<sub>Rohr</sub> = 2 · L · R · (1 + Z)  ·  Δp<sub>Ventil</sub> = Δp<sub>verfügbar</sub> − Δp<sub>Rohr</sub>  ·  "
             "k<sub>v</sub> = V̇[m³/h] / √(Δp<sub>Ventil</sub>[bar])</div>")
    for k, v in katalog.items():
        if v.get("hinweis"):
            o.append(f'<p class="hinweis"><b>{_t(v.get("bezeichnung", k))}:</b> {_t(v["hinweis"])}</p>')
        if "stufen" in v:
            o.append(_tabelle(["Voreinstellung"] + [_t(x) for x in v["stufen"]],
                              [("k<sub>v</sub> m³/h",) + tuple(de(x, 2) for x in v["stufen"].values())],
                              klasse="klein", zahlspalten=tuple(range(1, len(v["stufen"]) + 1))))

    o.append("<h3>3.3 Heizkreispumpe – Auslegung</h3>")
    sens = []
    for dp in (0, 100, 200, 300):
        hh = abg.foerderhoehe_m + dp * 100 / 9810.0
        sens.append((f"{dp} mbar", de(hh, 2) + " m", de(hh * (1 + abg.reserve), 2) + " m"))
    o.append(_tabelle(
        ["Größe", "Wert"],
        [
            ("Auslegungsvolumenstrom", f"{de(abg.m_gesamt)} l/h ({de(abg.m_gesamt / 1000, 2)} m³/h)"),
            ("Differenzdruck Verteilnetz (ungünstigster Strang + Ventil)", f"{de(abg.dp_verfuegbar / 100)} mbar"),
            ("Druckverlust Wärmeerzeuger (in Rechnung)", f"{de(abg.dp_erzeuger / 100)} mbar"),
            ("Förderhöhe rechnerisch", f"{de(abg.foerderhoehe_m, 2)} m"),
            (f"Förderhöhe mit {de(100 * abg.reserve)} % Reserve = <b>Auslegungspunkt</b>",
             f"<b>{de(abg.m_gesamt / 1000, 2)} m³/h bei {de(abg.foerderhoehe_ausl_m, 2)} m</b>"),
            ("Hydraulische Leistung", f"{de(abg.p_hyd_W, 1)} W (elektrisch bei Hocheffizienzpumpe ca. {de(abg.p_hyd_W / 0.25, 0)} W, Annahme η ≈ 25 %)"),
            ("Pumpentyp", "Hocheffizienzpumpe (EEI ≤ 0,20), DN 25, Förderhöhe max. mind. 4 m, z. B. Baureihe 25-40 / 25-60 – "
                          "Auslegungspunkt liegt am unteren Ende der Kennlinie"),
            ("Regelungsart", "Konstantdruck (Δp-c), Sollwert = Auslegungsförderhöhe; die Voreinstellungen sind für konstanten Differenzdruck gerechnet"),
            ("Mischrücklauf bei Auslegung", f"{de(abg.theta_R_misch, 1)} °C (Systemspreizung {de(abg.theta_V - abg.theta_R_misch, 1)} K)"),
        ], klasse="klein info"))
    o.append("<p><b>Falls die Pumpe auch den Wärmeerzeuger durchströmen muss</b> (keine hydraulische Weiche/Pufferentkopplung): "
             "Der Druckverlust der Wärmepumpe beim Auslegungsvolumenstrom steht im Datenblatt des Geräts und kommt hinzu.</p>")
    o.append(_tabelle(["Druckverlust Wärmepumpe", "Förderhöhe", f"mit {de(100 * abg.reserve)} % Reserve"], sens,
                      klasse="klein", zahlspalten=(1, 2)))

    # 4 Prüfpunkte
    o.append("<h2>4 Prüfpunkte vor Freigabe</h2><ul>")
    pruef = []
    if any(r.vorgabe for r in geb.raeume):
        pruef.append("Vorgegebene Raumheizlasten durch die Werte der Heizlastberechnung des Kunden ersetzen und den Abgleich neu rechnen.")
    pruef += [
        "Norm-Außentemperatur und Jahresmitteltemperatur für die PLZ des Objekts nach DIN/TS 12831-1 einsetzen.",
        "Bauteilaufbauten und U-Werte anhand Baubeschreibung, Energieausweis oder Vor-Ort-Aufnahme bestätigen.",
        "Raummaße, Fenster- und Türflächen aus dem Aufmaß übernehmen (Außenmaße bei Außenbauteilen).",
        "n<sub>50</sub>: Messwert verwenden, falls ein Blower-Door-Test vorliegt.",
        "Heizkörper vor Ort aufnehmen (Bauart, Höhe, Länge, Hersteller) und Normleistung aus Herstellerunterlagen übernehmen.",
        "Danfoss-Ventiltyp vor Ort bestätigen (RA-N, RA-U, RAVL …) und die Voreinstellwerte gegen das aktuelle Datenblatt prüfen.",
        "Kermi-Heizkörper mit Ventileinsatz: Auslegungsleistung, Volumenstrom und k<sub>v</sub> aus Abschnitt 3.2 bei der Bestellung für die werkseitige Voreinstellung angeben.",
        "Leitungslängen je Heizkörper plausibilisieren; bei sehr alten Netzen Querschnitte prüfen.",
        "Warmwasser- und Sperrzeitenzuschlag für die Auslegung der Wärmepumpe ergänzen.",
        "Für Förderanträge (BEG) das VdZ-Formular „Bestätigung des hydraulischen Abgleichs“ auf Basis dieser Werte ausfüllen.",
    ]
    o.append("".join(f"<li>{p}</li>" for p in pruef) + "</ul>")

    # Anhang Raumblätter
    o.append('<h2 class="seitenumbruch">Anhang A – Raumblätter</h2>')
    o.append('<div class="formel">Φ<sub>T</sub> = Σ A · (U + ΔU<sub>WB</sub>) · f · (θ<sub>i</sub> − θ<sub>e</sub>)  ·  '
             "Φ<sub>V</sub> = 0,34 · max(V̇<sub>inf</sub>; V̇<sub>min</sub>) · (θ<sub>i</sub> − θ<sub>e</sub>)  ·  "
             "V̇<sub>inf</sub> = 2 · V · n<sub>50</sub> · e · ε  ·  V̇<sub>min</sub> = n<sub>min</sub> · V</div>")
    for r in geb.raeume:
        if r.vorgabe:
            o.append('<div class="raumblatt">')
            o.append(f"<h3>{_t(r.geschoss)} · {_t(r.name)} – θ<sub>i</sub> = {de(r.theta_i)} °C, A = {de(r.A, 1)} m²</h3>")
            o.append(f"<p>Raumheizlast Φ<sub>HL</sub> = <b>{de(r.phi_HL)} W</b> ({de(r.spez)} W/m²), vorgegeben. "
                     f"{_t(r.vorgabe_quelle)}</p></div>")
            continue
        o.append('<div class="raumblatt">')
        o.append(f"<h3>{_t(r.geschoss)} · {_t(r.name)} – θ<sub>i</sub> = {de(r.theta_i)} °C, A = {de(r.A, 1)} m², "
                 f"V = {de(r.V, 1)} m³</h3>")
        zeilen = []
        for b in r.bauteile:
            zeilen.append((_t(b.typ), _t(b.text), _t(b.an), de(b.A, 2), de(b.U, 2), de(b.dU, 2), de(b.f, 3), de(b.H, 2), de(b.phi)))
        zeilen.append(("", "Transmission", "", "", "", "", "", de(r.H_T, 2), de(r.phi_T)))
        zeilen.append(("", f"Lüftung: V̇<sub>inf</sub> = {de(r.V_inf, 1)}, V̇<sub>min</sub> = {de(r.V_min, 1)} m³/h", "", "", "", "", "",
                       de(r.H_V, 2), de(r.phi_V)))
        if r.phi_RH:
            zeilen.append(("", "Aufheizzuschlag", "", "", "", "", "", "", de(r.phi_RH)))
        zeilen.append(("", "Raumheizlast Φ<sub>HL</sub>", "", "", "", "", "", "", de(r.phi_HL)))
        n = len(r.bauteile)
        o.append(_tabelle(
            ["Bauteil", "Lage", "grenzt an", "A m²", "U", "ΔU<sub>WB</sub>", "f", "H W/K", "Φ W"],
            zeilen, klasse="klein", zahlspalten=(3, 4, 5, 6, 7, 8),
            zeilenklassen=[""] * n + ["summe"] * (len(zeilen) - n)))
        o.append("</div>")

    o.append('<p class="hinweis" style="margin-top:14px">Vereinfachtes Verfahren in Anlehnung an DIN EN 12831-1 und DIN/TS 12831-1. '
             "Temperatur-Korrekturfaktor f: außen 1, unbeheizt b<sub>u</sub>, beheizte Nachbarräume (θ<sub>i</sub> − θ<sub>n</sub>)/(θ<sub>i</sub> − θ<sub>e</sub>) "
             "ohne Wärmebrückenzuschlag. Die Berechnung ist ein Entwurf und ersetzt nicht die Prüfung durch den verantwortlichen Energieberater.</p>")
    o.append("</body></html>")
    return "".join(o)
