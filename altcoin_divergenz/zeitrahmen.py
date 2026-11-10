"""Divergenzen auf einem frei wählbaren Zeitrahmen (Standard: 5-Minuten-Chart), Hyperliquid, 100 Altcoins.

  python3 -m altcoin_divergenz zeitrahmen                       # 5-Minuten-Daten aus Cache bzw. Hyperliquid
  python3 -m altcoin_divergenz zeitrahmen --kerzen <datei>      # gespeicherten Datensatz (1m oder 5m) auswerten
  python3 -m altcoin_divergenz zeitrahmen --name devisen --maerkte xyz:EUR,xyz:JPY,xyz:GBP --gebuehr 0.009
                                                                # eigene Märkte, z. B. die Devisenpaare (HIP-3)

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
NAMEN = {60_000: "1-Minuten", 300_000: "5-Minuten", 600_000: "10-Minuten", 900_000: "15-Minuten",
         3_600_000: "1-Stunden"}
SIGNALARTEN = ["Einfache klare Divergenz", "Musterbuch nahe 100 % (≥ 6/7)", "Musterbuch 100 % (7/7)"]


def laden(kerzen: Path | None, intervall: str, tage: float, maerkte: list[str] | None = None, name: str = ""):
    if kerzen:
        alle = pd.read_csv(kerzen)
        coins = pd.read_csv(kerzen.with_name(kerzen.name.replace("_kerzen.csv.gz", "_coins.csv")))
        daten = {c: g.drop(columns="coin").reset_index(drop=True) for c, g in alle.groupby("coin", sort=False)}
        return daten, coins
    schritt = hl.SCHRITT_MS[intervall]
    praefix = f"{name}_{intervall}_{tage:g}d" if name else f"hl{intervall}"
    fenster = CACHE / f"{praefix}_fenster.json"
    coins_datei = CACHE / f"{praefix}_coins.csv"
    if fenster.exists():
        f = json.loads(fenster.read_text())
        coins = pd.read_csv(coins_datei)
    else:
        ende = int(time.time() * 1000) // schritt * schritt
        f = {"start_ms": ende - (int(tage * 86_400_000 / schritt) + VORLAUF) * schritt, "ende_ms": ende}
        coins = hl.maerkte(maerkte) if maerkte else hl.top_altcoins(100)
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
    """Signale einer Art für die ausgewählten Märkte handeln, mit Slippage je Markt."""
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
    ap.add_argument("--maerkte", help="kommagetrennte Hyperliquid-Märkte statt der Top-100-Altcoins")
    ap.add_argument("--name", default="", help="Präfix für Cache und Ergebnisdateien (bei eigenen Märkten)")
    ap.add_argument("--gebuehr", type=float, help="Taker-Gebühr je Seite in Prozent (Standard 0,045)")
    ap.add_argument("--min-stop", type=float, help="Mindest-Stopabstand in Prozent (Standard 0,2)")
    a = ap.parse_args(argv)

    maerkte = a.maerkte.split(",") if a.maerkte else None
    h = replace(BASIS, gebuehr=a.gebuehr / 100) if a.gebuehr is not None else BASIS
    if a.min_stop is not None:
        h = replace(h, min_stop=a.min_stop / 100)
    daten, coins = laden(a.kerzen, a.intervall, a.tage, maerkte, a.name)
    erstes = next(iter(daten.values()))
    schritt = int(np.median(np.diff(erstes["ts"].to_numpy())))
    name = NAMEN.get(schritt, f"{schritt // 60_000}-Minuten")
    ende_ms = max(int(df["ts"].max()) for df in daten.values()) + schritt
    start_ms = int(erstes["ts"].min()) + VORLAUF * schritt
    kuerzel = {60_000: "1m", 300_000: "5m"}.get(schritt, f"{schritt // 60_000}m")
    datum = pd.Timestamp(ende_ms, unit="ms", tz="UTC").tz_convert(BERLIN).strftime("%Y-%m-%d_%H%M")
    stempel = f"{a.name}_{kuerzel}_{a.tage:g}d_{datum}" if a.name else f"zeitrahmen_{kuerzel}_{datum}"
    if a.min_stop is not None:
        stempel += f"_minstop{a.min_stop:g}"
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

    eigene = coins["coin"].str.contains(":").any() or len(alle) < 50
    if eigene:
        umfang = (f"Märkte: {', '.join(f'{c} (max. {m}x)' for c, m in zip(coins['coin'], coins['max_hebel']))}, "
                  "laufend parallel geprüft.")
        slip_text = (", ".join(f"{c} {de(v * 100, 3)} %" for c, v in slip.items()) if len(slip) <= 10
                     else f"Median {de(slip.median() * 100, 3)} %")
    else:
        umfang = (f"{len(alle)} Altcoins (Top 100 nach 24-h-Umsatz ohne BTC, ETH, PAXG) laufend parallel geprüft, "
                  f"davon {len(zehnfach)} mit 10x Hebel auf Hyperliquid.")
        slip_text = f"Median {de(slip.median() * 100, 3)} %, 10x-Coins {de(slip[list(zehnfach)].median() * 100, 3)} %"
    md = [f"# Divergenzen auf dem {name}-Chart (Hyperliquid)", "",
          f"Zeitraum: {zeit(start)} – {zeit(ende)} Uhr (MEZ), {de(tage, 1)} Tage, {name}-Kerzen. {umfang}", "",
          f"Konto {eur(KAPITAL)}, je Trade {eur(MARGE)} Margin × {de(HEBEL, 0)} = {eur(MARGE * HEBEL)} Position, "
          f"höchstens so viele Trades gleichzeitig, wie freie Margin da ist. Taker-Gebühr {de(h.gebuehr * 100, 4)} % "
          f"je Seite, Slippage je Markt aus dem Orderbuch für eine {eur(MARGE * HEBEL)}-Order ({slip_text}).", "",
          f"Regeln in Kerzen: Pivot 5 links / 3 rechts, Stop 0,05 % hinter dem Pivot ({de(h.min_stop * 100, 2)}–3 %), "
          "Ziel 2 × Stop, "
          f"Zeitstopp nach 60 Kerzen ({de(60 * schritt / 3_600_000, 0)} h). Einfache klare Divergenz = Regeln aus dem "
          "ersten OKX-Test (RSI ≤ 35 / ≥ 65, 2 Punkte, MACD-Histogramm bestätigt, Einstieg nach Pivot-Bestätigung). "
          "Musterbuch = 7-Punkte-Checkliste plus Schlusskurs-Auslöser (siehe muster.py).", ""]

    gruppen = [("alle Märkte" if eigene else "alle Coins", alle)]
    if zehnfach != alle:
        gruppen.append(("nur 10x-Coins", zehnfach))
    md += ["## Ergebnis", "", tabelle(KOPF, [zeile(f"{art}, {u}", handeln(ind, sig, coins, art, auswahl, h))
                                          for art in SIGNALARTEN for u, auswahl in gruppen]), ""]

    if len(alle) <= 10:
        md += ["## Je Markt (Ø je Trade netto, Anteil Gewinner)", "",
               "Wochenende = Samstag und Sonntag (MEZ); der echte Devisenmarkt ist dann geschlossen.", ""]
        zeilen = []
        for coin in coins["coin"]:
            z = [coin]
            for art in SIGNALARTEN:
                t = handeln(ind, sig, coins, art, {coin}, h)
                if t.empty:
                    z.append("–")
                    continue
                we = t["einstieg_zeit"].dt.tz_convert(BERLIN).dt.dayofweek >= 5
                z.append(f"{len(t)} Trades: {kurz(t)}" + (f"; davon Wochenende {int(we.sum())}: {kurz(t[we])}"
                                                          if we.any() else ""))
            zeilen.append(z)
        md += [tabelle(["Markt", *SIGNALARTEN], zeilen), ""]

    md += ["## Kosten und Haltedauer", ""]
    zeilen = []
    for art in SIGNALARTEN:
        t = handeln(ind, sig, coins, art, alle, h)
        if t.empty:
            continue
        risiko = t["stop_abstand_pct"].mean() / 100 * MARGE * HEBEL
        kosten = (2 * h.gebuehr + 2 * t["coin"].map(slip).mean()) * MARGE * HEBEL
        zeilen.append([art, de(t["stop_abstand_pct"].mean()) + " %", eur(risiko), eur(kosten),
                       de(100 * kosten / risiko, 0) + " %", de(t["minuten"].mean() * schritt / 60_000, 0) + " min",
                       ", ".join(f"{g} {n}" for g, n in t["grund"].value_counts().items())])
    md += [tabelle(["", "Ø Stop-Abstand", "Ø Risiko je Trade", "Ø Kosten je Trade", "Kosten in % des Risikos",
                    "Ø Haltedauer", "Ausstiege"], zeilen), ""]

    md += ["## Gegenproben (Ø je Trade netto, Anteil Gewinner)", ""]
    rng = np.random.default_rng(42)
    ab = {c: VORLAUF for c in ind}
    zeilen = []
    for art in SIGNALARTEN:
        t = handeln(ind, sig, coins, art, alle, h)
        if t.empty:
            continue
        hz = replace(h, slippage=float(t["coin"].map(slip).mean()))
        zufall = np.array([zufallstrades(ind, ab, t, hz, rng)["marge_netto_pct"].mean() for _ in range(100)])
        zeilen.append([art, kurz(t), kurz(t, "marge_brutto_pct"),
                       kurz(handeln(ind, sig, coins, art, alle, replace(h, umkehr="spiegel"))),
                       kurz(handeln(ind, sig, coins, art, alle, replace(h, umkehr="gleich"))),
                       f"{eur(zufall.mean() * MARGE / 100)} (besser als Signal: {de(100 * np.mean(zufall > t['marge_netto_pct'].mean()), 0)} %)"])
    md += [tabelle(["", "Original", "ohne Kosten", "Umkehr Spiegel", "Umkehr gleiche Regeln",
                    "Zufall (100 Läufe)"], zeilen), ""]

    md += ["## Konto je Tag (Ergebnis der im Konto gehandelten Trades, Anzahl in Klammern)", ""]
    spalten = {}
    for art in SIGNALARTEN:
        t = handeln(ind, sig, coins, art, alle, h)
        if t.empty:
            continue
        g = konto_mit_kapital(t, KAPITAL, MARGE)["genommen"]
        tag = g["ausstieg_zeit"].dt.tz_convert(BERLIN).dt.strftime("%d.%m. (%a)")
        spalten[art] = (g["marge_netto_pct"] / 100 * MARGE).groupby(tag, sort=False).agg(["count", "sum"])
    tage_liste = sorted({d for v in spalten.values() for d in v.index}, key=lambda d: (d[3:5], d[:2]))
    md += [tabelle(["Tag", *spalten], [[d, *[f"{eur(v.loc[d, 'sum'])} ({int(v.loc[d, 'count'])})" if d in v.index
                                              else "–" for v in spalten.values()]] for d in tage_liste]), ""]

    t = handeln(ind, sig, coins, SIGNALARTEN[2], alle, h)
    if not t.empty:
        genommen = set(zip(*[konto_mit_kapital(t, KAPITAL, MARGE)["genommen"][s] for s in ("coin", "einstieg_zeit")]))
        md += ["## Alle Musterbuch-100-%-Trades", ""]
        md += [tabelle(["Coin", "Richtung", "Einstieg", "Kurs inkl. Slippage", "Stop", "Ziel", "Ausstieg", "Zeit",
                        "Kurs Δ", "Ergebnis netto", "im Konto"],
                       [[r.coin, r.richtung, zeit(r.einstieg_zeit), f"{r.einstieg:.6g}", f"{r.stop:.6g}", f"{r.ziel:.6g}",
                         r.grund, zeit(r.ausstieg_zeit), de(r.kurs_brutto_pct) + " %",
                         eur(r.marge_netto_pct * MARGE / 100),
                         "ja" if (r.coin, r.einstieg_zeit) in genommen else "keine Margin frei"]
                        for r in t.itertuples()]), ""]
    alle_trades = []
    for art in SIGNALARTEN:
        x = handeln(ind, sig, coins, art, alle, h)
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
