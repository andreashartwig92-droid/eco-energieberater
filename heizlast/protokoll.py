"""Einstellprotokoll: raumweise Ventileinstellung für die Ausführenden (HTML für den PDF-Druck)."""

import datetime

from .bericht import _t
from .zahlen import de

CSS = """
@page { size: A4; margin: 15mm 14mm 16mm 14mm;
  @bottom-left { content: "__FUSS__"; font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
  @bottom-right { content: "Seite " counter(page) " von " counter(pages); font: 7.5pt 'Liberation Sans', 'DejaVu Sans', sans-serif; color: #666; }
}
* { box-sizing: border-box; }
body { font-family: 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif; font-size: 10pt; color: #1b1b1b; line-height: 1.4; margin: 0; }
h1 { font-size: 18pt; margin: 0 0 2px; color: #14532d; }
h2 { font-size: 12.5pt; margin: 14px 0 6px; color: #14532d; border-bottom: 1.5px solid #14532d; padding-bottom: 2px; break-after: avoid; }
p { margin: 4px 0; }
.untertitel { color: #444; margin-bottom: 8px; }
.warn { border: 2px solid #b91c1c; color: #b91c1c; padding: 6px 10px; margin: 8px 0; font-weight: bold; font-size: 9pt; }
table.info { border-collapse: collapse; width: 100%; margin: 4px 0 8px; }
table.info td { border: 0.6px solid #b8b8b8; padding: 3px 6px; vertical-align: top; }
table.info td:first-child { background: #eef4ef; width: 32%; font-weight: bold; }
ol { margin: 4px 0 4px 18px; padding: 0; } li { margin: 2px 0; }
.karte { border: 1.2px solid #14532d; border-radius: 4px; margin: 8px 0; break-inside: avoid; }
.karte .kopf { background: #14532d; color: #fff; padding: 4px 8px; font-weight: bold; font-size: 11pt; display: flex; justify-content: space-between; }
.karte .inhalt { display: flex; }
.karte .daten { flex: 1; padding: 5px 8px; font-size: 9.5pt; }
.karte .daten div { margin: 1px 0; }
.karte .stell { width: 38mm; border-left: 1.2px solid #14532d; text-align: center; padding: 5px 4px; background: #f3f8f4; }
.karte .stell .lbl { font-size: 8pt; color: #444; }
.karte .stell .wert { font-size: 26pt; font-weight: bold; color: #14532d; line-height: 1.1; }
.karte .stell .wert.klein { font-size: 13pt; }
.karte .fuss { border-top: 0.6px solid #b8b8b8; padding: 3px 8px; font-size: 8.5pt; color: #333; }
.hinw { color: #92400e; }
.formel { background: #f4f4f4; padding: 4px 8px; font-size: 8.5pt; margin: 6px 0; }
"""


def _einstellung(h):
    if h.ventil == "kermi":
        return "werkseitig", "klein", "Kermi-Ventileinsatz: nichts einstellen"
    return h.einstellung, "", "Danfoss-Ventil: Einstellring auf diesen Wert"


