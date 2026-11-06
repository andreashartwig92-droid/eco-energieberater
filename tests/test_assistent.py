import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from assistent import werkzeuge
from assistent.ki import pruefe_verlauf
from assistent.konfig import Konfig
from assistent.server import RateLimit, erzeuge_server
from assistent.wissen import lade_wissen

WURZEL = Path(__file__).resolve().parent.parent
MUSTERHAUS = json.loads((WURZEL / "beispiele" / "musterhaus.json").read_text(encoding="utf-8"))


class Werkzeuge(unittest.TestCase):
    def test_heizlast_musterhaus(self):
        r = werkzeuge.ausfuehren("heizlast_berechnen", {"projekt": MUSTERHAUS}, "t1")
        self.assertNotIn("is_error", r)
        daten = json.loads(r["content"])
        self.assertGreater(daten["gebaeude"]["heizlast_W"], 5000)
        self.assertEqual(len(daten["raeume"]), len(MUSTERHAUS["raeume"]))
        self.assertEqual(len(daten["abgleich"]["heizkoerper"]), len(MUSTERHAUS["heizkoerper"]))
        self.assertNotIn("bericht", daten)

    def test_heizlast_mit_bericht(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = werkzeuge.ausfuehren("heizlast_berechnen", {"projekt": MUSTERHAUS, "bericht_erzeugen": True}, "t2", tmp)
            daten = json.loads(r["content"])
            self.assertTrue(daten["bericht"]["html"].startswith("/berichte/"))
            self.assertTrue((Path(tmp) / Path(daten["bericht"]["html"]).name).is_file())

    def test_heizlast_fehlende_abschnitte(self):
        r = werkzeuge.ausfuehren("heizlast_berechnen", {"projekt": {"klima": {}}}, "t3")
        self.assertTrue(r["is_error"])
        self.assertIn("bauteile", r["content"])

    def test_ungueltige_eingabe(self):
        r = werkzeuge.ausfuehren("heizlast_berechnen", "abgeschnitten", "t4")
        self.assertTrue(r["is_error"])
        self.assertIn("INVALID_JSON", r["content"])

    def test_heizkoerper_leistung(self):
        r = werkzeuge.ausfuehren("heizkoerper_leistung", {"phi_N": 1000, "theta_V": 75, "theta_R": 65, "theta_i": 20}, "t5")
        self.assertAlmostEqual(json.loads(r["content"])["leistung_W"], 1000)
        r = werkzeuge.ausfuehren("heizkoerper_leistung", {"phi_N": 1000, "theta_V": 40, "theta_R": 45}, "t6")
        self.assertTrue(r["is_error"])
        r = werkzeuge.ausfuehren("heizkoerper_leistung", {"phi_N": "viel", "theta_V": 55, "theta_R": 45}, "t7")
        self.assertTrue(r["is_error"])

    def test_unbekanntes_werkzeug(self):
        self.assertTrue(werkzeuge.ausfuehren("kaffee_kochen", {}, "t8")["is_error"])

    def test_musterprojekt(self):
        r = werkzeuge.ausfuehren("musterprojekt_abrufen", {}, "t9")
        self.assertEqual(json.loads(r["content"])["projekt"]["titel"], MUSTERHAUS["projekt"]["titel"])

    def test_definitionen_passen_zu_funktionen(self):
        self.assertEqual({d["name"] for d in werkzeuge.DEFINITIONEN}, set(werkzeuge.FUNKTIONEN))


class Wissen(unittest.TestCase):
    def test_laden_sortiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "20_b.md").write_text("Zwei", encoding="utf-8")
            Path(tmp, "10_a.txt").write_text("Eins", encoding="utf-8")
            Path(tmp, "bild.png").write_bytes(b"\x89PNG")
            Path(tmp, "leer.md").write_text("  ", encoding="utf-8")
            text, namen = lade_wissen(tmp)
            self.assertEqual(namen, ["10_a.txt", "20_b.md"])
            self.assertLess(text.index("Eins"), text.index("Zwei"))
            self.assertIn('<dokument name="10_a.txt">', text)

    def test_fehlender_ordner(self):
        self.assertEqual(lade_wissen("/gibt/es/nicht"), ("", []))

    def test_mitgelieferte_wissensbasis(self):
        text, namen = lade_wissen(WURZEL / "wissen")
        self.assertGreaterEqual(len(namen), 3)
        self.assertIn("Heizlast", text)


class Konfiguration(unittest.TestCase):
    def test_passwort_pflicht_bei_oeffentlicher_adresse(self):
        with self.assertRaises(ValueError):
            Konfig(host="0.0.0.0", passwort="").pruefen()
        Konfig(host="0.0.0.0", passwort="geheim").pruefen()
        Konfig(host="127.0.0.1", passwort="").pruefen()

    def test_effort_pruefung(self):
        with self.assertRaises(ValueError):
            Konfig(effort="turbo").pruefen()

    def test_aus_umgebung(self):
        alt = dict(os.environ)
        try:
            os.environ.update({"KI_HOST": "0.0.0.0", "KI_PORT": "9000", "KI_PASSWORT": "x", "KI_FALLBACK": "nein", "KI_EFFORT": "high"})
            k = Konfig.aus_umgebung()
            self.assertEqual((k.host, k.port, k.fallback, k.effort), ("0.0.0.0", 9000, False, "high"))
        finally:
            os.environ.clear()
            os.environ.update(alt)


