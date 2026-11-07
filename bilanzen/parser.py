"""Bilanz- und GuV-Posten aus einem veröffentlichten Jahresabschluss (HTML) herauslesen.

Die Veröffentlichungen sind nicht einheitlich formatiert: mal Tabellen mit zwei Wertspalten (Berichtsjahr,
Vorjahr), mal Fließtext, mal in EUR, mal in TEUR, Minusbeträge als "-1.234" oder "(1.234)". Der Parser
arbeitet deshalb zeilenweise: Jede Zeile wird in Beschriftung + Zahlen zerlegt, die Beschriftung wird
über Schlüsselwörter einem Standardposten zugeordnet. Das Ergebnis ist ein `Abschluss` mit den Posten
(Berichtsjahr, Vorjahr), Hinweisen zur Größenklasse und einer Liste von Warnungen, wenn etwas fehlt.

Erwartungshaltung: Kleinst- und kleine Kapitalgesellschaften veröffentlichen nur eine verkürzte Bilanz
ohne Gewinn- und Verlustrechnung. Dann fehlen Umsatz und Jahresüberschuss; das Jahresergebnis lässt
sich dann nur aus der Veränderung des Eigenkapitals schätzen (siehe kennzahlen.py).
"""

import re
from dataclasses import dataclass, field

from .htmlbaum import parse

# Reihenfolge wichtig: speziellere Muster zuerst. (Posten, Muster auf der normalisierten Beschriftung)
POSTEN_MUSTER = [
    ("nicht_gedeckter_fehlbetrag", r"nicht durch eigenkapital gedeckter fehlbetrag"),
    ("bilanzsumme", r"^(summe aktiva|summe passiva|bilanzsumme|summe der aktiva|summe der passiva|aktiva gesamt|passiva gesamt|gesamtvermoegen|gesamtkapital|summe vermoegen|summe kapital)$"),
    ("anlagevermoegen", r"^anlagevermoegen$"),
    ("sachanlagen", r"^sachanlagen$"),
    ("umlaufvermoegen", r"^umlaufvermoegen$"),
    ("vorraete", r"^vorraete$"),
    ("forderungen", r"^forderungen und sonstige vermoegensgegenstaende$"),
    ("forderungen_lul", r"^forderungen aus lieferungen und leistungen"),
    ("liquide_mittel", r"(kassenbestand|guthaben bei kreditinstituten|fluessige mittel|zahlungsmittel|schecks)"),
    ("rechnungsabgrenzung_aktiv", r"^(aktive )?rechnungsabgrenzungsposten$"),
    ("eigenkapital", r"^eigenkapital$"),
    ("gezeichnetes_kapital", r"^gezeichnetes kapital"),
    ("kapitalruecklage", r"^kapitalruecklage"),
    ("gewinnruecklagen", r"^gewinnruecklagen"),
    ("gewinnvortrag", r"^(gewinnvortrag|verlustvortrag|gewinn-?/?\s?verlustvortrag|gewinn- oder verlustvortrag|verlust-?/?\s?gewinnvortrag)"),
    ("jahresueberschuss", r"^(jahresueberschuss|jahresfehlbetrag|jahresergebnis|jahresueberschuss ?/ ?jahresfehlbetrag|jahresfehlbetrag ?/ ?jahresueberschuss|jahresueberschuss ?/ ?-fehlbetrag|ergebnis nach steuern)"),
    ("bilanzgewinn", r"^(bilanzgewinn|bilanzverlust|bilanzgewinn ?/ ?bilanzverlust|bilanzgewinn ?/ ?-verlust)"),
    ("rueckstellungen", r"^rueckstellungen$"),
    ("verbindlichkeiten", r"^verbindlichkeiten$"),
    ("verbindlichkeiten_kreditinstitute", r"^verbindlichkeiten gegenueber kreditinstituten"),
    ("verbindlichkeiten_lul", r"^verbindlichkeiten aus lieferungen und leistungen"),
    ("verbindlichkeiten_gesellschafter", r"^verbindlichkeiten gegenueber gesellschaftern"),
    ("rechnungsabgrenzung_passiv", r"^(passive )?rechnungsabgrenzungsposten$"),
    ("umsatz", r"^umsatzerloese"),
    ("bestandsveraenderung", r"^(erhoehung|verminderung|veraenderung) des bestands"),
    ("sonstige_betriebliche_ertraege", r"^sonstige betriebliche ertraege"),
    ("rohergebnis", r"^(rohergebnis|rohertrag)"),
    ("materialaufwand", r"^materialaufwand$"),
    ("personalaufwand", r"^personalaufwand$"),
    ("loehne_gehaelter", r"^loehne und gehaelter"),
    ("abschreibungen", r"^abschreibungen"),
    ("sonstige_betriebliche_aufwendungen", r"^sonstige betriebliche aufwendungen"),
    ("zinsertrag", r"^sonstige zinsen und aehnliche ertraege"),
    ("zinsaufwand", r"^zinsen und aehnliche aufwendungen"),
    ("steuern_ertrag", r"^steuern vom einkommen und vom ertrag"),
    ("sonstige_steuern", r"^sonstige steuern"),
    ("ergebnis_gewoehnlich", r"^ergebnis der gewoehnlichen geschaeftstaetigkeit"),
]
_MUSTER = [(name, re.compile(m)) for name, m in POSTEN_MUSTER]

