"""Musterbuch-Divergenzen auf Hyperliquid: 100 Altcoins parallel, 1-Minuten-Chart,
10.000 € Kapital, je Trade 1.000 € Margin mit 10x Hebel (10.000 € Position).

  python3 -m altcoin_divergenz muster                      # Daten aus dem Cache bzw. von Hyperliquid
  python3 -m altcoin_divergenz muster --kerzen <datei>     # gespeicherten Datensatz auswerten
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import hyperliquid as hl
from .backtest import Handel, kennzahlen, konto_mit_kapital, trades_fuer_coin, zufallstrades
from .muster import KRITERIEN, Muster, musterdivergenzen
from .strategie import indikatoren

ORDNER = Path(__file__).resolve().parent
ERGEBNISSE = ORDNER / "ergebnisse"
CACHE = ORDNER / "cache"
BERLIN = ZoneInfo("Europe/Berlin")
KAPITAL, MARGE, HEBEL = 10_000.0, 1_000.0, 10.0
VORLAUF = 150  # Kerzen zum Einschwingen von RSI und MACD
EURUSD = 1.1214  # EZB-Referenzkurs 10.11.2026
# Hyperliquid, Gebührenstufe 0: Taker 0,045 %, Maker 0,015 %. Wartungsmarge bei 10x = 5 %.
BASIS = Handel(hebel=HEBEL, gebuehr=0.00045, slippage=0.0, wartungsmarge=0.05)


def de(x: float, n: int = 2) -> str:
    if x == float("inf"):
        return "∞"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def eur(x: float) -> str:
    return de(x, 0) + " €"


def zeit(ts: pd.Timestamp) -> str:
    return ts.tz_convert(BERLIN).strftime("%d.%m. %H:%M")


def tabelle(kopf: list[str], zeilen: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(kopf) + " |", "| " + " | ".join("---" for _ in kopf) + " |"]
                     + ["| " + " | ".join(z) + " |" for z in zeilen])


def laden(kerzen: Path | None) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, int, int]:
    if kerzen:
        alle = pd.read_csv(kerzen)
        coins = pd.read_csv(kerzen.with_name(kerzen.name.replace("_kerzen.csv.gz", "_coins.csv")))
        daten = {c: g.drop(columns="coin").reset_index(drop=True) for c, g in alle.groupby("coin", sort=False)}
        return daten, coins, int(alle["ts"].min()), int(alle["ts"].max()) + 60_000
    fenster_datei = CACHE / "hl_fenster.json"
    if fenster_datei.exists():
        f = json.loads(fenster_datei.read_text())
        coins = pd.read_csv(CACHE / "hl_coins.csv")
    else:
        ende = int(time.time() // 60 * 60 * 1000)
        f = {"start_ms": ende - 5000 * 60_000, "ende_ms": ende}
        coins = hl.top_altcoins(100)
        coins["slippage"] = [hl.slippage(c, MARGE * HEBEL * EURUSD) for c in coins["coin"]]
        CACHE.mkdir(parents=True, exist_ok=True)
        coins.to_csv(CACHE / "hl_coins.csv", index=False)
        fenster_datei.write_text(json.dumps(f))
    daten = hl.lade_alle(coins["coin"].tolist(), f["start_ms"], f["ende_ms"], CACHE)
    return daten, coins, f["start_ms"], f["ende_ms"]


def signale_alle(daten: dict[str, pd.DataFrame], m: Muster) -> tuple[dict, dict]:
    ind, sig = {}, {}
    for coin, df in daten.items():
        if len(df) <= VORLAUF + 10:
            continue
        ind[coin] = indikatoren(df)
        sig[coin] = [s for s in musterdivergenzen(ind[coin], m) if s["signal_idx"] >= VORLAUF]
    return ind, sig


def handeln(ind: dict, sig: dict, coins: pd.DataFrame, h: Handel, min_erfuellt: int, auswahl: set[str],
            echte_slippage: bool = True) -> pd.DataFrame:
    rang = {c: i for i, c in enumerate(coins["coin"])}
    slip = dict(zip(coins["coin"], coins["slippage"]))
    trades = []
    for coin in ind:
        if coin not in auswahl:
            continue
        hc = replace(h, slippage=slip[coin]) if echte_slippage else h
        trades += trades_fuer_coin(coin, ind[coin], [s for s in sig[coin] if s["erfuellt"] >= min_erfuellt],
                                   VORLAUF, hc)
    df = pd.DataFrame(trades)
    if df.empty:
        return df
    df["rang"] = df["coin"].map(rang)  # gleichzeitige Signale: umsatzstärkerer Coin zuerst
    return df.sort_values(["einstieg_zeit", "rang"]).reset_index(drop=True)


def ergebniszeile(name: str, t: pd.DataFrame) -> list[str]:
    if t.empty:
        return [name, "0", "–", "–", "–", "–", "–", "–", "–"]
    k = kennzahlen(t)
    kk = konto_mit_kapital(t, KAPITAL, MARGE)
    return [name, f"{len(t)} / {kk['trades']}", de(k["trefferquote_pct"], 0) + " %",
            f"{eur(k['erwartung_pct'] / 100 * MARGE)} ({eur(k['ki95_unten'] / 100 * MARGE)} … "
            f"{eur(k['ki95_oben'] / 100 * MARGE)})", de(k["profit_faktor"]),
            eur(kk["pnl"]), eur(kk["max_drawdown"]),
            eur(kk["tiefster_stand"]) + (" (keine Margin mehr frei)" if kk["tiefster_stand"] < MARGE else ""),
            eur(konto_mit_kapital(t, KAPITAL, MARGE, "marge_brutto_pct")["pnl"])]


KOPF = ["", "Trades (möglich / gehandelt*)", "Treffer", "Ø je Trade (95-%-Bereich)", "Profit-Faktor",
        "Konto netto", "größter Rückgang", "tiefster Kontostand", "Konto ohne Kosten"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kerzen", type=Path, help="gespeicherter Datensatz (…_kerzen.csv.gz)")
    ap.add_argument("--speichern", action="store_true", help="Datensatz für Wiederholungen ablegen")
    a = ap.parse_args(argv)

    daten, coins, start_ms, ende_ms = laden(a.kerzen)
    stempel = "hyperliquid_" + pd.Timestamp(ende_ms, unit="ms", tz="UTC").tz_convert(BERLIN).strftime("%Y-%m-%d_%H%M")
    ERGEBNISSE.mkdir(exist_ok=True)
    if a.speichern and not a.kerzen:
        pd.concat([df.assign(coin=c) for c, df in daten.items()]).round(10).to_csv(
            ERGEBNISSE / f"{stempel}_kerzen.csv.gz", index=False)
        coins.to_csv(ERGEBNISSE / f"{stempel}_coins.csv", index=False)

    m = Muster()
    ind, sig = signale_alle(daten, m)
    alle = set(ind)
    zehnfach = set(coins.loc[coins["max_hebel"] >= HEBEL, "coin"]) & alle
    h = BASIS

    t100 = handeln(ind, sig, coins, h, 7, alle)
    t100_10x = handeln(ind, sig, coins, h, 7, zehnfach)
    t6 = handeln(ind, sig, coins, h, 6, alle)
    t6_10x = handeln(ind, sig, coins, h, 6, zehnfach)

    start = pd.Timestamp(start_ms + VORLAUF * 60_000, unit="ms", tz="UTC")
    ende = pd.Timestamp(ende_ms, unit="ms", tz="UTC")
    tage = (ende - start).total_seconds() / 86400
    alle_sig = pd.DataFrame([dict(s, coin=c) for c, ss in sig.items() for s in ss])
    slip = coins.set_index("coin")["slippage"]

    md = ["# Musterbuch-Divergenzen auf Hyperliquid", ""]
    md += [f"Zeitraum: {zeit(start)} – {zeit(ende)} Uhr (MEZ), {de(tage, 1)} Tage = die gesamte 1-Minuten-Historie, "
           f"die Hyperliquid herausgibt. {len(alle)} Altcoins (Top 100 nach 24-h-Umsatz ohne BTC, ETH, PAXG) "
           f"laufend parallel geprüft; davon erlauben **nur {len(zehnfach)} Coins auf Hyperliquid 10x Hebel** "
           f"(übrige: {', '.join(f'{n}× {x}x' for x, n in coins['max_hebel'].value_counts().sort_index().items() if x < 10)}).",
           "",
           f"Konto {eur(KAPITAL)}, jeder Trade {eur(MARGE)} Margin × {de(HEBEL, 0)} = {eur(MARGE * HEBEL)} Position. "
           f"Damit laufen höchstens {int(KAPITAL // MARGE)} Trades gleichzeitig; ein Signal, für das keine freie Margin "
           "da ist, verfällt (*gehandelt). Kein Zinseszins, Verluste verringern die freie Margin.",
           "",
           f"Kosten: Hyperliquid-Taker-Gebühr {de(h.gebuehr * 100, 3)} % je Seite (Stufe 0). Slippage je Coin aus dem "
           f"aktuellen Orderbuch für eine {eur(MARGE * HEBEL)}-Market-Order (≈ {de(MARGE * HEBEL * EURUSD, 0)} USDC): "
           f"Median {de(slip.median() * 100, 3)} %, bei den 10x-Coins {de(slip[list(zehnfach)].median() * 100, 3)} %. "
           "Ziel-Orders (Take-Profit) ohne Slippage.",
           "",
           "Stop 0,05 % hinter dem zweiten Pivot (mind. 0,2 %, max. 3 %), Ziel 2 × Stop, Zeitstopp 60 min.", ""]

    md += ["## Wie oft gibt es ein Musterbuch-Signal?", ""]
    if not alle_sig.empty:
        verteilung = alle_sig["erfuellt"].value_counts().sort_index(ascending=False)
        md += [f"Divergenzen mit Auslöser in {de(tage, 1)} Tagen über alle {len(alle)} Coins: **{len(alle_sig)}**. "
               "Davon erfüllen von der 7-Punkte-Checkliste:", ""]
        md += [tabelle(["erfüllt", "Signale", "pro Tag"],
                       [[f"{k}/7" + (" (100 % Musterbuch)" if k == 7 else ""), str(v), de(v / tage, 1)]
                        for k, v in verteilung.items()]), ""]
        fehlt = pd.Series([f for x in alle_sig["fehlt"] for f in x.split(", ") if f]).value_counts()
        md += ["Am häufigsten verfehlt: " + ", ".join(f"{k} ({v}×)" for k, v in fehlt.head(4).items()) + ".", ""]

    md += ["## Ergebnis", "",
           f"Beträge in Euro bei {eur(MARGE)} Margin je Trade. „Ø je Trade“ zählt alle Signale, das Konto nur die "
           "mit freier Margin gehandelten.", ""]
    md += [tabelle(KOPF, [
        ergebniszeile("100 % Musterbuch, alle Coins (10x angenommen)", t100),
        ergebniszeile("100 % Musterbuch, nur 10x-Coins", t100_10x),
        ergebniszeile("≥ 6/7 (nahe 100 %), alle Coins", t6),
        ergebniszeile("≥ 6/7 (nahe 100 %), nur 10x-Coins", t6_10x),
    ]), ""]

    if not t100.empty:
        md += ["Ausstiege (100 %, alle Coins): " + ", ".join(f"{g} {n}" for g, n in t100["grund"].value_counts().items())
               + f". Ø Stop-Abstand {de(t100.stop_abstand_pct.mean())} % Kurs, Ø Haltedauer "
               f"{de(t100.minuten.mean(), 0)} min. Ø Kosten je Trade "
               f"{eur(((2 * h.gebuehr) + t100.coin.map(slip).mean() * 2) * MARGE * HEBEL)} "
               f"(Gebühren {eur(2 * h.gebuehr * MARGE * HEBEL)} + Slippage).", ""]
        kk = konto_mit_kapital(t100, KAPITAL, MARGE)
        g = kk["genommen"]
        tag = g["ausstieg_zeit"].dt.tz_convert(BERLIN).dt.strftime("%d.%m.")
        proto = (g["marge_netto_pct"] / 100 * MARGE).groupby(tag, sort=False).agg(["count", "sum"])
        md += ["Konto je Tag (100 %, alle Coins): " + ", ".join(f"{d} {eur(r['sum'])} ({int(r['count'])} Trades)"
                                                              for d, r in proto.iterrows()) + ".", ""]

        rng = np.random.default_rng(42)
        hz = replace(h, slippage=float(t100.coin.map(slip).mean()))
        ab = {c: VORLAUF for c in ind}
        zufall = np.array([zufallstrades(ind, ab, t100, hz, rng)["marge_netto_pct"].mean() for _ in range(200)])
        md += ["## Vergleich mit Zufall", "",
               f"200× gleich viele Trades mit denselben Stop-Abständen, Zielen und Kosten, aber zufälligem Coin, "
               f"Zeitpunkt und Richtung: Ø {eur(zufall.mean() / 100 * MARGE)} je Trade (90 % zwischen "
               f"{eur(np.percentile(zufall, 5) / 100 * MARGE)} und {eur(np.percentile(zufall, 95) / 100 * MARGE)}). "
               f"Musterbuch: {eur(t100.marge_netto_pct.mean() / 100 * MARGE)} – besser als "
               f"{de(100 * np.mean(zufall < t100.marge_netto_pct.mean()), 0)} % der Zufallsläufe.", ""]

        md += ["## Was die Kosten ausmachen (100 % Musterbuch, alle Coins)", ""]
        varianten = [
            ("Basis: Taker 0,045 %, Slippage aus Orderbuch", h, True),
            ("Gebührenstufe 2 (> 25 Mio. $ Volumen in 14 Tagen): Taker 0,035 %", replace(h, gebuehr=0.00035), True),
            ("nur Gebühren, keine Slippage", h, False),
            ("Maker 0,015 % auf beiden Seiten, keine Slippage (praktisch unerreichbar)", replace(h, gebuehr=0.00015), False),
            ("ganz ohne Kosten", replace(h, gebuehr=0.0), False),
            ("CRV 1,5 statt 2", replace(h, crv=1.5), True),
            ("CRV 3 statt 2", replace(h, crv=3.0), True),
        ]
        md += [tabelle(KOPF, [ergebniszeile(n, handeln(ind, sig, coins, hv, 7, alle, echt)) for n, hv, echt in varianten]),
               ""]

        md += ["## Alle 100-%-Musterbuch-Trades (alle Coins)", ""]
        genommen = set(zip(g["coin"], g["einstieg_zeit"]))
        zeilen = []
        for _, t in t100.iterrows():
            zeilen.append([t.coin, t.richtung, zeit(t.einstieg_zeit), f"{t.einstieg:.6g}", f"{t.stop:.6g}",
                           f"{t.ziel:.6g}", t.grund, zeit(t.ausstieg_zeit), de(t.kurs_brutto_pct) + " %",
                           eur(t.marge_netto_pct / 100 * MARGE),
                           "ja" if (t.coin, t.einstieg_zeit) in genommen else "keine Margin frei"])
        md += [tabelle(["Coin", "Richtung", "Einstieg", "Kurs inkl. Slippage", "Stop", "Ziel", "Ausstieg", "Zeit", "Kurs Δ",
                        "Ergebnis netto", "im Konto"], zeilen), ""]

        aus = t100.copy()
        for s in ("signal_zeit", "einstieg_zeit", "ausstieg_zeit"):
            aus[s] = aus[s].dt.tz_convert(BERLIN).dt.strftime("%Y-%m-%d %H:%M")
        aus["ergebnis_eur"] = aus["marge_netto_pct"] / 100 * MARGE
        aus.drop(columns=["einstieg_idx", "ausstieg_idx"]).to_csv(ERGEBNISSE / f"{stempel}_trades.csv", index=False)

    text = "\n".join(md) + "\n"
    (ERGEBNISSE / f"{stempel}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
