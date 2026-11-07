"""Kennzahlen, Punktwert (0–100) und Begründung für einen einzelnen Jahresabschluss.

Alles rechnet mit dem, was veröffentlicht wurde. Fehlt die Gewinn- und Verlustrechnung, wird das
Jahresergebnis aus der Veränderung des Eigenkapitals geschätzt (Ausschüttungen sind dann nicht
sichtbar, die Schätzung ist eine Untergrenze) und ausdrücklich als Schätzung gekennzeichnet.
"""

import math


def _div(z, n):
    if z is None or n is None or n == 0:
        return None
    return z / n


def _wachstum(aktuell, vorjahr):
    if aktuell is None or vorjahr is None or vorjahr == 0:
        return None
    return (aktuell - vorjahr) / abs(vorjahr)


def berechne(abschluss):
    """Kennzahlen als dict (Werte in EUR bzw. Anteile als Dezimalzahl; None, wenn nicht berechenbar)."""
    w = abschluss.wert
    bs, bs_v = w("bilanzsumme"), w("bilanzsumme", 1)
    ek, ek_v = w("eigenkapital"), w("eigenkapital", 1)
    umsatz, umsatz_v = w("umsatz"), w("umsatz", 1)
    jue, jue_v = w("jahresueberschuss"), w("jahresueberschuss", 1)
    verb = w("verbindlichkeiten")
    rueck = w("rueckstellungen")
    liquide = w("liquide_mittel")
    av = w("anlagevermoegen")
    personal = w("personalaufwand")
    material = w("materialaufwand")
    roh = w("rohergebnis")
    zins = w("zinsaufwand")

    ergebnis_geschaetzt = False
    if jue is None and ek is not None and ek_v is not None:
        jue = ek - ek_v
        ergebnis_geschaetzt = True

    fremdkapital = None
    if bs is not None and ek is not None:
        fremdkapital = bs - ek
    elif verb is not None or rueck is not None:
        fremdkapital = (verb or 0) + (rueck or 0)

    if roh is None and umsatz is not None and material is not None:
        roh = umsatz - abs(material)

    k = {
        "bilanzsumme": bs, "eigenkapital": ek, "umsatz": umsatz, "jahresueberschuss": jue,
        "ergebnis_geschaetzt": ergebnis_geschaetzt, "fremdkapital": fremdkapital, "liquide_mittel": liquide,
        "eigenkapitalquote": _div(ek, bs),
        "verschuldungsgrad": _div(fremdkapital, ek) if ek and ek > 0 else None,
        "anlagenintensitaet": _div(av, bs),
        "liquiditaet": _div(liquide, verb) if verb else None,  # vereinfacht: Kasse/Bank zu Verbindlichkeiten
        "liquiditaetsanteil": _div(liquide, bs),
        "umsatzrendite": _div(jue, umsatz) if not ergebnis_geschaetzt else None,
        # Renditen nur aus einer echten GuV; eine Schätzung aus der Eigenkapitalveränderung würde sonst wie ein Ist-Wert aussehen
        "gesamtkapitalrendite": _div((jue or 0) + abs(zins or 0), bs) if jue is not None and bs and not ergebnis_geschaetzt else None,
        "eigenkapitalrendite": _div(jue, ek) if ek and ek > 0 and jue is not None and not ergebnis_geschaetzt else None,
        "rohertragsquote": _div(roh, umsatz),
        "personalaufwandsquote": _div(abs(personal) if personal is not None else None, umsatz),
        "personalaufwand_zu_rohergebnis": _div(abs(personal) if personal is not None else None, roh),
        "umsatz_je_mitarbeiter": _div(umsatz, abschluss.mitarbeiter) if abschluss.mitarbeiter else None,
        "wachstum_bilanzsumme": _wachstum(bs, bs_v),
        "wachstum_eigenkapital": _wachstum(ek, ek_v),
        "wachstum_umsatz": _wachstum(umsatz, umsatz_v),
        "wachstum_ergebnis": _wachstum(jue, jue_v) if not ergebnis_geschaetzt else None,
        "mitarbeiter": abschluss.mitarbeiter,
        "guv_vorhanden": abschluss.guv_vorhanden,
        "negatives_eigenkapital": ek is not None and ek < 0,
    }
    k["datenlage"] = datenlage(k)
    k["score"], k["ampel"], k["begruendung"] = bewerte(k)
    return k


def datenlage(k):
    if k["bilanzsumme"] is None or k["eigenkapital"] is None:
        return "gering"
    if k["guv_vorhanden"] and k["umsatz"] is not None and k["jahresueberschuss"] is not None:
        return "vollstaendig"
    return "eingeschraenkt"


