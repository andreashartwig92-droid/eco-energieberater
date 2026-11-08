"""Gemeinsame Datenklassen für Trefferlisten, Veröffentlichungen und Sicherheitsabfragen."""

import re
from dataclasses import dataclass, field


@dataclass
class Treffer:
    name: str
    ort: str
    titel: str
    link: str  # leer bei Hinterlegungen ohne einsehbares Dokument
    datum: str  # Veröffentlichungsdatum TT.MM.JJJJ
    bereich: str = ""
    quelle: str = "unternehmensregister"
    register: str = ""  # z. B. "Amtsgericht Hamburg HRB 98565"
    herkunft: str = ""  # wo die Veröffentlichung ursprünglich erschien: "Unternehmensregister" oder "Bundesanzeiger"

    @property
    def ist_jahresabschluss(self):
        t = self.titel.lower()
        return bool(self.link) and ("jahresabschluss" in t or "konzernabschluss" in t or "jahresfinanzbericht" in t)


@dataclass
class Seite:
    treffer: list
    nummer: int
    anzahl_treffer: int  # Veröffentlichungen laut Portal (Schätzung aus Seitenzahl, wenn nicht angegeben)
    naechste_url: str  # leer auf der letzten Seite
    url: str
    anzahl_seiten: int = 0


@dataclass
class Dokument:
    html: str
    url: str
    text: str = ""


@dataclass
class CaptchaNoetig(Exception):
    """Die Veröffentlichung steht hinter einer Sicherheitsabfrage.

    art = "bestaetigen": ein Kästchen „Ich bin ein Mensch“, das ein Mensch bestätigt (das Bild zeigt die Abfrage);
    art = "text": ein Bild mit Zeichen, die ein Mensch abliest und eintippt.
    """

    bild: bytes
    bild_typ: str
    formular_url: str
    seite_url: str
    versuch: int = 1
    felder: dict = field(default_factory=dict)
    art: str = "text"

    def __str__(self):
        return "Sicherheitsabfrage muss von einem Menschen gelöst werden"


def geschaeftsjahr_aus_titel(titel):
    """'Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021' → ('2021-01-01', '2021-12-31')."""
    daten = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", titel)
    iso = [f"{j}-{m}-{t}" for t, m, j in daten]
    if len(iso) >= 2:
        return iso[0], iso[1]
    if len(iso) == 1:
        return "", iso[0]
    m = re.search(r"\b(19|20)(\d{2})\b", titel)
    return ("", f"{m.group(0)}-12-31") if m else ("", "")
