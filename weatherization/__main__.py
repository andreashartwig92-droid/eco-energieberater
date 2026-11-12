"""Aufruf: python -m weatherization projekt.json [--ausgabe ordner]

Erzeugt die Unterlagen eines Weatherization-Auftrags (englisch, US Letter):
<projekt>_audit_bericht.html/.pdf            Home Energy Audit Report mit SIR-Bewertung
<projekt>_work_order_bericht.html/.pdf       Work Order für die ausführende Firma
<projekt>_final_inspection_bericht.html/.pdf Final-Inspection-Formular für den QCI
"""

import argparse
import json
import sys
from pathlib import Path

from heizlast.__main__ import als_pdf

from .audit import run
from .report import audit_html, inspection_html, workorder_html


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weatherization: Energieaudit mit SIR, Work Order und QC-Inspektion")
    ap.add_argument("projekt", help="Projektdatei (JSON)")
    ap.add_argument("--ausgabe", help="Zielordner (Standard: neben der Projektdatei)")
    args = ap.parse_args(argv)

    quelle = Path(args.projekt)
    p = json.loads(quelle.read_text(encoding="utf-8"))
    A = run(p)

    ziel = Path(args.ausgabe) if args.ausgabe else quelle.parent
    ziel.mkdir(parents=True, exist_ok=True)
    for name, inhalt in (("audit", audit_html(p, A)), ("work_order", workorder_html(p, A)),
                         ("final_inspection", inspection_html(p, A))):
        h = ziel / f"{quelle.stem}_{name}_bericht.html"
        h.write_text(inhalt, encoding="utf-8")
        pdf = ziel / f"{quelle.stem}_{name}.pdf"
        print(f"{name}: {h}" + (f" und {pdf}" if als_pdf(h, pdf) else " (kein Chromium für PDF gefunden)"))

    pr = p["prices"]
    print(f"Abrechnung: {A.bill.gas_normalized:,.0f} therms/Jahr normalisiert, Kalibrierfaktor {A.bill.calibration:.2f}, R² {A.bill.r2:.3f}")
    for x in A.measures:
        print(f"  {x.m['id']:5} {x.m['name'][:46]:46} ${x.cost:>7,.0f}  SIR {x.pkg.sir:5.2f}  {x.decision}")
    print(f"Paket: SIR {A.package.sir:.2f}, ${A.package.dollars:,.0f}/Jahr, Maßnahmen ${A.costs['ecm']:,.0f}, H&S ${A.costs['hs']:,.0f}")
    print(f"Energiekosten ${A.pre.cost(pr):,.0f} → ${A.post.cost(pr):,.0f} pro Jahr · CFM50 {A.pre_state.cfm50:,.0f} → ≤ {A.post_state.cfm50:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
