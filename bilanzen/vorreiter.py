"""Vorreiter finden: Rangliste der Unternehmen einer Branche nach Wachstum, Ertrag, Größe, Substanz und Mehrjahrestrend.

Jede Dimension wird als Perzentilrang innerhalb der Vergleichsgruppe ausgedrückt (0 = schwächstes, 100 = stärkstes
Unternehmen), damit Unternehmen mit und ohne veröffentlichte GuV vergleichbar bleiben: Fehlt der Umsatz, zählt die
Bilanzsumme als Größen- und Wachstumsmaß, fehlt das Jahresergebnis, zählt die Eigenkapitalveränderung. Der
Vorreiter-Score ist das gewichtete Mittel der vorhandenen Dimensionen; Unternehmen mit zu wenigen Daten erhalten
keinen Rang, bleiben aber in der Liste sichtbar.
"""

import math

GEWICHTE_STANDARD = {"wachstum": 0.35, "ertrag": 0.25, "groesse": 0.20, "substanz": 0.10, "trend": 0.10}
DIMENSIONEN = {
    "wachstum": "Wachstum (Umsatz, sonst Bilanzsumme) gegenüber dem Vorjahr",
    "ertrag": "Ertragskraft (Umsatzrendite, sonst Eigenkapitalveränderung zur Bilanzsumme)",
    "groesse": "Größe (Umsatz, sonst Bilanzsumme)",
    "substanz": "Substanz (Eigenkapitalquote)",
    "trend": "Mehrjahrestrend (jährliches Wachstum über alle gespeicherten Jahre)",
}


