"""HTTP-Server (Standardbibliothek) für die Chat-Oberfläche und die API.

Routen:
  GET  /                 Chat-Oberfläche
  GET  /api/info         Name, Modell, ob ein Passwort nötig ist (ohne Anmeldung)
  POST /api/chat         {verlauf, frage} → Server-Sent-Events (text, werkzeug, hinweis, fertig, fehler)
  GET  /berichte/<name>  von der KI erzeugte Berichte (HTML/PDF)
  GET  /gesund           Health-Check für Reverse-Proxy / Docker

Anmeldung: Header `Authorization: Bearer <KI_PASSWORT>`.
"""

import collections
import hmac
import json
import logging
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .ki_lokal import LokalesModellFehler
from .verlauf import ROLLEN, erzeuge_assistent, pruefe_verlauf
from .wissen import lade_wissen

log = logging.getLogger("assistent.server")
STATIC = Path(__file__).resolve().parent / "static"


class RateLimit:
    """Einfaches Zeitfenster pro Client (Anfragen pro Stunde)."""

    def __init__(self, pro_stunde):
        self.pro_stunde = pro_stunde
        self._treffer = collections.defaultdict(collections.deque)
        self._sperre = threading.Lock()

    def erlaubt(self, schluessel, jetzt=None):
        if self.pro_stunde <= 0:
            return True
        jetzt = time.monotonic() if jetzt is None else jetzt
        with self._sperre:
            q = self._treffer[schluessel]
            while q and jetzt - q[0] > 3600:
                q.popleft()
            if len(q) >= self.pro_stunde:
                return False
            q.append(jetzt)
            return True


class Anwendung:
    """Hält Konfiguration, Assistent und Rate-Limit; wird vom Handler über server.app erreicht."""

    def __init__(self, konfig, ki=None):
        self.konfig = konfig
        self.limit = RateLimit(konfig.limit_pro_stunde)
        if ki is None:
            wissen, dateien = lade_wissen(konfig.wissen_ordner)
            self.wissen_dateien = dateien
            ki = erzeuge_assistent(konfig, wissen)
        else:
            self.wissen_dateien = []
        self.ki = ki
        self.rollen = ROLLEN.get(konfig.backend, ROLLEN["claude"])

    def status(self):
        """Erreichbarkeit des Modells (nur lokal prüfbar)."""
        if hasattr(self.ki, "pruefe_verbindung"):
            ok, meldung = self.ki.pruefe_verbindung()
            return {"bereit": ok, "meldung": meldung}
        return {"bereit": True, "meldung": "Claude-API"}

    def angemeldet(self, header_wert):
        if not self.konfig.passwort_noetig:
            return True
        if not header_wert or not header_wert.startswith("Bearer "):
            return False
        return hmac.compare_digest(header_wert[7:].strip(), self.konfig.passwort)


