"""Aufruf: python -m heizlast projekt.json [--ausgabe ordner]

Erzeugt <projekt>_bericht.html und – falls Chromium vorhanden – <projekt>_bericht.pdf.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .abgleich import berechne_abgleich
from .bericht import erzeuge_html
from .heizlast import berechne_gebaeude
from .zahlen import de

CHROMIUM_KANDIDATEN = ("/opt/pw-browsers/chromium", "chromium", "chromium-browser", "google-chrome")


def _chromium():
    pfad = os.environ.get("CHROMIUM")
    if pfad:
        return pfad
    for k in CHROMIUM_KANDIDATEN:
        gefunden = shutil.which(k) or (k if os.path.exists(k) else None)
        if gefunden:
            return gefunden
    return None


def als_pdf(html_datei, pdf_datei):
    chrome = _chromium()
    if not chrome:
        return False
    subprocess.run(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_datei}", Path(html_datei).resolve().as_uri()],
        check=True, capture_output=True,
    )
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Heizlast (DIN EN 12831-1, vereinfacht) und hydraulischer Abgleich (Verfahren B)")
    ap.add_argument("projekt", help="Projektdatei (JSON)")
    ap.add_argument("--ausgabe", help="Zielordner (Standard: neben der Projektdatei)")
    ap.add_argument("--nur-heizlast", action="store_true", help="nur Heizlastberechnung ohne hydraulischen Abgleich (Dateiname *_heizlast)")
    args = ap.parse_args(argv)

    quelle = Path(args.projekt)
    projekt = json.loads(quelle.read_text(encoding="utf-8"))
    geb = berechne_gebaeude(projekt)
    abg = berechne_abgleich(projekt, geb)

    ziel = Path(args.ausgabe) if args.ausgabe else quelle.parent
    ziel.mkdir(parents=True, exist_ok=True)
    name = "heizlast" if args.nur_heizlast else "bericht"
    html_datei = ziel / f"{quelle.stem}_{name}.html"
    html_datei.write_text(erzeuge_html(projekt, geb, abg, nur_heizlast=args.nur_heizlast), encoding="utf-8")
    pdf_datei = ziel / f"{quelle.stem}_{name}.pdf"
    pdf_ok = als_pdf(html_datei, pdf_datei)

    print(f"Gebäude-Heizlast:        {de(geb.phi_HL / 1000, 2)} kW ({de(geb.spez)} W/m²)")
    print(f"Summe Raumheizlasten:    {de(geb.summe_raumheizlasten / 1000, 2)} kW")
    print(f"Vorlauf Bestand / Ausl.: {de(abg.theta_V_bestand, 1)} / {de(abg.theta_V, 1)} °C")
    print(f"Heizkörpertausch:        {sum(h.getauscht for h in abg.heizkoerper)} Stück")
    print(f"Pumpe:                   {de(abg.m_gesamt)} l/h, {de(abg.foerderhoehe_m, 2)} m")
    print(f"Bericht: {html_datei}" + (f" und {pdf_datei}" if pdf_ok else " (kein Chromium für PDF gefunden)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
