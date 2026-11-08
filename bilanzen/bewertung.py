"""Branchenbild: viele Unternehmen (je der jüngste Abschluss) zu einem Urteil verdichten.

Frage: Wie läuft das Geschäft in dieser Branche, und ist ein Einstieg interessant? Das Urteil stützt sich
auf Verbreitung von Gewinnen, typische Margen, Wachstum, Krisenanteil, Kapitalbedarf (Anlagenintensität
und typische Unternehmensgröße) und Konzentration (Anteil der größten Anbieter). Es ist eine Orientierung
aus öffentlichen Zahlen, kein Ersatz für Marktgespräche – und es zeigt die Vergangenheit, da Abschlüsse
mit bis zu zwölf Monaten Verzug veröffentlicht werden.
"""

import statistics
from datetime import date

from .kennzahlen import geld, prozent


def _median(werte):
    w = [x for x in werte if x is not None]
    return statistics.median(w) if w else None


def _quartile(werte):
    w = sorted(x for x in werte if x is not None)
    if len(w) < 4:
        return (None, _median(w), None) if w else (None, None, None)
    q = statistics.quantiles(w, n=4)
    return q[0], q[1], q[2]


def _anteil(bedingung, werte):
    w = [x for x in werte if x is not None]
    if not w:
        return None
    return sum(1 for x in w if bedingung(x)) / len(w)


def groessenklasse_bilanzsumme(bs):
    if bs is None:
        return "unbekannt"
    if bs < 250_000:
        return "bis 250 T€"
    if bs < 1_000_000:
        return "250 T€ bis 1 Mio €"
    if bs < 5_000_000:
        return "1 bis 5 Mio €"
    if bs < 20_000_000:
        return "5 bis 20 Mio €"
    return "über 20 Mio €"


