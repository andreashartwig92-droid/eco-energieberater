import unittest
from dataclasses import replace

import numpy as np
import pandas as pd

from altcoin_divergenz.backtest import Handel, simuliere, umgekehrt
from altcoin_divergenz.muster import musterdivergenzen
from altcoin_divergenz.strategie import Parameter, divergenzen, indikatoren, rsi


def _zufallskerzen(n: int = 800, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    spanne = np.abs(rng.normal(0, 0.001, n)) * close
    return pd.DataFrame({"ts": np.arange(n) * 60_000, "open": open_, "close": close,
                         "high": np.maximum(open_, close) + spanne, "low": np.minimum(open_, close) - spanne})


def _divergenz_kerzen(rsi2: float = 40.0, hist2: float = -0.5) -> pd.DataFrame:
    n = 40
    low = np.full(n, 100.0)
    low[10], low[25] = 95.0, 94.0  # tieferes Tief im Kurs
    r = np.full(n, 50.0)
    r[10], r[25] = 30.0, rsi2       # höheres Tief im RSI
    h = np.zeros(n)
    h[10], h[25] = -1.0, hist2
    return pd.DataFrame({"low": low, "high": low + 1, "rsi": r, "hist": h})


class Indikatoren(unittest.TestCase):
    def test_rsi_grenzen(self):
        r = rsi(_zufallskerzen()["close"]).dropna()
        self.assertTrue(((r >= 0) & (r <= 100)).all())
        self.assertEqual(rsi(pd.Series(np.arange(1.0, 50.0))).iloc[-1], 100.0)


class Divergenz(unittest.TestCase):
    def test_klare_bullische_divergenz(self):
        s = divergenzen(_divergenz_kerzen())
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["richtung"], s[0]["pivot1"], s[0]["pivot2"]), ("long", 10, 25))
        self.assertEqual(s[0]["signal_idx"], 25 + Parameter().rechts)

    def test_zu_schwach_oder_ohne_macd(self):
        self.assertEqual(divergenzen(_divergenz_kerzen(rsi2=31.0)), [])
        self.assertEqual(divergenzen(_divergenz_kerzen(hist2=-2.0)), [])
        self.assertEqual(len(divergenzen(_divergenz_kerzen(hist2=-2.0), Parameter(macd_bestaetigung=False))), 1)

    def test_kein_blick_in_die_zukunft(self):
        """Signale bis Kerze T dürfen nicht davon abhängen, ob Daten nach T existieren."""
        df = _zufallskerzen()
        voll = divergenzen(indikatoren(df))
        self.assertGreater(len(voll), 0)
        for t in (300, 450, 600, 799):
            gekuerzt = divergenzen(indikatoren(df.iloc[:t].copy()))
            self.assertEqual(gekuerzt, [s for s in voll if s["signal_idx"] < t])


class Simulation(unittest.TestCase):
    def _df(self, high2: float, low2: float) -> pd.DataFrame:
        return pd.DataFrame({"open": [100.0] * 4, "close": [100.0] * 4,
                             "high": [100.2, 100.2, high2, 100.2], "low": [99.8, 99.8, low2, 99.8]})

    def test_stop_vor_ziel_in_derselben_kerze(self):
        t = simuliere(self._df(101.5, 99.0), 1, 1, 99.5, Handel(gebuehr=0, slippage=0))
        self.assertEqual(t["grund"], "Stop-Loss")
        self.assertAlmostEqual(t["marge_netto_pct"], -5.0)

    def test_ziel_mit_gebuehren(self):
        t = simuliere(self._df(101.5, 99.8), 1, 1, 99.5, Handel(gebuehr=0.0005, slippage=0))
        self.assertEqual(t["grund"], "Take-Profit")
        self.assertAlmostEqual(t["marge_brutto_pct"], 10.0)
        self.assertAlmostEqual(t["marge_netto_pct"], 10 * (0.01 - 0.0005 * (1 + 1.01)) * 100)

    def test_short_und_zu_weiter_stop(self):
        t = simuliere(self._df(100.2, 98.0), 1, -1, 100.5, Handel(gebuehr=0, slippage=0))
        self.assertEqual(t["grund"], "Take-Profit")
        self.assertIsNone(simuliere(self._df(100.2, 99.8), 1, 1, 90.0, Handel()))

    def test_umkehr(self):
        df, h = self._df(101.5, 99.8), Handel(gebuehr=0, slippage=0)
        normal = simuliere(df, 1, 1, 99.5, h)                                   # Long trifft Ziel 101: +10 %
        spiegel = umgekehrt(df, 1, 1, 99.5, replace(h, umkehr="spiegel"))     # Short, Stop 101, Ziel 99,5
        gleich = umgekehrt(df, 1, 1, 99.5, replace(h, umkehr="gleich"))       # Short, Stop 100,5, Ziel 99
        self.assertAlmostEqual(normal["marge_brutto_pct"], 10.0)
        self.assertAlmostEqual(spiegel["marge_brutto_pct"], -10.0)
        self.assertAlmostEqual(spiegel["stop"], 101.0)
        self.assertAlmostEqual(spiegel["ziel"], 99.5)
        self.assertAlmostEqual(gleich["marge_brutto_pct"], -5.0)
        self.assertAlmostEqual(gleich["ziel"], 99.0)


