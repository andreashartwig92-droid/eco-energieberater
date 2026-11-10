"""Nur ETH: alle bisherigen Strategien plus eine Mustersuche nach Art quantitativer Fonds.

  python3 -m altcoin_divergenz eth

ETH-Perpetual, Kurse von OKX (5 min: 6 Monate, 15 min: 1 Jahr, 1 h: 3 Jahre), Kosten wie auf Hyperliquid
(Taker 0,045 %, Maker 0,015 %, Slippage aus dem ETH-Orderbuch, Funding 0,00125 %/h). Konto 10.000 €, je Trade
1.000 € Margin mit 10x (ETH erlaubt auf Hyperliquid bis 25x). Da es nur einen Markt gibt, ist höchstens eine
Position gleichzeitig offen.

Teil 1 – bisherige Strategien auf ETH: Divergenzen (regulär, 100 % Musterbuch, versteckt im Trend, Kontrolle) mit
festem Ziel und Teilverkauf, Fair Value Gaps (alle Lücken, Standard, Standard + Trend) mit vorsichtiger Ausführung.

Teil 2 – Mustersuche: einfache Merkmale (Renditen der letzten Kerzen, RSI, Abstand zur EMA 200, Volumen,
Kerzenspanne, Tageszeit) werden auf ihre Vorhersagekraft für die nächsten 1, 4 und 12 Kerzen geprüft – getrennt in
der ersten und zweiten Hälfte. Danach werden alle Merkmale zu einem linearen Modell kombiniert, das nur mit der
ersten Hälfte geschätzt und nur in der zweiten Hälfte gehandelt wird.
"""
from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from . import fvg, okx
from .backtest import kennzahlen, konto_mit_kapital
from .merkmale import atr_adx
from .muster import Muster, musterdivergenzen, trendsignale
from .musterbuch import BASIS, KAPITAL, MARGE, de, eur, tabelle
from .strategie import indikatoren
from .trend import BERLIN, CACHE, ENDE, ERGEBNISSE, FUNDING_JE_STUNDE, MAKER, VORLAUF
from .trend import handeln as trend_handeln

INST = "ETH-USDT-SWAP"
ZEITRAHMEN = [("5m", "5 Minuten", 183, 300_000), ("15m", "15 Minuten", 365, 900_000),
              ("1H", "1 Stunde", 1095, 3_600_000)]


