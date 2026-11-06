"""Werkzeuge, die die KI aufrufen kann (Tool Use).

Jedes Werkzeug ist eine gewöhnliche Python-Funktion. Die KI bekommt die Definition aus
DEFINITIONEN und ruft `ausfuehren(name, eingabe, tool_use_id)` indirekt über ki.py auf.
Alle Fehler werden als Ergebnis mit is_error=True zurückgegeben, nie als Ausnahme.
"""

import json
import secrets
from pathlib import Path

from heizlast.__main__ import als_pdf
from heizlast.abgleich import berechne_abgleich, leistung
from heizlast.bericht import erzeuge_html
from heizlast.heizlast import berechne_gebaeude

from .konfig import WURZEL

MUSTERPROJEKT = WURZEL / "beispiele" / "musterhaus.json"

PROJEKT_FORMAT = (
    "Aufbau der Projektdatei (JSON-Objekt): "
    "`klima` {theta_e, theta_m_e}; `lueftung` {n50, epsilon, n_min_standard}; "
    "`waermebruecken` {delta_U}; `bauteile` {KUERZEL: {bezeichnung, U}}; "
    "`angrenzend` {NAME: {b_u}} für unbeheizte Bereiche; "
    "`raeume` [{name, geschoss, theta_i, A, h, e, bauteile: [{typ, A oder l+h, an, oeffnungen: [{typ, A oder l+h, anzahl}]}]}]; "
    "`hydraulik` {theta_V_ziel, spreizung_auslegung, R_Pa_pro_m, zuschlag_einzelwiderstaende, dp_ventil_min_mbar, "
    "dp_erzeuger_mbar, tausch_kritische}; `heizkoerper` [{id, raum, beschreibung, phi_N, n, L_einfach}]. "
    "`an` ist \"aussen\" (Standard), der Name eines unbeheizten Bereichs aus `angrenzend`, \"erdreich\" "
    "oder die Temperatur eines beheizten Nachbarraums als Zahl. Fenster und Türen gehören als `oeffnungen` "
    "in die Außenwand, sie werden von der Wandfläche abgezogen. Mit `musterprojekt_abrufen` bekommst du ein "
    "vollständiges Beispiel."
)

