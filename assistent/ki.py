"""Gespräch mit Claude: Streaming, Werkzeugschleife, Verlaufspflege.

Der Verlauf (Liste von Nachrichten im API-Format) liegt beim Browser und wird mit jeder
Anfrage mitgeschickt – der Server ist zustandslos. Die Antwortblöcke des Modells werden
unverändert (inkl. thinking-Blöcken mit Signatur) in den Verlauf übernommen.
"""

import logging

import anthropic

from . import werkzeuge
from .prompt import RAHMEN
from .verlauf import pruefe_verlauf  # noqa: F401 – Rückwärtskompatibilität

log = logging.getLogger("assistent.ki")

BETA_FALLBACK = "server-side-fallback-2026-07-01"

class Assistent:
    def __init__(self, konfig, wissen_text, client=None):
        self.konfig = konfig
        self.client = client or anthropic.Anthropic(max_retries=2)
        self.system = [
            {"type": "text", "text": RAHMEN},
            {
                "type": "text",
                "text": wissen_text or "(Noch keine Wissensbasis hinterlegt.)",
                "cache_control": {"type": "ephemeral"},
            },
        ]
        self.werkzeuge = werkzeuge.DEFINITIONEN

    def _anfrage(self, verlauf):
        params = dict(
            model=self.konfig.modell,
            max_tokens=self.konfig.max_tokens,
            system=self.system,
            tools=self.werkzeuge,
            messages=verlauf,
            output_config={"effort": self.konfig.effort},
        )
        if self.konfig.fallback:
            params["betas"] = [BETA_FALLBACK]
            params["fallbacks"] = "default"
        return self.client.beta.messages.stream(**params)

    def antworten(self, verlauf, frage):
        """Generator über Ereignisse: text, werkzeug, hinweis, fertig."""
        verlauf = list(verlauf) + [{"role": "user", "content": frage}]
        nutzung = {"eingabe": 0, "ausgabe": 0, "cache_gelesen": 0, "cache_geschrieben": 0}
        runden = 0
        json_fehler = 0

        while True:
            try:
                with self._anfrage(verlauf) as stream:
                    for ereignis in stream:
                        if ereignis.type == "text":
                            yield {"typ": "text", "text": ereignis.text}
                        elif ereignis.type == "content_block_start" and ereignis.content_block.type == "tool_use":
                            yield {"typ": "werkzeug", "name": ereignis.content_block.name, "status": "geplant"}
                    antwort = stream.get_final_message()
                json_fehler = 0
            except ValueError:
                # Werkzeug-Eingabe war kein gültiges JSON (eager_input_streaming) – Runde wiederholen
                json_fehler += 1
                if json_fehler > 2:
                    raise
                log.warning("Ungültiges Werkzeug-JSON, Runde wird wiederholt")
                continue

            self._zaehlen(nutzung, antwort.usage)
            verlauf.append({"role": "assistant", "content": _als_dicts(antwort.content)})

            if antwort.stop_reason == "pause_turn":
                continue
            if antwort.stop_reason == "refusal":
                yield {"typ": "hinweis", "text": "Dazu kann ich leider keine Auskunft geben."}
                break

            aufrufe = [b for b in antwort.content if b.type == "tool_use"]
            if not aufrufe:
                break
            if antwort.stop_reason == "max_tokens":
                yield {"typ": "hinweis", "text": "Die Antwort wurde abgeschnitten (Längenlimit). Bitte Frage kleiner fassen."}
                break

            runden += 1
            ergebnisse = []
            for aufruf in aufrufe:
                if runden > self.konfig.max_werkzeug_runden:
                    ergebnisse.append(werkzeuge._fehler(aufruf.id, "Zu viele Werkzeugaufrufe in einer Antwort – bitte mit den bisherigen Ergebnissen antworten."))
                    continue
                yield {"typ": "werkzeug", "name": aufruf.name, "status": "laeuft"}
                ergebnis = werkzeuge.ausfuehren(aufruf.name, aufruf.input, aufruf.id, self.konfig.berichte_ordner)
                ergebnisse.append(ergebnis)
                yield {"typ": "werkzeug", "name": aufruf.name, "status": "fehler" if ergebnis.get("is_error") else "fertig"}
            verlauf.append({"role": "user", "content": ergebnisse})

        log.info("Antwort: %s Eingabe, %s Ausgabe, %s aus Cache, %d Werkzeugrunden",
                 nutzung["eingabe"], nutzung["ausgabe"], nutzung["cache_gelesen"], runden)
        yield {"typ": "fertig", "verlauf": verlauf, "nutzung": nutzung, "modell": antwort.model}

    @staticmethod
    def _zaehlen(nutzung, usage):
        if usage is None:
            return
        nutzung["eingabe"] += usage.input_tokens or 0
        nutzung["ausgabe"] += usage.output_tokens or 0
        nutzung["cache_gelesen"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        nutzung["cache_geschrieben"] += getattr(usage, "cache_creation_input_tokens", 0) or 0


def _als_dicts(bloecke):
    return [b.model_dump(mode="json", exclude_none=True) for b in bloecke]