ZAHL = re.compile(r"\(?-?\d{1,3}(?:\.\d{3})+(?:,\d+)?\)?|\(?-?\d+(?:,\d+)?\)?")
DATUM = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")

POSTEN_NAMEN = {
    "bilanzsumme": "Bilanzsumme", "anlagevermoegen": "Anlagevermögen", "sachanlagen": "Sachanlagen",
    "umlaufvermoegen": "Umlaufvermögen", "vorraete": "Vorräte", "forderungen": "Forderungen und sonstige Vermögensgegenstände",
    "forderungen_lul": "Forderungen aus Lieferungen und Leistungen", "liquide_mittel": "Kasse und Bankguthaben",
    "rechnungsabgrenzung_aktiv": "Aktive Rechnungsabgrenzung", "eigenkapital": "Eigenkapital",
    "gezeichnetes_kapital": "Gezeichnetes Kapital", "kapitalruecklage": "Kapitalrücklage", "gewinnruecklagen": "Gewinnrücklagen",
    "gewinnvortrag": "Gewinn-/Verlustvortrag", "jahresueberschuss": "Jahresüberschuss/-fehlbetrag", "bilanzgewinn": "Bilanzgewinn/-verlust",
    "nicht_gedeckter_fehlbetrag": "Nicht durch Eigenkapital gedeckter Fehlbetrag", "rueckstellungen": "Rückstellungen",
    "verbindlichkeiten": "Verbindlichkeiten", "verbindlichkeiten_kreditinstitute": "Verbindlichkeiten gegenüber Kreditinstituten",
    "verbindlichkeiten_lul": "Verbindlichkeiten aus Lieferungen und Leistungen", "verbindlichkeiten_gesellschafter": "Verbindlichkeiten gegenüber Gesellschaftern",
    "rechnungsabgrenzung_passiv": "Passive Rechnungsabgrenzung", "umsatz": "Umsatzerlöse", "bestandsveraenderung": "Bestandsveränderung",
    "sonstige_betriebliche_ertraege": "Sonstige betriebliche Erträge", "rohergebnis": "Rohergebnis", "materialaufwand": "Materialaufwand",
    "personalaufwand": "Personalaufwand", "loehne_gehaelter": "Löhne und Gehälter", "abschreibungen": "Abschreibungen",
    "sonstige_betriebliche_aufwendungen": "Sonstige betriebliche Aufwendungen", "zinsertrag": "Zinserträge", "zinsaufwand": "Zinsaufwand",
    "steuern_ertrag": "Steuern vom Einkommen und Ertrag", "sonstige_steuern": "Sonstige Steuern",
    "ergebnis_gewoehnlich": "Ergebnis der gewöhnlichen Geschäftstätigkeit",
}
GUV_POSTEN = ("umsatz", "rohergebnis", "materialaufwand", "personalaufwand", "sonstige_betriebliche_aufwendungen",
              "abschreibungen", "zinsaufwand", "steuern_ertrag", "ergebnis_gewoehnlich")

