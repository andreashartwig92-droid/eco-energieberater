"""Fair Value Gaps (FVG) nach den gängigen ICT-Regeln – Backtest.

  python3 -m altcoin_divergenz fvg

Fair Value Gap: drei Kerzen, die mittlere ist eine kräftige Bewegungskerze ("Displacement"), und zwischen
Kerze 1 und Kerze 3 bleibt eine Kurslücke.
  Bullisch: Tief von Kerze 3 > Hoch von Kerze 1  -> Lücke [Hoch K1, Tief K3]
  Bärisch:  Hoch von Kerze 3 < Tief von Kerze 1  -> Lücke [Hoch K3, Tief K1]

Handel (Standard-Lehre, die genauen Regeln aus dem Video sind nicht bekannt):
  Einstieg  Limit-Order in der Mitte der Lücke ("Consequent Encroachment"), gültig 20 Kerzen nach Kerze 3.
            Ausgeführt wird nur, wenn der Kurs die Mitte wirklich erreicht.
  Stop      0,05 % hinter Kerze 1 (Ursprung der Bewegung), mindestens 0,2 %, höchstens 3 %.
  Ziel      fest: 2 × Stop-Abstand (CRV 1:2) – oder "Halb": Hälfte bei +1R, Rest mit 2-ATR-Trailing-Stop.
  Kosten    Hyperliquid: Einstieg und Ziele als Limit-Order (Maker 0,015 %), Stops als Market-Order
            (Taker 0,045 % + Slippage aus dem Orderbuch), Funding 0,00125 % je Stunde.

Varianten: alle Lücken; Standard (Lücke >= 0,25 ATR und Bewegungskerze >= 1 ATR); Standard plus Trendfilter
(nur in Richtung von EMA 50/200). Zeitrahmen 5 min (3 Monate), 15 min (6 Monate), 1 h (12 Monate), OKX-Kurse
der 31 Coins mit 10x auf Hyperliquid. 100x wird aus denselben Trades abgeleitet: wer zwischendurch mehr als
0,5 % gegen sich hatte, wäre bei 100x liquidiert worden (Margin weg).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import okx
from .backtest import kennzahlen, konto_mit_kapital
from .merkmale import atr_adx
from .musterbuch import BASIS, KAPITAL, MARGE, de, eur, tabelle
from .strategie import indikatoren
from .trend import BERLIN, CACHE, COINS, ENDE, ERGEBNISSE, MAKER, OKX_NAME, VORLAUF, simuliere

ZEITRAHMEN = [("5m", "5 Minuten", 92, 300_000), ("15m", "15 Minuten", 183, 900_000), ("1H", "1 Stunde", 365, 3_600_000)]
VARIANTEN = {"alle Lücken": (0.0, 0.0, False), "Standard-FVG": (0.25, 1.0, False),
             "Standard-FVG + Trend": (0.25, 1.0, True)}
AUSSTIEGE = ["fest", "Halb"]
GUELTIG = 20
LIQ_100X = 0.5  # % Gegenbewegung, ab der eine 100x-Position liquidiert ist (1 % Margin abzüglich Wartungsmarge)


def fvg_signale(x: pd.DataFrame, min_luecke_atr: float, min_koerper_atr: float, trend: bool) -> list[dict]:
    o, hi, lo, c = (x[s].to_numpy() for s in ("open", "high", "low", "close"))
    atr, e50, e200 = x["atr"].to_numpy(), x["ema50"].to_numpy(), x["ema200"].to_numpy()
    signale = []
    for i in range(max(VORLAUF, 3), len(c)):
        a = atr[i - 3]  # ATR vor dem Muster
        if np.isnan(a):
            continue
        for r in (1, -1):
            if r > 0:
                unten, oben, koerper, stop = hi[i - 2], lo[i], c[i - 1] - o[i - 1], lo[i - 2]
            else:
                unten, oben, koerper, stop = hi[i], lo[i - 2], o[i - 1] - c[i - 1], hi[i - 2]
            if oben - unten <= 0 or oben - unten < min_luecke_atr * a or koerper < min_koerper_atr * a:
                continue
            if trend and not (r * (c[i] - e200[i]) > 0 and r * (e50[i] - e200[i]) > 0):
                continue
            signale.append({"idx": i, "richtung": r, "einstieg": (oben + unten) / 2, "stop": stop})
    return signale


def handeln(coin: str, x: pd.DataFrame, signale: list[dict], h, art: str, stunden: float, maker,
            durchlauf: float = 0.0) -> list[dict]:
    """Limit-Order je Lücke. Ausgeführt wird zum Limitkurs, wenn der Kurs ihn um mindestens `durchlauf`
    (Anteil) unterschreitet (Long) bzw. überschreitet (Short) – bei 0 reicht eine bloße Berührung. Dasselbe gilt
    für die Ziel-Orders."""
    o, hi, lo, c = (x[s].to_numpy() for s in ("open", "high", "low", "close"))
    atr, ts, n = x["atr"].to_numpy(), x["ts"].to_numpy(), len(x)
    frei_ab, trades = VORLAUF, []
    for s in signale:
        r, einstieg = s["richtung"], s["einstieg"]
        stop = s["stop"] * (1 - r * h.stop_puffer)
        schwelle = einstieg * (1 - r * durchlauf)
        for j in range(max(s["idx"] + 1, frei_ab), min(s["idx"] + 1 + GUELTIG, n)):
            gegen = lo[j] if r > 0 else hi[j]
            if r * (gegen - schwelle) > 0:
                continue
            if r * (o[j] - stop) <= 0:  # Kurslücke über den Stop hinweg: Lücke ungültig
                break
            t = simuliere(o, hi, lo, c, atr, j, r, stop, h, art, stunden, maker, einstieg=einstieg,
                          durchlauf=durchlauf)
            if t is not None:
                frei_ab = t["ausstieg_idx"] + 1
                t.update({"coin": coin, "richtung": "long" if r > 0 else "short",
                          "einstieg_zeit": pd.Timestamp(int(ts[j]), unit="ms", tz="UTC"),
                          "ausstieg_zeit": pd.Timestamp(int(ts[t["ausstieg_idx"]]), unit="ms", tz="UTC"),
                          "wartezeit_kerzen": j - s["idx"]})
                trades.append(t)
            break
    return trades


def mit_100x(t: pd.DataFrame) -> pd.DataFrame:
    """Dieselben Trades mit 100x statt 10x: Ergebnis ×10, aber Totalverlust der Margin, sobald die Gegenbewegung
    zwischendurch die Liquidationsgrenze erreicht hat."""
    t = t.copy()
    liquidiert = t["mae_pct"] >= LIQ_100X
    t["marge_netto_pct"] = np.where(liquidiert, -100.0, np.maximum(-100.0, t["kurs_netto_pct"] * 100))
    t["marge_brutto_pct"] = np.where(liquidiert, -100.0, np.maximum(-100.0, t["marge_brutto_pct"] * 10))
    t["liquidiert"] = liquidiert
    return t


def daten_laden(bar: str, tage: int, schritt: int, coins: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ende = int(ENDE.value // 1_000_000)
    start = ende - tage * 86_400_000 - VORLAUF * schritt
    inst = {c: f"{OKX_NAME.get(c, c)}-USDT-SWAP" for c in coins["coin"]}
    roh = okx.lade_alle(list(inst.values()), start, ende, cache=CACHE, bar=bar)
    daten = {}
    for coin, i in inst.items():
        df = roh[i].rename(columns={"vol_usdt": "vol_usd"})
        if len(df) <= VORLAUF + 100:
            continue
        x = indikatoren(df).join(atr_adx(df))
        x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
        x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()
        daten[coin] = x
    return daten


def kurz(t: pd.DataFrame) -> str:
    """Ø je Trade netto in Euro und Anteil Gewinner."""
    if t.empty:
        return "–"
    return f"{eur(t['marge_netto_pct'].mean() * MARGE / 100)} ({de(100 * (t['marge_netto_pct'] > 0).mean(), 0)} %)"


FUELLUNG = [("bloße Berührung reicht (optimistisch)", 0.0),
            ("Kurs muss 0,05 % durch Einstiegs- und Zielkurs laufen (vorsichtig)", 0.0005)]


def zufall_signale(daten: dict[str, pd.DataFrame], signale: dict[str, list[dict]], seed: int = 7) -> dict:
    """Kontrolle: je echter Lücke eine Limit-Order an einer zufälligen Kerze mit zufälliger Richtung, aber gleicher
    Geometrie (Abstand Schlusskurs–Einstieg und Einstieg–Stop wie bei der Lücke)."""
    rng = np.random.default_rng(seed)
    aus = {}
    for coin, x in daten.items():
        c, z = x["close"].to_numpy(), []
        for s in signale[coin]:
            i, r = int(rng.integers(VORLAUF, len(c) - GUELTIG - 2)), (1 if rng.random() < 0.5 else -1)
            abst_ein = (c[s["idx"]] - s["einstieg"]) / c[s["idx"]] * s["richtung"]
            abst_stop = (s["einstieg"] - s["stop"]) / s["einstieg"] * s["richtung"]
            ein = c[i] * (1 - r * abst_ein)
            z.append({"idx": i, "richtung": r, "einstieg": ein, "stop": ein * (1 - r * abst_stop)})
        aus[coin] = sorted(z, key=lambda q: q["idx"])
    return aus


def zeile(name: str, art: str, daten, signale, coins, stunden, durchlauf, mitte, uebersicht, kopf: dict) -> list[str]:
    slip = dict(zip(coins["coin"], coins["slippage"]))
    rang = {c: i for i, c in enumerate(coins["coin"])}
    trades = []
    for coin, x in daten.items():
        trades += handeln(coin, x, signale[coin], replace(BASIS, slippage=slip[coin]), art, stunden, MAKER, durchlauf)
    t = pd.DataFrame(trades)
    if t.empty:
        return [name, art, "0", *["–"] * 8]
    t["rang"] = t["coin"].map(rang)
    t = t.sort_values(["einstieg_zeit", "rang"], kind="stable").reset_index(drop=True)
    t100 = mit_100x(t)
    k = kennzahlen(t)
    h1, h2 = t[t["einstieg_zeit"] < mitte], t[t["einstieg_zeit"] >= mitte]
    kk, kk100 = konto_mit_kapital(t, KAPITAL, MARGE), konto_mit_kapital(t100, KAPITAL, MARGE)
    in_r = (t["marge_brutto_pct"] / BASIS.hebel / t["stop_abstand_pct"]).mean()
    uebersicht.append({**kopf, "Variante": name, "Ausstieg": art, "Trades": len(t),
                       "netto_10x": t["marge_netto_pct"].mean() * MARGE / 100,
                       "brutto_10x": t["marge_brutto_pct"].mean() * MARGE / 100, "brutto_R": in_r,
                       "ki_unten": k["ki95_unten"] * MARGE / 100, "ki_oben": k["ki95_oben"] * MARGE / 100,
                       "h1": h1["marge_netto_pct"].mean() * MARGE / 100 if len(h1) else np.nan,
                       "h2": h2["marge_netto_pct"].mean() * MARGE / 100 if len(h2) else np.nan,
                       "treffer": 100 * (t["marge_netto_pct"] > 0).mean(), "stop_pct": t["stop_abstand_pct"].mean(),
                       "konto_10x": KAPITAL + kk["pnl"], "trades_konto_10x": kk["trades"],
                       "netto_100x": t100["marge_netto_pct"].mean() * MARGE / 100,
                       "liquidiert_100x": 100 * t100["liquidiert"].mean(), "konto_100x": KAPITAL + kk100["pnl"]})
    return [name, art, str(len(t)), kurz(t), f"{eur(k['ki95_unten'] * MARGE / 100)} … {eur(k['ki95_oben'] * MARGE / 100)}",
            f"{eur(t['marge_brutto_pct'].mean() * MARGE / 100)} ({de(in_r, 2)} R)", f"{kurz(h1)} / {kurz(h2)}",
            f"{eur(KAPITAL + kk['pnl'])} ({kk['trades']} Trades)" + (" – leer" if kk["tiefster_stand"] < MARGE else ""),
            f"{kurz(t100)}, liquidiert {de(100 * t100['liquidiert'].mean(), 0)} %; Konto "
            f"{eur(KAPITAL + kk100['pnl'])}" + (" – leer" if kk100["tiefster_stand"] < MARGE else "")]


KOPF = ["Variante", "Ausstieg", "Trades", "10x: Ø je Trade netto", "95-%-Bereich", "ohne Kosten", "1. / 2. Hälfte",
        "Konto 10.000 € (10x)", "100x: Ø je Trade, Liquidationen, Konto"]


def hyperliquid_daten() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Gegenprobe mit echten Hyperliquid-Kerzen (5 min, 16 Tage, gespeicherter Datensatz)."""
    kerzen = pd.read_csv(ERGEBNISSE / "zehnfach_5m_16d_2026-11-10_2200_kerzen.csv.gz")
    daten = {}
    for coin, df in kerzen.groupby("coin", sort=False):
        df = df.drop(columns="coin").reset_index(drop=True)
        x = indikatoren(df).join(atr_adx(df))
        x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
        x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()
        daten[coin] = x
    return daten, pd.read_csv(COINS)


