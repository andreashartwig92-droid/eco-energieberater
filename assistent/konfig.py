"""Konfiguration aus Umgebungsvariablen (siehe deploy/.env.beispiel)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

EFFORT_STUFEN = ("low", "medium", "high", "xhigh", "max")
BACKENDS = ("lokal", "claude")
STANDARD_MODELL = {"lokal": "qwen3:8b", "claude": "claude-opus-5-5"}


def _bool(name, standard):
    wert = os.environ.get(name)
    if wert is None or wert == "":
        return standard
    return wert.strip().lower() in ("1", "true", "ja", "yes", "on")


def _denken(wert):
    """KI_DENKEN: leer/aus → False, an → True, auto → None (Modellstandard)."""
    if wert is None or wert.strip() == "":
        return False
    w = wert.strip().lower()
    if w in ("auto", "standard", "modell"):
        return None
    return w in ("1", "true", "ja", "yes", "on", "an")


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
    backend: str = "lokal"  # "lokal" = eigenes Modell über Ollama, "claude" = Anthropic-API
    modell: str = ""  # leer = Standard des Backends
    max_tokens: int = 16000
    # nur lokal (Ollama)
    ollama_url: str = "http://127.0.0.1:11434"
    num_ctx: int = 16384  # Kontextfenster in Token; Wissensbasis + Werkzeuge + Gespräch müssen hineinpassen
    denken: object = False  # None = Modellstandard, False = Denkmodus aus (schneller), True = an
    ollama_keep_alive: str = "30m"
    zeitlimit: int = 600  # Sekunden je Modellantwort (CPU-Betrieb ist langsam)
    # nur Claude
    effort: str = "medium"
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

    def __post_init__(self):
        if not self.modell:
            self.modell = STANDARD_MODELL.get(self.backend, "")

    @classmethod
    def aus_umgebung(cls):
        k = cls(
            host=os.environ.get("KI_HOST", "127.0.0.1"),
            port=_int("KI_PORT", 8080),
            passwort=os.environ.get("KI_PASSWORT", ""),
            backend=os.environ.get("KI_BACKEND", "lokal").strip().lower(),
            modell=os.environ.get("KI_MODELL", ""),
            max_tokens=_int("KI_MAX_TOKENS", 16000),
            ollama_url=os.environ.get("KI_OLLAMA_URL", "http://127.0.0.1:11434"),
            num_ctx=_int("KI_NUM_CTX", 16384),
            denken=_denken(os.environ.get("KI_DENKEN")),
            ollama_keep_alive=os.environ.get("KI_KEEP_ALIVE", "30m"),
            zeitlimit=_int("KI_ZEITLIMIT", 600),
            effort=os.environ.get("KI_EFFORT", "medium"),
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
        if self.backend not in BACKENDS:
            raise ValueError(f"KI_BACKEND muss {' oder '.join(BACKENDS)} sein, nicht {self.backend!r}")
        if not self.modell:
            self.modell = STANDARD_MODELL[self.backend]
        if self.num_ctx < 2048:
            raise ValueError("KI_NUM_CTX zu klein (mindestens 2048)")
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