class Handler(BaseHTTPRequestHandler):
    server_version = "eco-assistent/1.0"
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

    def _json(self, status, daten):
        body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _datei(self, pfad, typ, download=False):
        daten = pfad.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(daten)))
        if download:
            self.send_header("Content-Disposition", f'inline; filename="{pfad.name}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(daten)

    def _fehler(self, status, text):
        self.close_connection = True
        self._json(status, {"fehler": text})

    def _pruefe_anmeldung(self):
        if self.app.angemeldet(self.headers.get("Authorization")):
            return True
        self._fehler(HTTPStatus.UNAUTHORIZED, "Passwort fehlt oder ist falsch.")
        return False

    # --- Routen ----------------------------------------------------------

    def do_GET(self):
        pfad = self.path.split("?", 1)[0]
        if pfad in ("/", "/index.html"):
            return self._datei(STATIC / "index.html", "text/html; charset=utf-8")
        if pfad == "/gesund":
            return self._json(HTTPStatus.OK, {"status": "ok"})
        if pfad == "/api/info":
            k = self.app.konfig
            return self._json(HTTPStatus.OK, {
                "name": k.name, "modell": k.modell, "backend": k.backend, "passwort_noetig": k.passwort_noetig,
                "wissen": self.app.wissen_dateien, **self.app.status(),
            })
        if pfad.startswith("/berichte/"):
            return self._bericht(pfad[len("/berichte/"):])
        self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")

    def _bericht(self, name):
        if not self._pruefe_anmeldung():
            return
        ordner = Path(self.app.konfig.berichte_ordner).resolve()
        ziel = (ordner / name).resolve()
        if ziel.parent != ordner or ziel.suffix not in (".html", ".pdf") or not ziel.is_file():
            return self._fehler(HTTPStatus.NOT_FOUND, "Bericht nicht gefunden")
        typ = "application/pdf" if ziel.suffix == ".pdf" else "text/html; charset=utf-8"
        self._datei(ziel, typ, download=True)

    def do_POST(self):
        # Rumpf immer zuerst lesen: Bei Keep-Alive würde ein ungelesener Rumpf sonst als nächste Anfrage gedeutet.
        try:
            laenge = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            laenge = 0
        if laenge <= 0 or laenge > self.app.konfig.max_anfrage_bytes:
            self.close_connection = True
            return self._fehler(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Anfrage leer oder zu groß")
        rumpf = self.rfile.read(laenge)

        if self.path.split("?", 1)[0] != "/api/chat":
            return self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        if not self._pruefe_anmeldung():
            return
        if not self.app.limit.erlaubt(self._client()):
            return self._fehler(HTTPStatus.TOO_MANY_REQUESTS, "Zu viele Anfragen. Bitte später erneut versuchen.")

        try:
            daten = json.loads(rumpf.decode("utf-8"))
            frage = daten.get("frage")
            if not isinstance(frage, str) or not frage.strip():
                raise ValueError("frage fehlt")
            verlauf = pruefe_verlauf(daten.get("verlauf"), self.app.konfig.max_verlauf_nachrichten, self.app.rollen)
        except (ValueError, UnicodeDecodeError, AttributeError) as e:
            return self._fehler(HTTPStatus.BAD_REQUEST, f"Ungültige Anfrage: {e}")

        self._sse_start()
        try:
            for ereignis in self.app.ki.antworten(verlauf, frage.strip()):
                self._sse(ereignis)
        except LokalesModellFehler as e:
            log.error("Lokales Modell: %s", e)
            self._sse({"typ": "fehler", "text": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            log.info("Client hat die Verbindung beendet")
            return
        except Exception as e:  # noqa: BLE001 – der Server soll weiterlaufen
            text = _api_fehlertext(e)
            if text is None:
                log.exception("Unerwarteter Fehler")
                text = "Unerwarteter Fehler im Server."
            self._sse({"typ": "fehler", "text": text})
        self._sse_ende()

    # --- Server-Sent Events -----------------------------------------------

    def _sse_start(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")  # nginx: nicht puffern
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _chunk(self, daten):
        self.wfile.write(f"{len(daten):X}\r\n".encode("ascii") + daten + b"\r\n")
        self.wfile.flush()

    def _sse(self, ereignis):
        self._chunk(f"data: {json.dumps(ereignis, ensure_ascii=False)}\n\n".encode("utf-8"))

    def _sse_ende(self):
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def _api_fehlertext(e):
    """Verständliche Meldung für Fehler des anthropic-SDK; None, wenn es kein solcher ist."""
    if "anthropic" not in type(e).__module__ and not isinstance(e, TypeError):
        return None
    import anthropic
    if isinstance(e, TypeError):
        if "authentication" not in str(e).lower():
            return None
        log.error("ANTHROPIC_API_KEY fehlt: %s", e)
        return "Der Server ist nicht korrekt eingerichtet (API-Schlüssel). Bitte den Betreiber informieren."
    if isinstance(e, anthropic.AuthenticationError):
        log.error("ANTHROPIC_API_KEY ungültig")
        return "Der Server ist nicht korrekt eingerichtet (API-Schlüssel). Bitte den Betreiber informieren."
    if isinstance(e, anthropic.RateLimitError):
        return "Das KI-Modell ist gerade ausgelastet. Bitte in einer Minute erneut versuchen."
    if isinstance(e, anthropic.BadRequestError):
        log.error("Ungültige Anfrage an die API: %s", e.message)
        return "Die Anfrage konnte nicht verarbeitet werden. Bitte ein neues Gespräch beginnen."
    if isinstance(e, anthropic.APIStatusError):
        log.error("API-Fehler %s: %s", e.status_code, e.message)
        return "Der KI-Dienst hat einen Fehler gemeldet. Bitte später erneut versuchen."
    if isinstance(e, anthropic.APIConnectionError):
        log.error("Keine Verbindung zur API")
        return "Keine Verbindung zum KI-Dienst."
    return None


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, adresse, app):
        super().__init__(adresse, Handler)
        self.app = app


def erzeuge_server(konfig, ki=None):
    return Server((konfig.host, konfig.port), Anwendung(konfig, ki))


def starte(konfig):
    import os
    if konfig.backend == "claude" and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.warning("ANTHROPIC_API_KEY ist nicht gesetzt – Anfragen schlagen fehl, sofern kein anderes "
                    "Anmeldeverfahren des SDK (z. B. `ant auth login`) eingerichtet ist")
    server = erzeuge_server(konfig)
    status = server.app.status()
    (log.info if status["bereit"] else log.warning)("Modell: %s", status["meldung"])
    log.info("%s läuft auf http://%s:%d (Backend %s, Modell %s, Passwort %s)", konfig.name, konfig.host, konfig.port,
             konfig.backend, konfig.modell, "aktiv" if konfig.passwort_noetig else "AUS – nur lokal")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
