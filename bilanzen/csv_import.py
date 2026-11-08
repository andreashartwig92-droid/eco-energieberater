"""Kennzahlen aus CSV-Dateien übernehmen – etwa lizenzierte Bilanzdaten eines Datenanbieters oder eine eigene Excel-Liste.

Erwartet wird eine Kopfzeile; die Spalten werden an ihren Namen erkannt (Synonyme siehe SPALTEN). Zahlen dürfen im
deutschen Format stehen (1.234.567,89), Beträge in EUR oder TEUR (Spaltenname mit „TEUR“/„T€“ oder Kopfzeile mit
„in TEUR“). Je Zeile entsteht ein Abschluss (Firma + Geschäftsjahr); Vorjahreswerte kommen aus Spalten mit dem
Zusatz „Vorjahr“/„VJ“ oder aus der Zeile desselben Unternehmens zum Vorjahr.

    python -m bilanzen import-csv daten.csv --suchbegriff Energieberatung
"""

import csv
import io
import re

from .parser import Abschluss, erkenne_rechtsform, zahl

SPALTEN = {
    "name": ("firma", "firmenname", "unternehmen", "name", "gesellschaft", "company", "company_name"),
    "ort": ("ort", "sitz", "stadt", "city", "standort"),
    "jahr": ("jahr", "geschäftsjahr", "geschaeftsjahr", "gj", "stichtag", "bilanzstichtag", "year", "fiscal_year", "gj_bis", "geschäftsjahr bis"),
    "bilanzsumme": ("bilanzsumme", "total_assets", "summe aktiva", "gesamtkapital"),
    "eigenkapital": ("eigenkapital", "equity", "ek"),
    "umsatz": ("umsatz", "umsatzerlöse", "umsatzerloese", "revenue", "sales", "erlöse"),
    "jahresueberschuss": ("jahresüberschuss", "jahresueberschuss", "jahresergebnis", "ergebnis", "gewinn", "net_income", "jahresüberschuss/-fehlbetrag", "jü"),
    "mitarbeiter": ("mitarbeiter", "beschäftigte", "beschaeftigte", "employees", "ma", "arbeitnehmer"),
    "verbindlichkeiten": ("verbindlichkeiten", "liabilities", "fremdkapital"),
    "rueckstellungen": ("rückstellungen", "rueckstellungen", "provisions"),
    "anlagevermoegen": ("anlagevermögen", "anlagevermoegen", "fixed_assets", "av"),
    "umlaufvermoegen": ("umlaufvermögen", "umlaufvermoegen", "current_assets", "uv"),
    "liquide_mittel": ("liquide mittel", "liquide_mittel", "kasse", "bankguthaben", "cash", "zahlungsmittel", "flüssige mittel"),
    "personalaufwand": ("personalaufwand", "personalkosten", "personnel_expenses", "löhne und gehälter"),
    "materialaufwand": ("materialaufwand", "material"),
    "rechtsform": ("rechtsform", "legal_form"),
}
POSTEN = ("bilanzsumme", "eigenkapital", "umsatz", "jahresueberschuss", "verbindlichkeiten", "rueckstellungen", "anlagevermoegen",
          "umlaufvermoegen", "liquide_mittel", "personalaufwand", "materialaufwand")
VORJAHR = re.compile(r"\b(vorjahr|vj|prev(ious)?|py|t-1)\b", re.I)
TEUR = re.compile(r"\b(teur|t€|tsd|in tausend|thousand)\b", re.I)


class CsvFehler(Exception):
    pass


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("_", " ").replace("-", " ")).strip()


def _zuordnung(kopf):
    """Spaltenindex → (feld, vorjahr?, teur?). Unbekannte Spalten werden ignoriert."""
    zuordnung = {}
    for i, roh in enumerate(kopf):
        n = _norm(roh)
        if not n:
            continue
        vorjahr = bool(VORJAHR.search(n))
        teur = bool(TEUR.search(n))
        kern = TEUR.sub("", VORJAHR.sub("", n))
        kern = re.sub(r"[()€\[\]]|in eur|eur\b", "", kern).strip(" :.-")
        kern = re.sub(r"\s+", " ", kern)
        for feld, synonyme in SPALTEN.items():
            if kern in synonyme or kern.replace(" ", "_") in synonyme:
                zuordnung[i] = (feld, vorjahr, teur)
                break
    return zuordnung


def _jahr(wert):
    w = (wert or "").strip()
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", w)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", w)
    if m:
        return m.group(0)
    m = re.search(r"\b(19|20)\d{2}\b", w)
    return f"{m.group(0)}-12-31" if m else ""