def laden(bar: str, tage: int, schritt: int) -> pd.DataFrame:
    ende = int(ENDE.value // 1_000_000)
    df = okx.lade_alle([INST], ende - tage * 86_400_000 - VORLAUF * schritt, ende, cache=CACHE, bar=bar)[INST]
    df = df.rename(columns={"vol_usdt": "vol_usd"})
    x = indikatoren(df).join(atr_adx(df))
    x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
    x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()
    return x


def handel_eth() -> object:
    info = json.loads((CACHE / "eth_hyperliquid.json").read_text())
    # ETH: maximal 25x -> Wartungsmarge 2 % (Hälfte der Anfangsmarge bei Höchsthebel)
    return replace(BASIS, slippage=info["slippage"], wartungsmarge=1 / (2 * info["max_hebel"])), info


def bewerten(name: str, trades: list[dict], mitte: pd.Timestamp) -> list[str]:
    t = pd.DataFrame(trades)
    if t.empty:
        return [name, "0", *["–"] * 5]
    k = kennzahlen(t)
    h1, h2 = t[t["einstieg_zeit"] < mitte], t[t["einstieg_zeit"] >= mitte]
    kk = konto_mit_kapital(t.sort_values("einstieg_zeit", kind="stable"), KAPITAL, MARGE)

    def kurz(x: pd.DataFrame) -> str:
        if x.empty:
            return "–"
        return f"{eur(x['marge_netto_pct'].mean() * MARGE / 100)} ({de(100 * (x['marge_netto_pct'] > 0).mean(), 0)} %)"
    return [name, str(len(t)), kurz(t), f"{eur(k['ki95_unten'] * MARGE / 100)} … {eur(k['ki95_oben'] * MARGE / 100)}",
            eur(t["marge_brutto_pct"].mean() * MARGE / 100), f"{kurz(h1)} / {kurz(h2)}",
            eur(KAPITAL + kk["pnl"]) + (" – leer" if kk["tiefster_stand"] < MARGE else "")]


def strategien(x: pd.DataFrame, h, stunden: float, mitte: pd.Timestamp) -> list[list[str]]:
    m = Muster()
    regulaer = [s for s in musterdivergenzen(x, m) if s["signal_idx"] >= VORLAUF]
    divergenz = {
        "Divergenz regulär (alle)": regulaer,
        "Divergenz 100 % Musterbuch": [s for s in regulaer if s["erfuellt"] == 7],
        "Divergenz versteckt im Trend": [s for s in trendsignale(x, m, True) if s["signal_idx"] >= VORLAUF],
        "Kontrolle: Rücksetzer im Trend ohne RSI": [s for s in trendsignale(x, m, False) if s["signal_idx"] >= VORLAUF],
    }
    zeilen = []
    for name, sig in divergenz.items():
        for art in ("fest", "Halb"):
            zeilen.append(bewerten(f"{name}, {art}", trend_handeln("ETH", x, sig, h, art, stunden), mitte))
    for name, (luecke, koerper, trend) in fvg.VARIANTEN.items():
        sig = fvg.fvg_signale(x, luecke, koerper, trend)
        zeilen.append(bewerten(f"FVG {name}, fest (vorsichtige Ausführung)",
                               fvg.handeln("ETH", x, sig, h, "fest", stunden, MAKER, 0.0005), mitte))
    return zeilen


# ---------------------------------------------------------------- Mustersuche

MERKMALE = ["Rendite letzte Kerze", "Rendite letzte 4 Kerzen", "Rendite letzte 12 Kerzen", "Rendite letzte 48 Kerzen",
            "RSI 14", "Abstand zur EMA 200", "Volumen / Ø 20", "Kerzenspanne / ATR"]
HORIZONTE = [1, 4, 12]


def merkmal_tabelle(x: pd.DataFrame) -> pd.DataFrame:
    c = x["close"]
    f = pd.DataFrame(index=x.index)
    f["Rendite letzte Kerze"] = c.pct_change()
    f["Rendite letzte 4 Kerzen"] = c.pct_change(4)
    f["Rendite letzte 12 Kerzen"] = c.pct_change(12)
    f["Rendite letzte 48 Kerzen"] = c.pct_change(48)
    f["RSI 14"] = x["rsi"]
    f["Abstand zur EMA 200"] = c / x["ema200"] - 1
    f["Volumen / Ø 20"] = x["vol_usd"] / x["vol_usd"].rolling(20).mean().shift(1)
    f["Kerzenspanne / ATR"] = (x["high"] - x["low"]) / x["atr"].shift(1)
    o = x["open"]
    for hz in HORIZONTE:  # Einstieg zur nächsten Eröffnung, Ausstieg hz Kerzen später zur Eröffnung
        f[f"ziel_{hz}"] = o.shift(-(1 + hz)) / o.shift(-1) - 1
    f["stunde"] = pd.to_datetime(x["ts"], unit="ms", utc=True).dt.tz_convert(BERLIN).dt.hour
    return f.iloc[VORLAUF:].replace([np.inf, -np.inf], np.nan)


def rang_korrelation(a: pd.Series, b: pd.Series) -> float:
    ok = a.notna() & b.notna()
    return float(np.corrcoef(a[ok].rank(), b[ok].rank())[0, 1])


def mustersuche(f: pd.DataFrame, kosten: float) -> tuple[list[list[str]], list[str]]:
    """Je Merkmal und Horizont: Rangkorrelation (IC) in beiden Hälften und die Rendite je Trade, wenn man das oberste
    gegen das unterste Zehntel handelt (Richtung aus der ersten Hälfte)."""
    n = len(f)
    h1, h2 = f.iloc[: n // 2], f.iloc[n // 2:]
    zeilen = []
    for m in MERKMALE:
        for hz in HORIZONTE:
            ziel = f"ziel_{hz}"
            ic1, ic2 = rang_korrelation(h1[m], h1[ziel]), rang_korrelation(h2[m], h2[ziel])
            unten, oben = h1[m].quantile([0.1, 0.9])
            vorzeichen = 1 if ic1 > 0 else -1

            def je_trade(teil: pd.DataFrame) -> float:
                lang = teil.loc[teil[m] >= oben, ziel] * vorzeichen
                kurz = -teil.loc[teil[m] <= unten, ziel] * vorzeichen
                return float(pd.concat([lang, kurz]).mean())
            r1, r2 = je_trade(h1), je_trade(h2)
            haelt = np.sign(ic1) == np.sign(ic2) and r2 > 0
            zeilen.append([m, f"{hz}", de(ic1, 3), de(ic2, 3), de(r1 * 100, 3) + " %", de(r2 * 100, 3) + " %",
                           "ja" if haelt and r2 > kosten else ("hält, aber < Kosten" if haelt else "nein")])
    # Tageszeit: Ø Rendite der nächsten Kerze je Stunde, beide Hälften
    s1 = h1.groupby("stunde")["ziel_1"].mean()
    s2 = h2.groupby("stunde")["ziel_1"].mean()
    stunden = [f"{st:02d} Uhr ({de(s1[st] * 100, 3)} % / {de(s2[st] * 100, 3)} %)" for st in s1.index
               if np.sign(s1[st]) == np.sign(s2[st]) and min(abs(s1[st]), abs(s2[st])) > kosten]
    return zeilen, stunden


def modell(f: pd.DataFrame, hz: int, kosten: float, stunden_je_kerze: float, schwelle: float = 1.0) -> dict:
    """Alle Merkmale zu einer Vorhersage kombinieren (Ridge-Regression), nur mit der ersten Hälfte geschätzt.
    Gehandelt wird, wenn die vorhergesagte Rendite größer als `schwelle` × Kosten ist; Haltedauer hz Kerzen,
    eine Position gleichzeitig, Einstieg und Ausstieg zur Eröffnung."""
    d = f.dropna(subset=MERKMALE + [f"ziel_{hz}"]).copy()
    for st in range(24):
        d[f"h{st}"] = (d["stunde"] == st).astype(float)
    spalten = MERKMALE + [f"h{st}" for st in range(24)]
    n = len(d)
    h1, h2 = d.iloc[: n // 2], d.iloc[n // 2:]
    mu, sd = h1[spalten].mean(), h1[spalten].std().replace(0, 1)
    x1 = ((h1[spalten] - mu) / sd).to_numpy()
    y1 = h1[f"ziel_{hz}"].to_numpy()
    lam = 0.1 * len(x1)
    beta = np.linalg.solve(x1.T @ x1 + lam * np.eye(x1.shape[1]), x1.T @ (y1 - y1.mean()))

    def handeln(teil: pd.DataFrame) -> dict:
        p = y1.mean() + ((teil[spalten] - mu) / sd).to_numpy() @ beta
        y = teil[f"ziel_{hz}"].to_numpy()
        ergebnisse, i = [], 0
        while i < len(p):
            if abs(p[i]) > schwelle * kosten:
                r = np.sign(p[i])
                ergebnisse.append(r * y[i] - kosten - r * FUNDING_JE_STUNDE * hz * stunden_je_kerze)
                i += hz + 1
            else:
                i += 1
        e = np.array(ergebnisse)
        return {"trades": len(e), "je_trade": e.mean() if len(e) else np.nan,
                "treffer": (e > 0).mean() if len(e) else np.nan, "summe": e.sum() if len(e) else 0.0}
    return {"lernen": handeln(h1), "pruefen": handeln(h2)}


def main() -> None:
    h, info = handel_eth()
    kosten_taker = 2 * (h.gebuehr + h.slippage)
    md = ["# Nur ETH", "",
          f"ETH-Perpetual, OKX-Kurse, Hyperliquid-Kosten: Taker {de(h.gebuehr * 100, 3)} %, Maker "
          f"{de(MAKER * 100, 3)} %, Slippage aus dem ETH-Orderbuch {de(h.slippage * 100, 4)} % je Seite (für "
          f"10.000 €), Funding 0,00125 %/h. Hyperliquid erlaubt bei ETH bis {info['max_hebel']}x. Konto 10.000 €, "
          "je Trade 1.000 € Margin × 10, höchstens eine Position gleichzeitig. In Klammern: Anteil Gewinner.", ""]
    md_muster = ["# Teil 2: Mustersuche nach Art quantitativer Fonds", "",
                 f"Kosten für Ein- und Ausstieg als Market-Order: {de(kosten_taker * 100, 3)} % des Positionswerts. "
                 "IC = Rangkorrelation zwischen Merkmal und späterer Rendite (0 = kein Zusammenhang). „Je Trade“: "
                 "oberstes Zehntel kaufen, unterstes verkaufen (bzw. umgekehrt, je nach Vorzeichen in der 1. Hälfte), "
                 "Rendite je Trade vor Kosten. Nur was in der 2. Hälfte hält UND über den Kosten liegt, wäre handelbar.",
                 ""]
    for bar, name, tage, schritt in ZEITRAHMEN:
        x = laden(bar, tage, schritt)
        stunden = schritt / 3_600_000
        start = pd.Timestamp(int(x["ts"].iat[VORLAUF]), unit="ms", tz="UTC")
        mitte = start + (ENDE - start) / 2
        md += [f"## {name}: {start.tz_convert(BERLIN):%d.%m.%Y} – {ENDE.tz_convert(BERLIN):%d.%m.%Y} "
               f"(Mitte {mitte.tz_convert(BERLIN):%d.%m.%Y})", "",
               tabelle(["Strategie", "Trades", "Ø je Trade netto", "95-%-Bereich", "ohne Kosten", "1. / 2. Hälfte",
                        "Konto 10.000 €"], strategien(x, h, stunden, mitte)), ""]
        f = merkmal_tabelle(x)
        zeilen, gute_stunden = mustersuche(f, kosten_taker)
        md_muster += [f"## {name}", "",
                      tabelle(["Merkmal", "Horizont (Kerzen)", "IC 1. Hälfte", "IC 2. Hälfte", "je Trade 1. Hälfte",
                               "je Trade 2. Hälfte", "handelbar?"], zeilen), "",
                      "Tageszeiten, deren Ø Rendite der nächsten Kerze in beiden Hälften dasselbe Vorzeichen hat und "
                      "größer als die Kosten ist: " + (", ".join(gute_stunden) if gute_stunden else "keine") + ".", ""]
        modell_zeilen = []
        for hz in HORIZONTE:
            for schwelle in (1.0, 2.0):
                r = modell(f, hz, kosten_taker, stunden, schwelle)
                modell_zeilen.append([f"{hz}", f"{de(schwelle, 0)} × Kosten",
                                      *[f"{r[t]['trades']}: {de(r[t]['je_trade'] * 100, 3)} % "
                                        f"({de(100 * r[t]['treffer'], 0)} %), Summe {de(r[t]['summe'] * 100, 1)} %"
                                        if r[t]["trades"] else "0" for t in ("lernen", "pruefen")],
                                      eur(r["pruefen"]["je_trade"] * 10 * MARGE) if r["pruefen"]["trades"] else "–"])
        md_muster += ["Kombiniertes Modell (alle Merkmale + Tageszeit, Ridge-Regression, nur mit der 1. Hälfte "
                      "geschätzt). Je Trade nach Kosten in % des Positionswerts, in Klammern Treffer:", "",
                      tabelle(["Haltedauer (Kerzen)", "handeln ab", "1. Hälfte (gelernt)", "2. Hälfte (ungesehen)",
                               "2. Hälfte je Trade bei 10x / 1.000 € Margin"], modell_zeilen), ""]
    text = "\n".join(md + [""] + md_muster) + "\n"
    (ERGEBNISSE / "eth_2026-11-10.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
