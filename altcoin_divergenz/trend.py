"""Verbesserungsversuch: Divergenz in Trendrichtung, größere Zeitrahmen, bessere Ausstiege.

  python3 -m altcoin_divergenz trend

31 Coins mit 10x Hebel auf Hyperliquid, lange Historie mit OKX-Kursen (15 Minuten: 6 Monate, 1 Stunde:
12 Monate), Kosten wie auf Hyperliquid (Taker 0,045 %, Slippage je Coin aus dem Orderbuch) plus Funding.
Konto 10.000 €, je Trade 1.000 € Margin mit 10x Hebel.

Signalarten
  Regulär (alle)      reguläre Divergenz gegen den Trend, alle mit Auslöser (Musterbuch-Basis)
  Regulär 100 %       nur 100 % Musterbuch
  Versteckt im Trend  versteckte Divergenz in Trendrichtung (muster.trendsignale)
  Kontrolle           derselbe Rücksetzer im Trend ohne RSI-Bedingung – zeigt, ob die Divergenz etwas beiträgt

Ausstiege (R = Abstand Einstieg–Stop)
  fest       Ziel 2R, Zeitstopp 60 Kerzen
  Einstand   ab +1R Stop auf Einstand (inkl. Kosten), Ziel 2R, Zeitstopp 60 Kerzen
  Trailing   kein Ziel; Stop läuft im Abstand von 2 ATR hinter dem besten Kurs her, Zeitstopp 120 Kerzen
  Halb       Hälfte bei +1R verkaufen, dann Einstand und 2-ATR-Trailing für den Rest, Zeitstopp 120 Kerzen
Innerhalb einer Kerze wird immer zuerst der Stop geprüft; nachgezogene Stops gelten ab der nächsten Kerze.

Gegen Zufallsfunde: jeder Zeitraum wird in zwei Hälften geteilt. Nur was in beiden Hälften netto vorne liegt,
ist ein Kandidat.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import okx
from .backtest import Handel, kennzahlen, konto_mit_kapital
from .merkmale import atr_adx
from .muster import Muster, musterdivergenzen, trendsignale
from .musterbuch import BASIS, KAPITAL, MARGE, de, eur, tabelle
from .strategie import indikatoren

ORDNER = Path(__file__).resolve().parent
ERGEBNISSE = ORDNER / "ergebnisse"
CACHE = ORDNER / "cache"
BERLIN = ZoneInfo("Europe/Berlin")
COINS = ERGEBNISSE / "zehnfach_5m_16d_2026-11-10_2200_coins.csv"
OKX_NAME = {"kPEPE": "PEPE", "kSHIB": "SHIB", "kBONK": "BONK"}
ENDE = pd.Timestamp("2026-11-10 00:00", tz="UTC")
ZEITRAHMEN = [("15m", "15 Minuten", 183, 900_000), ("1H", "1 Stunde", 365, 3_600_000)]
VORLAUF = 300
MAKER = 0.00015  # Hyperliquid-Maker-Gebühr, Stufe 0
FUNDING_JE_STUNDE = 0.0000125  # Hyperliquid-Grundsatz 0,01 % je 8 h; Longs zahlen, Shorts erhalten
SIGNALARTEN = ["Regulär (alle)", "Regulär 100 % Musterbuch", "Versteckt im Trend", "Kontrolle: Rücksetzer ohne RSI"]
AUSSTIEGE = ["fest", "Einstand", "Trailing", "Halb"]


def simuliere(o, hi, lo, c, atr, e: int, richtung: int, stop: float, h: Handel, art: str,
              stunden_je_kerze: float, maker: float | None = None, einstieg: float | None = None,
              durchlauf: float = 0.0) -> dict | None:
    """Einen Trade mit der Ausstiegsart `art` ab Eröffnung der Kerze e simulieren.
    `maker`: Einstieg und Ziele (Take-Profit, Teilverkauf) als Limit-Order mit dieser Gebühr und ohne Slippage;
    Stops und Zeitstopp bleiben Market-Orders. Ohne `maker` alles als Market-Order.
    `einstieg`: Limit-Order wird in Kerze e zu diesem Kurs ausgeführt (statt zur Eröffnung). In dieser Kerze zählt
    danach nur noch der Stop, weil unbekannt ist, ob ihr Hoch bzw. Tief vor oder nach der Ausführung lag.
    `durchlauf`: Ziel-Orders (Take-Profit, Teilverkauf) gelten erst als ausgeführt, wenn der Kurs sie um diesen
    Anteil überschreitet (Long) bzw. unterschreitet (Short) – bei 0 reicht eine Berührung."""
    n = len(c)
    if e >= n:
        return None
    roh = o[e] if einstieg is None else einstieg
    abstand = richtung * (roh - stop) / roh
    if abstand <= 0 or abstand > min(h.max_stop, 1 / h.hebel - h.wartungsmarge):
        return None
    if abstand < h.min_stop:
        abstand = h.min_stop
        stop = roh * (1 - richtung * abstand)
    r_preis = roh * abstand
    ziel = roh + richtung * h.crv * r_preis
    eins_r = roh + richtung * r_preis
    einstand = roh * (1 + richtung * 2 * (h.gebuehr + h.slippage))
    abstand_atr = 2 * atr[e - 1] if e > 0 and not np.isnan(atr[e - 1]) else 2 * r_preis
    max_kerzen = 60 if art in ("fest", "Einstand") else 120
    ende = min(e + max_kerzen, n)

    def besser(a: float, b: float) -> float:
        return max(a, b) if richtung > 0 else min(a, b)

    teile: list[tuple[float, float, bool, int]] = []  # Anteil, Kurs, Market-Order?, Kerze
    rest, akt_stop, bester, halb, grund = 1.0, stop, roh, False, ""
    mae = 0.0  # größte Gegenbewegung seit dem Einstieg (Anteil)
    for j in range(e, ende):
        gegen, mit = (lo[j], hi[j]) if richtung > 0 else (hi[j], lo[j])
        mae = max(mae, richtung * (roh - gegen) / roh)
        if richtung * (gegen - akt_stop) <= 0:
            kurs = o[j] if richtung * (o[j] - akt_stop) < 0 and (einstieg is None or j > e) else akt_stop
            teile.append((rest, kurs, True, j))
            rest = 0.0
            grund = "Stop-Loss" if akt_stop == stop else "nachgezogener Stop"
            break
        if einstieg is not None and j == e:
            continue
        if art == "Halb" and not halb and richtung * (mit - eins_r * (1 + richtung * durchlauf)) >= 0:
            teile.append((0.5, eins_r, False, j))
            rest, halb = 0.5, True
        if art in ("fest", "Einstand") and richtung * (mit - ziel * (1 + richtung * durchlauf)) >= 0:
            teile.append((rest, ziel, False, j))
            rest, grund = 0.0, "Take-Profit"
            break
        bester = besser(bester, mit)
        if art == "Einstand" and richtung * (bester - eins_r) >= 0:
            akt_stop = besser(akt_stop, einstand)
        if art in ("Trailing", "Halb"):
            if halb:
                akt_stop = besser(akt_stop, einstand)
            akt_stop = besser(akt_stop, bester - richtung * abstand_atr)
    if rest > 0:
        teile.append((rest, c[ende - 1], True, ende - 1))
        grund = "Zeitstopp" if ende - e == max_kerzen else "offen (letzter Kurs)"

    ein = roh if maker is not None else roh * (1 + richtung * h.slippage)
    netto, brutto, funding = -(h.gebuehr if maker is None else maker), 0.0, 0.0
    for anteil, kurs, markt, j in teile:
        aus = kurs * (1 - richtung * h.slippage) if markt else kurs
        gebuehr = h.gebuehr if markt or maker is None else maker
        netto += anteil * (richtung * (aus - ein) / ein - gebuehr * aus / ein)
        brutto += anteil * richtung * (kurs - roh) / roh
        funding += anteil * (j - e + 1) * stunden_je_kerze * FUNDING_JE_STUNDE * richtung
    netto -= funding
    j_aus = max(t[3] for t in teile)
    return {"einstieg_idx": e, "ausstieg_idx": j_aus, "grund": grund, "stop_abstand_pct": abstand * 100,
            "kerzen": j_aus - e + 1, "marge_brutto_pct": max(-100.0, brutto * h.hebel * 100),
            "marge_netto_pct": max(-100.0, netto * h.hebel * 100), "funding_pct": funding * h.hebel * 100,
            "kurs_netto_pct": netto * 100, "mae_pct": mae * 100}


def handeln(coin: str, x: pd.DataFrame, signale: list[dict], h: Handel, art: str, stunden: float,
            maker: float | None = None) -> list[dict]:
    """Signale ab Kerze VORLAUF handeln, je Coin höchstens eine offene Position."""
    o, hi, lo, c = (x[s].to_numpy() for s in ("open", "high", "low", "close"))
    atr, ts = x["atr"].to_numpy(), x["ts"].to_numpy()
    frei_ab, trades = VORLAUF, []
    for s in signale:
        e = s["signal_idx"] + 1
        if e < frei_ab:
            continue
        richtung = 1 if s["richtung"] == "long" else -1
        t = simuliere(o, hi, lo, c, atr, e, richtung, s["pivot_preis"] * (1 - richtung * h.stop_puffer), h, art,
                      stunden, maker)
        if t is None:
            continue
        frei_ab = t["ausstieg_idx"] + 1
        t.update({"coin": coin, "richtung": s["richtung"],
                  "einstieg_zeit": pd.Timestamp(int(ts[e]), unit="ms", tz="UTC"),
                  "ausstieg_zeit": pd.Timestamp(int(ts[t["ausstieg_idx"]]), unit="ms", tz="UTC")})
        trades.append(t)
    return trades


def vorbereiten(bar: str, tage: int, schritt: int, coins: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, dict]]:
    ende = int(ENDE.value // 1_000_000)
    start = ende - tage * 86_400_000 - VORLAUF * schritt
    inst = {c: f"{OKX_NAME.get(c, c)}-USDT-SWAP" for c in coins["coin"]}
    roh = okx.lade_alle(list(inst.values()), start, ende, cache=CACHE, bar=bar)
    m = Muster()
    daten = {}
    for coin, i in inst.items():
        df = roh[i].rename(columns={"vol_usdt": "vol_usd"})
        if len(df) <= VORLAUF + 100:
            continue
        x = indikatoren(df).join(atr_adx(df))
        x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
        x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()
        regulaer = [s for s in musterdivergenzen(x, m) if s["signal_idx"] >= VORLAUF]
        daten[coin] = (x, {
            SIGNALARTEN[0]: regulaer,
            SIGNALARTEN[1]: [s for s in regulaer if s["erfuellt"] == 7],
            SIGNALARTEN[2]: [s for s in trendsignale(x, m, mit_rsi=True) if s["signal_idx"] >= VORLAUF],
            SIGNALARTEN[3]: [s for s in trendsignale(x, m, mit_rsi=False) if s["signal_idx"] >= VORLAUF],
        })
    return daten


def auswerten(daten, coins: pd.DataFrame, art_signal: str, art_ausstieg: str, stunden: float,
              maker: float | None = None) -> pd.DataFrame:
    slip = dict(zip(coins["coin"], coins["slippage"]))
    rang = {c: i for i, c in enumerate(coins["coin"])}
    trades = []
    for coin, (x, sig) in daten.items():
        trades += handeln(coin, x, sig[art_signal], replace(BASIS, slippage=slip[coin]), art_ausstieg, stunden,
                          maker)
    t = pd.DataFrame(trades)
    if t.empty:
        return t
    t["rang"] = t["coin"].map(rang)
    return t.sort_values(["einstieg_zeit", "rang"], kind="stable").reset_index(drop=True)


def kurz(t: pd.DataFrame) -> str:
    """Ø je Trade netto in Euro und Anteil Gewinner."""
    if t.empty:
        return "–"
    return f"{eur(t['marge_netto_pct'].mean() * MARGE / 100)} ({de(100 * (t['marge_netto_pct'] > 0).mean(), 0)} %)"


def main() -> None:
    coins = pd.read_csv(COINS)
    md = ["# Verbesserungsversuch: Trendrichtung, größere Zeitrahmen, bessere Ausstiege", "",
          "31 Coins mit 10x Hebel auf Hyperliquid, Kurse von OKX (lange Historie), Kosten wie auf Hyperliquid: "
          "Taker 0,045 % je Seite, Slippage je Coin aus dem Orderbuch, Funding 0,00125 % je Stunde (Longs zahlen, "
          "Shorts erhalten). Konto 10.000 €, je Trade 1.000 € Margin × 10. Ø je Trade in Euro, in Klammern der "
          "Anteil der Gewinner-Trades. R = Abstand Einstieg–Stop.", ""]
    zusammenfassung = []
    for bar, name, tage, schritt in ZEITRAHMEN:
        daten = vorbereiten(bar, tage, schritt, coins)
        stunden = schritt / 3_600_000
        start = ENDE - pd.Timedelta(days=tage)
        mitte = start + pd.Timedelta(days=tage / 2)
        md += [f"## {name}: {start.tz_convert(BERLIN):%d.%m.%Y} – {ENDE.tz_convert(BERLIN):%d.%m.%Y} "
               f"({len(daten)} Coins mit Daten)", "",
               f"1. Hälfte bis {mitte.tz_convert(BERLIN):%d.%m.%Y}, 2. Hälfte danach.", ""]
        for kosten, maker in (("alles als Market-Order (Taker 0,045 % + Slippage)", None),
                              ("Einstieg und Ziele als Limit-Order (Maker 0,015 %, ohne Slippage), Stops als "
                               "Market-Order", MAKER)):
            zeilen = []
            for art_signal in SIGNALARTEN:
                for art_ausstieg in AUSSTIEGE:
                    t = auswerten(daten, coins, art_signal, art_ausstieg, stunden, maker)
                    if t.empty:
                        zeilen.append([art_signal, art_ausstieg, "0", *["–"] * 6])
                        continue
                    k = kennzahlen(t)
                    h1, h2 = t[t["einstieg_zeit"] < mitte], t[t["einstieg_zeit"] >= mitte]
                    kk = konto_mit_kapital(t, KAPITAL, MARGE)
                    beide = len(h1) and len(h2) and h1["marge_netto_pct"].mean() > 0 and h2["marge_netto_pct"].mean() > 0
                    zeilen.append([art_signal, art_ausstieg, str(len(t)), kurz(t),
                                   f"{eur(k['ki95_unten'] * MARGE / 100)} … {eur(k['ki95_oben'] * MARGE / 100)}",
                                   eur(t["marge_brutto_pct"].mean() * MARGE / 100), kurz(h1), kurz(h2),
                                   eur(KAPITAL + kk["pnl"]) + (" – Konto leer" if kk["tiefster_stand"] < MARGE else "")
                                   + (" ✔ beide Hälften im Plus" if beide else "")])
                    zusammenfassung.append({"Zeitrahmen": name, "Kosten": "Limit" if maker else "Market",
                                            "Signal": art_signal, "Ausstieg": art_ausstieg, "Trades": len(t),
                                            "netto": t["marge_netto_pct"].mean() * MARGE / 100,
                                            "brutto": t["marge_brutto_pct"].mean() * MARGE / 100,
                                            "ki_unten": k["ki95_unten"] * MARGE / 100,
                                            "ki_oben": k["ki95_oben"] * MARGE / 100,
                                            "h1": h1["marge_netto_pct"].mean() * MARGE / 100 if len(h1) else np.nan,
                                            "h2": h2["marge_netto_pct"].mean() * MARGE / 100 if len(h2) else np.nan,
                                            "konto": KAPITAL + kk["pnl"]})
            md += [f"### Kosten: {kosten}", "",
                   tabelle(["Signal", "Ausstieg", "Trades", "Ø je Trade netto", "95-%-Bereich", "Ø ohne Kosten",
                            "1. Hälfte", "2. Hälfte", "Konto 10.000 € am Ende"], zeilen), ""]
    z = pd.DataFrame(zusammenfassung)
    z.to_csv(ERGEBNISSE / "trend_2026-11-10_uebersicht.csv", index=False)
    text = "\n".join(md) + "\n"
    (ERGEBNISSE / "trend_2026-11-10.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
