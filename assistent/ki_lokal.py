"""Gespräch mit einem lokalen Modell über Ollama (http://127.0.0.1:11434) – ohne fremde API.

Benutzt nur die Standardbibliothek. Nachrichtenformat im Verlauf ist das von Ollama:
  {"role": "user"|"assistant"|"tool", "content": "...", "tool_calls": [...], "tool_name": "..."}
Der Verlauf liegt beim Browser; der Server bleibt zustandslos.
"""

import json
import logging
import urllib.error
import urllib.request

from . import werkzeuge
from .prompt import systemprompt

log = logging.getLogger("assistent.lokal")


class LokalesModellFehler(Exception):
    """Fehler, die dem Nutzer verständlich gemeldet werden."""


def werkzeuge_fuer_ollama(definitionen=werkzeuge.DEFINITIONEN):
    return [
        {
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": d["input_schema"],
            },
        }
        for d in definitionen
    ]


class LokalerAssistent:
    def __init__(self, konfig, wissen_text, oeffner=None):
        self.konfig = konfig
        self.system = systemprompt(wissen_text)
        self.werkzeuge = werkzeuge_fuer_ollama()
        self._oeffner = oeffner or urllib.request.urlopen  # austauschbar für Tests
        self._denken_moeglich = True

    # --- HTTP ---------------------------------------------------------------

    def _post(self, pfad, daten, timeout):
        anfrage = urllib.request.Request(
            self.konfig.ollama_url.rstrip("/") + pfad,
            data=json.dumps(daten).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return self._oeffner(anfrage, timeout=timeout)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                text = json.loads(text).get("error", text)
            except ValueError:
                pass
            if e.code == 404 and "not found" in text:
                raise LokalesModellFehler(
                    f"Modell {self.konfig.modell!r} ist nicht geladen. Auf dem Server ausführen: "
                    f"ollama pull {self.konfig.modell}") from e
            raise LokalesModellFehler(f"Ollama meldet: {text}") from e
        except urllib.error.URLError as e:
            raise LokalesModellFehler(
                f"Lokales Modell nicht erreichbar ({self.konfig.ollama_url}). Läuft `ollama serve`?") from e

    def _chat_stream(self, nachrichten):
        daten = {
            "model": self.konfig.modell,
            "messages": [{"role": "system", "content": self.system}] + nachrichten,
            "tools": self.werkzeuge,
            "stream": True,
            "keep_alive": self.konfig.ollama_keep_alive,
            "options": {"num_ctx": self.konfig.num_ctx, "num_predict": self.konfig.max_tokens},
        }
        if self.konfig.denken is not None and self._denken_moeglich:
            daten["think"] = self.konfig.denken
        try:
            antwort = self._post("/api/chat", daten, timeout=self.konfig.zeitlimit)
        except LokalesModellFehler as e:
            # Modelle ohne Denkmodus (z. B. llama3.1) lehnen den Parameter ab – dann ohne ihn weiter
            if "think" in str(e).lower() and "think" in daten:
                log.info("Modell %s kennt keinen Denkmodus, Parameter wird weggelassen", self.konfig.modell)
                self._denken_moeglich = False
                del daten["think"]
                antwort = self._post("/api/chat", daten, timeout=self.konfig.zeitlimit)
            else:
                raise
        for zeile in antwort:
            zeile = zeile.strip()
            if not zeile:
                continue
            stueck = json.loads(zeile)
            if stueck.get("error"):
                raise LokalesModellFehler(f"Ollama meldet: {stueck['error']}")
            yield stueck

    # --- Gespräch -------------------------------------------------------------

    def antworten(self, verlauf, frage):
        """Generator über Ereignisse: text, werkzeug, hinweis, fertig."""
        verlauf = list(verlauf) + [{"role": "user", "content": frage}]
        nutzung = {"eingabe": 0, "ausgabe": 0}
        runden = 0

        while True:
            text, aufrufe, fertig_grund = [], [], None
            for stueck in self._chat_stream(verlauf):
                nachricht = stueck.get("message") or {}
                if nachricht.get("content"):
                    text.append(nachricht["content"])
                    yield {"typ": "text", "text": nachricht["content"]}
                for aufruf in nachricht.get("tool_calls") or []:
                    aufrufe.append(aufruf)
                    yield {"typ": "werkzeug", "name": aufruf.get("function", {}).get("name", "?"), "status": "geplant"}
                if stueck.get("done"):
                    fertig_grund = stueck.get("done_reason")
                    nutzung["eingabe"] += stueck.get("prompt_eval_count", 0) or 0
                    nutzung["ausgabe"] += stueck.get("eval_count", 0) or 0

            assistent_nachricht = {"role": "assistant", "content": "".join(text)}
            if aufrufe:
                assistent_nachricht["tool_calls"] = aufrufe
            verlauf.append(assistent_nachricht)

            if not aufrufe:
                if fertig_grund == "length":
                    yield {"typ": "hinweis", "text": "Die Antwort wurde abgeschnitten (Längenlimit)."}
                break

            runden += 1
            for aufruf in aufrufe:
                fn = aufruf.get("function", {})
                name = fn.get("name", "?")
                eingabe = fn.get("arguments")
                if isinstance(eingabe, str):  # manche Modelle liefern die Argumente als JSON-Text
                    try:
                        eingabe = json.loads(eingabe)
                    except ValueError:
                        pass
                if runden > self.konfig.max_werkzeug_runden:
                    ergebnis = werkzeuge._fehler("", "Zu viele Werkzeugaufrufe – bitte mit den bisherigen Ergebnissen antworten.")
                else:
                    yield {"typ": "werkzeug", "name": name, "status": "laeuft"}
                    ergebnis = werkzeuge.ausfuehren(name, eingabe, "", self.konfig.berichte_ordner)
                yield {"typ": "werkzeug", "name": name, "status": "fehler" if ergebnis.get("is_error") else "fertig"}
                inhalt = ergebnis["content"]
                if ergebnis.get("is_error"):
                    inhalt = json.dumps({"fehler": inhalt}, ensure_ascii=False)
                verlauf.append({"role": "tool", "content": inhalt, "tool_name": name})

        log.info("Antwort (lokal, %s): %s Eingabe-, %s Ausgabe-Token, %d Werkzeugrunden",
                 self.konfig.modell, nutzung["eingabe"], nutzung["ausgabe"], runden)
        yield {"typ": "fertig", "verlauf": verlauf, "nutzung": nutzung, "modell": self.konfig.modell}

    # --- Diagnose ---------------------------------------------------------------

    def pruefe_verbindung(self):
        """Liefert (ok, meldung) – für den Start und /api/info."""
        try:
            anfrage = urllib.request.Request(self.konfig.ollama_url.rstrip("/") + "/api/tags")
            with self._oeffner(anfrage, timeout=5) as a:
                modelle = [m.get("name", "") for m in json.loads(a.read()).get("models", [])]
        except (urllib.error.URLError, OSError, ValueError) as e:
            return False, f"Ollama unter {self.konfig.ollama_url} nicht erreichbar: {e}"
        gesucht = self.konfig.modell
        if gesucht in modelle or (":" not in gesucht and f"{gesucht}:latest" in modelle):
            return True, f"Modell {gesucht} bereit"
        return False, f"Modell {gesucht!r} fehlt. Vorhanden: {', '.join(modelle) or 'keins'}. Bitte: ollama pull {gesucht}"
