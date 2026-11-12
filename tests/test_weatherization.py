import copy
import json
import unittest
from pathlib import Path

from weatherization.audit import (apply, ashrae_62_2, climate, initial_state, materials, measure_cost, regression, run, simulate,
                                  upv)
from weatherization.report import audit_html, inspection_html, workorder_html

MUSTER = Path(__file__).resolve().parent.parent / "beispiele" / "usa_wap_musterhaus.json"


def projekt():
    return json.loads(MUSTER.read_text(encoding="utf-8"))


class Grundlagen(unittest.TestCase):
    def test_regression_exakt(self):
        rows = [{"days": d, "hdd65": h, "therms": d * (0.6 + 0.25 * h / d)} for d, h in ((30, 600), (31, 300), (31, 20), (28, 500))]
        a, b, r2 = regression(rows)
        self.assertAlmostEqual(a, 0.6, places=9)
        self.assertAlmostEqual(b, 0.25, places=9)
        self.assertAlmostEqual(r2, 1.0, places=9)

    def test_upv(self):
        p = {"economics": {"discount_rate": 0.03, "escalation": {"gas": 0.0, "electric": 0.0}}}
        # Rentenbarwertfaktor 3 %, 20 Jahre
        self.assertAlmostEqual(upv(p, "gas", 20), 14.877, places=3)
        p["economics"]["upv_star"] = {"gas": {"20": 16.5}}
        self.assertEqual(upv(p, "gas", 20), 16.5)
        self.assertAlmostEqual(upv(p, "electric", 20), 14.877, places=3)

    def test_ashrae_62_2(self):
        p = projekt()
        v = ashrae_62_2(p, 2300, {})
        self.assertAlmostEqual(v["q_tot"], 0.03 * 1150 + 7.5 * 4)
        self.assertAlmostEqual(v["q_inf"], 0.052 * 2300 * 0.53 * (9.5 / 8.2) ** 0.4)
        self.assertAlmostEqual(v["deficit"], 80 + 30)  # Fenstergutschrift 20 cfm je Raum
        # Badlüfter mit 80 cfm beseitigt das Defizit im Bad, die Küche bleibt
        v2 = ashrae_62_2(p, 2300, {"Bathroom": 80})
        self.assertAlmostEqual(v2["deficit"], 80)
        self.assertGreater(v2["q_fan"], 0)
        # dichteres Haus braucht mehr Ventilator
        self.assertGreater(ashrae_62_2(p, 1500, {"Bathroom": 80})["q_fan"], v2["q_fan"])

    def test_materialmengen(self):
        m = {"materials": {"kind": "loose_fill", "added_R": 37, "r_per_inch": 3.7, "density": 1.5, "bag_lb": 25, "area": 1000}}
        x = materials(m)
        self.assertAlmostEqual(x["depth"], 10.0)
        self.assertEqual(x["bags"], 50)  # 1000 ft² × 10/12 ft × 1,5 lb/ft³ = 1250 lb


class Modell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = projekt()
        cls.clim = climate(cls.p)

    def test_klima(self):
        self.assertTrue(4500 < self.clim.hdd65 < 5300)
        self.assertEqual(len(self.clim.hours), 8760)

    def test_daemmung_und_luftdichtheit_senken_heizung(self):
        s0 = initial_state(self.p)
        e0 = simulate(self.p, s0, self.clim)
        for m in self.p["measures"]:
            if m["type"] in ("envelope", "air_sealing", "dse", "heating_eff"):
                self.assertLess(simulate(self.p, apply(s0, m), self.clim).heat_therms, e0.heat_therms, m["id"])
        # zusätzlicher Abluftventilator erhöht den Heizbedarf
        s1 = copy.deepcopy(s0)
        s1.q_fan = 40
        self.assertGreater(simulate(self.p, s1, self.clim).heat_therms, e0.heat_therms)


class Musterhaus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = projekt()
        cls.A = run(cls.p)

    def test_kalibrierung(self):
        b = self.A.bill
        self.assertGreater(b.r2, 0.95)
        self.assertTrue(0.7 <= b.calibration <= 1.3)
        self.assertAlmostEqual(self.A.pre.heat_therms, b.heat_normalized, places=6)
        self.assertAlmostEqual(self.A.pre.elec, b.elec_annual, places=6)

    def test_sir_regeln(self):
        ecm = [x for x in self.A.measures if x.decision == "ECM"]
        self.assertGreater(len(ecm), 0)
        self.assertEqual(sorted(x.rank for x in ecm), list(range(1, len(ecm) + 1)))
        for x in ecm:
            self.assertGreaterEqual(x.pkg.sir, 1.0, x.m["id"])
        for x in self.A.measures:
            if x.decision != "ECM":
                self.assertLess(x.pkg.sir, 1.0, x.m["id"])
        self.assertGreaterEqual(self.A.package.sir, 1.0)
        self.assertAlmostEqual(self.A.package.pv, sum(x.pkg.pv for x in ecm))
        d = {x.m["id"]: x.decision for x in self.A.measures}
        self.assertEqual(d["HF-1"], "Not cost-effective")
        self.assertEqual(d["DS-1"], "H&S")  # Kanalabdichtung fällt unter SIR 1 und wird wegen CAZ als H&S ausgeführt

    def test_wechselwirkung(self):
        hf = next(x for x in self.A.measures if x.m["id"] == "HF-1")
        self.assertLess(hf.pkg.therms, hf.alone.therms)  # nach der Dämmung spart der neue Kessel weniger

    def test_kosten(self):
        c = self.A.costs
        self.assertAlmostEqual(c["ecm"], sum(measure_cost(x.m) for x in self.A.measures if x.decision == "ECM"))
        self.assertAlmostEqual(c["total"], c["ecm"] + c["hs"])
        self.assertAlmostEqual(c["hs_avg"], 0.14 * 8813)

    def test_zustand_und_ergebnis(self):
        self.assertEqual(self.A.pre_state.cfm50, 3400)
        self.assertEqual(self.A.post_state.cfm50, 2300)
        self.assertLess(self.A.post.gas, self.A.pre.gas)
        self.assertLess(self.A.post.elec, self.A.pre.elec)
        self.assertGreaterEqual(self.p["ventilation_62_2"]["continuous_fan_cfm"], self.A.vent_post["q_fan"])

    def test_caz(self):
        failed = [r[0] for r in self.A.caz if not r[3]]
        self.assertEqual(len(failed), 3)
        self.assertTrue(any("depressurization" in f for f in failed))

    def test_berichte(self):
        h = audit_html(self.p, self.A)
        self.assertIn("Home Energy Audit Report", h)
        self.assertIn("SAMPLE", h)
        self.assertIn("WAIVER REQUIRED", h)
        w = workorder_html(self.p, self.A)
        self.assertIn("Stop work", w)
        self.assertNotIn("HF-1</td>", w)  # nicht wirtschaftliche Maßnahme steht nicht im Auftrag
        i = inspection_html(self.p, self.A)
        self.assertIn("certification no.", i)
        self.assertIn("Assessment of the energy audit", i)


if __name__ == "__main__":
    unittest.main()