def branchenbild(firmen, bezeichnung=""):
    """`firmen`: Liste von dicts mit 'name', 'gj_bis' und 'kennzahlen' (aus kennzahlen.berechne), je Firma der jüngste Abschluss."""
    ks = [f["kennzahlen"] for f in firmen if f.get("kennzahlen")]
    n = len(ks)
    if n == 0:
        return {"bezeichnung": bezeichnung, "anzahl": 0, "urteil": "keine Daten", "score": None,
                "begruendung": ["Noch keine ausgewerteten Abschlüsse."], "hinweise": [], "kennzahlen": {}, "verteilungen": {}}

    ekq = [k.get("eigenkapitalquote") for k in ks]
    ur = [k.get("umsatzrendite") for k in ks]
    gkr = [k.get("gesamtkapitalrendite") for k in ks if not k.get("ergebnis_geschaetzt")]
    umsatz = [k.get("umsatz") for k in ks]
    bs = [k.get("bilanzsumme") for k in ks]
    w_umsatz = [k.get("wachstum_umsatz") for k in ks]
    w_bs = [k.get("wachstum_bilanzsumme") for k in ks]
    w_ek = [k.get("wachstum_eigenkapital") for k in ks]
    ergebnisse = [k.get("jahresueberschuss") for k in ks]
    anlagen = [k.get("anlagenintensitaet") for k in ks]
    personalq = [k.get("personalaufwandsquote") for k in ks]
    mitarbeiter = [k.get("mitarbeiter") for k in ks]
    scores = [k.get("score") for k in ks]

    anteil_gewinn = _anteil(lambda x: x > 0, ergebnisse)
    anteil_wachsend = _anteil(lambda x: x > 0.03, [a if a is not None else b for a, b in zip(w_umsatz, w_bs)])
    anteil_krise = _anteil(lambda x: x < 0.10, ekq)  # dünne oder negative Eigenkapitaldecke
    anteil_negativ_ek = _anteil(lambda x: x < 0, ekq)
    ek_wachsend = _anteil(lambda x: x > 0, w_ek)

    bs_bekannt = sorted((x for x in bs if x), reverse=True)
    konzentration = sum(bs_bekannt[:3]) / sum(bs_bekannt) if len(bs_bekannt) >= 3 else None

    q_ekq = _quartile(ekq)
    q_ur = _quartile(ur)
    q_umsatz = _quartile(umsatz)
    q_bs = _quartile(bs)

    kennzahlen = {
        "anzahl_firmen": n,
        "anzahl_mit_guv": sum(1 for k in ks if k.get("guv_vorhanden")),
        "anteil_gewinn": anteil_gewinn,
        "anteil_wachsend": anteil_wachsend,
        "anteil_duennes_eigenkapital": anteil_krise,
        "anteil_negatives_eigenkapital": anteil_negativ_ek,
        "anteil_eigenkapital_wachsend": ek_wachsend,
        "eigenkapitalquote_quartile": q_ekq,
        "umsatzrendite_quartile": q_ur,
        "gesamtkapitalrendite_median": _median(gkr),
        "umsatz_quartile": q_umsatz,
        "bilanzsumme_quartile": q_bs,
        "wachstum_umsatz_median": _median(w_umsatz),
        "wachstum_bilanzsumme_median": _median(w_bs),
        "anlagenintensitaet_median": _median(anlagen),
        "personalaufwandsquote_median": _median(personalq),
        "mitarbeiter_median": _median(mitarbeiter),
        "konzentration_top3": konzentration,
        "score_median": _median(scores),
    }

    verteilungen = {
        "groessenklassen": _zaehle(groessenklasse_bilanzsumme(x) for x in bs),
        "ampeln": _zaehle(k.get("ampel") or "grau" for k in ks),
        "geschaeftsjahre": _zaehle((f.get("gj_bis") or "")[:4] or "unbekannt" for f in firmen),
        "rechtsformen": _zaehle(f.get("rechtsform") or "unbekannt" for f in firmen),
    }

    score, urteil, gruende, hinweise = _urteil(kennzahlen, n)
    jahre = sorted(j for j in verteilungen["geschaeftsjahre"] if j.isdigit())
    if jahre and int(jahre[-1]) < date.today().year - 2:
        hinweise.append(f"Jüngstes ausgewertetes Geschäftsjahr ist {jahre[-1]}; Abschlüsse werden mit bis zu zwölf Monaten Verzug "
                        "offengelegt, neuere Jahre lassen sich mit „Daten holen“ nachladen.")
    return {"bezeichnung": bezeichnung, "anzahl": n, "score": score, "urteil": urteil, "begruendung": gruende,
            "hinweise": hinweise, "kennzahlen": kennzahlen, "verteilungen": verteilungen}


def _zaehle(werte):
    z = {}
    for w in werte:
        z[w] = z.get(w, 0) + 1
    return dict(sorted(z.items(), key=lambda kv: -kv[1]))


