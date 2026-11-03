import json
import unittest
from pathlib import Path

from usa.energy import run_all, weather
from usa.hvac import friction, interp, manual_d, manual_j, manual_s, rect_equiv, ventilation_62_2
from usa.report_energy import html as energy_html
from usa.report_hvac import html as hvac_html

MUSTER = Path(__file__).resolve().parent.parent / "beispiele" / "usa_musterhaus.json"


def projekt():
    return json.loads(MUSTER.read_text(encoding="utf-8"))


class Grundlagen(unittest.TestCase):
    def test_ventilation_62_2(self):
        v = ventilation_62_2(2400, 4)
        self.assertAlmostEqual(v["q_tot"], 109.5)
        self.assertEqual(v["q_fan"], 110)

    def test_friction_chart(self):
        # Reibungsdiagramm: 6" rund, 100 cfm ≈ 0,08–0,09 in. w.c. / 100 ft
        self.assertAlmostEqual(friction(100, 6), 0.085, delta=0.005)
        # Rechteck 8×8 ≈ 8,7" gleichwertiger Durchmesser
        self.assertAlmostEqual(rect_equiv(8, 8), 8.75, delta=0.05)

    def test_interp(self):
        tab = [[5, 10.0], [17, 22.0]]
        self.assertAlmostEqual(interp(tab, 11), 16.0)
        self.assertAlmostEqual(interp(tab, -7), -2.0)


class Musterhaus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = projekt()
        cls.L = manual_j(cls.p)
        cls.S = manual_s(cls.p, cls.L)
        cls.D = manual_d(cls.p, cls.L)

    def test_lastsummen(self):
        L = self.L
        self.assertAlmostEqual(L.heating, sum(r.heating for r in L.rooms) + L.vent_heat, places=6)
        self.assertAlmostEqual(L.cfa, 2400)
        self.assertTrue(20000 < L.heating < 30000)
        self.assertTrue(L.sensible > L.latent > 0)

    def test_raumluftmengen_ergeben_geblaese(self):
        eq = self.p["equipment"]
        self.assertAlmostEqual(sum(r.cfm_heat for r in self.L.rooms), eq["blower_cfm_heating"], places=6)
        self.assertAlmostEqual(sum(r.cfm_cool for r in self.L.rooms), eq["blower_cfm_cooling"], places=6)

    def test_manual_s(self):
        self.assertTrue(all(ok for _, ok, _ in self.S.checks))
        self.assertIsNotNone(self.S.balance_point)
        self.assertGreater(self.S.balance_point, self.p["climate"]["heating_db"])

    def test_manual_d(self):
        D = self.D
        self.assertTrue(0.06 <= D.fr <= 0.18)
        for r in D.runs:
            self.assertLessEqual(friction(r.cfm, r.dia), D.fr + 1e-9)
            self.assertLessEqual(r.vel, self.p["ducts"]["v_max_supply"])
        self.assertAlmostEqual(D.trunks[0]["cfm"], self.p["equipment"]["blower_cfm_cooling"])

    def test_berichte(self):
        h = hvac_html(self.p, self.L, self.S, self.D)
        self.assertIn("Plans examiner summary", h)
        self.assertIn("SAMPLE", h)


class Energie(unittest.TestCase):
    def test_wetter(self):
        h = weather(40.8, 21)
        self.assertEqual(len(h), 8760)
        hdd = sum(max(0.0, 65 - t) for _, t, _ in h) / 24
        self.assertTrue(4500 < hdd < 6500)

    def test_r405(self):
        p = projekt()
        R = run_all(p)
        self.assertLess(R["proposed"].cost, R["reference"].cost)
        for _, r in R["upgrades"]:
            self.assertLess(r.total, R["proposed"].total)
        self.assertIn("COMPLIES", energy_html(p, R))


if __name__ == "__main__":
    unittest.main()