RECHTSFORMEN = [
    ("GmbH & Co. KG", r"gmbh\s*&\s*co\.?\s*kg"), ("UG (haftungsbeschränkt) & Co. KG", r"ug\s*\(haftungsbeschr[aä]nkt\)\s*&\s*co\.?\s*kg"),
    ("UG (haftungsbeschränkt)", r"\bug\b.*haftungsbeschr|haftungsbeschr[aä]nkt"), ("AG & Co. KG", r"\bag\s*&\s*co\.?\s*kg"),
    ("SE", r"\bse\b"), ("AG", r"\bag\b"), ("KGaA", r"kgaa"), ("eG", r"\beg\b"), ("GmbH", r"gmbh|gesellschaft mit beschr[aä]nkter haftung"),
    ("KG", r"\bkg\b"), ("OHG", r"\bohg\b"), ("e.K.", r"\be\.\s?k\.|eingetragene[rn]? kaufmann"), ("e.V.", r"\be\.\s?v\."),
    ("Stiftung", r"stiftung"), ("Ltd.", r"\bltd\b|limited"),
]


@dataclass
class Abschluss:
    firma: str = ""
    titel: str = ""
    gj_von: str = ""  # ISO-Datum
    gj_bis: str = ""
    einheit: str = "EUR"
    posten: dict = field(default_factory=dict)  # name → [berichtsjahr, vorjahr] (float oder None)
    guv_vorhanden: bool = False
    groessenklasse: str = ""  # kleinst, klein, mittel, gross oder leer
    mitarbeiter: int | None = None
    rechtsform: str = ""
    hinweise: list = field(default_factory=list)
    warnungen: list = field(default_factory=list)
    zeilen_erkannt: int = 0

    def wert(self, name, jahr=0):
        p = self.posten.get(name)
        return p[jahr] if p and jahr < len(p) else None

    def als_dict(self):
        return {
            "firma": self.firma, "titel": self.titel, "gj_von": self.gj_von, "gj_bis": self.gj_bis, "einheit": self.einheit,
            "posten": self.posten, "guv_vorhanden": self.guv_vorhanden, "groessenklasse": self.groessenklasse,
            "mitarbeiter": self.mitarbeiter, "rechtsform": self.rechtsform, "hinweise": self.hinweise,
            "warnungen": self.warnungen, "zeilen_erkannt": self.zeilen_erkannt,
        }


# --- Hilfsfunktionen --------------------------------------------------------------------------