def main() -> None:
    coins = pd.read_csv(COINS)
    md = ["# Fair Value Gaps (FVG) – Backtest", "",
          "Standard-Regeln nach ICT (die genauen Regeln aus dem Video sind nicht bekannt): Limit-Einstieg in der Mitte "
          "der Lücke (gültig 20 Kerzen), Stop hinter Kerze 1, Ziel 2R bzw. Hälfte bei +1R und Rest mit Trailing-Stop. "
          "31 Coins mit 10x auf Hyperliquid, OKX-Kurse, Hyperliquid-Kosten (Maker 0,015 % für Einstieg und Ziele, "
          "Taker 0,045 % + Slippage für Stops, Funding 0,00125 %/h). Konto 10.000 €, je Trade 1.000 € Margin. "
          "In Klammern: Anteil der Gewinner-Trades; R = Abstand Einstieg–Stop.", "",
          "Limit-Orders auf Kerzendaten: Ob eine Order bei bloßer Berührung wirklich ausgeführt wird, hängt von der "
          "Warteschlange im Orderbuch ab. Deshalb zwei Annahmen – „Berührung reicht“ ist zu optimistisch, „0,05 % "
          "durchlaufen“ eher vorsichtig. Die Wahrheit liegt dazwischen.", "",
          f"100x: dieselben Trades mit 1.000 € Margin × 100 = 100.000 € Position. Wer zwischendurch {de(LIQ_100X, 1)} % "
          "gegen sich hatte, ist liquidiert (−1.000 €). Slippage wie bei 10.000 € – bei 100.000 € wäre sie höher.", "",
          "Kontrolle „Zufall“: je echter Lücke eine Limit-Order an zufälliger Stelle mit zufälliger Richtung, aber "
          "gleichem Abstand zum Einstieg und gleichem Stop/Ziel.", ""]
    uebersicht: list[dict] = []
    abschnitte = [(name, lambda b=bar, t=tage, s=schritt: (daten_laden(b, t, s, coins), coins), tage, schritt)
                  for bar, name, tage, schritt in ZEITRAHMEN]
    abschnitte.append(("Gegenprobe Hyperliquid-Kerzen, 5 Minuten", hyperliquid_daten, 16, 300_000))
    for name, lader, tage, schritt in abschnitte:
        daten, cs = lader()
        stunden = schritt / 3_600_000
        erste = min(int(x["ts"].iat[VORLAUF]) for x in daten.values())
        letzte = max(int(x["ts"].iat[-1]) for x in daten.values())
        start, ende = pd.Timestamp(erste, unit="ms", tz="UTC"), pd.Timestamp(letzte, unit="ms", tz="UTC")
        mitte = start + (ende - start) / 2
        md += [f"## {name}: {start.tz_convert(BERLIN):%d.%m.%Y} – {ende.tz_convert(BERLIN):%d.%m.%Y}", ""]
        signale = {v: {coin: fvg_signale(x, *VARIANTEN[v]) for coin, x in daten.items()} for v in VARIANTEN}
        zufall = zufall_signale(daten, signale["alle Lücken"])
        for fuell_name, durchlauf in FUELLUNG:
            kopf = {"Zeitrahmen": name, "Füllung": fuell_name}
            zeilen = [zeile(v, art, daten, signale[v], cs, stunden, durchlauf, mitte, uebersicht, kopf)
                      for v in VARIANTEN for art in AUSSTIEGE]
            zeilen.append(zeile("Kontrolle: Zufall, gleiche Geometrie", "fest", daten, zufall, cs, stunden, durchlauf,
                                mitte, uebersicht, kopf))
            md += [f"### Füllung: {fuell_name}", "", tabelle(KOPF, zeilen), ""]
    pd.DataFrame(uebersicht).to_csv(ERGEBNISSE / "fvg_2026-11-10_uebersicht.csv", index=False)
    text = "\n".join(md) + "\n"
    (ERGEBNISSE / "fvg_2026-11-10.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
