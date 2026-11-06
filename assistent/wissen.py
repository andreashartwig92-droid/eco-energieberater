"""Wissensbasis: alle .md- und .txt-Dateien im Ordner `wissen/` werden Teil des Systemprompts.

Die Dateien werden alphabetisch sortiert eingelesen. Mit einem Zahlenpräfix (00_, 10_, ...)
steuert man die Reihenfolge. Ändert sich eine Datei, wird der Server neu gestartet
(oder `Wissen.laden()` erneut aufgerufen).
"""

import logging
from pathlib import Path

log = logging.getLogger("assistent.wissen")

ENDUNGEN = (".md", ".txt")
WARNGRENZE_ZEICHEN = 400_000  # ~100k Tokens; darüber wird es teuer und langsam


def lade_wissen(ordner):
    """Liefert (text, dateinamen). Fehlender Ordner → leerer Text."""
    ordner = Path(ordner)
    if not ordner.is_dir():
        log.warning("Wissensordner %s existiert nicht – die KI antwortet ohne eigenes Wissen", ordner)
        return "", []
    teile = []
    namen = []
    for datei in sorted(ordner.iterdir()):
        if datei.suffix.lower() not in ENDUNGEN or datei.name.startswith("."):
            continue
        inhalt = datei.read_text(encoding="utf-8").strip()
        if not inhalt:
            continue
        namen.append(datei.name)
        teile.append(f"<dokument name=\"{datei.name}\">\n{inhalt}\n</dokument>")
    text = "\n\n".join(teile)
    if len(text) > WARNGRENZE_ZEICHEN:
        log.warning("Wissensbasis ist %d Zeichen groß – jede Anfrage wird dadurch teuer", len(text))
    log.info("Wissensbasis: %d Dateien, %d Zeichen", len(namen), len(text))
    return text, namen
