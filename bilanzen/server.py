"""HTTP-Server (Standardbibliothek) für die interne Oberfläche des Bilanz-Radars.

Routen (JSON, Anmeldung über Header `Authorization: Bearer <BILANZ_PASSWORT>`, lokal ohne Passwort):
  GET  /                              Oberfläche
  GET  /gesund                        Health-Check
  GET  /api/info                      Name, Passwortpflicht, Statistik, Suchbegriffe
  GET  /api/auftraege                 alle Aufträge
  POST /api/auftraege                 {begriffe: [...], max_seiten, nur_neue, nur_liste, ab_jahr, nur_juengster} → neuer Auftrag im Unternehmensregister
  GET  /api/auftraege/<id>            Zustand (inkl. Captcha-Bild als data-URL, wenn offen)
  POST /api/auftraege/<id>/captcha    {loesung} – "bestaetigt", wenn ein Mensch „Ich bin ein Mensch“ bestätigt hat
  POST /api/auftraege/<id>/abbrechen
  GET  /api/firmen?suchbegriff=       Firmenliste mit Kennzahlen des jüngsten Abschlusses
  GET  /api/firmen/<id>               Firma mit allen Abschlüssen, Posten und Kennzahlen
  DELETE /api/firmen/<id>
  GET  /api/abschluesse/<id>/roh      Originaldokument (HTML, in Sandbox-iframe anzeigbar)
  GET  /api/branche?suchbegriff=      Branchenbild und Urteil
  GET  /api/vorreiter?suchbegriff=&n= Rangliste der Vorreiter (Wachstum, Ertrag, Größe, Substanz, Mehrjahrestrend)
  POST /api/import-csv                {dateiname, text, suchbegriff, teur?} → Kennzahlen aus CSV (z. B. lizenzierte Daten)
  POST /api/import                    {dateiname, html, name?, ort?, suchbegriff?} → Abschluss aus Datei (z. B. Unternehmensregister)
  POST /api/neu-berechnen             alle gespeicherten Dokumente mit dem aktuellen Parser neu auswerten
  GET  /api/export.csv?suchbegriff=   Kennzahlen als CSV (Semikolon, deutsche Zahlen)
  GET  /api/uebersprungen?suchbegriff=
"""

import csv
import hmac
import io
import json
import logging
import re
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import bewertung, csv_import, vorreiter
from .auftraege import Verwalter
from .speicher import Speicher

log = logging.getLogger("bilanzen.server")
STATIC = Path(__file__).resolve().parent / "static"

CSV_SPALTEN = [
    ("name", "Firma"), ("ort", "Ort"), ("rechtsform", "Rechtsform"), ("gj_bis", "Geschäftsjahr bis"), ("quelle", "Quelle"),
    ("k:bilanzsumme", "Bilanzsumme €"), ("k:eigenkapital", "Eigenkapital €"), ("k:umsatz", "Umsatz €"), ("k:jahresueberschuss", "Jahresergebnis €"),
    ("k:ergebnis_geschaetzt", "Ergebnis geschätzt"), ("k:eigenkapitalquote", "EK-Quote"), ("k:umsatzrendite", "Umsatzrendite"),
    ("k:gesamtkapitalrendite", "Gesamtkapitalrendite"), ("k:wachstum_umsatz", "Umsatzwachstum"), ("k:wachstum_bilanzsumme", "Wachstum Bilanzsumme"),
    ("k:liquiditaet", "Liquidität (Kasse/Verb.)"), ("k:anlagenintensitaet", "Anlagenintensität"), ("k:personalaufwandsquote", "Personalaufwandsquote"),
    ("k:mitarbeiter", "Mitarbeiter"), ("k:score", "Score"), ("k:ampel", "Ampel"), ("k:datenlage", "Datenlage"),
]


class Anwendung:
    def __init__(self, konfig, speicher=None, verwalter=None):
        self.konfig = konfig
        self.speicher = speicher or Speicher(konfig.datenbank)
        self.verwalter = verwalter or Verwalter(self.speicher, pause=konfig.pause, chromium_pfad=konfig.chromium)

    def quellen(self):
        from .unternehmensregister import verfuegbar
        ok, grund = verfuegbar(self.konfig.chromium)
        if getattr(self.verwalter, "_eigene_fabrik", False):  # Tests mit Attrappe
            ok, grund = True, ""
        return {"unternehmensregister": {"bereit": ok, "hinweis": grund or "Suche und Abruf direkt im Unternehmensregister (alle offengelegten "
                                                                       "Jahresabschlüsse, auch die älteren aus dem Bundesanzeiger)"}}

    def quelle_standard(self):
        return "unternehmensregister" if self.quellen()["unternehmensregister"]["bereit"] else ""

    def angemeldet(self, header_wert):
        if not self.konfig.passwort_noetig:
            return True
        if not header_wert or not header_wert.startswith("Bearer "):
            return False
        return hmac.compare_digest(header_wert[7:].strip(), self.konfig.passwort)

    def branche(self, suchbegriff):
        firmen = [f for f in self.speicher.firmen(suchbegriff) if f.get("kennzahlen")]
        return bewertung.branchenbild(firmen, suchbegriff or "alle gespeicherten Unternehmen")