DEFINITIONEN = [
    {
        "name": "heizlast_berechnen",
        "description": (
            "Berechnet die raumweise Norm-Heizlast (DIN EN 12831-1, vereinfachtes Verfahren) und den "
            "hydraulischen Abgleich nach Verfahren B für ein Gebäude mit Heizkörpern. Nutze es, wenn der "
            "Nutzer Gebäudedaten nennt und eine Heizlast, Vorlauftemperatur, Heizkörperprüfung oder "
            "Pumpenauslegung wissen will. Fehlende Werte musst du vorher beim Nutzer erfragen oder als "
            "klar benannte Annahme setzen. Mit bericht_erzeugen=true wird zusätzlich der PDF/HTML-Bericht "
            "erzeugt und ein Download-Pfad zurückgegeben. " + PROJEKT_FORMAT
        ),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "projekt": {"type": "object", "description": "Vollständige Projektdatei im beschriebenen Format."},
                "bericht_erzeugen": {"type": "boolean", "description": "Bericht als HTML/PDF ablegen (Standard: false)."},
            },
            "required": ["projekt"],
        },
    },
    {
        "name": "heizkoerper_leistung",
        "description": (
            "Wärmeleistung eines Heizkörpers nach DIN EN 442 bei beliebigen Temperaturen: "
            "Phi = Phi_N · (dT_log / 49,83 K)^n. phi_N ist die Normleistung bei 75/65/20 °C in Watt, "
            "n der Heizkörperexponent (Plattenheizkörper ≈ 1,3, Gussradiatoren ≈ 1,3, Konvektoren ≈ 1,4, "
            "Fußbodenheizung ≈ 1,1). Nutze es für schnelle Einzelprüfungen ohne komplettes Projekt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phi_N": {"type": "number", "description": "Normleistung in W (75/65/20)"},
                "n": {"type": "number", "description": "Heizkörperexponent, Standard 1,3"},
                "theta_V": {"type": "number", "description": "Vorlauftemperatur °C"},
                "theta_R": {"type": "number", "description": "Rücklauftemperatur °C"},
                "theta_i": {"type": "number", "description": "Raumtemperatur °C, Standard 20"},
            },
            "required": ["phi_N", "theta_V", "theta_R"],
        },
    },
    {
        "name": "musterprojekt_abrufen",
        "description": (
            "Liefert die vollständige Muster-Projektdatei (fiktives Einfamilienhaus) als Vorlage für "
            "heizlast_berechnen. Rufe es auf, bevor du zum ersten Mal eine Projektdatei zusammenstellst."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _zahl(wert, name, mindest=None):
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        raise ValueError(f"{name} muss eine Zahl sein")
    if mindest is not None and wert < mindest:
        raise ValueError(f"{name} muss mindestens {mindest} sein")
    return float(wert)


def _runde(x, stellen=1):
    return None if x is None else round(x, stellen)


def heizlast_berechnen(eingabe, berichte_ordner=None):
    projekt = eingabe.get("projekt")
    if not isinstance(projekt, dict):
        raise ValueError("projekt muss ein JSON-Objekt sein")
    for schluessel in ("klima", "bauteile", "raeume", "hydraulik", "heizkoerper"):
        if schluessel not in projekt:
            raise ValueError(f"Im Projekt fehlt der Abschnitt '{schluessel}'")

    geb = berechne_gebaeude(projekt)
    abg = berechne_abgleich(projekt, geb)

    ergebnis = {
        "gebaeude": {
            "heizlast_W": _runde(geb.phi_HL, 0),
            "spezifisch_W_m2": _runde(geb.spez),
            "transmission_W": _runde(geb.phi_T, 0),
            "lueftung_W": _runde(geb.phi_V, 0),
            "beheizte_flaeche_m2": _runde(geb.A),
            "summe_raumheizlasten_W": _runde(geb.summe_raumheizlasten, 0),
        },
        "raeume": [
            {
                "name": r.name,
                "geschoss": r.geschoss,
                "theta_i": r.theta_i,
                "A_m2": _runde(r.A),
                "heizlast_W": _runde(r.phi_HL, 0),
                "spezifisch_W_m2": _runde(r.spez),
                "transmission_W": _runde(r.phi_T, 0),
                "lueftung_W": _runde(r.phi_V, 0),
            }
            for r in geb.raeume
        ],
        "abgleich": {
            "vorlauf_auslegung_C": abg.theta_V,
            "vorlauf_noetig_mit_bestandsheizkoerpern_C": abg.theta_V_bestand,
            "vorlauf_ziel_C": abg.theta_V_ziel,
            "spreizung_auslegung_K": abg.spreizung_ausl,
            "ruecklauf_misch_C": _runde(abg.theta_R_misch),
            "heizkoerper_tausch": sum(h.getauscht for h in abg.heizkoerper),
            "volumenstrom_gesamt_l_h": _runde(abg.m_gesamt, 0),
            "pumpenfoerderhoehe_m": _runde(abg.foerderhoehe_m, 2),
            "heizkoerper": [
                {
                    "id": h.id,
                    "raum": h.raum,
                    "phi_N_W": h.phi_N,
                    "soll_W": _runde(h.phi_soll, 0),
                    "vorlauf_noetig_C": _runde(h.theta_V_erf),
                    "ruecklauf_C": _runde(h.theta_R),
                    "volumenstrom_l_h": _runde(h.m),
                    "ventil_dp_mbar": _runde(h.dp_ventil / 100.0, 0),
                    "kv": _runde(h.kv, 3),
                    "tausch": h.getauscht,
                    "neue_normleistung_W": h.phi_N_ausl if h.getauscht else None,
                    "hinweise": list(h.hinweise),
                }
                for h in abg.heizkoerper
            ],
        },
        "hinweis": (
            "Vereinfachtes Verfahren. Ergebnis ist vom Energieberater zu prüfen; "
            "Norm-Außentemperatur und U-Werte sind Eingaben und wurden nicht geprüft."
        ),
    }

    if eingabe.get("bericht_erzeugen") and berichte_ordner is not None:
        ordner = Path(berichte_ordner)
        ordner.mkdir(parents=True, exist_ok=True)
        kennung = secrets.token_urlsafe(12)
        html_datei = ordner / f"{kennung}.html"
        html_datei.write_text(erzeuge_html(projekt, geb, abg), encoding="utf-8")
        pdf_datei = ordner / f"{kennung}.pdf"
        pdf_ok = als_pdf(html_datei, pdf_datei)
        ergebnis["bericht"] = {
            "html": f"/berichte/{html_datei.name}",
            "pdf": f"/berichte/{pdf_datei.name}" if pdf_ok else None,
            "hinweis": "Pfade dem Nutzer als Links nennen." if pdf_ok else "Kein Chromium gefunden, nur HTML erzeugt.",
        }
    return ergebnis


def heizkoerper_leistung(eingabe):
    phi_N = _zahl(eingabe.get("phi_N"), "phi_N", 1)
    n = _zahl(eingabe.get("n", 1.3), "n", 1.0)
    theta_V = _zahl(eingabe.get("theta_V"), "theta_V")
    theta_R = _zahl(eingabe.get("theta_R"), "theta_R")
    theta_i = _zahl(eingabe.get("theta_i", 20.0), "theta_i")
    if theta_R >= theta_V:
        raise ValueError("Rücklauf muss unter dem Vorlauf liegen")
    phi = leistung(phi_N, n, theta_V, theta_R, theta_i)
    return {
        "leistung_W": round(phi, 0),
        "anteil_der_normleistung": round(phi / phi_N, 3),
        "bedingungen": f"{theta_V:g}/{theta_R:g}/{theta_i:g} °C, n={n:g}",
    }


def musterprojekt_abrufen(eingabe):
    return json.loads(MUSTERPROJEKT.read_text(encoding="utf-8"))


FUNKTIONEN = {
    "heizlast_berechnen": heizlast_berechnen,
    "heizkoerper_leistung": heizkoerper_leistung,
    "musterprojekt_abrufen": musterprojekt_abrufen,
}


def ausfuehren(name, eingabe, tool_use_id, berichte_ordner=None):
    """Führt ein Werkzeug aus und liefert den tool_result-Block für die API."""
    if not isinstance(eingabe, dict):
        # Bei eager_input_streaming prüft der Server die Eingabe nicht mehr – ein
        # abgeschnittenes oder falsch geparstes JSON landet hier.
        return _fehler(tool_use_id, json.dumps({"INVALID_JSON": json.dumps(eingabe, default=str)}))
    fn = FUNKTIONEN.get(name)
    if fn is None:
        return _fehler(tool_use_id, f"Unbekanntes Werkzeug {name!r}")
    try:
        if name == "heizlast_berechnen":
            ergebnis = fn(eingabe, berichte_ordner)
        else:
            ergebnis = fn(eingabe)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
        return _fehler(tool_use_id, f"Fehler in {name}: {type(e).__name__}: {e}")
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(ergebnis, ensure_ascii=False),
    }


def _fehler(tool_use_id, text):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": True, "content": text}
