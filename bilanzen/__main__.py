"""Aufruf:
  python -m bilanzen                                   Webserver (Oberfläche) starten, http://127.0.0.1:8081
  python -m bilanzen suche "Energieberatung" [--seiten 3] [--nur-liste] [--quelle unternehmensregister]
  python -m bilanzen suche "Energieberatung" --quelle openregister [--suchfeld zweck|name|branche] [--ort Hamburg]
  python -m bilanzen diagnose "Energieberatung" [--sichtbar]   Unternehmensregister Schritt für Schritt prüfen
  python -m bilanzen import datei.html [...] [--suchbegriff Energieberatung]
  python -m bilanzen bericht [--suchbegriff Energieberatung]
  python -m bilanzen vorreiter [--suchbegriff Energieberatung] [--n 20]
  python -m bilanzen import-csv daten.csv [--suchbegriff Energieberatung] [--teur]
  python -m bilanzen export [--suchbegriff ...] > bilanzen.csv
  python -m bilanzen neu-berechnen
"""

import argparse
import logging
import sys
from pathlib import Path

from .konfig import Konfig


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bilanz-Radar: Jahresabschlüsse aus dem Bundesanzeiger auswerten")
    sub = ap.add_subparsers(dest="befehl")
    sub.add_parser("server", help="Webserver starten (Standard)")
    s = sub.add_parser("suche", help="Suchbegriff abfragen und Abschlüsse laden (Captcha im Terminal lösen)")
    s.add_argument("begriffe", nargs="+")
    s.add_argument("--seiten", type=int, default=None, help="Trefferseiten je Begriff (0 = alle)")
    s.add_argument("--nur-liste", action="store_true", help="nur Treffer anzeigen, nichts laden")
    s.add_argument("--auch-vorhandene", action="store_true", help="bereits gespeicherte Abschlüsse erneut laden")
    s.add_argument("--quelle", choices=("bundesanzeiger", "unternehmensregister", "openregister"), default="bundesanzeiger")
    s.add_argument("--suchfeld", choices=("zweck", "name", "branche"), default="zweck", help="OpenRegister: Unternehmensgegenstand, Firmenname oder WZ-Code")
    s.add_argument("--ort", default="", help="OpenRegister: auf Orte eingrenzen (Komma-getrennt)")
    s.add_argument("--auch-inaktive", action="store_true", help="OpenRegister: auch gelöschte/inaktive Firmen")
    d = sub.add_parser("diagnose", help="Unternehmensregister: Suche, Trefferliste und erste Veröffentlichung bis zum Captcha durchspielen")
    d.add_argument("begriff")
    d.add_argument("--sichtbar", action="store_true", help="Browserfenster anzeigen statt unsichtbar laufen zu lassen")
    d.add_argument("--ordner", default=None, help="Ablage für Bildschirmfotos und Seitenquelltexte (Standard: daten/diagnose)")
    i = sub.add_parser("import", help="Jahresabschluss-Dateien (HTML/XHTML, z. B. aus dem Unternehmensregister) einlesen")
    i.add_argument("dateien", nargs="+")
    i.add_argument("--suchbegriff", default="", help="Branche/Suchbegriff, dem die Firmen zugeordnet werden")
    i.add_argument("--name", default="", help="Firmenname (sonst aus dem Dokument)")
    b = sub.add_parser("bericht", help="Branchenbild im Terminal ausgeben")
    b.add_argument("--suchbegriff", default=None)
    vr = sub.add_parser("vorreiter", help="Rangliste der Vorreiter einer Branche")
    vr.add_argument("--suchbegriff", default=None)
    vr.add_argument("--n", type=int, default=20)
    ic = sub.add_parser("import-csv", help="Kennzahlen aus CSV (lizenzierte Daten, eigene Listen) übernehmen")
    ic.add_argument("dateien", nargs="+")
    ic.add_argument("--suchbegriff", default="")
    ic.add_argument("--teur", action="store_true", help="Beträge in der Datei stehen in TEUR")
    e = sub.add_parser("export", help="CSV auf die Standardausgabe")
    e.add_argument("--suchbegriff", default=None)
    sub.add_parser("neu-berechnen", help="alle gespeicherten Dokumente neu auswerten")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        konfig = Konfig.aus_umgebung()
    except ValueError as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2

    if args.befehl in (None, "server"):
        from .server import starte
        starte(konfig)
        return 0
    from .speicher import Speicher
    speicher = Speicher(konfig.datenbank)
    if args.befehl == "suche":
        return suche(konfig, speicher, args.begriffe, args.seiten if args.seiten is not None else konfig.max_seiten_standard,
                     args.nur_liste, not args.auch_vorhandene, args.quelle,
                     {"suchfeld": args.suchfeld, "ort": args.ort, "nur_aktive": not args.auch_inaktive})
    if args.befehl == "diagnose":
        from .unternehmensregister import diagnose
        ordner = Path(args.ordner) if args.ordner else Path(konfig.datenbank).parent / "diagnose"
        for zeile in diagnose(args.begriff, ordner, chromium_pfad=konfig.chromium or None, sichtbar=args.sichtbar, pause=konfig.pause):
            print(zeile)
        print(f"Dateien liegen in {ordner}")
        return 0
    if args.befehl == "import":
        return importieren(speicher, args.dateien, args.suchbegriff, args.name)
    if args.befehl == "bericht":
        return bericht(speicher, args.suchbegriff)
    if args.befehl == "vorreiter":
        return vorreiter_bericht(speicher, args.suchbegriff, args.n)
    if args.befehl == "import-csv":
        from . import csv_import
        for datei in args.dateien:
            p = Path(datei)
            try:
                r = csv_import.importieren(speicher, p.read_bytes().decode("utf-8-sig", errors="replace"), args.suchbegriff, p.name, args.teur)
            except csv_import.CsvFehler as e:
                print(f"{p.name}: {e}", file=sys.stderr)
                return 1
            print(f"{p.name}: {r['abschluesse']} Abschlüsse von {r['firmen']} Firmen übernommen")
        return 0
    if args.befehl == "export":
        return export(speicher, args.suchbegriff)
    if args.befehl == "neu-berechnen":
        print(f"{speicher.neu_berechnen()} Abschlüsse neu ausgewertet.")
        return 0
    return 0