def _musterbuch_kerzen(**aenderung) -> pd.DataFrame:
    n = 40
    low = np.full(n, 100.0)
    low[10], low[25] = 95.0, 94.0
    r = np.full(n, 50.0)
    r[10], r[25] = 25.0, 35.0
    hist = np.zeros(n)
    hist[10], hist[25] = -1.0, -0.5
    macd = np.zeros(n)
    macd[10], macd[25] = -2.0, -1.0
    df = pd.DataFrame({"low": low, "high": low + 1, "close": low + 0.5, "rsi": r, "hist": hist, "macd": macd})
    for spalte, werte in aenderung.items():
        for i, v in werte.items():
            df.loc[i, spalte] = v
    return df


class Musterbuch(unittest.TestCase):
    def test_lehrbuch_bullisch(self):
        s = musterdivergenzen(_musterbuch_kerzen())
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["richtung"], s[0]["erfuellt"], s[0]["fehlt"]), ("long", 7, ""))
        self.assertEqual(s[0]["signal_idx"], 28)  # Bestätigung nach 3 Kerzen, Schluss über Pivot-Hoch

    def test_rsi_linie_durchbrochen(self):
        s = musterdivergenzen(_musterbuch_kerzen(rsi={18: 26.0}))
        self.assertEqual((s[0]["erfuellt"], s[0]["fehlt"]), (6, "M5 RSI-Linie sauber"))

    def test_ohne_ausloeser_kein_signal(self):
        nach = {i: 94.5 for i in range(26, 40)}
        df = _musterbuch_kerzen(low=nach, high={i: 95.0 for i in range(26, 40)}, close={i: 94.8 for i in range(26, 40)})
        self.assertEqual(musterdivergenzen(df), [])

    def test_kein_blick_in_die_zukunft(self):
        df = _zufallskerzen(3000, seed=5)
        voll = musterdivergenzen(indikatoren(df))
        self.assertGreater(len(voll), 0)
        for t in (700, 1500, 2999):
            gekuerzt = musterdivergenzen(indikatoren(df.iloc[:t].copy()))
            self.assertEqual(gekuerzt, [s for s in voll if s["signal_idx"] <= t - 2])


class Zusammenfassen(unittest.TestCase):
    def test_zehn_aus_fuenf_minuten(self):
        from altcoin_divergenz.hyperliquid import zusammenfassen
        fuenf = pd.DataFrame({"ts": np.arange(5) * 300_000 + 300_000,  # beginnt mitten in einer 10-Minuten-Kerze
                              "open": [1.0, 2, 3, 4, 5], "high": [1.5, 2.5, 3.5, 4.5, 5.5],
                              "low": [0.5, 1.5, 2.5, 3.5, 4.5], "close": [1.2, 2.2, 3.2, 4.2, 5.2],
                              "vol_usd": [10.0, 20, 30, 40, 50]})
        zehn = zusammenfassen(fuenf, 600_000, 300_000)
        self.assertEqual(zehn["ts"].tolist(), [600_000, 1_200_000])  # unvollständige Rand-Kerzen entfallen
        self.assertEqual(zehn.iloc[0][["open", "high", "low", "close", "vol_usd"]].tolist(), [2.0, 3.5, 1.5, 3.2, 50.0])


