"""Divergenz-Konzept prüfen.

  python3 -m altcoin_divergenz live            # letzte 2 Stunden, 100 Altcoins, 1-Minuten-Chart
  python3 -m altcoin_divergenz robust --tage 7  # dieselben Regeln über 7 Tage (Stichprobe groß genug)
  python3 -m altcoin_divergenz live --kerzen ergebnisse/<datei>_kerzen.csv.gz   # gespeicherten Lauf wiederholen
"""
from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import okx
from .backtest import Handel, kennzahlen, konto, trades_fuer_coin, zufallstrades
from .strategie import Parameter, divergenzen, indikatoren

ORDNER = Path(__file__).resolve().parent
ERGEBNISSE = ORDNER / "ergebnisse"
CACHE = ORDNER / "cache"
BERLIN = ZoneInfo("Europe/Berlin")
VORLAUF = 300  # Kerzen zum Einschwingen von RSI und MACD vor dem Testfenster
KAPITAL = 1000.0


def de(x: float, n: int = 2) -> str:
    if x == float("inf"):
        return "∞"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def zeit(ts: pd.Timestamp) -> str:
    return ts.tz_convert(BERLIN).strftime("%d.%m. %H:%M")


def tabelle(kopf: list[str], zeilen: list[list[str]]) -> str:
    linien = ["| " + " | ".join(kopf) + " |", "| " + " | ".join("---" for _ in kopf) + " |"]
    linien += ["| " + " | ".join(z) + " |" for z in zeilen]
    return "\n".join(linien)


def lauf(daten: dict[str, pd.DataFrame], ab_ts: int, p: Parameter, h: Handel):
    """Signale suchen und handeln. Gibt Trades, Signalzahl und Start-Index je Coin zurück."""
    trades, ab, n_signale = [], {}, 0
    for coin, df in daten.items():
        if df.empty:
            continue
        i0 = int(np.searchsorted(df["ts"].to_numpy(), ab_ts))
        if i0 < 100 or i0 >= len(df):  # neu gelistet: zu wenig Vorlauf für die Indikatoren
            continue
        ab[coin] = i0
        ind = indikatoren(df, p)
        sig = divergenzen(ind, p)
        n_signale += sum(s["signal_idx"] >= i0 for s in sig)
        trades += trades_fuer_coin(coin, ind, sig, i0, h)
    return pd.DataFrame(trades), n_signale, ab


def zufallsvergleich(daten, ab, trades, h, wiederholungen) -> np.ndarray:
    rng = np.random.default_rng(42)
    return np.array([zufallstrades(daten, ab, trades, h, rng)["marge_netto_pct"].mean()
                     for _ in range(wiederholungen)])


def korrelation(daten: dict[str, pd.DataFrame], ab_ts: int) -> float:
    """Mittlere paarweise Korrelation der 1-Minuten-Renditen im Testfenster."""
    kurse = pd.DataFrame({c: df.set_index("ts")["close"] for c, df in daten.items() if not df.empty})
    r = kurse[kurse.index >= ab_ts].pct_change(fill_method=None).dropna(how="all")
    k = r.corr(min_periods=30).to_numpy()
    return float(np.nanmean(k[~np.eye(len(k), dtype=bool)]))


def kennzahl_zeilen(name: str, k: dict) -> list[str]:
    if not k.get("trades"):
        return [name, "0", "–", "–", "–", "–", "–"]
    return [name, str(k["trades"]), de(k["trefferquote_pct"], 0) + " %", de(k["schnitt_gewinn_pct"]) + " %",
            de(k["schnitt_verlust_pct"]) + " %", de(k["profit_faktor"]),
            f"{de(k['erwartung_pct'])} % ({de(k['ki95_unten'])} … {de(k['ki95_oben'])})"]


KOPF_KENNZAHLEN = ["", "Trades", "Treffer", "Ø Gewinn", "Ø Verlust", "Profit-Faktor",
                   "Ø je Trade (95-%-Bereich)"]