def suche(konfig, speicher, begriffe, seiten, nur_liste, nur_neue, quelle="bundesanzeiger", optionen=None):
    """Wie der Hintergrundauftrag, aber im Vordergrund; Captcha-Bild wird als Datei abgelegt und abgefragt."""
    import time

    from .auftraege import Verwalter

    verwalter = Verwalter(speicher, pause=konfig.pause, chromium_pfad=konfig.chromium or None)
    try:
        a = verwalter.anlegen(begriffe, max_seiten=seiten, nur_neue=nur_neue, nur_liste=nur_liste, quelle=quelle, optionen=optionen)
    except ValueError as e:
        print(e, file=sys.stderr)
        verwalter.stoppen()
        return 2
    gesehen = 0
    try:
        while a.zustand not in ("fertig", "fehler", "abgebrochen"):
            for eintrag in list(a.protokoll)[gesehen:]:
                print(eintrag["text"])
            gesehen = len(a.protokoll)
            if a.zustand == "captcha" and a.captcha is not None:
                endung = ".png" if "png" in a.captcha.bild_typ else ".jpg"
                pfad = Path(konfig.datenbank).parent / ("captcha" + endung)
                pfad.write_bytes(a.captcha.bild)
                loesung = input(f"Sicherheitsabfrage: Bild in {pfad} öffnen und Zeichen eingeben: ")
                verwalter.captcha_beantworten(a.id, loesung)
                time.sleep(0.5)
            time.sleep(0.5)
        for eintrag in list(a.protokoll)[gesehen:]:
            print(eintrag["text"])
    except KeyboardInterrupt:
        verwalter.abbrechen(a.id)
        print("\nAbgebrochen.")
    finally:
        verwalter.stoppen()
    if nur_liste:
        for t in a.treffer_liste:
            print(f"{'✓' if t['vorhanden'] else ' '} {t['gj_bis'] or '????':10} {t['name']} ({t['ort']}) – {t['titel']}")
    return 0 if a.zustand == "fertig" else 1


