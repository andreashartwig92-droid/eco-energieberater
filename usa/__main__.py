"""Aufruf: python -m usa projekt.json [--ausgabe ordner]

Erzeugt zwei Musterunterlagen für ein US-Einfamilienhaus:
<projekt>_hvac_design_bericht.html/.pdf   (ACCA Manual J/S/D, ASHRAE 62.2)
<projekt>_energy_report_bericht.html/.pdf (IECC 2021 R405)
"""

import argparse
import json
import sys
from pathlib import Path

from heizlast.__main__ import als_pdf

from . import report_energy, report_hvac
from .energy import run_all
from .hvac import manual_d, manual_j, manual_s


def main(argv=None):
    ap = argparse.ArgumentParser(description="US-Musterunterlagen: HVAC Design Package und IECC-R405-Nachweis")
    ap.add_argument("projekt", help="Projektdatei (JSON)")
    ap.add_argument("--ausgabe", help="Zielordner (Standard: neben der Projektdatei)")
    args = ap.parse_args(argv)

    quelle = Path(args.projekt)
    p = json.loads(quelle.read_text(encoding="utf-8"))
    L = manual_j(p)
    S = manual_s(p, L)
    D = manual_d(p, L)
    R = run_all(p)

    ziel = Path(args.ausgabe) if args.ausgabe else quelle.parent
    ziel.mkdir(parents=True, exist_ok=True)
    for name, inhalt in (("hvac_design", report_hvac.html(p, L, S, D)), ("energy_report", report_energy.html(p, R))):
        h = ziel / f"{quelle.stem}_{name}_bericht.html"
        h.write_text(inhalt, encoding="utf-8")
        pdf = ziel / f"{quelle.stem}_{name}.pdf"
        print(f"{name}: {h}" + (f" und {pdf}" if als_pdf(h, pdf) else " (kein Chromium für PDF gefunden)"))

    print(f"Heating load {L.heating:,.0f} Btu/h · cooling {L.cooling:,.0f} Btu/h · friction rate {D.fr:.3f}")
    print(f"Proposed {R['proposed'].total:,.0f} kWh (${R['proposed'].cost:,.0f}) · reference {R['reference'].total:,.0f} kWh "
          f"(${R['reference'].cost:,.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
