"""Einstellungen aus Umgebungsvariablen (BILANZ_*)."""

import os
from dataclasses import dataclass
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


def _int(name, standard):
    wert = os.environ.get(name)
    return standard if wert is None or wert.strip() == "" else int(wert)


def _float(name, standard):
    wert = os.environ.get(name)
    return standard if wert is None or wert.strip() == "" else float(wert.replace(",", "."))


def _bool(name, standard):
    wert = os.environ.get(name)
    if wert is None or wert == "":
        return standard
    return wert.strip().lower() in ("1", "true", "ja", "yes", "on")


@dataclass
class Konfig:
    host: str = "127.0.0.1"
    port: int = 8081
    passwort: str = ""
    datenbank: Path = WURZEL / "daten" / "bilanzen.sqlite"
    pause: float = 2.0  # Sekunden zwischen zwei Anfragen an den Bundesanzeiger
    max_seiten_standard: int = 5  # Trefferseiten je Suchbegriff (20 Treffer je Seite)
    vertraue_proxy: bool = False
    max_anfrage_bytes: int = 20_000_000  # Import von Abschlüssen (HTML) über die Oberfläche
    name: str = "Bilanz-Radar"

    @property
    def passwort_noetig(self):
        return self.host not in ("127.0.0.1", "localhost", "::1")

    @classmethod
    def aus_umgebung(cls):
        k = cls(
            host=os.environ.get("BILANZ_HOST", "127.0.0.1"),
            port=_int("BILANZ_PORT", 8081),
            passwort=os.environ.get("BILANZ_PASSWORT", ""),
            datenbank=Path(os.environ.get("BILANZ_DATENBANK") or (WURZEL / "daten" / "bilanzen.sqlite")),
            pause=_float("BILANZ_PAUSE", 2.0),
            max_seiten_standard=_int("BILANZ_MAX_SEITEN", 5),
            vertraue_proxy=_bool("BILANZ_VERTRAUE_PROXY", False),
            name=os.environ.get("BILANZ_NAME", "Bilanz-Radar"),
        )
        if k.passwort_noetig and not k.passwort:
            raise ValueError("BILANZ_PASSWORT muss gesetzt sein, sobald BILANZ_HOST nicht 127.0.0.1 ist.")
        if k.pause < 1.0:
            raise ValueError("BILANZ_PAUSE unter 1 Sekunde ist nicht erlaubt (Rücksicht auf den Bundesanzeiger).")
        return k
