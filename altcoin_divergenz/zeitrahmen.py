"""Divergenzen auf einem frei wählbaren Zeitrahmen (Standard: 5-Minuten-Chart), Hyperliquid, 100 Altcoins.

  python3 -m altcoin_divergenz zeitrahmen                       # 5-Minuten-Daten aus Cache bzw. Hyperliquid
  python3 -m altcoin_divergenz zeitrahmen --kerzen <datei>      # gespeicherten Datensatz (1m oder 5m) auswerten

Dieselben Regeln wie zuvor, gezählt in Kerzen: Pivots 5 links / 3 rechts, Pivot-Abstand 5–60 (einfach) bzw.
8–60 Kerzen (Musterbuch), Stop am Pivot, Ziel 2 × Stop, Zeitstopp nach 60 Kerzen (auf 5 Minuten = 5 Stunden).
Konto 10.000 €, je Trade 1.000 € Margin mit 10x Hebel.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import hyperliquid as hl
from .backtest import kennzahlen, konto_mit_kapital, trades_fuer_coin, zufallstrades
from .muster import Muster, musterdivergenzen
from .musterbuch import BASIS, BERLIN, EURUSD, HEBEL, KAPITAL, MARGE, de, eur, tabelle, zeit
from .strategie import Parameter, divergenzen, indikatoren

ORDNER = Path(__file__).resolve().parent
ERGEBNISSE = ORDNER / "ergebnisse"
CACHE = ORDNER / "cache"
VORLAUF = 150  # Kerzen zum Einschwingen von RSI und MACD
NAMEN = {60_000: "1-Minuten", 300_000: "5-Minuten", 900_000: "15-Minuten", 3_600_000: "1-Stunden"}
SIGNALARTEN = ["Einfache klare Divergenz", "Musterbuch nahe 100 % (≥ 6/7)", "Musterbuch 100 % (7/7)"]


def laden(kerzen: Path | None, intervall: str, tage: float):
    if kerzen:
        alle = pd.read_csv(kerzen)
        coins = pd.read_csv(kerzen.with_name(kerzen.name.replace("_kerzen.csv.gz", "_coins.csv")))
        daten = {c: g.drop(columns="coin").reset_index(drop=True) for c, g in alle.groupby("coin", sort=False)}
        return daten, coins
    schritt = hl.SCHRITT_MS[intervall]
    fenster = CACHE / f"hl{intervall}_fenster.json"
    coins_datei = CACHE / f"hl{intervall}_coins.csv"
    if fenster.exists():
        f = json.loads(fenster.read_text())
        coins = pd.read_csv(coins_datei)
    else:
        ende = int(time.time() * 1000) // schritt * schritt
        f = {"start_ms": ende - (int(tage * 86_400_000 / schritt) + VORLAUF) * schritt, "ende_ms": ende}
        coins = hl.top_altcoins(100)
        coins["slippage"] = [hl.slippage(c, MARGE * HEBEL * EURUSD) for c in coins["coin"]]
        CACHE.mkdir(parents=True, exist_ok=True)
        coins.to_csv(coins_datei, index=False)
        fenster.write_text(json.dumps(f))
    daten = hl.lade_alle(coins["coin"].tolist(), f["start_ms"], f["ende_ms"], CACHE, intervall)
    return daten, coins


def signale(daten: dict[str, pd.DataFrame]) -> tuple[dict, dict]:
    """Je Coin: Indikatoren und die drei Signalarten (nur Signale im Testfenster)."""
    ind, sig = {}, {}
    for coin, df in daten.items():
        if len(df) <= VORLAUF + 10:
            continue
        ind[coin] = indikatoren(df)
        einfach = [s for s in divergenzen(ind[coin], Parameter()) if s["signal_idx"] >= VORLAUF]
        muster = [s for s in musterdivergenzen(ind[coin], Muster()) if s["signal_idx"] >= VORLAUF]
        sig[coin] = {SIGNALARTEN[0]: einfach,
                     SIGNALARTEN[1]: [s for s in muster if s["erfuellt"] >= 6],
                     SIGNALARTEN[2]: [s for s in muster if s["erfuellt"] == 7]}
    return ind, sig


def handeln(ind, sig, coins, art: str, auswahl: set[str], h=BASIS, echte_slippage: bool = True) -> pd.DataFrame:
    rang = {c: i for i, c in enumerate(coins["coin"])}
    slip = dict(zip(coins["coin"], coins["slippage"]))
    trades = []
    for coin in ind:
        if coin in auswahl:
            hc = replace(h, slippage=slip[coin]) if echte_slippage else h
            trades += trades_fuer_coin(coin, ind[coin], sig[coin][art], VORLAUF, hc)
    t = pd.DataFrame(trades)
    if t.empty:
        return t
    t["rang"] = t["coin"].map(rang)  # gleichzeitige Signale: umsatzstärkerer Coin zuerst
    return t.sort_values(["einstieg_zeit", "rang"], kind="stable").reset_index(drop=True)


def kurz(t: pd.DataFrame, spalte: str = "marge_netto_pct") -> str:
    """Ø je Trade in Euro und Anteil Gewinner."""
    return f"{eur(t[spalte].mean() * MARGE / 100)} ({de(100 * (t[spalte] > 0).mean(), 0)} %)"


def zeile(name: str, t: pd.DataFrame) -> list[str]:
    if t.empty:
        return [name] + ["0"] + ["–"] * 7
    k, kb = kennzahlen(t), kennzahlen(t, "marge_brutto_pct")
    kk = konto_mit_kapital(t, KAPITAL, MARGE)
    pos = int((t["marge_netto_pct"] > 0).sum())
    return [name, f"{len(t)} / {kk['trades']}", f"{pos} ({de(100 * pos / len(t), 0)} %)",
            f"{eur(k['erwartung_pct'] * MARGE / 100)} ({eur(k['ki95_unten'] * MARGE / 100)} … "
            f"{eur(k['ki95_oben'] * MARGE / 100)})",
            eur(kb["erwartung_pct"] * MARGE / 100), de(k["profit_faktor"]),
            eur(t["marge_netto_pct"].sum() * MARGE / 100),
            eur(KAPITAL + kk["pnl"]) + (" – keine Margin mehr frei" if kk["tiefster_stand"] < MARGE else "")]


KOPF = ["", "Trades (Signale / im Konto)", "mit Gewinn", "Ø je Trade netto (95-%-Bereich)", "Ø ohne Kosten",
        "Profit-Faktor", "Summe aller Signale", "Konto 10.000 € am Ende"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kerzen", type=Path, help="gespeicherter Datensatz (…_kerzen.csv.gz)")
    ap.add_argument("--intervall", default="5m", choices=list(hl.SCHRITT_MS))
    ap.add_argument("--tage", type=float, default=3.5)
    ap.add_argument("--speichern", action="store_true", help="Datensatz für Wiederholungen ablegen")
    a = ap.parse_args(argv)

    daten, coins = laden(a.kerzen, a.intervall, a.tage)
    erstes = next(iter(daten.values()))
    schritt = int(np.median(np.diff(erstes["ts"].to_numpy())))
    name = NAMEN.get(schritt, f"{schritt // 60_000}-Minuten")
    ende_ms = max(int(df["ts"].max()) for df in daten.values()) + schritt
    start_ms = int(erstes["ts"].min()) + VORLAUF * schritt
    kuerzel = {60_000: "1m", 300_000: "5m"}.get(schritt, f"{schritt // 60_000}m")
    stempel = (f"zeitrahmen_{kuerzel}_" + pd.Timestamp(ende_ms, unit="ms", tz="UTC").tz_convert(BERLIN)
               .strftime("%Y-%m-%d_%H%M"))
    ERGEBNISSE.mkdir(exist_ok=True)
    if a.speichern and not a.kerzen:
        pd.concat([df.assign(coin=c) for c, df in daten.items()]).round(10).to_csv(
            ERGEBNISSE / f"{stempel}_kerzen.csv.gz", index=False)
        coins.to_csv(ERGEBNISSE / f"{stempel}_coins.csv", index=False)

    ind, sig = signale(daten)
    alle = set(ind)
    zehnfach = set(coins.loc[coins["max_hebel"] >= HEBEL, "coin"]) & alle
    slip = coins.set_index("coin")["slippage"]
    tage = (ende_ms - start_ms) / 86_400_000
    start, ende = pd.Timestamp(start_ms, unit="ms", tz="UTC"), pd.Timestamp(ende_ms, unit="ms", tz="UTC")

    md = [f"# Divergenzen auf dem {name}-Chart (Hyperliquid)", "",
          f"Zeitraum: {zeit(start)} – {zeit(ende)} Uhr (MEZ), {de(tage, 1)} Tage, {name}-Kerzen. {len(alle)} Altcoins "
          f"(Top 100 nach 24-h-Umsatz ohne BTC, ETH, PAXG) laufend parallel geprüft, davon {len(zehnfach)} mit 10x Hebel "
          "auf Hyperliquid.", "",
          f"Konto {eur(KAPITAL)}, je Trade {eur(MARGE)} Margin × {de(HEBEL, 0)} = {eur(MARGE * HEBEL)} Position, "
          "höchstens so viele Trades gleichzeitig, wie freie Margin da ist. Taker-Gebühr 0,045 % je Seite, Slippage je "
          f"Coin aus dem Orderbuch (Median {de(slip.median() * 100, 3)} %, 10x-Coins "
          f"{de(slip[list(zehnfach)].median() * 100, 3)} %).", "",
          "Regeln in Kerzen: Pivot 5 links / 3 rechts, Stop 0,05 % hinter dem Pivot (0,2–3 %), Ziel 2 × Stop, "
          f"Zeitstopp nach 60 Kerzen ({de(60 * schritt / 3_600_000, 0)} h). Einfache klare Divergenz = Regeln aus dem "
          "ersten OKX-Test (RSI ≤ 35 / ≥ 65, 2 Punkte, MACD-Histogramm bestätigt, Einstieg nach Pivot-Bestätigung). "
          "Musterbuch = 7-Punkte-Checkliste plus Schlusskurs-Auslöser (siehe muster.py).", ""]

    md += ["## Ergebnis", "", tabelle(KOPF, [zeile(f"{art}, {u}", handeln(ind, sig, coins, art, auswahl))
                                          for art in SIGNALARTEN
                                          for u, auswahl in (("alle Coins", alle), ("nur 10x-Coins", zehnfach))]), ""]

    md += ["## Kosten und Haltedauer (alle Coins)", ""]
    zeilen = []
    for art in SIGNALARTEN:
        t = handeln(ind, sig, coins, art, alle)
        if t.empty:
            continue
        risiko = t["stop_abstand_pct"].mean() / 100 * MARGE * HEBEL
        kosten = (2 * BASIS.gebuehr + 2 * t["coin"].map(slip).mean()) * MARGE * HEBEL
        zeilen.append([art, de(t["stop_abstand_pct"].mean()) + " %", eur(risiko), eur(kosten),
                       de(100 * kosten / risiko, 0) + " %", de(t["minuten"].mean() * schritt / 60_000, 0) + " min",
                       ", ".join(f"{g} {n}" for g, n in t["grund"].value_counts().items())])
    md += [tabelle(["", "Ø Stop-Abstand", "Ø Risiko je Trade", "Ø Kosten je Trade", "Kosten in % des Risikos",
                    "Ø Haltedauer", "Ausstiege"], zeilen), ""]

    md += ["## Gegenproben (alle Coins, Ø je Trade netto, Anteil Gewinner)", ""]
    rng = np.random.default_rng(42)
    ab = {c: VORLAUF for c in ind}
    zeilen = []
    for art in SIGNALARTEN:
        t = handeln(ind, sig, coins, art, alle)
        if t.empty:
            continue
        hz = replace(BASIS, slippage=float(t["coin"].map(slip).mean()))
        zufall = np.array([zufallstrades(ind, ab, t, hz, rng)["marge_netto_pct"].mean() for _ in range(100)])
        zeilen.append([art, kurz(t), kurz(t, "marge_brutto_pct"),
                       kurz(handeln(ind, sig, coins, art, alle, replace(BASIS, umkehr="spiegel"))),
                       kurz(handeln(ind, sig, coins, art, alle, replace(BASIS, umkehr="gleich"))),
                       f"{eur(zufall.mean() * MARGE / 100)} (besser als Signal: {de(100 * np.mean(zufall > t['marge_netto_pct'].mean()), 0)} %)"])
    md += [tabelle(["", "Original", "ohne Kosten", "Umkehr Spiegel", "Umkehr gleiche Regeln",
                    "Zufall (100 Läufe)"], zeilen), ""]

    md += ["## Konto je Tag (alle Coins)", ""]
    zeilen = []
    for art in SIGNALARTEN:
        t = handeln(ind, sig, coins, art, alle)
        if t.empty:
            continue
        g = konto_mit_kapital(t, KAPITAL, MARGE)["genommen"]
        tag = g["ausstieg_zeit"].dt.tz_convert(BERLIN).dt.strftime("%d.%m.")
        proto = (g["marge_netto_pct"] / 100 * MARGE).groupby(tag, sort=False).agg(["count", "sum"])
        zeilen.append([art] + [f"{d}: {eur(r['sum'])} ({int(r['count'])})" for d, r in proto.iterrows()])
    breite = max(len(z) for z in zeilen)
    md += [tabelle(["", *["Tag (Trades)"] * (breite - 1)], [z + [""] * (breite - len(z)) for z in zeilen]), ""]

    t = handeln(ind, sig, coins, SIGNALARTEN[2], alle)
    if not t.empty:
        genommen = set(zip(*[konto_mit_kapital(t, KAPITAL, MARGE)["genommen"][s] for s in ("coin", "einstieg_zeit")]))
        md += ["## Alle Musterbuch-100-%-Trades (alle Coins)", ""]
        md += [tabelle(["Coin", "Richtung", "Einstieg", "Kurs inkl. Slippage", "Stop", "Ziel", "Ausstieg", "Zeit",
                        "Kurs Δ", "Ergebnis netto", "im Konto"],
                       [[r.coin, r.richtung, zeit(r.einstieg_zeit), f"{r.einstieg:.6g}", f"{r.stop:.6g}", f"{r.ziel:.6g}",
                         r.grund, zeit(r.ausstieg_zeit), de(r.kurs_brutto_pct) + " %",
                         eur(r.marge_netto_pct * MARGE / 100),
                         "ja" if (r.coin, r.einstieg_zeit) in genommen else "keine Margin frei"]
                        for r in t.itertuples()]), ""]
    alle_trades = []
    for art in SIGNALARTEN:
        x = handeln(ind, sig, coins, art, alle)
        if not x.empty:
            alle_trades.append(x.assign(signalart=art))
    if alle_trades:
        aus = pd.concat(alle_trades)
        for s in ("signal_zeit", "einstieg_zeit", "ausstieg_zeit"):
            aus[s] = aus[s].dt.tz_convert(BERLIN).dt.strftime("%Y-%m-%d %H:%M")
        aus["ergebnis_eur"] = aus["marge_netto_pct"] * MARGE / 100
        aus["minuten"] = aus["minuten"] * schritt // 60_000  # simuliere zählt Kerzen
        aus.drop(columns=["einstieg_idx", "ausstieg_idx"]).to_csv(ERGEBNISSE / f"{stempel}_trades.csv", index=False)

    text = "\n".join(md) + "\n"
    (ERGEBNISSE / f"{stempel}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
