import http.client
import json
import os
import unittest.mock
import tempfile
import threading
import time
import unittest
from pathlib import Path

from bilanzen import bewertung, kennzahlen
from bilanzen.auftraege import Verwalter
from bilanzen.modelle import CaptchaNoetig, Dokument, Seite, Treffer, geschaeftsjahr_aus_titel
from bilanzen.htmlbaum import parse
from bilanzen.konfig import Konfig
from bilanzen.parser import normalisiere, ordne_posten, parse_jahresabschluss, zahl, zerlege_zeile
from bilanzen.server import erzeuge_server
from bilanzen.speicher import Speicher

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "bilanzen"


def lies(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class HtmlBaum(unittest.TestCase):
    def test_suche_und_text(self):
        b = parse('<div class="a b"><p>Hallo <b>Welt</b></p><table><tr><td>1</td><td>2</td></tr></table></div>')
        self.assertEqual(b.erster("div", klasse="b").text(), "Hallo Welt 1 2")
        self.assertEqual([k.text() for k in b.suche("td")], ["1", "2"])
        self.assertEqual(b.erster("p").zeilen(), ["Hallo Welt"])

    def test_unvollstaendiges_html(self):
        b = parse("<div><p>eins<p>zwei<br>drei</div><span>vier")
        self.assertIn("zwei", b.text())
        self.assertIn("vier", b.text())


class Modelle(unittest.TestCase):
    def test_geschaeftsjahr(self):
        self.assertEqual(geschaeftsjahr_aus_titel("Jahresabschluss zum Geschäftsjahr vom 01.06.2020 bis zum 31.05.2021"), ("2020-06-01", "2021-05-31"))
        self.assertEqual(geschaeftsjahr_aus_titel("Jahresabschluss zum 31.12.2019"), ("", "2019-12-31"))
        self.assertEqual(geschaeftsjahr_aus_titel("Konzernabschluss 2018"), ("", "2018-12-31"))

    def test_hinterlegung_ohne_link(self):
        t = Treffer(name="X GmbH", ort="Y", titel="Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021", link="", datum="")
        self.assertFalse(t.ist_jahresabschluss)
        self.assertEqual(t.quelle, "unternehmensregister")


class Parser(unittest.TestCase):
    def test_hilfsfunktionen(self):
        self.assertEqual(normalisiere("A. Anlagevermögen"), "anlagevermoegen")
        self.assertEqual(normalisiere("III. Kassenbestand, Guthaben"), "kassenbestand, guthaben")
        self.assertEqual(normalisiere("Summe Aktiva"), "summe aktiva")
        self.assertEqual(normalisiere("1. Umsatzerlöse"), "umsatzerloese")
        self.assertEqual(zahl("1.234.567,89"), 1234567.89)
        self.assertEqual(zahl("(1.234)"), -1234.0)
        self.assertEqual(zahl("-12,50"), -12.5)
        self.assertIsNone(zahl("abc"))
        self.assertEqual(zerlege_zeile("Umsatzerlöse 1.284.500,00 1.102.300,00"), ("Umsatzerlöse", [1284500.0, 1102300.0]))
        self.assertEqual(zerlege_zeile("Eigenkapital 25.000,00 EUR 25.000,00 EUR"), ("Eigenkapital", [25000.0, 25000.0]))
        self.assertEqual(zerlege_zeile("Gewinn- und Verlustrechnung 2021"), ("Gewinn- und Verlustrechnung 2021", []))
        self.assertEqual(ordne_posten("B. Verbindlichkeiten"), "verbindlichkeiten")
        self.assertEqual(ordne_posten("davon gegenüber Kreditinstituten"), None)
        self.assertEqual(ordne_posten("Verbindlichkeiten gegenüber Kreditinstituten"), "verbindlichkeiten_kreditinstitute")

    def test_gmbh_mit_guv(self):
        a = parse_jahresabschluss(lies("jahresabschluss_gmbh.html"))
        self.assertEqual(a.firma, "Muster Energieberatung GmbH")
        self.assertEqual((a.gj_von, a.gj_bis), ("2021-01-01", "2021-12-31"))
        self.assertEqual(a.posten["bilanzsumme"], [667260.45, 523915.3])
        self.assertEqual(a.posten["eigenkapital"], [312480.12, 241230.0])
        self.assertEqual(a.posten["umsatz"], [1284500.0, 1102300.0])
        self.assertEqual(a.posten["jahresueberschuss"], [71250.12, 56130.0])
        self.assertEqual(a.posten["verbindlichkeiten"], [256380.33, 211485.3])
        self.assertEqual(a.posten["liquide_mittel"], [321000.0, 221000.0])
        self.assertEqual(a.posten["personalaufwand"], [-748900.0, -652300.0])
        self.assertTrue(a.guv_vorhanden)
        self.assertEqual(a.groessenklasse, "klein")
        self.assertEqual(a.mitarbeiter, 11)
        self.assertEqual(a.rechtsform, "GmbH")
        self.assertEqual(a.warnungen, [])

    def test_kleinst_ohne_guv(self):
        a = parse_jahresabschluss(lies("jahresabschluss_kleinst.html"))
        self.assertEqual(a.posten["bilanzsumme"], [50325.18, 40510.02])
        self.assertEqual(a.posten["eigenkapital"], [21880.4, 12410.3])
        self.assertFalse(a.guv_vorhanden)
        self.assertEqual(a.groessenklasse, "kleinst")
        self.assertEqual(a.rechtsform, "UG (haftungsbeschränkt)")
        self.assertIsNone(a.mitarbeiter)

    def test_teur_und_fehlbetrag_fliesstext(self):
        html = """<div class="publication_container"><h1>Verlust Energie GmbH</h1>
        <p>Bilanz zum 31.12.2020 (Angaben in TEUR)</p>
        <p>A. Anlagevermögen 120 150</p><p>B. Umlaufvermögen 80 90</p>
        <p>C. Nicht durch Eigenkapital gedeckter Fehlbetrag 40 10</p>
        <p>Bilanzsumme 240 250</p>
        <p>A. Eigenkapital 0 0</p><p>I. Gezeichnetes Kapital 25 25</p><p>II. Verlustvortrag -35 -20</p><p>III. Jahresfehlbetrag -30 -15</p>
        <p>B. Verbindlichkeiten 240 250</p>
        <p>Die Gesellschaft beschäftigte im Jahresdurchschnitt 3 Mitarbeiter.</p></div>"""
        a = parse_jahresabschluss(html)
        self.assertEqual(a.einheit, "TEUR")
        self.assertEqual(a.gj_bis, "2020-12-31")
        self.assertEqual(a.posten["bilanzsumme"], [240000.0, 250000.0])
        self.assertEqual(a.posten["jahresueberschuss"], [-30000.0, -15000.0])
        self.assertEqual(a.posten["eigenkapital"][0], -40000.0)
        self.assertEqual(a.mitarbeiter, 3)
        k = kennzahlen.berechne(a)
        self.assertTrue(k["negatives_eigenkapital"])
        self.assertLessEqual(k["score"], 25)
        self.assertEqual(k["ampel"], "rot")


class Kennzahlen(unittest.TestCase):
    def test_gmbh(self):
        a = parse_jahresabschluss(lies("jahresabschluss_gmbh.html"))
        k = kennzahlen.berechne(a)
        self.assertAlmostEqual(k["eigenkapitalquote"], 312480.12 / 667260.45)
        self.assertAlmostEqual(k["umsatzrendite"], 71250.12 / 1284500.0)
        self.assertAlmostEqual(k["wachstum_umsatz"], (1284500.0 - 1102300.0) / 1102300.0)
        self.assertAlmostEqual(k["personalaufwandsquote"], 748900.0 / 1284500.0)
        self.assertEqual(k["umsatz_je_mitarbeiter"], 1284500.0 / 11)
        self.assertFalse(k["ergebnis_geschaetzt"])
        self.assertEqual(k["datenlage"], "vollstaendig")
        self.assertEqual(k["ampel"], "gruen")
        self.assertTrue(any("Eigenkapitalquote" in g for g in k["begruendung"]))

    def test_kleinst_schaetzung(self):
        a = parse_jahresabschluss(lies("jahresabschluss_kleinst.html"))
        k = kennzahlen.berechne(a)
        self.assertTrue(k["ergebnis_geschaetzt"])
        self.assertAlmostEqual(k["jahresueberschuss"], 21880.4 - 12410.3)
        self.assertIsNone(k["umsatzrendite"])
        self.assertEqual(k["datenlage"], "eingeschraenkt")
        self.assertTrue(any("Keine GuV" in g for g in k["begruendung"]))

    def test_formatierung(self):
        self.assertEqual(kennzahlen.geld(1234567.8), "1.234.568 €")
        self.assertEqual(kennzahlen.prozent(0.0556), "5,6 %")
        self.assertEqual(kennzahlen.prozent(None), "–")


class Branchenbild(unittest.TestCase):
    def _firmen(self):
        firmen = []
        for name in ("jahresabschluss_gmbh.html", "jahresabschluss_kleinst.html"):
            a = parse_jahresabschluss(lies(name))
            firmen.append({"name": a.firma, "gj_bis": a.gj_bis, "rechtsform": a.rechtsform, "kennzahlen": kennzahlen.berechne(a)})
        return firmen

    def test_urteil(self):
        b = bewertung.branchenbild(self._firmen(), "Energieberatung")
        self.assertEqual(b["anzahl"], 2)
        self.assertEqual(b["kennzahlen"]["anzahl_mit_guv"], 1)
        self.assertEqual(b["kennzahlen"]["anteil_gewinn"], 1.0)
        self.assertIn(b["urteil"], ("attraktiv", "bedingt attraktiv", "wenig attraktiv"))
        self.assertTrue(any("Stichprobe" in h for h in b["hinweise"]))
        self.assertEqual(b["verteilungen"]["rechtsformen"], {"GmbH": 1, "UG (haftungsbeschränkt)": 1})

    def test_leer(self):
        b = bewertung.branchenbild([], "x")
        self.assertEqual(b["anzahl"], 0)
        self.assertIsNone(b["score"])


class SpeicherTest(unittest.TestCase):
    def test_roundtrip(self):
        s = Speicher(":memory:")
        fid, aid, a = s.dokument_speichern("Muster Energieberatung GmbH", "Musterstadt", lies("jahresabschluss_gmbh.html"),
                                           titel="Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021", veroeffentlicht="01.02.2023",
                                           suchbegriff="Energieberatung")
        self.assertTrue(s.hat_abschluss("Muster Energieberatung GmbH", "Musterstadt", "2021-12-31"))
        self.assertFalse(s.hat_abschluss("Muster Energieberatung GmbH", "Musterstadt", "2020-12-31"))
        # gleiche Firma, gleiches Jahr → ersetzt, nicht doppelt
        s.dokument_speichern("Muster Energieberatung GmbH", "Musterstadt", lies("jahresabschluss_gmbh.html"), titel="x", suchbegriff="Energieberater")
        firmen = s.firmen()
        self.assertEqual(len(firmen), 1)
        self.assertEqual(firmen[0]["anzahl_abschluesse"], 1)
        self.assertEqual(sorted(firmen[0]["suchbegriffe"]), ["Energieberater", "Energieberatung"])
        self.assertEqual(firmen[0]["kennzahlen"]["ampel"], "gruen")
        self.assertEqual(s.firmen("Energieberatung")[0]["id"], fid)
        self.assertEqual(s.firmen("Gibtsnicht"), [])
        detail = s.firma(fid)
        self.assertEqual(detail["abschluesse"][0]["abschluss"]["posten"]["umsatz"], [1284500.0, 1102300.0])
        self.assertIn("publication_container", s.roh_html(aid))
        self.assertEqual(s.statistik()["suchbegriffe"], {"Energieberater": 1, "Energieberatung": 1})
        self.assertEqual(s.neu_berechnen(), 1)
        s.firma_loeschen(fid)
        self.assertEqual(s.firmen(), [])


class FakeClient:
    """Spielt das Unternehmensregister: drei Treffer, der erste verlangt einmal die Bestätigung „Ich bin ein Mensch“."""

    def __init__(self, loesung="bestaetigt"):
        self.loesung = loesung
        self.anfragen = 0
        self.captcha_gesendet = 0
        self.pause = 0

    def suche(self, begriff, bereich="22"):
        self.anfragen += 1
        treffer = [
            Treffer("Muster Energieberatung GmbH", "Musterstadt", "Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021", "https://x/1", "01.02.2023"),
            Treffer("Klein Energieberatung UG (haftungsbeschränkt)", "Kleinstadt", "Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021", "https://x/2", "01.03.2023"),
            Treffer("Hinterlegt GmbH", "Irgendwo", "Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021", "", "01.03.2023"),
        ]
        return Seite(treffer=treffer, nummer=1, anzahl_treffer=3, naechste_url="", url="https://x/suche")

    def naechste_seite(self, seite):
        return None

    def dokument(self, treffer):
        self.anfragen += 1
        if treffer.link.endswith("/1") and self.captcha_gesendet == 0:
            raise CaptchaNoetig(bild=b"\x89PNG...", bild_typ="image/png", formular_url="https://x/captcha", seite_url=treffer.link, art="bestaetigen")
        return Dokument(html=lies("jahresabschluss_gmbh.html" if treffer.link.endswith("/1") else "jahresabschluss_kleinst.html"), url=treffer.link)

    def captcha_loesen(self, captcha, loesung):
        self.anfragen += 1
        self.captcha_gesendet += 1
        if loesung != self.loesung:
            raise CaptchaNoetig(bild=b"\x89PNG...", bild_typ="image/png", formular_url="https://x/captcha", seite_url=captcha.seite_url,
                                versuch=captcha.versuch + 1, art="bestaetigen")
        return Dokument(html=lies("jahresabschluss_gmbh.html"), url=captcha.seite_url)


def warte_bis(bedingung, sekunden=5):
    ende = time.time() + sekunden
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.02)
    return False


