import json
import unittest
from pathlib import Path

from heizlast.abgleich import (
    DT_LOG_N, berechne_abgleich, dt_log_erforderlich, leistung, ruecklauf_bei_vorlauf, vorlauf_erforderlich,
)
from heizlast.heizlast import berechne_gebaeude, berechne_raum
from heizlast.zahlen import de

MUSTERHAUS = Path(__file__).resolve().parent.parent / "beispiele" / "musterhaus.json"


def _projekt(**raum):
    return {
        "klima": {"theta_e": -10.0, "theta_m_e": 9.0},
        "lueftung": {"n50": 4.0, "epsilon": 1.0, "n_min_standard": 0.5},
        "waermebruecken": {"delta_U": 0.10},
        "bauteile": {"AW": {"bezeichnung": "Wand", "U": 1.0}, "FE": {"bezeichnung": "Fenster", "U": 1.0},
                     "IW": {"bezeichnung": "Innenwand", "U": 2.0}},
        "angrenzend": {"Keller": {"b_u": 0.5}},
        "raeume": [dict({"name": "R", "theta_i": 20, "A": 10.0, "h": 2.5, "e": 0.02}, **raum)],
    }


class HeizkoerperKennlinie(unittest.TestCase):
    def test_normbedingung(self):
        self.assertAlmostEqual(DT_LOG_N, 49.83, places=2)
        self.assertAlmostEqual(leistung(1000, 1.3, 75, 65, 20), 1000, places=6)

    def test_vorlauf_umkehrung(self):
        dT = dt_log_erforderlich(700, 1500, 1.3)
        tv = vorlauf_erforderlich(dT, 7.0, 20)
        self.assertAlmostEqual(leistung(1500, 1.3, tv, tv - 7.0, 20), 700, places=3)

    def test_ruecklauf_umkehrung(self):
        dT = dt_log_erforderlich(700, 1500, 1.3)
        tr = ruecklauf_bei_vorlauf(dT, 55.0, 20)
        self.assertAlmostEqual(leistung(1500, 1.3, 55.0, tr, 20), 700, places=3)

    def test_heizkoerper_zu_klein(self):
        self.assertIsNone(ruecklauf_bei_vorlauf(dt_log_erforderlich(3000, 1000, 1.3), 55.0, 20))


class Raumheizlast(unittest.TestCase):
    def test_handrechnung(self):
        p = _projekt(bauteile=[{"typ": "AW", "A": 10.0}])
        r = berechne_raum(p["raeume"][0], p)
        # 10 m² * (1,0 + 0,1) * 30 K
        self.assertAlmostEqual(r.phi_T, 330.0)
        # V = 25 m³, V_min = 12,5 m³/h > V_inf = 2*25*4*0,02 = 4 m³/h
        self.assertAlmostEqual(r.V_inf, 4.0)
        self.assertAlmostEqual(r.phi_V, 0.34 * 12.5 * 30)
        self.assertAlmostEqual(r.phi_HL, 330.0 + 127.5)

    def test_oeffnung_wird_abgezogen(self):
        p = _projekt(bauteile=[{"typ": "AW", "l": 4.0, "h": 2.5, "oeffnungen": [{"typ": "FE", "l": 1.0, "h": 2.0}]}])
        r = berechne_raum(p["raeume"][0], p)
        self.assertEqual([round(b.A, 6) for b in r.bauteile], [8.0, 2.0])

    def test_unbeheizt_und_nachbarraum(self):
        p = _projekt(bauteile=[{"typ": "AW", "A": 10.0, "an": "Keller"}, {"typ": "IW", "A": 10.0, "an": 15}])
        r = berechne_raum(p["raeume"][0], p)
        keller, nachbar = r.bauteile
        self.assertAlmostEqual(keller.phi, 10 * 1.1 * 0.5 * 30)
        self.assertEqual(nachbar.dU, 0.0)
        self.assertAlmostEqual(nachbar.phi, 10 * 2.0 * 5)
        self.assertTrue(nachbar.intern)
        self.assertAlmostEqual(r.phi_T_gebaeude, keller.phi)


class Musterhaus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = json.loads(MUSTERHAUS.read_text(encoding="utf-8"))
        cls.geb = berechne_gebaeude(cls.p)
        cls.abg = berechne_abgleich(cls.p, cls.geb)

    def test_gebaeude_kleiner_als_raumsumme(self):
        self.assertLess(self.geb.phi_HL, self.geb.summe_raumheizlasten)

    def test_alle_heizkoerper_decken_raumheizlast(self):
        self.assertLessEqual(self.abg.theta_V, self.abg.theta_V_ziel)
        for h in self.abg.heizkoerper:
            q = leistung(h.phi_N_ausl, h.n, self.abg.theta_V, h.theta_R, h.theta_i)
            self.assertAlmostEqual(q, h.phi_soll, delta=0.5, msg=h.id)

    def test_raumlast_vollstaendig_verteilt(self):
        je_raum = {}
        for h in self.abg.heizkoerper:
            je_raum[h.raum] = je_raum.get(h.raum, 0.0) + h.phi_soll
        for r in self.geb.raeume:
            self.assertAlmostEqual(je_raum[r.name], r.phi_HL, places=6)

    def test_ungünstigster_strang_hat_mindestdruck(self):
        self.assertAlmostEqual(min(h.dp_ventil for h in self.abg.heizkoerper),
                               self.p["hydraulik"]["dp_ventil_min_mbar"] * 100)


class Zahlen(unittest.TestCase):
    def test_deutsches_format(self):
        self.assertEqual(de(12891.4), "12.891")
        self.assertEqual(de(1.5, 2), "1,50")


if __name__ == "__main__":
    unittest.main()