class Verlauf(unittest.TestCase):
    def test_ok(self):
        v = [{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]}]
        self.assertEqual(pruefe_verlauf(v, 10), v)
        self.assertEqual(pruefe_verlauf(None, 10), [])

    def test_fehler(self):
        for kaputt in ("nein", [{"role": "system", "content": "x"}], [{"role": "assistant", "content": "x"}],
                       [{"role": "user"}], [{"role": "user", "content": "a"}] * 3):
            with self.assertRaises(ValueError):
                pruefe_verlauf(kaputt, 2)


class Limit(unittest.TestCase):
    def test_zeitfenster(self):
        lim = RateLimit(2)
        self.assertTrue(lim.erlaubt("a", 0))
        self.assertTrue(lim.erlaubt("a", 1))
        self.assertFalse(lim.erlaubt("a", 2))
        self.assertTrue(lim.erlaubt("b", 2))
        self.assertTrue(lim.erlaubt("a", 3601.5))

    def test_aus(self):
        self.assertTrue(all(RateLimit(0).erlaubt("a") for _ in range(50)))


class FakeKI:
    """Ersetzt den Assistenten: liefert feste Ereignisse, merkt sich die Eingabe."""

    def __init__(self):
        self.aufrufe = []

    def antworten(self, verlauf, frage):
        self.aufrufe.append((list(verlauf), frage))
        yield {"typ": "text", "text": "Hallo "}
        yield {"typ": "werkzeug", "name": "heizkoerper_leistung", "status": "laeuft"}
        yield {"typ": "text", "text": "Welt"}
        neu = list(verlauf) + [{"role": "user", "content": frage}, {"role": "assistant", "content": [{"type": "text", "text": "Hallo Welt"}]}]
        yield {"typ": "fertig", "verlauf": neu, "nutzung": {}, "modell": "fake"}


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ki = FakeKI()
        konfig = Konfig(host="127.0.0.1", port=0, passwort="geheim", limit_pro_stunde=3, berichte_ordner=Path(cls.tmp.name))
        cls.server = erzeuge_server(konfig, cls.ki)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def _anfrage(self, methode, pfad, body=None, passwort="geheim"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        kopf = {"Content-Type": "application/json"}
        if passwort:
            kopf["Authorization"] = f"Bearer {passwort}"
        c.request(methode, pfad, body=json.dumps(body) if body is not None else None, headers=kopf)
        antwort = c.getresponse()
        daten = antwort.read()
        c.close()
        return antwort, daten

    def _ereignisse(self, daten):
        return [json.loads(z[6:]) for z in daten.decode("utf-8").split("\n\n") if z.startswith("data: ")]

    def test_startseite_und_info(self):
        a, d = self._anfrage("GET", "/", passwort=None)
        self.assertEqual(a.status, 200)
        self.assertIn(b"<title>Energieberater-KI</title>", d)
        a, d = self._anfrage("GET", "/api/info", passwort=None)
        self.assertEqual(json.loads(d)["passwort_noetig"], True)
        a, _ = self._anfrage("GET", "/gesund", passwort=None)
        self.assertEqual(a.status, 200)

    def test_chat_braucht_passwort(self):
        a, _ = self._anfrage("POST", "/api/chat", {"frage": "Hi"}, passwort=None)
        self.assertEqual(a.status, 401)
        a, _ = self._anfrage("POST", "/api/chat", {"frage": "Hi"}, passwort="falsch")
        self.assertEqual(a.status, 401)

    def test_chat_stream(self):
        a, d = self._anfrage("POST", "/api/chat", {"verlauf": [], "frage": "Hi"})
        self.assertEqual(a.status, 200)
        self.assertTrue(a.getheader("Content-Type").startswith("text/event-stream"))
        ev = self._ereignisse(d)
        self.assertEqual("".join(e["text"] for e in ev if e["typ"] == "text"), "Hallo Welt")
        self.assertEqual(ev[-1]["typ"], "fertig")
        self.assertEqual(ev[-1]["verlauf"][-1]["role"], "assistant")
        self.assertEqual(self.ki.aufrufe[-1], ([], "Hi"))

    def test_ungueltige_anfragen(self):
        a, d = self._anfrage("POST", "/api/chat", {"frage": ""})
        self.assertEqual(a.status, 400)
        a, d = self._anfrage("POST", "/api/chat", {"frage": "x", "verlauf": [{"role": "assistant", "content": "x"}]})
        self.assertEqual(a.status, 400)
        self.assertIn("Nutzernachricht", json.loads(d)["fehler"])

    def test_berichte_geschuetzt_und_ohne_pfadausbruch(self):
        Path(self.tmp.name, "abc.html").write_text("<p>ok</p>", encoding="utf-8")
        a, d = self._anfrage("GET", "/berichte/abc.html")
        self.assertEqual((a.status, d), (200, b"<p>ok</p>"))
        a, _ = self._anfrage("GET", "/berichte/abc.html", passwort=None)
        self.assertEqual(a.status, 401)
        a, _ = self._anfrage("GET", "/berichte/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(a.status, 404)
        a, _ = self._anfrage("GET", "/berichte/../README.md")
        self.assertEqual(a.status, 404)

    def test_rate_limit(self):
        self.server.app.limit = RateLimit(1)
        try:
            a, _ = self._anfrage("POST", "/api/chat", {"frage": "1"})
            self.assertEqual(a.status, 200)
            a, _ = self._anfrage("POST", "/api/chat", {"frage": "2"})
            self.assertEqual(a.status, 429)
        finally:
            self.server.app.limit = RateLimit(0)


if __name__ == "__main__":
    unittest.main()


# --- Gesprächsschleife mit nachgebauter API -------------------------------------

class _Block:
    def __init__(self, **felder):
        self.__dict__.update(felder)

    def model_dump(self, **kw):
        return dict(self.__dict__)


class _Ereignis:
    def __init__(self, typ, **felder):
        self.type = typ
        self.__dict__.update(felder)


class _Usage:
    input_tokens = 10
    output_tokens = 5
    cache_read_input_tokens = 7
    cache_creation_input_tokens = 0


class _Antwort:
    def __init__(self, content, stop_reason):
        self.content, self.stop_reason, self.usage, self.model = content, stop_reason, _Usage(), "fake-modell"


class _Stream:
    def __init__(self, ereignisse, antwort):
        self._ereignisse, self._antwort = ereignisse, antwort

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._ereignisse)

    def get_final_message(self):
        return self._antwort


class FakeClient:
    """Erste Runde: Werkzeugaufruf. Zweite Runde: Textantwort."""

    def __init__(self):
        self.anfragen = []
        self.beta = self
        self.messages = self

    def stream(self, **params):
        params["anzahl_nachrichten"] = len(params["messages"])  # die Liste wird später weiter befüllt
        self.anfragen.append(params)
        if len(self.anfragen) == 1:
            aufruf = _Block(type="tool_use", id="tu_1", name="heizkoerper_leistung",
                            input={"phi_N": 1000, "theta_V": 75, "theta_R": 65, "theta_i": 20})
            return _Stream([_Ereignis("content_block_start", content_block=aufruf)],
                           _Antwort([_Block(type="thinking", thinking="", signature="sig"), aufruf], "tool_use"))
        return _Stream([_Ereignis("text", text="1.000 W")],
                       _Antwort([_Block(type="text", text="1.000 W")], "end_turn"))


class Gespraech(unittest.TestCase):
    def test_werkzeugschleife(self):
        from assistent.ki import Assistent
        konfig = Konfig(host="127.0.0.1", effort="low", fallback=True)
        client = FakeClient()
        ki = Assistent(konfig, "Wissen", client=client)
        ereignisse = list(ki.antworten([], "Was leistet ein Heizkörper mit 1000 W bei 75/65?"))

        typen = [e["typ"] for e in ereignisse]
        self.assertEqual(typen, ["werkzeug", "werkzeug", "werkzeug", "text", "fertig"])
        self.assertEqual([e["status"] for e in ereignisse[:3]], ["geplant", "laeuft", "fertig"])

        fertig = ereignisse[-1]
        verlauf = fertig["verlauf"]
        self.assertEqual([n["role"] for n in verlauf], ["user", "assistant", "user", "assistant"])
        # Werkzeugergebnis wurde als tool_result mit passender ID zurückgegeben
        ergebnis = verlauf[2]["content"][0]
        self.assertEqual((ergebnis["type"], ergebnis["tool_use_id"]), ("tool_result", "tu_1"))
        self.assertAlmostEqual(json.loads(ergebnis["content"])["leistung_W"], 1000)
        # thinking-Block unverändert im Verlauf
        self.assertEqual(verlauf[1]["content"][0]["signature"], "sig")
        self.assertEqual(fertig["nutzung"]["cache_gelesen"], 14)

        # Anfrageparameter
        p = client.anfragen[0]
        self.assertEqual(p["model"], "claude-opus-5-5")
        self.assertEqual(p["output_config"], {"effort": "low"})
        self.assertEqual(p["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", p["betas"])
        self.assertEqual(p["system"][1]["cache_control"], {"type": "ephemeral"})
        self.assertIn("Wissen", p["system"][1]["text"])
        self.assertTrue(any(t.get("eager_input_streaming") for t in p["tools"]))
        self.assertNotIn("thinking", p)
        # zweite Runde enthält den vollen Verlauf inkl. tool_result
        self.assertEqual(client.anfragen[1]["anzahl_nachrichten"], 3)

    def test_ohne_fallback(self):
        from assistent.ki import Assistent
        client = FakeClient()
        ki = Assistent(Konfig(fallback=False), "", client=client)
        list(ki.antworten([], "Hallo"))
        self.assertNotIn("fallbacks", client.anfragen[0])
        self.assertNotIn("betas", client.anfragen[0])