def normalisiere(text):
    t = text.lower().strip()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = re.sub(r"^(?:(?:[a-z]|[ivx]+|\d+)[\.\)]\s*)+", "", t)  # Gliederungsziffern "A.", "I.", "1.", "a)"
    t = re.sub(r"[:;*]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip(" .-")
    return t


def zahl(text):
    """Deutsches Zahlenformat → float. '(1.234,50)' und '-1.234,50' sind negativ. None bei Unlesbarem."""
    t = text.strip().replace(" ", "").replace(" ", "")
    negativ = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = t.strip("()").lstrip("-").replace(".", "").replace(",", ".")
    if not t or not re.fullmatch(r"\d+(\.\d+)?", t):
        return None
    w = float(t)
    return -w if negativ else w


def zerlege_zeile(zeile):
    """'Umsatzerlöse 1.234,00 2.345,00' → ('Umsatzerlöse', [1234.0, 2345.0])."""
    zeile = zeile.replace(" ", " ").replace("EUR", " ").replace("€", " ").replace("TEUR", " ").replace("T€", " ")
    zeile = re.sub(r"\s+", " ", zeile).strip()
    tokens = zeile.split(" ")
    zahlen = []
    while tokens:
        t = tokens[-1].strip()
        if t in ("-", "–", "—", "0,00", "./.", "-,--"):
            zahlen.append(0.0 if t in ("0,00",) else None)
            tokens.pop()
            continue
        if ZAHL.fullmatch(t) and not DATUM.fullmatch(t):
            w = zahl(t)
            # Jahreszahlen wie 2021 ohne Tausenderpunkt sind in Werttabellen selten, in Überschriften häufig
            if w is not None and w.is_integer() and 1900 <= w <= 2100 and "." not in t and "," not in t and not zahlen:
                break
            zahlen.append(w)
            tokens.pop()
            continue
        break
    zahlen.reverse()
    beschriftung = " ".join(tokens).strip()
    while zahlen and zahlen[0] is None:
        zahlen.pop(0)
    return beschriftung, zahlen


def ordne_posten(beschriftung):
    n = normalisiere(beschriftung)
    if not n:
        return None
    for name, muster in _MUSTER:
        if muster.search(n):
            return name
    return None


def _zeilen_aus_html(html):
    """Tabellenzeilen → 'Zelle | Zelle', übriger Text → einzelne Zeilen. Nur der Veröffentlichungsteil, wenn vorhanden."""
    baum = parse(html)
    wurzel = baum.erster("div", klasse="publication_container") or baum
    zeilen = []
    tabellen = set()

    def tabelle(knoten):
        for tr in knoten.suche("tr"):
            zellen = [z.text() for z in tr.kinder if not isinstance(z, str) and z.tag in ("td", "th")]
            zellen = [z for z in zellen if z != ""]
            if zellen:
                zeilen.append(" | ".join(zellen))

    for k in wurzel.alle():
        if k.tag == "table":
            if any(e in tabellen for e in _vorfahren(k)):
                continue
            tabellen.add(id(k))
            tabelle(k)
    # Fließtext (ohne Tabelleninhalt) hinten anhängen, damit Tabellenwerte Vorrang haben
    for k in wurzel.alle():
        if k.tag in ("p", "h1", "h2", "h3", "h4", "h5", "li", "div") and not any(e in tabellen for e in _vorfahren(k)):
            direkt = "".join(t for t in k.kinder if isinstance(t, str)).strip()
            if direkt:
                zeilen.append(re.sub(r"\s+", " ", direkt))
    return zeilen, wurzel.text("\n")


def _vorfahren(k):
    e = k.eltern
    while e is not None:
        yield id(e)
        e = e.eltern


def _zelle_zu_zeile(zeile):
    """Tabellenzeile 'A. | Anlagevermögen | 1.000,00 | 2.000,00' → gemeinsame Zeichenkette ohne Trenner."""
    teile = [t.strip() for t in zeile.split(" | ")]
    beschriftung = []
    werte = []
    for t in teile:
        b, z = zerlege_zeile(t)
        if b and not z:
            beschriftung.append(b)
        elif z and not b:
            werte.extend(z)
        elif b and z:
            beschriftung.append(b)
            werte.extend(z)
    return " ".join(beschriftung), werte


# --- Hauptfunktion ----------------------------------------------------------------------------

def parse_jahresabschluss(html, titel="", firma=""):
    zeilen, volltext = _zeilen_aus_html(html)
    a = Abschluss(firma=firma, titel=titel)
    text_klein = volltext.lower()

    # Einheit
    if re.search(r"\b(teur|t€|in tsd\.? ?eur|tausend euro)\b", text_klein):
        a.einheit = "TEUR"
        a.hinweise.append("Beträge in TEUR angegeben; Werte wurden mit 1.000 multipliziert.")
    faktor = 1000.0 if a.einheit == "TEUR" else 1.0

    # Geschäftsjahr aus Titel oder Text
    quelle = titel or ""
    m = re.search(r"gesch[aä]ftsjahr\w*\s+vom\s+(\d{2}\.\d{2}\.\d{4})\s+bis\s+(?:zum\s+)?(\d{2}\.\d{2}\.\d{4})", quelle + " " + volltext, re.I)
    if m:
        a.gj_von, a.gj_bis = _iso(m.group(1)), _iso(m.group(2))
    else:
        m = re.search(r"bilanz\s+zum\s+(\d{2}\.\d{2}\.\d{4})", volltext, re.I) or re.search(r"zum\s+(\d{2}\.\d{2}\.\d{4})", quelle, re.I)
        if m:
            a.gj_bis = _iso(m.group(1))
    if not a.firma:
        for z in volltext.split("\n"):
            z = z.strip()
            if z and len(z) < 150 and any(rf in z for rf in ("GmbH", "AG", "KG", "UG", "e.K.", "eG", "SE")):
                a.firma = z
                break
    a.rechtsform = erkenne_rechtsform(a.firma)

    # Posten
    for roh in zeilen:
        if " | " in roh:
            beschriftung, werte = _zelle_zu_zeile(roh)
        else:
            beschriftung, werte = zerlege_zeile(roh)
        if not werte or not beschriftung:
            continue
        name = ordne_posten(beschriftung)
        if name is None:
            continue
        werte = [w * faktor if w is not None else None for w in werte[:2]]
        if len(werte) == 1:
            werte.append(None)
        if name in a.posten:
            alt = a.posten[name]
            # Bilanzsumme steht auf Aktiv- und Passivseite; sonst erste Nennung behalten, Lücken auffüllen
            a.posten[name] = [alt[i] if alt[i] is not None else werte[i] for i in range(2)]
        else:
            a.posten[name] = werte
        a.zeilen_erkannt += 1

    # Zusammengesetzte Größen ableiten
    _ableitungen(a)

    # GuV vorhanden?
    a.guv_vorhanden = ("umsatz" in a.posten) or sum(1 for p in GUV_POSTEN if p in a.posten) >= 2
    if "gewinn- und verlustrechnung" in text_klein and not a.guv_vorhanden:
        a.hinweise.append("Gewinn- und Verlustrechnung erwähnt, aber keine Posten erkannt.")

    # Größenklasse und Mitarbeiter
    a.groessenklasse = erkenne_groessenklasse(text_klein)
    a.mitarbeiter = erkenne_mitarbeiter(volltext)

    # Warnungen
    if "bilanzsumme" not in a.posten:
        a.warnungen.append("Bilanzsumme nicht gefunden.")
    if "eigenkapital" not in a.posten and "nicht_gedeckter_fehlbetrag" not in a.posten:
        a.warnungen.append("Eigenkapital nicht gefunden.")
    if not a.guv_vorhanden:
        a.hinweise.append("Keine Gewinn- und Verlustrechnung veröffentlicht (bei kleinen und Kleinstgesellschaften üblich); "
                          "Umsatz und Ergebnis sind nicht direkt ablesbar.")
    if a.zeilen_erkannt == 0:
        a.warnungen.append("Keine Bilanzposten erkannt – Dokument prüfen.")
    return a


def _ableitungen(a):
    p = a.posten

    def summe(namen, jahr):
        werte = [p[n][jahr] for n in namen if n in p and p[n][jahr] is not None]
        return sum(werte) if werte else None

    if "eigenkapital" not in p:
        teile = ("gezeichnetes_kapital", "kapitalruecklage", "gewinnruecklagen", "gewinnvortrag", "jahresueberschuss", "bilanzgewinn")
        if "gezeichnetes_kapital" in p:
            namen = [n for n in teile if n in p and not (n == "jahresueberschuss" and "bilanzgewinn" in p)]
            p["eigenkapital"] = [summe(namen, 0), summe(namen, 1)]
            a.hinweise.append("Eigenkapital aus den Einzelposten summiert.")
    if "eigenkapital" in p and "nicht_gedeckter_fehlbetrag" in p:
        ek = p["eigenkapital"]
        f = p["nicht_gedeckter_fehlbetrag"]
        # Verkürzte Darstellung: Die Eigenkapitalzeile zeigt 0 oder den Fehlbetrag selbst; das echte Eigenkapital ist negativ.
        if ek[0] is not None and f[0] and ek[0] >= 0 and (ek[0] < 1 or abs(ek[0] - f[0]) < 1):
            p["eigenkapital"] = [-(f[0] or 0), -(f[1] or 0) if f[1] is not None else ek[1]]
        if p["eigenkapital"][0] is not None and p["eigenkapital"][0] < 0:
            a.hinweise.append("Eigenkapital negativ (nicht durch Eigenkapital gedeckter Fehlbetrag).")
    if "bilanzsumme" not in p:
        aktiv = ("anlagevermoegen", "umlaufvermoegen", "rechnungsabgrenzung_aktiv", "nicht_gedeckter_fehlbetrag")
        if "anlagevermoegen" in p or "umlaufvermoegen" in p:
            p["bilanzsumme"] = [summe(aktiv, 0), summe(aktiv, 1)]
            a.hinweise.append("Bilanzsumme aus Aktivposten summiert.")
    if "verbindlichkeiten" not in p:
        teile = ("verbindlichkeiten_kreditinstitute", "verbindlichkeiten_lul", "verbindlichkeiten_gesellschafter")
        if any(n in p for n in teile):
            p["verbindlichkeiten"] = [summe(teile, 0), summe(teile, 1)]
            a.hinweise.append("Verbindlichkeiten aus Teilposten summiert (ggf. unvollständig).")
    if "jahresueberschuss" not in p and "bilanzgewinn" in p and "gewinnvortrag" in p:
        bg, gv = p["bilanzgewinn"], p["gewinnvortrag"]
        p["jahresueberschuss"] = [None if bg[i] is None or gv[i] is None else bg[i] - gv[i] for i in range(2)]
        a.hinweise.append("Jahresergebnis als Bilanzgewinn abzüglich Gewinnvortrag abgeleitet.")
    if "personalaufwand" not in p and "loehne_gehaelter" in p:
        p["personalaufwand"] = list(p["loehne_gehaelter"])


def _iso(d):
    t, m, j = d.split(".")
    return f"{j}-{m}-{t}"


def erkenne_rechtsform(name):
    n = (name or "").lower()
    for form, muster in RECHTSFORMEN:
        if re.search(muster, n):
            return form
    return ""


def erkenne_groessenklasse(text_klein):
    if "kleinstkapitalgesellschaft" in text_klein or "§ 267a" in text_klein or "267a hgb" in text_klein:
        return "kleinst"
    if "kleine kapitalgesellschaft" in text_klein or "§ 267 abs. 1" in text_klein or "größenabhängige erleichterungen" in text_klein \
            or "groessenabhaengige erleichterungen" in text_klein or "§ 274a" in text_klein or "§ 288" in text_klein or "§ 326" in text_klein:
        return "klein"
    if "mittelgroße kapitalgesellschaft" in text_klein or "§ 267 abs. 2" in text_klein:
        return "mittel"
    if "große kapitalgesellschaft" in text_klein or "§ 267 abs. 3" in text_klein:
        return "gross"
    return ""


def erkenne_mitarbeiter(text):
    muster = [
        r"durchschnittlich(?:e)?\s+(?:zahl\s+(?:der|von)\s+)?(?:beschäftigt\w*\s+)?(\d{1,5})\s+(?:arbeitnehmer|mitarbeiter|beschäftigte|angestellte)",
        r"(?:arbeitnehmer|mitarbeiter|beschäftigte)[^.\d]{0,80}?(?:durchschnitt\w*|jahresdurchschnitt)[^.\d]{0,40}?(\d{1,5})\b",
        r"(?:durchschnitt\w*|jahresdurchschnitt)[^.\d]{0,60}?(\d{1,5})\s+(?:arbeitnehmer|mitarbeiter|beschäftigte|angestellte|personen)",
        r"(?:anzahl|zahl)\s+der\s+(?:im\s+\w+\s+)?(?:durchschnittlich\s+)?beschäftigten\s+(?:arbeitnehmer|mitarbeiter)[^.\d]{0,60}?(\d{1,5})\b",
        r"beschäftigte\s+die\s+gesellschaft\s+(?:im\s+\w+\s+)?(?:durchschnittlich\s+)?(\d{1,5})\s",
    ]
    t = re.sub(r"\s+", " ", text)
    for m in muster:
        f = re.search(m, t, re.I)
        if f:
            try:
                wert = int(f.group(1))
                if wert < 100000:
                    return wert
            except ValueError:
                pass
    if re.search(r"keine (arbeitnehmer|mitarbeiter) beschäftigt|beschäftigte keine (arbeitnehmer|mitarbeiter)", t, re.I):
        return 0
    return None