def bericht(titel: str, daten, coins: pd.DataFrame, ab_ts: int, ende_ms: int, p: Parameter, h: Handel,
            trades: pd.DataFrame, n_signale: int, ab: dict, wiederholungen: int,
            empfindlichkeit: list[tuple[str, Parameter, Handel]] | None, mit_tradeliste: bool) -> str:
    start = pd.Timestamp(ab_ts, unit="ms", tz="UTC")
    ende = pd.Timestamp(ende_ms, unit="ms", tz="UTC")
    md = [f"# {titel}", ""]
    md += [f"Zeitraum: {zeit(start)} – {zeit(ende)} Uhr (MEZ), 1-Minuten-Kerzen, OKX USDT-Perpetuals. "
           f"{len(ab)} von {len(coins)} Coins mit genug Vorlauf für die Indikatoren.", ""]
    md += ["Regeln: RSI 14, MACD 12/26/9. Klare Divergenz = Kurs neues Tief/Hoch, RSI mindestens "
           f"{de(p.rsi_abstand, 0)} Punkte gegenläufig, RSI beim ersten Pivot ≤ {de(p.rsi_ueberverkauft, 0)} "
           f"(Long) bzw. ≥ {de(p.rsi_ueberkauft, 0)} (Short), MACD-Histogramm bestätigt. Pivot bestätigt nach "
           f"{p.rechts} Kerzen, Einstieg zur nächsten Eröffnung. Stop 0,05 % hinter dem Pivot "
           f"(mind. {de(h.min_stop * 100, 1)} %, max. {de(h.max_stop * 100, 0)} %), Ziel {de(h.crv, 1)} × Stop, "
           f"Zeitstopp {h.max_halten} min. Hebel {de(h.hebel, 0)}x, Gebühr {de(h.gebuehr * 100, 2)} % je Seite, "
           f"Slippage {de(h.slippage * 100, 2)} % je Market-Order.", ""]
    md += [f"Klare Divergenz-Signale: **{n_signale}**, davon gehandelt: **{len(trades)}** "
           "(übrige: Coin hatte schon eine offene Position, Stop zu weit oder Signal in der letzten Minute).", ""]
    if trades.empty:
        return "\n".join(md + ["Keine Trades."])

    md += ["## Ergebnis je Trade (in % der eingesetzten Margin, 10x Hebel)", ""]
    zeilen = [kennzahl_zeilen("Alle (netto)", kennzahlen(trades))]
    for r in ("long", "short"):
        zeilen.append(kennzahl_zeilen(f"{r.capitalize()} (netto)", kennzahlen(trades[trades.richtung == r])))
    zeilen.append(kennzahl_zeilen("Alle ohne Kosten", kennzahlen(trades, "marge_brutto_pct")))
    md += [tabelle(KOPF_KENNZAHLEN, zeilen), ""]

    gruende = trades["grund"].value_counts()
    md += ["Ausstiege: " + ", ".join(f"{g} {n}" for g, n in gruende.items())
           + f". Ø Haltedauer {de(trades.minuten.mean(), 0)} min, Ø Stop-Abstand "
           f"{de(trades.stop_abstand_pct.mean())} % Kurs = {de(trades.stop_abstand_pct.mean() * h.hebel, 1)} % "
           f"Margin. Kosten je Trade (Gebühren + Slippage) ≈ "
           f"{de((2 * h.gebuehr + 2 * h.slippage) * h.hebel * 100, 1)} % der Margin.", ""]

    zufall = zufallsvergleich(daten, ab, trades, h, wiederholungen)
    besser = 100 * np.mean(zufall < trades["marge_netto_pct"].mean())
    md += ["## Vergleich mit Zufall", "",
           f"{wiederholungen}× gleich viele Trades mit denselben Stop-Abständen, Zielen, Kosten und Hebel – "
           "aber zufälliger Coin, Zeitpunkt und Richtung:", "",
           f"- Zufall: Ø {de(zufall.mean())} % je Trade (90 % der Läufe zwischen {de(np.percentile(zufall, 5))} "
           f"und {de(np.percentile(zufall, 95))} %)",
           f"- Divergenz-Strategie: Ø {de(trades['marge_netto_pct'].mean())} % je Trade – besser als "
           f"{de(besser, 0)} % der Zufallsläufe", ""]

    md += [f"## Was das mit {de(KAPITAL, 0)} € bedeutet", ""]
    varianten = [("10 € Margin je Coin (1.000 € / 100 Coins), Position 100 €", 10.0, None),
                 ("100 € Margin je Trade, Position 1.000 €, max. 10 gleichzeitig", 100.0, 10)]
    zeilen = []
    for name, marge, slots in varianten:
        k = konto(trades, marge, slots)
        k0 = konto(trades, marge, slots, "marge_brutto_pct")
        zeilen.append([name, str(k["trades"]), str(k["max_parallel"]), de(k["pnl_eur"]) + " €",
                       de(k0["pnl_eur"]) + " €", de(k["max_drawdown_eur"]) + " €"])
    md += [tabelle(["Aufteilung", "Trades", "max. gleichzeitig", "Ergebnis netto", "ohne Kosten",
                    "größter Rückgang"], zeilen), ""]
    md += [f"Mittlere Korrelation der 1-Minuten-Renditen zwischen den Coins im Zeitraum: "
           f"**{de(korrelation(daten, ab_ts))}**", ""]

    if empfindlichkeit:
        md += ["## Empfindlichkeit (netto)", ""]
        zeilen = []
        for name, p2, h2 in empfindlichkeit:
            t2, _, _ = lauf(daten, ab_ts, p2, h2)
            zeilen.append(kennzahl_zeilen(name, kennzahlen(t2)))
        md += [tabelle(KOPF_KENNZAHLEN, zeilen), ""]

    if mit_tradeliste:
        md += ["## Alle Trades", ""]
        zeilen = []
        for _, t in trades.sort_values("einstieg_zeit").iterrows():
            zeilen.append([t.coin, t.richtung, zeit(t.einstieg_zeit), f"{t.einstieg:.6g}", f"{t.stop:.6g}",
                           f"{t.ziel:.6g}", t.grund, zeit(t.ausstieg_zeit), de(t.kurs_brutto_pct) + " %",
                           de(t.marge_netto_pct, 1) + " %", de(t.marge_netto_pct) + " €"])
        md += [tabelle(["Coin", "Richtung", "Einstieg", "Kurs", "Stop", "Ziel", "Ausstieg", "Zeit",
                        "Kurs Δ", "Margin netto", "bei 100 € Margin"], zeilen), ""]
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modus", choices=["live", "robust"])
    ap.add_argument("--minuten", type=int, default=120, help="Testfenster für 'live' (Standard 120)")
    ap.add_argument("--tage", type=float, default=7, help="Testzeitraum für 'robust' (Standard 7)")
    ap.add_argument("--anzahl", type=int, default=100)
    ap.add_argument("--kerzen", type=Path, help="gespeicherte Kerzen statt OKX laden")
    a = ap.parse_args()

    p, h = Parameter(), Handel()
    minuten = a.minuten if a.modus == "live" else int(a.tage * 1440)
    ERGEBNISSE.mkdir(exist_ok=True)

    if a.kerzen:
        alle = pd.read_csv(a.kerzen)
        daten = {c: g.drop(columns="coin").reset_index(drop=True) for c, g in alle.groupby("coin", sort=False)}
        coins = pd.DataFrame({"coin": list(daten)})
        ende_ms = int(alle["ts"].max()) + 60_000
        stempel = a.kerzen.name.split("_kerzen")[0]
    else:
        ende_ms = int(time.time() // 60 * 60 * 1000)  # laufende Minute ausschließen
        coins = okx.top_altcoins(a.anzahl)
        start_ms = ende_ms - (minuten + VORLAUF) * 60_000
        print(f"Lade {len(coins)} Coins, {minuten + VORLAUF} Minuten …", flush=True)
        roh = okx.lade_alle(coins["inst_id"].tolist(), start_ms, ende_ms,
                            cache=CACHE if a.modus == "robust" else None)
        daten = {c: roh[i] for c, i in zip(coins["coin"], coins["inst_id"])}
        stempel = (f"{a.modus}_" + pd.Timestamp(ende_ms, unit="ms", tz="UTC").tz_convert(BERLIN)
                   .strftime("%Y-%m-%d_%H%M"))
        if a.modus == "live":
            pd.concat([df.assign(coin=c) for c, df in daten.items()]).to_csv(
                ERGEBNISSE / f"{stempel}_kerzen.csv.gz", index=False)
        coins.to_csv(ERGEBNISSE / f"{stempel}_coins.csv", index=False)

    ab_ts = ende_ms - minuten * 60_000
    trades, n_signale, ab = lauf(daten, ab_ts, p, h)
    if not trades.empty:
        aus = trades.copy()
        for s in ("signal_zeit", "einstieg_zeit", "ausstieg_zeit"):
            aus[s] = aus[s].dt.tz_convert(BERLIN).dt.strftime("%Y-%m-%d %H:%M")
        aus.drop(columns=["einstieg_idx", "ausstieg_idx"]).to_csv(ERGEBNISSE / f"{stempel}_trades.csv",
                                                                   index=False)

    empfindlichkeit = None
    if a.modus == "robust":
        empfindlichkeit = [
            ("Basis (CRV 2)", p, h),
            ("CRV 1", p, replace(h, crv=1.0)),
            ("CRV 1,5", p, replace(h, crv=1.5)),
            ("CRV 3", p, replace(h, crv=3.0)),
            ("RSI 30/70 statt 35/65", replace(p, rsi_ueberverkauft=30, rsi_ueberkauft=70), h),
            ("ohne MACD-Bestätigung", replace(p, macd_bestaetigung=False), h),
            ("Maker-Gebühr 0,02 %, keine Slippage", p, replace(h, gebuehr=0.0002, slippage=0.0)),
        ]
    titel = ("Divergenz-Test: letzte 2 Stunden" if a.modus == "live" and minuten == 120
             else f"Divergenz-Test: {de(minuten / 1440, 1)} Tage" if a.modus == "robust"
             else f"Divergenz-Test: letzte {minuten} Minuten")
    md = bericht(titel, daten, coins, ab_ts, ende_ms, p, h, trades, n_signale, ab,
                 wiederholungen=200 if a.modus == "live" else 30,
                 empfindlichkeit=empfindlichkeit, mit_tradeliste=a.modus == "live")
    (ERGEBNISSE / f"{stempel}.md").write_text(md + "\n", encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