def importieren(speicher, dateien, suchbegriff, name):
    for datei in dateien:
        p = Path(datei)
        html = p.read_bytes().decode("utf-8", errors="replace")
        _, _, a = speicher.dokument_speichern(name, "", html, titel=f"Import: {p.name}", suchbegriff=suchbegriff, quelle="import", quelle_url=p.name)
        from .kennzahlen import berechne
        k = berechne(a)
        print(f"{p.name}: {a.firma or name} GJ bis {a.gj_bis or '?'} – {a.zeilen_erkannt} Posten, Score {k['score']}, {'; '.join(a.warnungen) or 'ok'}")
    return 0


def bericht(speicher, suchbegriff):
    from . import bewertung
    from .kennzahlen import geld, prozent

    firmen = [f for f in speicher.firmen(suchbegriff) if f.get("kennzahlen")]
    bild = bewertung.branchenbild(firmen, suchbegriff or "alle gespeicherten Unternehmen")
    print(f"Branchenbild: {bild['bezeichnung']} – {bild['anzahl']} Unternehmen")
    print(f"Urteil: {bild['urteil'].upper()} (Score {bild['score']})\n")
    for g in bild["begruendung"]:
        print(f"  • {g}")
    print()
    for h in bild["hinweise"]:
        print(f"  ! {h}")
    print(f"\n{'Firma':50} {'GJ':>5} {'Bilanzsumme':>14} {'EK-Quote':>9} {'Ums.-Rend.':>10} {'Score':>6}  Ampel")
    for f in sorted(firmen, key=lambda f: -(f["kennzahlen"].get("score") or 0)):
        k = f["kennzahlen"]
        print(f"{f['name'][:50]:50} {(f['gj_bis'] or '')[:4]:>5} {geld(k.get('bilanzsumme')):>14} {prozent(k.get('eigenkapitalquote'), 0):>9} "
              f"{prozent(k.get('umsatzrendite')):>10} {str(k.get('score') or '–'):>6}  {k.get('ampel')}")
    return 0


def vorreiter_bericht(speicher, suchbegriff, n):
    from . import vorreiter
    from .kennzahlen import geld, prozent

    r = vorreiter.rangliste(speicher.firmen(suchbegriff), n=n)
    print(f"Vorreiter: {suchbegriff or 'alle gespeicherten Unternehmen'} – {r['bewertet']} von {r['anzahl']} Unternehmen bewertet\n")
    print(f"{'Rang':>4} {'Firma':48} {'GJ':>5} {'Score':>6} {'Wachstum':>9} {'Ertrag':>8} {'Größe':>14}  Gründe")
    for e in r["rangliste"]:
        w = e["werte"]
        print(f"{str(e['rang'] or '–'):>4} {e['name'][:48]:48} {(e['gj_bis'] or '')[:4]:>5} {str(e['vorreiter_score'] if e['vorreiter_score'] is not None else '–'):>6} "
              f"{prozent(w['wachstum'], 0):>9} {prozent(w['ertrag']):>8} {geld(w['groesse']):>14}  {' '.join(e['gruende'][:2])}")
    print()
    for h in r["hinweise"]:
        print(f"  ! {h}")
    return 0


def export(speicher, suchbegriff):
    import csv

    from .server import CSV_SPALTEN

    w = csv.writer(sys.stdout, delimiter=";")
    w.writerow([t for _, t in CSV_SPALTEN])
    for f in speicher.firmen(suchbegriff):
        k = f.get("kennzahlen") or {}
        zeile = []
        for s, _ in CSV_SPALTEN:
            wert = k.get(s[2:]) if s.startswith("k:") else f.get(s)
            if isinstance(wert, bool):
                wert = "ja" if wert else "nein"
            elif isinstance(wert, float):
                wert = f"{wert:.4f}".replace(".", ",")
            zeile.append("" if wert is None else wert)
        w.writerow(zeile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