def _perzentile(werte):
    """{id: wert} → {id: Perzentilrang 0..100}; None-Werte fehlen im Ergebnis."""
    gueltig = [(k, v) for k, v in werte.items() if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not gueltig:
        return {}
    if len(gueltig) == 1:
        return {gueltig[0][0]: 50.0}
    sortiert = sorted(gueltig, key=lambda kv: kv[1])
    n = len(sortiert)
    ergebnis = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sortiert[j + 1][1] == sortiert[i][1]:
            j += 1
        rang = (i + j) / 2  # Mittelrang bei Gleichstand
        for k, _ in sortiert[i:j + 1]:
            ergebnis[k] = rang / (n - 1) * 100
        i = j + 1
    return ergebnis


def _cagr(verlauf, schluessel):
    """Jährliche Wachstumsrate aus dem Verlauf (Liste von {gj_bis, <schluessel>}), None bei weniger als zwei Jahren."""
    punkte = [(v["gj_bis"], v.get(schluessel)) for v in verlauf if v.get("gj_bis") and v.get(schluessel)]
    punkte = [(g, w) for g, w in punkte if w > 0]
    if len(punkte) < 2:
        return None
    punkte.sort()
    (g0, w0), (g1, w1) = punkte[0], punkte[-1]
    jahre = int(g1[:4]) - int(g0[:4])
    if jahre <= 0:
        return None
    return (w1 / w0) ** (1 / jahre) - 1


def rangliste(firmen, n=20, gewichte=None, mindest_dimensionen=2):
    """`firmen` wie speicher.firmen() (mit 'kennzahlen' und optional 'verlauf'). Liefert Rangliste und Kategorien-Spitzen."""
    gewichte = dict(GEWICHTE_STANDARD, **(gewichte or {}))
    mit = [f for f in firmen if f.get("kennzahlen")]
    rohwerte = {d: {} for d in gewichte}
    for f in mit:
        k = f["kennzahlen"]
        fid = f["id"]
        rohwerte["wachstum"][fid] = k.get("wachstum_umsatz") if k.get("wachstum_umsatz") is not None else k.get("wachstum_bilanzsumme")
        if k.get("umsatzrendite") is not None:
            rohwerte["ertrag"][fid] = k["umsatzrendite"]
        elif k.get("jahresueberschuss") is not None and k.get("bilanzsumme"):
            rohwerte["ertrag"][fid] = k["jahresueberschuss"] / k["bilanzsumme"]
        else:
            rohwerte["ertrag"][fid] = None
        groesse = k.get("umsatz") if k.get("umsatz") else k.get("bilanzsumme")
        rohwerte["groesse"][fid] = math.log(groesse) if groesse and groesse > 0 else None
        rohwerte["substanz"][fid] = k.get("eigenkapitalquote")
        verlauf = f.get("verlauf") or []
        rohwerte["trend"][fid] = _cagr(verlauf, "umsatz") if any(v.get("umsatz") for v in verlauf) else _cagr(verlauf, "bilanzsumme")

    perzentile = {d: _perzentile(w) for d, w in rohwerte.items()}
    eintraege = []
    for f in mit:
        fid = f["id"]
        k = f["kennzahlen"]
        p = {d: perzentile[d].get(fid) for d in gewichte}
        vorhanden = {d: p[d] for d in p if p[d] is not None}
        score = None
        if len(vorhanden) >= mindest_dimensionen:
            g = sum(gewichte[d] for d in vorhanden)
            score = round(sum(gewichte[d] * vorhanden[d] for d in vorhanden) / g)
        eintraege.append({
            "id": fid, "name": f["name"], "ort": f.get("ort", ""), "rechtsform": f.get("rechtsform", ""), "gj_bis": f.get("gj_bis", ""),
            "quelle": f.get("quelle", ""), "anzahl_abschluesse": f.get("anzahl_abschluesse", 1),
            "vorreiter_score": score, "perzentile": p,
            "werte": {
                "wachstum": rohwerte["wachstum"][fid], "ertrag": rohwerte["ertrag"][fid],
                "groesse": (k.get("umsatz") if k.get("umsatz") else k.get("bilanzsumme")), "groesse_ist_umsatz": bool(k.get("umsatz")),
                "substanz": rohwerte["substanz"][fid], "trend": rohwerte["trend"][fid],
                "ertrag_ist_rendite": k.get("umsatzrendite") is not None,
                "wachstum_ist_umsatz": k.get("wachstum_umsatz") is not None,
                "mitarbeiter": k.get("mitarbeiter"), "score": k.get("score"), "ampel": k.get("ampel"), "datenlage": k.get("datenlage"),
            },
            "gruende": _gruende(p, rohwerte, fid, k),
        })
    eintraege.sort(key=lambda e: (-(e["vorreiter_score"] if e["vorreiter_score"] is not None else -1), e["name"]))
    for i, e in enumerate(eintraege):
        e["rang"] = i + 1 if e["vorreiter_score"] is not None else None

    kategorien = {}
    for d in gewichte:
        beste = sorted((e for e in eintraege if e["perzentile"].get(d) is not None), key=lambda e: -e["perzentile"][d])[:5]
        kategorien[d] = [{"id": e["id"], "name": e["name"], "wert": e["werte"][d]} for e in beste]
    return {
        "anzahl": len(eintraege), "bewertet": sum(1 for e in eintraege if e["vorreiter_score"] is not None),
        "gewichte": gewichte, "dimensionen": DIMENSIONEN,
        "rangliste": eintraege[:n] if n else eintraege, "kategorien": kategorien,
        "hinweise": _hinweise(eintraege, rohwerte),
    }


def _pz(wert):
    return f"{wert * 100:.0f} %".replace(".", ",") if wert is not None else "–"


def _gruende(p, rohwerte, fid, k):
    g = []
    def lage(x):
        return "Spitzengruppe" if x >= 80 else "oberes Viertel" if x >= 75 else "obere Hälfte" if x >= 50 else "untere Hälfte"
    w = rohwerte["wachstum"][fid]
    if p.get("wachstum") is not None:
        g.append(f"Wachstum {_pz(w)} ({'Umsatz' if k.get('wachstum_umsatz') is not None else 'Bilanzsumme'}) – {lage(p['wachstum'])}.")
    e = rohwerte["ertrag"][fid]
    if p.get("ertrag") is not None:
        art = "Umsatzrendite" if k.get("umsatzrendite") is not None else "Eigenkapitalveränderung zur Bilanzsumme"
        g.append(f"{art} {_pz(e)} – {lage(p['ertrag'])}.")
    if p.get("groesse") is not None:
        gr = k.get("umsatz") if k.get("umsatz") else k.get("bilanzsumme")
        g.append(f"{'Umsatz' if k.get('umsatz') else 'Bilanzsumme'} {gr:,.0f} € – {lage(p['groesse'])} nach Größe.".replace(",", "."))
    if p.get("substanz") is not None:
        g.append(f"Eigenkapitalquote {_pz(rohwerte['substanz'][fid])}.")
    t = rohwerte["trend"][fid]
    if t is not None:
        g.append(f"Mehrjahrestrend {_pz(t)} pro Jahr.")
    if k.get("datenlage") != "vollstaendig":
        g.append("Datenlage eingeschränkt (keine GuV).")
    return g


def _hinweise(eintraege, rohwerte):
    h = []
    ohne_trend = sum(1 for e in eintraege if e["perzentile"].get("trend") is None)
    if eintraege and ohne_trend == len(eintraege):
        h.append("Für den Mehrjahrestrend fehlen zweite Jahrgänge: mehrere Geschäftsjahre je Firma laden (Bundesanzeiger bis 2021, "
                 "Unternehmensregister ab 2022), dann zählt die jährliche Wachstumsrate.")
    ohne_umsatz = sum(1 for e in eintraege if not e["werte"]["groesse_ist_umsatz"])
    if eintraege and ohne_umsatz > len(eintraege) / 2:
        h.append("Mehr als die Hälfte veröffentlicht keinen Umsatz; Größe und Wachstum beruhen dort auf der Bilanzsumme.")
    h.append("Perzentile beziehen sich auf die geladene Vergleichsgruppe – je mehr Unternehmen der Branche geladen sind, desto belastbarer das Ranking.")
    return h