def _skala(wert, schlecht, gut):
    """Lineare Abbildung von [schlecht, gut] auf [0, 100]; außerhalb begrenzt. None bleibt None."""
    if wert is None:
        return None
    if gut == schlecht:
        return 50.0
    x = (wert - schlecht) / (gut - schlecht)
    return max(0.0, min(1.0, x)) * 100.0


def bewerte(k):
    """Punktwert 0–100 aus Substanz, Ertrag, Wachstum und Liquidität; dazu Ampel und Begründungszeilen."""
    teile = []  # (gewicht, punkte)
    gruende = []

    ekq = k["eigenkapitalquote"]
    p = _skala(ekq, 0.0, 0.5)
    if p is not None:
        teile.append((0.35, p))
        if ekq < 0:
            gruende.append(f"Negatives Eigenkapital (Quote {prozent(ekq, 0)}) – bilanziell überschuldet.")
        elif ekq < 0.15:
            gruende.append(f"Dünne Eigenkapitaldecke ({prozent(ekq, 0)}).")
        elif ekq >= 0.4:
            gruende.append(f"Solide Eigenkapitalquote ({prozent(ekq, 0)}).")
        else:
            gruende.append(f"Eigenkapitalquote im Mittelfeld ({prozent(ekq, 0)}).")

    if k["umsatzrendite"] is not None:
        ur = k["umsatzrendite"]
        teile.append((0.30, _skala(ur, -0.05, 0.12)))
        if ur < 0:
            gruende.append(f"Verlustjahr: Umsatzrendite {prozent(ur)}.")
        elif ur >= 0.08:
            gruende.append(f"Hohe Umsatzrendite ({prozent(ur)}).")
        else:
            gruende.append(f"Umsatzrendite {prozent(ur)}.")
    elif k["gesamtkapitalrendite"] is not None and not k["ergebnis_geschaetzt"]:
        gkr = k["gesamtkapitalrendite"]
        teile.append((0.30, _skala(gkr, -0.05, 0.15)))
        gruende.append(f"Gesamtkapitalrendite {prozent(gkr)}.")
    elif k["ergebnis_geschaetzt"] and k["jahresueberschuss"] is not None and k["bilanzsumme"]:
        rel = k["jahresueberschuss"] / k["bilanzsumme"]
        teile.append((0.20, _skala(rel, -0.10, 0.15)))
        gruende.append(f"Keine GuV veröffentlicht; Eigenkapital hat sich um {geld(k['jahresueberschuss'])} verändert "
                       f"({prozent(rel)} der Bilanzsumme; Untergrenze des Ergebnisses, Ausschüttungen unbekannt).")

    wachstum = k["wachstum_umsatz"] if k["wachstum_umsatz"] is not None else k["wachstum_bilanzsumme"]
    if wachstum is not None:
        teile.append((0.20, _skala(wachstum, -0.15, 0.20)))
        was = "Umsatz" if k["wachstum_umsatz"] is not None else "Bilanzsumme"
        if wachstum > 0.10:
            gruende.append(f"{was} deutlich gewachsen ({prozent(wachstum, 0)}).")
        elif wachstum < -0.10:
            gruende.append(f"{was} deutlich geschrumpft ({prozent(wachstum, 0)}).")
        else:
            gruende.append(f"{was} etwa stabil ({prozent(wachstum, 0)}).")

    liq = k["liquiditaet"]
    if liq is not None:
        teile.append((0.15, _skala(liq, 0.0, 1.0)))
        if liq < 0.2:
            gruende.append("Wenig Kasse im Verhältnis zu den Verbindlichkeiten.")
        elif liq >= 0.8:
            gruende.append("Verbindlichkeiten weitgehend durch Kasse/Bank gedeckt.")
    elif k["liquiditaetsanteil"] is not None:
        teile.append((0.10, _skala(k["liquiditaetsanteil"], 0.0, 0.4)))

    if not teile:
        return None, "grau", ["Zu wenige Daten für eine Bewertung."]
    gewicht = sum(g for g, _ in teile)
    score = sum(g * p for g, p in teile) / gewicht
    if k["negatives_eigenkapital"]:
        score = min(score, 25.0)
    score = round(score)
    ampel = "gruen" if score >= 65 else "gelb" if score >= 40 else "rot"
    if k["datenlage"] != "vollstaendig":
        gruende.append("Datenlage eingeschränkt – Bewertung mit Vorsicht lesen.")
    return score, ampel, gruende


def geld(wert):
    """1234567.8 → '1.234.568 €' (deutsche Schreibweise)."""
    if wert is None:
        return "–"
    return f"{wert:,.0f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def prozent(wert, stellen=1):
    """0.0555 → '5,6 %'; mit Vorzeichen bei Veränderungen ist nicht nötig, negative Werte tragen ein Minus."""
    if wert is None or (isinstance(wert, float) and math.isnan(wert)):
        return "–"
    return f"{wert * 100:.{stellen}f} %".replace(".", ",")