class Auftraege(unittest.TestCase):
    def test_ablauf_mit_captcha(self):
        s = Speicher(":memory:")
        fake = FakeClient()
        v = Verwalter(s, client_fabrik=lambda: fake)
        try:
            a = v.anlegen(["Energieberatung"], max_seiten=1)
            self.assertTrue(warte_bis(lambda: a.zustand == "captcha"))
            d = a.als_dict()
            self.assertTrue(d["captcha_bild"].startswith("data:image/png;base64,"))
            self.assertEqual(d["captcha_art"], "bestaetigen")
            self.assertIn("Muster Energieberatung GmbH", d["captcha_treffer"])
            v.captcha_beantworten(a.id, "nein")
            self.assertTrue(warte_bis(lambda: a.captcha_versuche == 1 and a.zustand == "captcha"))
            v.captcha_beantworten(a.id, "bestaetigt")
            self.assertTrue(warte_bis(lambda: a.zustand == "fertig"))
            self.assertEqual(a.geladen, 2)
            self.assertEqual(a.uebersprungen, 1)  # nur hinterlegt
            self.assertEqual(a.fehler, 0)
            self.assertEqual(len(s.firmen("Energieberatung")), 2)
            self.assertEqual(s.statistik()["uebersprungen"], 1)
            # zweiter Lauf: alles schon vorhanden
            b = v.anlegen(["Energieberatung"], max_seiten=1)
            self.assertTrue(warte_bis(lambda: b.zustand == "fertig"))
            self.assertEqual((b.geladen, b.uebersprungen), (0, 3))
            # nur Liste
            c = v.anlegen(["Energieberatung"], nur_liste=True)
            self.assertTrue(warte_bis(lambda: c.zustand == "fertig"))
            self.assertEqual(len(c.treffer_liste), 3)
            self.assertTrue(c.treffer_liste[0]["vorhanden"])
        finally:
            v.stoppen()

    def test_ab_jahr_ueberspringt_alte_abschluesse(self):
        s = Speicher(":memory:")
        v = Verwalter(s, client_fabrik=lambda: FakeClient())
        try:
            a = v.anlegen(["Energieberatung"], ab_jahr=2022)  # alle Treffer sind von 2021
            self.assertTrue(warte_bis(lambda: a.zustand == "fertig"))
            self.assertEqual((a.geladen, a.uebersprungen, a.captcha_versuche), (0, 3, 0))
            self.assertEqual(a.als_dict()["ab_jahr"], 2022)
        finally:
            v.stoppen()
            s.schliessen()

    def test_abbrechen_im_captcha(self):
        s = Speicher(":memory:")
        v = Verwalter(s, client_fabrik=lambda: FakeClient())
        try:
            a = v.anlegen(["Energieberatung"])
            self.assertTrue(warte_bis(lambda: a.zustand == "captcha"))
            v.abbrechen(a.id)
            self.assertTrue(warte_bis(lambda: a.zustand == "abgebrochen"))
            self.assertEqual(a.geladen, 0)
        finally:
            v.stoppen()

    def test_leere_begriffe(self):
        v = Verwalter(Speicher(":memory:"), client_fabrik=lambda: FakeClient())
        try:
            with self.assertRaises(ValueError):
                v.anlegen(["", "  "])
        finally:
            v.stoppen()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.konfig = Konfig(host="127.0.0.1", port=0, datenbank=Path(cls.tmp.name) / "t.sqlite")
        cls.speicher = Speicher(cls.konfig.datenbank)
        cls.verwalter = Verwalter(cls.speicher, client_fabrik=lambda: FakeClient())
        cls.server = erzeuge_server(cls.konfig, cls.speicher, cls.verwalter)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.verwalter.stoppen()
        cls.server.shutdown()
        cls.server.server_close()
        cls.speicher.schliessen()
        cls.tmp.cleanup()

    def anfrage(self, methode, pfad, daten=None, roh=False):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        rumpf = json.dumps(daten).encode("utf-8") if daten is not None else None
        c.request(methode, pfad, body=rumpf, headers={"Content-Type": "application/json"} if rumpf else {})
        r = c.getresponse()
        inhalt = r.read()
        c.close()
        return r.status, (inhalt if roh else json.loads(inhalt.decode("utf-8")))

    def test_ablauf(self):
        status, info = self.anfrage("GET", "/api/info")
        self.assertEqual(status, 200)
        self.assertFalse(info["passwort_noetig"])
        self.assertEqual(info["statistik"]["firmen"], 0)

        status, imp = self.anfrage("POST", "/api/import", {"dateiname": "kleinst.html", "html": lies("jahresabschluss_kleinst.html"), "ort": "Kleinstadt", "suchbegriff": "Energieberatung"})
        self.assertEqual(status, 201)
        self.assertEqual(imp["abschluss"]["firma"], "Klein Energieberatung UG (haftungsbeschränkt)")

        status, auftrag = self.anfrage("POST", "/api/auftraege", {"begriffe": "Energieberatung\nEnergieberater", "max_seiten": 1})
        self.assertEqual(status, 201)
        self.assertEqual(auftrag["begriffe"], ["Energieberatung", "Energieberater"])
        aid = auftrag["id"]
        self.assertTrue(warte_bis(lambda: self.anfrage("GET", f"/api/auftraege/{aid}")[1]["zustand"] == "captcha"))
        self.assertEqual(self.anfrage("GET", f"/api/auftraege/{aid}")[1]["captcha_art"], "bestaetigen")
        status, _ = self.anfrage("POST", f"/api/auftraege/{aid}/captcha", {"loesung": "bestaetigt"})
        self.assertEqual(status, 200)
        self.assertTrue(warte_bis(lambda: self.anfrage("GET", f"/api/auftraege/{aid}")[1]["zustand"] == "fertig"))

        status, firmen = self.anfrage("GET", "/api/firmen?suchbegriff=Energieberatung")
        self.assertEqual(status, 200)
        self.assertEqual(len(firmen["firmen"]), 2)  # importierte UG wurde erkannt und nicht erneut geladen
        klein = next(f for f in firmen["firmen"] if f["name"].startswith("Klein"))
        self.assertEqual(klein["quelle"], "import")
        gmbh = next(f for f in firmen["firmen"] if f["name"].startswith("Muster"))
        self.assertEqual(gmbh["kennzahlen"]["ampel"], "gruen")

        status, detail = self.anfrage("GET", f"/api/firmen/{gmbh['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["abschluesse"][0]["abschluss"]["mitarbeiter"], 11)

        status, roh = self.anfrage("GET", f"/api/abschluesse/{detail['abschluesse'][0]['id']}/roh", roh=True)
        self.assertEqual(status, 200)
        self.assertIn(b"publication_container", roh)

        status, branche = self.anfrage("GET", "/api/branche?suchbegriff=Energieberatung")
        self.assertEqual(status, 200)
        self.assertEqual(branche["anzahl"], 2)
        self.assertIn("urteil", branche)

        status, csv_daten = self.anfrage("GET", "/api/export.csv?suchbegriff=Energieberatung", roh=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(csv_daten.decode("utf-8-sig").strip().splitlines()), 3)

        status, _ = self.anfrage("DELETE", f"/api/firmen/{gmbh['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(self.anfrage("GET", "/api/firmen")[1]["firmen"]), 1)

        status, antwort = self.anfrage("POST", "/api/auftraege", {"begriffe": []})
        self.assertEqual(status, 400)
        status, info = self.anfrage("GET", "/api/info")
        self.assertEqual(info["quelle_standard"], "unternehmensregister")
        self.assertEqual(list(info["quellen"]), ["unternehmensregister"])
        status, antwort = self.anfrage("GET", "/api/auftraege/gibtsnicht")
        self.assertEqual(status, 404)

    def test_oberflaeche_und_gesund(self):
        status, html = self.anfrage("GET", "/", roh=True)
        self.assertEqual(status, 200)
        self.assertIn(b"Bilanz-Radar", html)
        self.assertEqual(self.anfrage("GET", "/gesund")[0], 200)


class KonfigTest(unittest.TestCase):
    def test_passwort_pflicht_und_pause(self):
        import os
        alt = dict(os.environ)
        try:
            os.environ["BILANZ_HOST"] = "0.0.0.0"
            os.environ.pop("BILANZ_PASSWORT", None)
            with self.assertRaises(ValueError):
                Konfig.aus_umgebung()
            os.environ["BILANZ_PASSWORT"] = "geheim"
            self.assertTrue(Konfig.aus_umgebung().passwort_noetig)
            os.environ["BILANZ_PAUSE"] = "0.1"
            with self.assertRaises(ValueError):
                Konfig.aus_umgebung()
        finally:
            os.environ.clear()
            os.environ.update(alt)


if __name__ == "__main__":
    unittest.main()


# --- Unternehmensregister (gesteuerter Browser) -------------------------------------------------

import functools
import http.server
import os
import unittest.mock

from bilanzen import unternehmensregister as ureg

UREG_FIXTURES = FIXTURES / "ureg"
_CHROMIUM = os.environ.get("BILANZ_CHROMIUM") or os.environ.get("CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else "")


def _browser_moeglich():
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return bool(_CHROMIUM) and Path(_CHROMIUM).exists()


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(_browser_moeglich(), "Playwright oder Chromium fehlt")
class UnternehmensregisterBrowser(unittest.TestCase):
    """Spielt den Ablauf gegen eine lokale Nachbildung der Registerseite durch (Cookie-Dialog, Formular, Trefferliste, Blättern,
    Sicherheitsabfrage „Ich bin ein Mensch“, Dokument)."""

    @classmethod
    def setUpClass(cls):
        handler = functools.partial(_Stumm, directory=str(UREG_FIXTURES))
        cls.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.basis = f"http://127.0.0.1:{cls.http.server_address[1]}"
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def test_ablauf(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ureg.BrowserClient(pause=0, chromium_pfad=_CHROMIUM, diagnose_ordner=tmp)
            client.suche_url = self.basis + "/suche.html"
            try:
                seite = client.suche("Energieberatung")
                self.assertEqual(seite.anzahl_seiten, 2)
                self.assertEqual([t.name for t in seite.treffer], ["Muster Energieberatung GmbH", "Klein Energieberatung UG (haftungsbeschränkt)"])
                t = seite.treffer[0]
                self.assertEqual((t.ort, t.datum, t.quelle, t.herkunft), ("Musterstadt", "12.03.2024", "unternehmensregister", "Unternehmensregister"))
                self.assertEqual(t.register, "Amtsgericht Musterstadt HRB 12345")
                self.assertEqual(t.bereich, "Rechnungslegung / Finanzberichte")
                self.assertEqual(seite.treffer[1].herkunft, "Bundesanzeiger")
                self.assertTrue(t.ist_jahresabschluss)
                self.assertTrue(t.link.endswith("veroeffentlichung.html?id=1"))
                self.assertEqual(seite.nummer, 1)
                self.assertTrue(seite.naechste_url)

                seite2 = client.naechste_seite(seite)
                self.assertEqual(seite2.nummer, 2)
                self.assertEqual([t.name for t in seite2.treffer], ["Dritte Energieberatung GmbH"])
                self.assertEqual(seite2.naechste_url, "")
                self.assertIsNone(client.naechste_seite(seite2))

                with self.assertRaises(CaptchaNoetig) as cm:
                    client.dokument(seite.treffer[0])
                self.assertTrue(cm.exception.bild.startswith(b"\x89PNG"))
                self.assertEqual((cm.exception.versuch, cm.exception.art), (1, "bestaetigen"))
                # erst nach der menschlichen Bestätigung klickt der Browser das Kästchen
                dok = client.captcha_loesen(cm.exception, "bestaetigt")
                self.assertIn("publication_container", dok.html)
                self.assertNotIn("companyName", dok.html)  # Suchformular gehört nicht ins Dokument
                a = parse_jahresabschluss(dok.html)
                self.assertEqual(a.posten["bilanzsumme"], [750000.0, 667260.45])
                self.assertEqual(a.posten["umsatz"], [1400000.0, 1284500.0])
                self.assertEqual(a.gj_bis, "2022-12-31")
                self.assertEqual(a.mitarbeiter, 12)
                self.assertTrue(any(p.suffix == ".png" for p in Path(tmp).iterdir()))
            finally:
                client.schliessen()


class UnternehmensregisterVerwaltung(unittest.TestCase):
    def test_quelle_im_auftrag(self):
        s = Speicher(":memory:")
        fake = FakeClient()
        fake.schliessen_aufgerufen = False
        fake.schliessen = lambda: setattr(fake, "schliessen_aufgerufen", True)
        v = Verwalter(s, client_fabrik=lambda: fake)
        try:
            a = v.anlegen(["Energieberatung"], max_seiten=1)
            self.assertEqual(a.als_dict()["quelle"], "unternehmensregister")
            self.assertTrue(warte_bis(lambda: a.zustand == "captcha"))
            v.captcha_beantworten(a.id, "bestaetigt")
            self.assertTrue(warte_bis(lambda: a.zustand == "fertig"))
            self.assertEqual(a.geladen, 2)
            self.assertTrue(fake.schliessen_aufgerufen)
            self.assertEqual({f["quelle"] for f in s.firmen("Energieberatung")}, {"unternehmensregister"})
        finally:
            v.stoppen()
            s.schliessen()

    def test_ohne_playwright_klare_meldung(self):
        s = Speicher(":memory:")
        v = Verwalter(s)  # echter Browser-Client
        try:
            with unittest.mock.patch.object(ureg, "verfuegbar", return_value=(False, "playwright fehlt")):
                with self.assertRaises(ValueError) as cm:
                    v.anlegen(["x"])
            self.assertIn("playwright", str(cm.exception))
        finally:
            v.stoppen()
            s.schliessen()

    def test_verfuegbar_meldet_fehlendes_chromium(self):
        ok, grund = ureg.verfuegbar("/gibt/es/nicht")
        try:
            import playwright  # noqa: F401
            self.assertFalse(ok)
            self.assertIn("Chromium", grund)
        except ImportError:
            self.assertFalse(ok)
            self.assertIn("playwright", grund)


# --- Vorreiter und CSV-Import ----------------------------------------------------------------------

from bilanzen import csv_import, vorreiter


class CsvImport(unittest.TestCase):
    def test_lesen_mit_teur_und_vorjahr(self):
        daten = csv_import.lese(lies("kennzahlen.csv"))
        self.assertEqual(len(daten), 4)
        alpha23 = next(d for d in daten if d["name"].startswith("Alpha") and d["gj_bis"] == "2023-12-31")
        self.assertEqual(alpha23["posten"]["bilanzsumme"], [1480000.0, 1250500.0])  # Vorjahr aus der Zeile 2022
        self.assertEqual(alpha23["posten"]["umsatz"], [4100000.0, 3400000.0])
        self.assertEqual(alpha23["mitarbeiter"], 33)
        self.assertEqual(alpha23["rechtsform"], "GmbH")
        beta = next(d for d in daten if d["name"].startswith("Beta"))
        self.assertEqual(beta["gj_bis"], "2023-12-31")
        self.assertNotIn("umsatz", beta["posten"])
        gamma = next(d for d in daten if d["name"].startswith("Gamma"))
        self.assertEqual(gamma["posten"]["jahresueberschuss"], [-120000.0, None])
        self.assertEqual(gamma["rechtsform"], "GmbH & Co. KG")

    def test_fehler(self):
        with self.assertRaises(csv_import.CsvFehler):
            csv_import.lese("a;b\n1;2\n")
        with self.assertRaises(csv_import.CsvFehler):
            csv_import.lese("Firma;Umsatz\nX GmbH;100\n")  # kein Jahr

    def test_import_in_speicher(self):
        s = Speicher(":memory:")
        r = csv_import.importieren(s, lies("kennzahlen.csv"), suchbegriff="Energieberatung", dateiname="kennzahlen.csv")
        self.assertEqual((r["abschluesse"], r["firmen"]), (4, 3))
        firmen = s.firmen("Energieberatung")
        self.assertEqual(len(firmen), 3)
        alpha = next(f for f in firmen if f["name"].startswith("Alpha"))
        self.assertEqual(alpha["gj_bis"], "2023-12-31")
        self.assertEqual(alpha["quelle"], "csv")
        self.assertEqual(alpha["anzahl_abschluesse"], 2)
        self.assertEqual([v["gj_bis"] for v in alpha["verlauf"]], ["2022-12-31", "2023-12-31"])
        self.assertAlmostEqual(alpha["kennzahlen"]["wachstum_umsatz"], 4100000 / 3400000 - 1)
        self.assertAlmostEqual(alpha["kennzahlen"]["umsatzrendite"], 265000 / 4100000)
        gamma = next(f for f in firmen if f["name"].startswith("Gamma"))
        self.assertEqual(gamma["kennzahlen"]["ampel"], "rot")
        s.schliessen()


class Vorreiter(unittest.TestCase):
    def test_rangliste(self):
        s = Speicher(":memory:")
        csv_import.importieren(s, lies("kennzahlen.csv"), suchbegriff="Energieberatung")
        s.dokument_speichern("Muster Energieberatung GmbH", "Musterstadt", lies("jahresabschluss_gmbh.html"), titel="x", suchbegriff="Energieberatung")
        r = vorreiter.rangliste(s.firmen("Energieberatung"), n=10)
        self.assertEqual(r["anzahl"], 4)
        self.assertEqual(r["rangliste"][0]["name"], "Alpha Energieberatung GmbH")  # wächst, verdient, hat Mehrjahrestrend
        self.assertEqual(r["rangliste"][0]["rang"], 1)
        self.assertIsNotNone(r["rangliste"][0]["perzentile"]["trend"])
        self.assertAlmostEqual(r["rangliste"][0]["werte"]["trend"], 4100000 / 3400000 - 1)
        namen = [e["name"] for e in r["rangliste"]]
        self.assertLess(namen.index("Alpha Energieberatung GmbH"), namen.index("Gamma Energie-Consulting GmbH & Co. KG"))
        self.assertEqual(r["kategorien"]["groesse"][0]["name"], "Gamma Energie-Consulting GmbH & Co. KG")
        self.assertTrue(all(0 <= p <= 100 for e in r["rangliste"] for p in e["perzentile"].values() if p is not None))
        self.assertTrue(r["rangliste"][0]["gruende"])
        s.schliessen()

    def test_perzentile_und_leer(self):
        self.assertEqual(vorreiter._perzentile({"a": 1, "b": 2, "c": 3}), {"a": 0.0, "b": 50.0, "c": 100.0})
        self.assertEqual(vorreiter._perzentile({"a": 1, "b": 1}), {"a": 50.0, "b": 50.0})
        self.assertEqual(vorreiter._perzentile({"a": None}), {})
        r = vorreiter.rangliste([])
        self.assertEqual((r["anzahl"], r["rangliste"]), (0, []))


class ServerVorreiterCsv(ServerTest):
    def test_ablauf(self):
        pass  # geerbter Ablauf läuft in ServerTest

    def test_oberflaeche_und_gesund(self):
        pass

    def test_csv_und_vorreiter(self):
        status, r = self.anfrage("POST", "/api/import-csv", {"dateiname": "k.csv", "text": lies("kennzahlen.csv"), "suchbegriff": "CSV-Test"})
        self.assertEqual(status, 201)
        self.assertEqual(r["firmen"], 3)
        status, v = self.anfrage("GET", "/api/vorreiter?suchbegriff=CSV-Test&n=2")
        self.assertEqual(status, 200)
        self.assertEqual(len(v["rangliste"]), 2)
        self.assertEqual(v["rangliste"][0]["rang"], 1)
        status, fehler = self.anfrage("POST", "/api/import-csv", {"dateiname": "x.csv", "text": "a;b\n1;2\n"})
        self.assertEqual(status, 400)
