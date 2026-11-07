import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from bilanzen import bewertung, kennzahlen
from bilanzen.auftraege import Verwalter
from bilanzen.bundesanzeiger import (CaptchaNoetig, Dokument, Seite, Treffer, erkenne_captcha, geschaeftsjahr_aus_titel,
                                     parse_trefferseite)
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


class Trefferliste(unittest.TestCase):
    def test_parse(self):
        s = parse_trefferseite(lies("trefferliste.html"), "https://www.bundesanzeiger.de/pub/de/suchen2?3")
        self.assertEqual(s.nummer, 1)
        self.assertEqual(s.anzahl_treffer, 759)
        self.assertEqual(len(s.treffer), 3)
        t = s.treffer[0]
        self.assertEqual(t.name, "Beispiel Energieberatung 1 GmbH")
        self.assertEqual(t.ort, "Musterort 1")
        self.assertTrue(t.ist_jahresabschluss)
        self.assertTrue(t.link.startswith("https://www.bundesanzeiger.de/pub/de/suchen2?3-1.-search~table~panel-rows-0-"))
        self.assertEqual(t.datum, "27.06.2025")
        self.assertEqual(s.naechste_url, "https://www.bundesanzeiger.de/pub/de/suchen2?3-1.-top~nav-pager-next")

    def test_geschaeftsjahr(self):
        self.assertEqual(geschaeftsjahr_aus_titel("Jahresabschluss zum Geschäftsjahr vom 01.06.2020 bis zum 31.05.2021"), ("2020-06-01", "2021-05-31"))
        self.assertEqual(geschaeftsjahr_aus_titel("Jahresabschluss zum 31.12.2019"), ("", "2019-12-31"))
        self.assertEqual(geschaeftsjahr_aus_titel("Konzernabschluss 2018"), ("", "2018-12-31"))

    def test_hinterlegung_ohne_link(self):
        t = Treffer(name="X GmbH", ort="Y", titel="Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021", link="", datum="")
        self.assertFalse(t.ist_jahresabschluss)


class Captcha(unittest.TestCase):
    def test_erkennen(self):
        c = erkenne_captcha(parse(lies("captcha.html")), "https://www.bundesanzeiger.de/pub/de/suchergebnis?4")
        self.assertIsNotNone(c)
        self.assertIn("captcha_image", c["bild_url"])
        self.assertEqual(c["formular_url"], "https://www.bundesanzeiger.de/pub/de/suchergebnis?4-1.-captcha~panel-captcha_form")

    def test_kein_captcha(self):
        self.assertIsNone(erkenne_captcha(parse(lies("jahresabschluss_gmbh.html")), "https://x/"))


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
    """Spielt den Bundesanzeiger: zwei Treffer, der erste verlangt einmal ein Captcha."""

    def __init__(self, loesung="ABC123"):
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
            raise CaptchaNoetig(bild=b"\x89PNG...", bild_typ="image/png", formular_url="https://x/captcha", seite_url=treffer.link)
        return Dokument(html=lies("jahresabschluss_gmbh.html" if treffer.link.endswith("/1") else "jahresabschluss_kleinst.html"), url=treffer.link)

    def captcha_loesen(self, captcha, loesung):
        self.anfragen += 1
        self.captcha_gesendet += 1
        if loesung != self.loesung:
            raise CaptchaNoetig(bild=b"\x89PNG...", bild_typ="image/png", formular_url="https://x/captcha", seite_url=captcha.seite_url, versuch=captcha.versuch + 1)
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
            v.captcha_beantworten(a.id, "falsch")
            self.assertTrue(warte_bis(lambda: a.captcha_versuche == 1 and a.zustand == "captcha"))
            v.captcha_beantworten(a.id, "ABC123")
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
        status, _ = self.anfrage("POST", f"/api/auftraege/{aid}/captcha", {"loesung": "ABC123"})
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
