"""Konfiguration aus Umgebungsvariablen (siehe deploy/.env.beispiel)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

EFFORT_STUFEN = ("low", "medium", "high", "xhigh", "max")


def _bool(name, standard):
    wert = os.environ.get(name)
    if wert is None or wert == "":
        return standard
    return wert.strip().lower() in ("1", "true", "ja", "yes", "on")


def _int(name, standard):
    wert = os.environ.get(name)
    if wert is None or wert.strip() == "":
        return standard
    return int(wert)


@dataclass
class Konfig:
    host: str = "127.0.0.1"
    port: int = 8080
    passwort: str = ""
    modell: str = "claude-opus-5-5"
    effort: str = "medium"
    max_tokens: int = 16000
    fallback: bool = True  # server-seitiger Fallback bei Sicherheitsablehnungen (Beta)
    wissen_ordner: Path = WURZEL / "wissen"
    berichte_ordner: Path = WURZEL / "berichte"
    limit_pro_stunde: int = 60
    vertraue_proxy: bool = False
    max_verlauf_nachrichten: int = 80
    max_anfrage_bytes: int = 1_000_000
    max_werkzeug_runden: int = 8
    name: str = "eco Energieberater-KI"
    zusatz: dict = field(default_factory=dict)

    @classmethod
    def aus_umgebung(cls):
        k = cls(
            host=os.environ.get("KI_HOST", "127.0.0.1"),
            port=_int("KI_PORT", 8080),
            passwort=os.environ.get("KI_PASSWORT", ""),
            modell=os.environ.get("KI_MODELL", "claude-opus-5-5"),
            effort=os.environ.get("KI_EFFORT", "medium"),
            max_tokens=_int("KI_MAX_TOKENS", 16000),
            fallback=_bool("KI_FALLBACK", True),
            wissen_ordner=Path(os.environ.get("KI_WISSEN", WURZEL / "wissen")),
            berichte_ordner=Path(os.environ.get("KI_BERICHTE", WURZEL / "berichte")),
            limit_pro_stunde=_int("KI_LIMIT_PRO_STUNDE", 60),
            vertraue_proxy=_bool("KI_VERTRAUE_PROXY", False),
            name=os.environ.get("KI_NAME", "eco Energieberater-KI"),
        )
        k.pruefen()
        return k

    def pruefen(self):
        if self.effort not in EFFORT_STUFEN:
            raise ValueError(f"KI_EFFORT muss eine von {EFFORT_STUFEN} sein, nicht {self.effort!r}")
        if self.max_tokens < 256:
            raise ValueError("KI_MAX_TOKENS zu klein")
        if not self.passwort and self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "KI_PASSWORT ist leer, der Server soll aber auf "
                f"{self.host} erreichbar sein. Ohne Passwort könnte jeder auf Ihre Kosten "
                "Anfragen stellen. Setzen Sie KI_PASSWORT oder binden Sie an 127.0.0.1 "
                "hinter einem Reverse-Proxy mit eigener Anmeldung."
            )

    @property
    def passwort_noetig(self):
        return bool(self.passwort)