def lese(text, einheit_teur=False):
    """CSV-Text → Liste von dicts: name, ort, gj_bis, rechtsform, posten {feld: [aktuell, vorjahr]}, mitarbeiter."""
    text = text.lstrip("﻿")
    probe = text[:4000]
    try:
        dialekt = csv.Sniffer().sniff(probe, delimiters=";,\t|")
    except csv.Error:
        dialekt = csv.excel
        dialekt.delimiter = ";" if probe.count(";") >= probe.count(",") else ","
    zeilen = list(csv.reader(io.StringIO(text), dialekt))
    zeilen = [z for z in zeilen if any(c.strip() for c in z)]
    if len(zeilen) < 2:
        raise CsvFehler("CSV braucht eine Kopfzeile und mindestens eine Datenzeile.")
    kopf = zeilen[0]
    teur_global = einheit_teur or bool(TEUR.search(" ".join(kopf)))
    zuordnung = _zuordnung(kopf)
    felder = {f for f, _, _ in zuordnung.values()}
    if "name" not in felder:
        raise CsvFehler(f"Keine Spalte für den Firmennamen erkannt (gefunden: {', '.join(kopf)}).")
    if not felder & set(POSTEN):
        raise CsvFehler("Keine Kennzahlenspalte erkannt (z. B. Bilanzsumme, Eigenkapital, Umsatz, Jahresüberschuss).")
    datensaetze = []
    for nr, zeile in enumerate(zeilen[1:], start=2):
        d = {"name": "", "ort": "", "gj_bis": "", "rechtsform": "", "posten": {}, "mitarbeiter": None, "zeile": nr}
        for i, wert in enumerate(zeile):
            if i not in zuordnung:
                continue
            feld, vorjahr, teur = zuordnung[i]
            wert = wert.strip()
            if feld in ("name", "ort", "rechtsform"):
                d[feld] = wert
            elif feld == "jahr":
                d["gj_bis"] = _jahr(wert)
            elif feld == "mitarbeiter":
                z = zahl(wert.replace(" ", ""))
                d["mitarbeiter"] = int(z) if z is not None else None
            else:
                z = zahl(wert)
                if z is None:
                    continue
                if teur or teur_global:
                    z *= 1000
                d["posten"].setdefault(feld, [None, None])[1 if vorjahr else 0] = z
        if not d["name"]:
            continue
        if not d["gj_bis"]:
            raise CsvFehler(f"Zeile {nr}: kein Geschäftsjahr/Stichtag erkannt.")
        d["rechtsform"] = d["rechtsform"] or erkenne_rechtsform(d["name"])
        datensaetze.append(d)
    _vorjahre_ergaenzen(datensaetze)
    return datensaetze


def _vorjahre_ergaenzen(datensaetze):
    """Fehlende Vorjahreswerte aus der Zeile desselben Unternehmens zum Vorjahr übernehmen."""
    nach_firma = {}
    for d in datensaetze:
        nach_firma.setdefault((d["name"].strip().lower(), d["ort"].strip().lower()), []).append(d)
    for gruppe in nach_firma.values():
        gruppe.sort(key=lambda d: d["gj_bis"])
        for vorher, jetzt in zip(gruppe, gruppe[1:]):
            if int(jetzt["gj_bis"][:4]) - int(vorher["gj_bis"][:4]) != 1:
                continue
            for feld, werte in vorher["posten"].items():
                if werte[0] is None:
                    continue
                aktuell = jetzt["posten"].setdefault(feld, [None, None])
                if aktuell[1] is None:
                    aktuell[1] = werte[0]


def als_abschluss(d, titel=""):
    a = Abschluss(firma=d["name"], titel=titel or f"CSV-Import Geschäftsjahr {d['gj_bis'][:4]}", gj_bis=d["gj_bis"], einheit="EUR",
                  posten={k: list(v) for k, v in d["posten"].items()}, mitarbeiter=d.get("mitarbeiter"), rechtsform=d.get("rechtsform", ""))
    a.guv_vorhanden = a.posten.get("umsatz", [None])[0] is not None or a.posten.get("jahresueberschuss", [None])[0] is not None
    a.zeilen_erkannt = len(a.posten)
    a.hinweise.append("Kennzahlen aus CSV übernommen (kein Originaldokument).")
    if not a.guv_vorhanden:
        a.hinweise.append("Kein Umsatz und kein Jahresergebnis in der Datei.")
    return a


def importieren(speicher, text, suchbegriff="", dateiname="", einheit_teur=False):
    """CSV in den Speicher übernehmen. Liefert eine Zusammenfassung."""
    datensaetze = lese(text, einheit_teur)
    firmen = set()
    for d in datensaetze:
        a = als_abschluss(d)
        firma_id = speicher.firma_anlegen(d["name"], d["ort"], a.rechtsform, suchbegriff)
        speicher.abschluss_speichern(firma_id, a, roh_html="", titel=a.titel, quelle="csv", quelle_url=dateiname)
        firmen.add(firma_id)
    return {"abschluesse": len(datensaetze), "firmen": len(firmen), "dateiname": dateiname}