def erzeuge_protokoll_html(projekt, geb, abg, datum=None):
    datum = datum or datetime.date.today()
    pj = projekt["projekt"]
    katalog = projekt.get("ventile", {})
    fuss = f"{pj['titel']} · Einstellprotokoll · Stand {datum:%d.%m.%Y} · Entwurf"
    raeume = {r.name: r for r in geb.raeume}
    o = [f"<!doctype html><html lang='de'><head><meta charset='utf-8'><title>Einstellprotokoll {_t(pj['titel'])}</title>",
         f"<style>{CSS.replace('__FUSS__', fuss.replace(chr(34), ''))}</style></head><body>",
         "<h1>Einstellprotokoll Heizkörperventile</h1>",
         '<div class="untertitel">Hydraulischer Abgleich – Voreinstellung je Raum</div>']
    if pj.get("warnung"):
        o.append(f'<div class="warn">{_t(pj["warnung"])}</div>')
    ger = {"Objekt": pj["titel"], "Adresse": pj.get("adresse", "–"), "Stand": f"{datum:%d.%m.%Y}",
           "Vorlauftemperatur (Auslegung)": f"{de(abg.theta_V, 0)} °C",
           "Heizkreispumpe": f"Konstantdruck (Δp-c), Förderhöhe {de(abg.foerderhoehe_ausl_m, 2)} m "
                             f"(≈ {de(abg.foerderhoehe_ausl_m * 9.81, 1)} kPa), Volumenstrom ca. {de(abg.m_gesamt / 1000, 2)} m³/h"}
    o.append('<table class="info">' + "".join(f"<tr><td>{_t(k)}</td><td>{_t(v)}</td></tr>" for k, v in ger.items()) + "</table>")

    o.append("<h2>So wird eingestellt</h2><ol>"
             "<li>Thermostatkopf am Danfoss-Ventil abschrauben (Überwurfmutter lösen, Heizung dabei nicht verstellen).</li>"
             "<li>Den Einstellring am Ventileinsatz (Voreinstellung) mit dem Einstellschlüssel oder von Hand drehen, "
             "bis der Wert aus dieser Liste gegenüber der Markierung steht. <b>N</b> bedeutet: Voreinstellung aufgehoben, Ventil ganz offen.</li>"
             "<li>Thermostatkopf wieder aufschrauben und auf die gewünschte Raumtemperatur stellen (Stufe 3 ≈ 20 °C).</li>"
             "<li>Gemacht? In der Karte abhaken, Datum und Namen eintragen.</li></ol>"
             "<p>Bei den neuen Kermi-Heizkörpern mit Ventileinsatz ist die Voreinstellung ab Werk auf die Heizkörperleistung angepasst; "
             "dort wird nichts eingestellt, nur die Lieferung gegen die Angabe auf der Karte prüfen.</p>")

    o.append("<h2>Einstellung je Raum</h2>")
    for h in abg.heizkoerper:
        r = raeume[h.raum]
        wert, kl, hilfe = _einstellung(h)
        zeilen = [f"<div><b>Heizkörper:</b> {_t(h.beschreibung)}</div>",
                  f"<div><b>Ventil:</b> {_t(katalog.get(h.ventil, {}).get('kurz', h.ventil))}</div>",
                  f"<div><b>Raumheizlast:</b> {de(h.phi_soll)} W · Soll-Volumenstrom {de(h.m_ist if h.unterdeckt else h.m)} l/h</div>"]
        hinweis = ""
        if h.unterdeckt:
            hinweis = (f"Dieser Heizkörper ist bei {de(abg.theta_V, 0)} °C Vorlauf zu klein: er schafft nur {de(100 * h.phi_ist / h.phi_soll)} % "
                       f"der Raumheizlast, der Raum wird bei Außentemperaturen unter ca. {de(h.theta_a_grenz, 0)} °C nicht voll warm. "
                       "Ventil deshalb ganz öffnen.")
        elif h.getauscht:
            hinweis = f"Neuer Heizkörper: mind. {de(h.phi_N_ausl)} W Normleistung (75/65/20)."
        o.append('<div class="karte">'
                 f'<div class="kopf"><span>{_t(r.geschoss)} · {_t(h.raum)}</span><span>{_t(h.id)}</span></div>'
                 f'<div class="inhalt"><div class="daten">{"".join(zeilen)}</div>'
                 f'<div class="stell"><div class="lbl">Voreinstellung</div><div class="wert {kl}">{_t(wert)}</div>'
                 f'<div class="lbl">{_t(hilfe)}</div></div></div>'
                 + (f'<div class="fuss hinw">{_t(hinweis)}</div>' if hinweis else "")
                 + '<div class="fuss">☐ eingestellt &nbsp;&nbsp; Datum: ____________ &nbsp;&nbsp; Name: ______________________</div></div>')

    o.append('<p style="margin-top:10px;font-size:8.5pt;color:#444">Die Werte beruhen auf einer vorläufigen Heizlastberechnung. '
             "Voreinstellwerte bitte gegen das aktuelle Danfoss-Datenblatt des verbauten Ventiltyps prüfen. "
             "Entwurf – Freigabe durch den Energieberater erforderlich.</p></body></html>")
    return "".join(o)