def _urteil(k, n):
    teile = []
    gruende = []
    hinweise = []

    def pkt(wert, schlecht, gut):
        return max(0.0, min(1.0, (wert - schlecht) / (gut - schlecht))) * 100

    if k["anteil_gewinn"] is not None:
        teile.append((0.30, pkt(k["anteil_gewinn"], 0.3, 0.85)))
        gruende.append(f"{prozent(k['anteil_gewinn'], 0)} der Unternehmen haben im jüngsten Jahr Gewinn gemacht bzw. Eigenkapital aufgebaut.")
    ur_med = k["umsatzrendite_quartile"][1]
    if ur_med is not None:
        teile.append((0.20, pkt(ur_med, -0.02, 0.10)))
        gruende.append(f"Typische Umsatzrendite (Median) {prozent(ur_med)}" + (
            f", oberes Viertel ab {prozent(k['umsatzrendite_quartile'][2])}." if k["umsatzrendite_quartile"][2] is not None else "."))
    elif k["gesamtkapitalrendite_median"] is not None:
        teile.append((0.15, pkt(k["gesamtkapitalrendite_median"], -0.02, 0.12)))
        gruende.append(f"Typische Gesamtkapitalrendite (Median) {prozent(k['gesamtkapitalrendite_median'])}.")
    else:
        hinweise.append("Für die meisten Unternehmen liegt keine Gewinn- und Verlustrechnung vor; Margen sind nicht ablesbar.")
    if k["anteil_wachsend"] is not None:
        teile.append((0.20, pkt(k["anteil_wachsend"], 0.2, 0.7)))
        gruende.append(f"{prozent(k['anteil_wachsend'], 0)} der Unternehmen sind gewachsen (Umsatz, sonst Bilanzsumme, über 3 %).")
    if k["anteil_duennes_eigenkapital"] is not None:
        teile.append((0.15, 100 - pkt(k["anteil_duennes_eigenkapital"], 0.1, 0.5)))
        gruende.append(f"{prozent(k['anteil_duennes_eigenkapital'], 0)} haben eine Eigenkapitalquote unter 10 % "
                       f"({prozent(k['anteil_negatives_eigenkapital'], 0)} sogar negativ) – Hinweis auf Krisenanteil.")
    ekq_med = k["eigenkapitalquote_quartile"][1]
    if ekq_med is not None:
        teile.append((0.10, pkt(ekq_med, 0.1, 0.5)))
        gruende.append(f"Mittlere Eigenkapitalquote {prozent(ekq_med, 0)}.")

    # Einstiegshürden (zählen eigens; niedrige Hürden machen den Einstieg leichter, aber auch den Wettbewerb härter)
    huerden = []
    if k["anlagenintensitaet_median"] is not None:
        if k["anlagenintensitaet_median"] < 0.25:
            huerden.append(f"geringe Kapitalbindung (Anlagevermögen typischerweise {prozent(k['anlagenintensitaet_median'], 0)} der Bilanzsumme)")
        elif k["anlagenintensitaet_median"] > 0.6:
            huerden.append(f"hohe Kapitalbindung (Anlagevermögen {prozent(k['anlagenintensitaet_median'], 0)} der Bilanzsumme)")
    bs_med = k["bilanzsumme_quartile"][1]
    if bs_med is not None:
        huerden.append(f"typische Unternehmensgröße: Bilanzsumme {geld(bs_med)}")
    if k["konzentration_top3"] is not None:
        if k["konzentration_top3"] > 0.6:
            huerden.append(f"stark konzentriert: die drei größten Anbieter stellen {prozent(k['konzentration_top3'], 0)} der Bilanzsumme der Stichprobe")
        elif k["konzentration_top3"] < 0.3:
            huerden.append(f"zersplitterter Markt: die drei größten Anbieter stellen nur {prozent(k['konzentration_top3'], 0)} der Bilanzsumme")
    if k["personalaufwandsquote_median"] is not None:
        huerden.append(f"Personalaufwand typischerweise {prozent(k['personalaufwandsquote_median'], 0)} vom Umsatz (personalgetriebenes Geschäft)"
                       if k["personalaufwandsquote_median"] > 0.4 else
                       f"Personalaufwand typischerweise {prozent(k['personalaufwandsquote_median'], 0)} vom Umsatz")
    if huerden:
        gruende.append("Einstieg: " + "; ".join(huerden) + ".")

    if n < 10:
        hinweise.append(f"Nur {n} Unternehmen ausgewertet – die Stichprobe ist klein, das Bild entsprechend unsicher.")
    if k["anzahl_mit_guv"] < n / 2:
        hinweise.append("Weniger als die Hälfte der Unternehmen veröffentlicht eine GuV (Kleinst-/kleine Gesellschaften); "
                        "Ertragsaussagen beruhen überwiegend auf der Eigenkapitalveränderung.")
    hinweise.append("Veröffentlichte Abschlüsse sind nur für Kapitalgesellschaften und bestimmte Personengesellschaften Pflicht; "
                    "Einzelunternehmer und Freiberufler fehlen im Bild.")

    if not teile:
        return None, "keine Bewertung möglich", gruende, hinweise
    score = round(sum(g * p for g, p in teile) / sum(g for g, _ in teile))
    if score >= 65:
        urteil = "attraktiv"
    elif score >= 45:
        urteil = "bedingt attraktiv"
    else:
        urteil = "wenig attraktiv"
    return score, urteil, gruende, hinweise