class Merkmale(unittest.TestCase):
    def test_indikatoren_grenzen_und_kein_blick_in_die_zukunft(self):
        from altcoin_divergenz.merkmale import erweitern
        df = _zufallskerzen(600).assign(ts=lambda x: x["ts"] * 5, vol_usd=1000.0)  # 5-Minuten-Raster
        voll = erweitern(df)
        for spalte in ("stoch_k", "adx"):
            w = voll[spalte].dropna()
            self.assertTrue(((w >= 0) & (w <= 100)).all(), spalte)
        gekuerzt = erweitern(df.iloc[:400].copy())
        for spalte in ("rsi_1h", "stoch_k", "adx", "ema200", "vol_schnitt"):
            pd.testing.assert_series_equal(gekuerzt[spalte], voll[spalte].iloc[:400], check_names=False)


class Trend(unittest.TestCase):
    def _kerzen(self):
        # Einstieg Kerze 1 bei 100, Stop 99 (R = 1); Kerze 2 erreicht +1,2, Kerze 3 fällt auf 99,9 zurück
        o = np.array([100.0, 100.0, 100.4, 100.8, 100.0, 100.0])
        hi = np.array([100.2, 100.5, 101.2, 100.8, 100.2, 100.2])
        lo = np.array([99.8, 99.5, 100.2, 99.9, 99.8, 99.8])
        c = np.array([100.0, 100.4, 100.8, 100.0, 100.0, 100.0])
        return o, hi, lo, c, np.full(6, 0.5)

    def test_ausstiegsarten(self):
        from altcoin_divergenz.trend import simuliere as sim
        h = Handel(gebuehr=0, slippage=0, min_stop=0, max_stop=0.05)
        ergebnis = {art: sim(*self._kerzen(), 1, 1, 99.0, h, art, 0.0) for art in ("fest", "Einstand", "Trailing", "Halb")}
        self.assertEqual(ergebnis["fest"]["grund"], "offen (letzter Kurs)")
        self.assertAlmostEqual(ergebnis["Einstand"]["marge_brutto_pct"], 0.0)       # Stop auf Einstand
        self.assertAlmostEqual(ergebnis["Trailing"]["marge_brutto_pct"], 2.0)       # 101,2 - 2 ATR = 100,2
        self.assertAlmostEqual(ergebnis["Halb"]["marge_brutto_pct"], 6.0)           # ½ bei 101, ½ bei 100,2
        self.assertEqual(ergebnis["Halb"]["grund"], "nachgezogener Stop")

    def test_funding_longs_zahlen(self):
        from altcoin_divergenz.trend import FUNDING_JE_STUNDE, simuliere as sim
        h = Handel(gebuehr=0, slippage=0, min_stop=0, max_stop=0.05)
        ohne = sim(*self._kerzen(), 1, 1, 99.0, h, "fest", 0.0)
        mit = sim(*self._kerzen(), 1, 1, 99.0, h, "fest", 1.0)
        self.assertAlmostEqual(ohne["marge_netto_pct"] - mit["marge_netto_pct"],
                               10 * FUNDING_JE_STUNDE * ohne["kerzen"] * 100)

    def test_versteckte_divergenz_im_aufwaertstrend(self):
        from altcoin_divergenz.muster import trendsignale
        df = _musterbuch_kerzen(low={25: 96.0}, rsi={10: 40.0, 25: 35.0}).assign(ema50=95.0, ema200=90.0)
        s = trendsignale(df)
        self.assertEqual([(x["richtung"], x["pivot1"], x["pivot2"], x["signal_idx"]) for x in s],
                         [("long", 10, 25, 28)])
        df_ohne = df.assign(rsi=df["rsi"].where(df.index != 25, 41.0))  # RSI höheres Tief: keine versteckte Divergenz
        self.assertEqual(trendsignale(df_ohne), [])
        self.assertEqual(len(trendsignale(df_ohne, mit_rsi=False)), 1)      # Kontrolle ohne RSI-Bedingung
        self.assertEqual(trendsignale(df.assign(ema50=85.0)), [])            # kein Aufwärtstrend


if __name__ == "__main__":
    unittest.main()
