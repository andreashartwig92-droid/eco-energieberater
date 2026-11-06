"""Aufruf: python -m assistent            Webserver starten
         python -m assistent --terminal Gespräch im Terminal (zum Testen)
"""

import argparse
import logging
import sys

from .konfig import Konfig
from .wissen import lade_wissen


def main(argv=None):
    ap = argparse.ArgumentParser(description="Selbst gehosteter KI-Assistent für die Energieberatung")
    ap.add_argument("--terminal", action="store_true", help="statt Webserver: Gespräch im Terminal")
    ap.add_argument("--frage", help="eine einzelne Frage stellen und beenden")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.terminal or args.frage:
        konfig = Konfig.aus_umgebung() if not args.frage else _konfig_lokal()
        return terminal(konfig, args.frage)

    try:
        konfig = Konfig.aus_umgebung()
    except ValueError as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    from .server import starte
    starte(konfig)
    return 0


def _konfig_lokal():
    import os
    os.environ.setdefault("KI_HOST", "127.0.0.1")
    return Konfig.aus_umgebung()


def terminal(konfig, einzelfrage=None):
    from .verlauf import erzeuge_assistent
    wissen, _ = lade_wissen(konfig.wissen_ordner)
    ki = erzeuge_assistent(konfig, wissen)
    verlauf = []
    while True:
        frage = einzelfrage or input("\nSie: ").strip()
        if not frage or frage.lower() in ("exit", "quit", "ende"):
            return 0
        print("KI: ", end="", flush=True)
        for ev in ki.antworten(verlauf, frage):
            if ev["typ"] == "text":
                print(ev["text"], end="", flush=True)
            elif ev["typ"] == "werkzeug":
                print(f"\n  [{ev['name']}: {ev['status']}]", flush=True)
            elif ev["typ"] == "hinweis":
                print(f"\n  ({ev['text']})", flush=True)
            elif ev["typ"] == "fertig":
                verlauf = ev["verlauf"]
        print()
        if einzelfrage:
            return 0


if __name__ == "__main__":
    sys.exit(main())