class Handler(BaseHTTPRequestHandler):
    server_version = "eco-bilanzradar/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        log.info("%s %s", self._client(), fmt % args)

    def _client(self):
        if self.app.konfig.vertraue_proxy:
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                return xff.split(",")[0].strip()
        return self.client_address[0]

    # --- Antworten -------------------------------------------------------

    def _senden(self, status, daten, typ, zusatz=None):
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(daten)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (zusatz or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(daten)

    def _json(self, status, daten):
        self._senden(status, json.dumps(daten, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _fehler(self, status, text):
        self.close_connection = True
        self._json(status, {"fehler": text})

    def _pruefe_anmeldung(self):
        if self.app.angemeldet(self.headers.get("Authorization")):
            return True
        self._fehler(HTTPStatus.UNAUTHORIZED, "Passwort fehlt oder ist falsch.")
        return False

    def _query(self):
        q = urllib.parse.urlparse(self.path).query
        return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}

    # --- GET ---------------------------------------------------------------

    def do_GET(self):
        pfad = urllib.parse.urlparse(self.path).path
        if pfad in ("/", "/index.html"):
            daten = (STATIC / "index.html").read_bytes()
            return self._senden(HTTPStatus.OK, daten, "text/html; charset=utf-8")
        if pfad == "/gesund":
            return self._json(HTTPStatus.OK, {"status": "ok"})
        if pfad == "/api/info":
            k = self.app.konfig
            return self._json(HTTPStatus.OK, {"name": k.name, "passwort_noetig": k.passwort_noetig, "pause": k.pause,
                                              "max_seiten_standard": k.max_seiten_standard, "statistik": self.app.speicher.statistik(),
                                              "quellen": self.app.quellen(), "quelle_standard": self.app.quelle_standard()})
        if not pfad.startswith("/api/"):
            return self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        if not self._pruefe_anmeldung():
            return
        q = self._query()
        if pfad == "/api/auftraege":
            return self._json(HTTPStatus.OK, {"auftraege": self.app.verwalter.liste()})
        m = re.fullmatch(r"/api/auftraege/([0-9a-f]+)", pfad)
        if m:
            a = self.app.verwalter.holen(m.group(1))
            return self._json(HTTPStatus.OK, a.als_dict()) if a else self._fehler(HTTPStatus.NOT_FOUND, "Auftrag unbekannt")
        if pfad == "/api/firmen":
            return self._json(HTTPStatus.OK, {"firmen": self.app.speicher.firmen(q.get("suchbegriff") or None)})
        m = re.fullmatch(r"/api/firmen/(\d+)", pfad)
        if m:
            f = self.app.speicher.firma(int(m.group(1)))
            return self._json(HTTPStatus.OK, f) if f else self._fehler(HTTPStatus.NOT_FOUND, "Firma unbekannt")
        m = re.fullmatch(r"/api/abschluesse/(\d+)/roh", pfad)
        if m:
            html = self.app.speicher.roh_html(int(m.group(1)))
            if html is None:
                return self._fehler(HTTPStatus.NOT_FOUND, "Abschluss unbekannt")
            return self._senden(HTTPStatus.OK, html.encode("utf-8"), "text/html; charset=utf-8",
                                {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:", "X-Frame-Options": "SAMEORIGIN"})
        if pfad == "/api/branche":
            return self._json(HTTPStatus.OK, self.app.branche(q.get("suchbegriff") or None))
        if pfad == "/api/vorreiter":
            try:
                n = int(q.get("n") or 20)
            except ValueError:
                n = 20
            firmen = self.app.speicher.firmen(q.get("suchbegriff") or None)
            return self._json(HTTPStatus.OK, vorreiter.rangliste(firmen, n=n))
        if pfad == "/api/uebersprungen":
            return self._json(HTTPStatus.OK, {"uebersprungen": self.app.speicher.uebersprungene(q.get("suchbegriff") or None)})
        if pfad == "/api/export.csv":
            return self._csv(q.get("suchbegriff") or None)
        self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")

    def _csv(self, suchbegriff):
        puffer = io.StringIO()
        w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
        w.writerow([titel for _, titel in CSV_SPALTEN])
        for f in self.app.speicher.firmen(suchbegriff):
            k = f.get("kennzahlen") or {}
            zeile = []
            for schluessel, _ in CSV_SPALTEN:
                wert = k.get(schluessel[2:]) if schluessel.startswith("k:") else f.get(schluessel)
                if isinstance(wert, bool):
                    wert = "ja" if wert else "nein"
                elif isinstance(wert, float):
                    wert = f"{wert:.4f}".replace(".", ",")
                zeile.append("" if wert is None else wert)
            w.writerow(zeile)
        daten = ("﻿" + puffer.getvalue()).encode("utf-8")
        self._senden(HTTPStatus.OK, daten, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="bilanzen.csv"'})

    # --- POST / DELETE -----------------------------------------------------

    def _rumpf_json(self):
        try:
            laenge = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            laenge = 0
        if laenge < 0 or laenge > self.app.konfig.max_anfrage_bytes:
            self.close_connection = True
            self._fehler(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Anfrage zu groß")
            return None
        rumpf = self.rfile.read(laenge) if laenge else b"{}"
        try:
            daten = json.loads(rumpf.decode("utf-8") or "{}")
            if not isinstance(daten, dict):
                raise ValueError("Objekt erwartet")
            return daten
        except (ValueError, UnicodeDecodeError) as e:
            self._fehler(HTTPStatus.BAD_REQUEST, f"Ungültiges JSON: {e}")
            return None

    def do_POST(self):
        pfad = urllib.parse.urlparse(self.path).path
        daten = self._rumpf_json()
        if daten is None:
            return
        if not self._pruefe_anmeldung():
            return
        try:
            if pfad == "/api/auftraege":
                begriffe = daten.get("begriffe")
                if isinstance(begriffe, str):
                    begriffe = re.split(r"[\n;,]+", begriffe)
                if not isinstance(begriffe, list):
                    raise ValueError("begriffe fehlt")
                if not self.app.quelle_standard():
                    raise ValueError("Unternehmensregister nicht nutzbar: " + self.app.quellen()["unternehmensregister"]["hinweis"])
                a = self.app.verwalter.anlegen(
                    [str(b) for b in begriffe], max_seiten=daten.get("max_seiten", self.app.konfig.max_seiten_standard),
                    nur_neue=daten.get("nur_neue", True), nur_liste=daten.get("nur_liste", False), ab_jahr=daten.get("ab_jahr") or 0,
                    nur_juengster=daten.get("nur_juengster", False))
                return self._json(HTTPStatus.CREATED, a.als_dict())
            m = re.fullmatch(r"/api/auftraege/([0-9a-f]+)/captcha", pfad)
            if m:
                self.app.verwalter.captcha_beantworten(m.group(1), str(daten.get("loesung", "")))
                return self._json(HTTPStatus.OK, {"ok": True})
            m = re.fullmatch(r"/api/auftraege/([0-9a-f]+)/abbrechen", pfad)
            if m:
                self.app.verwalter.abbrechen(m.group(1))
                return self._json(HTTPStatus.OK, {"ok": True})
            if pfad == "/api/import":
                return self._import(daten)
            if pfad == "/api/import-csv":
                text = daten.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("text fehlt (Inhalt der CSV-Datei)")
                try:
                    ergebnis = csv_import.importieren(self.app.speicher, text, suchbegriff=(daten.get("suchbegriff") or "").strip(),
                                                      dateiname=daten.get("dateiname") or "", einheit_teur=bool(daten.get("teur")))
                except csv_import.CsvFehler as e:
                    raise ValueError(str(e)) from e
                return self._json(HTTPStatus.CREATED, ergebnis)
            if pfad == "/api/neu-berechnen":
                n = self.app.speicher.neu_berechnen()
                return self._json(HTTPStatus.OK, {"neu_berechnet": n})
        except KeyError:
            return self._fehler(HTTPStatus.NOT_FOUND, "Auftrag unbekannt")
        except ValueError as e:
            return self._fehler(HTTPStatus.BAD_REQUEST, str(e))
        self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")

    def _import(self, daten):
        html = daten.get("html")
        if not isinstance(html, str) or not html.strip():
            raise ValueError("html fehlt (Inhalt der Datei)")
        name = (daten.get("name") or "").strip()
        from .parser import parse_jahresabschluss
        if not name:
            vorab = parse_jahresabschluss(html)
            name = vorab.firma or Path(daten.get("dateiname") or "Import").stem
        firma_id, abschluss_id, abschluss = self.app.speicher.dokument_speichern(
            name, (daten.get("ort") or "").strip(), html, titel=daten.get("titel") or "Import: " + (daten.get("dateiname") or ""),
            suchbegriff=(daten.get("suchbegriff") or "").strip(), quelle="import", quelle_url=daten.get("dateiname") or "")
        return self._json(HTTPStatus.CREATED, {"firma_id": firma_id, "abschluss_id": abschluss_id, "abschluss": abschluss.als_dict()})

    def do_DELETE(self):
        pfad = urllib.parse.urlparse(self.path).path
        if not self._pruefe_anmeldung():
            return
        m = re.fullmatch(r"/api/firmen/(\d+)", pfad)
        if m:
            self.app.speicher.firma_loeschen(int(m.group(1)))
            return self._json(HTTPStatus.OK, {"ok": True})
        self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, adresse, app):
        super().__init__(adresse, Handler)
        self.app = app


def erzeuge_server(konfig, speicher=None, verwalter=None):
    return Server((konfig.host, konfig.port), Anwendung(konfig, speicher, verwalter))


def starte(konfig):
    server = erzeuge_server(konfig)
    log.info("%s läuft auf http://%s:%d (Datenbank %s, Pause %.1f s, Passwort %s)", konfig.name, konfig.host, konfig.port,
             konfig.datenbank, konfig.pause, "aktiv" if konfig.passwort_noetig else "AUS – nur lokal")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.app.verwalter.stoppen()
        server.server_close()
