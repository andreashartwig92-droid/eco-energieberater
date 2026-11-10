"""Welche Bedingungen hatten Gewinner- und Verlierer-Trades gemeinsam?

  python3 -m altcoin_divergenz merkmale

Grundlage: 31 Coins mit 10x Hebel auf Hyperliquid, 5-Minuten-Chart, 16 Tage (gespeicherter Datensatz), alle
regulären Divergenzen mit Auslöser (Musterbuch-Basis, 0–7 Checklisten-Punkte). Für jeden Trade werden zum
Signalzeitpunkt – also ohne Blick in die Zukunft – weitere Merkmale erfasst: Volumen, Stochastik, Trend,
Trendstärke (ADX), Volatilität, Bollinger-Bänder, RSI auf 1 Stunde, BTC-Lage, Tageszeit, Signal-Häufung u. a.

Gegen Zufallsfunde: Merkmale werden in den ersten 8 Tagen gesucht ("Entdeckung"), in den letzten 8 Tagen
geprüft ("Prüfung") und zuletzt an einem unabhängigen Zeitraum gegengeprüft: dieselben 31 Coins vom
1.–24. Oktober mit Kursen von OKX ("Oktober"), gerechnet mit Hyperliquid-Kosten.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import konto_mit_kapital, trades_fuer_coin
from .muster import KRITERIEN, Muster, musterdivergenzen
from .musterbuch import BASIS, BERLIN, KAPITAL, MARGE, de, eur, tabelle
from .strategie import indikatoren, rsi

ORDNER = Path(__file__).resolve().parent
ERGEBNISSE = ORDNER / "ergebnisse"
DATENSATZ = "zehnfach_5m_16d_2026-11-10_2200"
VORLAUF = 150
SCHRITT = 300_000


# ---------------------------------------------------------------- zusätzliche Indikatoren

def stochastik(df: pd.DataFrame, n: int = 14, k: int = 3, d: int = 3) -> pd.DataFrame:
    tief, hoch = df["low"].rolling(n).min(), df["high"].rolling(n).max()
    roh = 100 * (df["close"] - tief) / (hoch - tief).replace(0, np.nan)
    langsam = roh.rolling(k).mean()
    return pd.DataFrame({"stoch_k": langsam, "stoch_d": langsam.rolling(d).mean()})


def atr_adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    auf, ab = h.diff(), -l.diff()
    plus = auf.where((auf > ab) & (auf > 0), 0.0)
    minus = ab.where((ab > auf) & (ab > 0), 0.0)
    w = dict(alpha=1 / n, adjust=False)
    atr = tr.ewm(**w).mean()
    pdi, mdi = 100 * plus.ewm(**w).mean() / atr, 100 * minus.ewm(**w).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pd.DataFrame({"atr": atr, "adx": dx.ewm(**w).mean()})


def stunden_rsi(df: pd.DataFrame) -> pd.Series:
    """RSI 14 auf 1-Stunden-Kerzen, je 5-Minuten-Kerze der Wert der zuletzt abgeschlossenen Stunde."""
    stunde = df["ts"] // 3_600_000 * 3_600_000
    schluss = df.groupby(stunde)["close"].last()
    r = rsi(schluss, 14)
    fertig = pd.DataFrame({"ab": schluss.index + 3_600_000, "rsi_1h": r.to_numpy()})
    links = pd.DataFrame({"zu": df["ts"] + SCHRITT})  # Schlusszeit der 5-Minuten-Kerze
    return pd.merge_asof(links, fertig, left_on="zu", right_on="ab", direction="backward")["rsi_1h"]


def erweitern(df: pd.DataFrame) -> pd.DataFrame:
    x = indikatoren(df)
    x = x.join(stochastik(x)).join(atr_adx(x))
    x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()
    x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()
    mitte = x["close"].rolling(20).mean()
    breite = 2 * x["close"].rolling(20).std()
    x["bb_unten"], x["bb_oben"] = mitte - breite, mitte + breite
    x["vol_schnitt"] = x["vol_usd"].rolling(20).mean().shift(1)
    x["hoch_24h"] = x["high"].rolling(288, min_periods=100).max()
    x["tief_24h"] = x["low"].rolling(288, min_periods=100).min()
    x["rsi_1h"] = stunden_rsi(x).to_numpy()
    return x


# ---------------------------------------------------------------- Merkmale je Trade

def merkmale(x: pd.DataFrame, s: dict, btc: pd.DataFrame) -> dict:
    """Alle Werte zum Schluss der Auslöser-Kerze (Einstieg erfolgt zur nächsten Eröffnung)."""
    i, p1, p2 = s["signal_idx"], s["pivot1"], s["pivot2"]
    r = 1 if s["richtung"] == "long" else -1
    z = x.iloc[i]
    preis = x["low"] if r > 0 else x["high"]
    k_p1, k_p2 = x["stoch_k"].iat[p1], x["stoch_k"].iat[p2]
    stoch_p2_richtung = k_p2 if r > 0 else 100 - k_p2  # klein = überverkauft (Long) bzw. überkauft (Short)
    spanne = z["hoch_24h"] - z["tief_24h"]
    lage = (z["close"] - z["tief_24h"]) / spanne if spanne > 0 else np.nan
    b = btc.iloc[int(np.searchsorted(btc["ts"].to_numpy(), z["ts"], side="right")) - 1]
    m = {
        "Richtung Long": r > 0,
        "Musterbuch-Punkte (0–7)": s["erfuellt"],
        **{name: name not in s["fehlt"] for name in KRITERIEN},
        "RSI-Divergenz in Punkten": abs(s["rsi2"] - s["rsi1"]),
        "Kursabstand der Pivots in %": abs(preis.iat[p2] / preis.iat[p1] - 1) * 100,
        "Pivot-Abstand in Kerzen": p2 - p1,
        "Volumen Auslöser / Ø 20": z["vol_usd"] / z["vol_schnitt"] if z["vol_schnitt"] > 0 else np.nan,
        "Volumen 2. Pivot / 1. Pivot": (x["vol_usd"].iat[p2] / x["vol_usd"].iat[p1]
                                        if x["vol_usd"].iat[p1] > 0 else np.nan),
        "Stochastik am 2. Pivot (Richtung)": stoch_p2_richtung,
        "Stochastik-Divergenz": (k_p2 - k_p1) * r > 0,
        "Stochastik %K über %D (Richtung)": (z["stoch_k"] - z["stoch_d"]) * r > 0,
        "Stochastik am Auslöser (Richtung)": z["stoch_k"] if r > 0 else 100 - z["stoch_k"],
        "ADX (Trendstärke)": z["adx"],
        "ATR in % (Volatilität)": z["atr"] / z["close"] * 100,
        "Mit EMA-200-Trend": (z["close"] - z["ema200"]) * r > 0,
        "Abstand zur EMA 200 in % (Richtung)": (z["close"] / z["ema200"] - 1) * 100 * r,
        "EMA-50-Steigung 1 h in % (Richtung)": (z["ema50"] / x["ema50"].iat[max(i - 12, 0)] - 1) * 100 * r,
        "2. Pivot außerhalb Bollinger": (preis.iat[p2] < x["bb_unten"].iat[p2]) if r > 0
                                        else (preis.iat[p2] > x["bb_oben"].iat[p2]),
        "RSI 1 h (Richtung)": z["rsi_1h"] if r > 0 else 100 - z["rsi_1h"],
        "Lage in 24-h-Spanne (Richtung)": lage if r > 0 else 1 - lage,
        "Auslöser-Kerze Körper/Spanne (Richtung)": ((z["close"] - z["open"]) * r / (z["high"] - z["low"])
                                                   if z["high"] > z["low"] else 0.0),
        "BTC 1-h-Rendite in % (Richtung)": b["btc_ret_1h"] * r,
        "BTC RSI 5 min (Richtung)": b["btc_rsi"] if r > 0 else 100 - b["btc_rsi"],
        "Stunde (MEZ)": pd.Timestamp(z["ts"], unit="ms", tz="UTC").tz_convert(BERLIN).hour,
        "Wochenende": pd.Timestamp(z["ts"], unit="ms", tz="UTC").tz_convert(BERLIN).dayofweek >= 5,
    }
    return m


def datensatz(kerzen: pd.DataFrame, slip: dict[str, float], btc: pd.DataFrame) -> pd.DataFrame:
    """Alle Divergenz-Trades (Musterbuch-Basis) mit ihren Merkmalen."""
    btc = btc.copy()
    btc["btc_rsi"] = rsi(btc["close"], 14)
    btc["btc_ret_1h"] = (btc["close"] / btc["close"].shift(12) - 1) * 100
    zeilen = []
    for coin, df in kerzen.groupby("coin", sort=False):
        x = erweitern(df.drop(columns="coin").reset_index(drop=True))
        sig = [s for s in musterdivergenzen(x, Muster()) if s["signal_idx"] >= VORLAUF]
        nach_idx = {s["signal_idx"]: s for s in sig}
        for t in trades_fuer_coin(coin, x, sig, VORLAUF, replace(BASIS, slippage=slip[coin])):
            s = nach_idx[t["einstieg_idx"] - 1]
            zeilen.append({"coin": coin, "signal_zeit": t["signal_zeit"], "einstieg_zeit": t["einstieg_zeit"],
                           "ausstieg_zeit": t["ausstieg_zeit"], "richtung": t["richtung"], "grund": t["grund"],
                           "netto_eur": t["marge_netto_pct"] * MARGE / 100,
                           "brutto_eur": t["marge_brutto_pct"] * MARGE / 100,
                           "marge_netto_pct": t["marge_netto_pct"], "marge_brutto_pct": t["marge_brutto_pct"],
                           **merkmale(x, s, btc)})
    d = pd.DataFrame(zeilen).sort_values("einstieg_zeit", kind="stable").reset_index(drop=True)
    # Signal-Häufung: wie viele andere Coins in den letzten 30 Minuten dieselbe Richtung signalisiert haben
    zeit = ((d["signal_zeit"] - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy()
    richtung, coin = d["richtung"].to_numpy(), d["coin"].to_numpy()
    d["Andere Coins gleiche Richtung, letzte 30 min"] = [
        int(np.sum((zeit <= zeit[j]) & (zeit >= zeit[j] - 1_800_000) & (richtung == richtung[j]) & (coin != coin[j])))
        for j in range(len(d))]
    d["gewinn"] = d["netto_eur"] > 0
    return d


# ---------------------------------------------------------------- Auswertung

PERIODEN = ["Entdeckung", "Prüfung", "Oktober"]
KEINE_MERKMALE = {"coin", "signal_zeit", "einstieg_zeit", "ausstieg_zeit", "richtung", "grund", "netto_eur",
                  "brutto_eur", "marge_netto_pct", "marge_brutto_pct", "gewinn", "periode"}


def gruppen(d: pd.DataFrame, merkmal: str, grenzen: list[float] | None) -> pd.Series:
    w = d[merkmal]
    if grenzen is None:  # ja/nein
        return w.map({True: "ja", False: "nein", 1: "ja", 0: "nein"})
    return pd.cut(w, [-np.inf, *grenzen, np.inf], labels=["unteres Drittel", "mittleres Drittel", "oberes Drittel"])


def merkmal_tabelle(d: pd.DataFrame, merkmale_liste: list[str]) -> pd.DataFrame:
    """Je Merkmal und Bereich: Trades, Trefferquote und Ø netto in jedem Zeitraum.
    Die Drittel-Grenzen stammen nur aus der Entdeckung."""
    ent = d[d["periode"] == "Entdeckung"]
    zeilen = []
    for m in merkmale_liste:
        diskret = d[m].dtype == bool or d[m].nunique() <= 2
        grenzen = None if diskret else list(np.unique(np.quantile(ent[m].dropna(), [1 / 3, 2 / 3])))
        if grenzen is not None and len(grenzen) < 2:
            continue
        g = gruppen(d, m, grenzen)
        for stufe in (g.cat.categories if hasattr(g, "cat") else sorted(g.dropna().unique())):
            z = {"Merkmal": m, "Bereich": stufe, "Grenzen": grenzen}
            for per in PERIODEN:
                t = d[(g == stufe) & (d["periode"] == per)]
                z[f"{per} n"] = len(t)
                z[f"{per} Treffer"] = t["gewinn"].mean() * 100 if len(t) else np.nan
                z[f"{per} Ø"] = t["netto_eur"].mean() if len(t) else np.nan
            zeilen.append(z)
    return pd.DataFrame(zeilen)


def rangliste(tab: pd.DataFrame, n: dict[str, int], min_anteil: float = 0.15) -> pd.DataFrame:
    """Je Merkmal bester und schlechtester Bereich in der Entdeckung; hält der Unterschied später?"""
    zeilen = []
    for m, g in tab.groupby("Merkmal", sort=False):
        g = g[(g["Entdeckung n"] >= min_anteil * n["Entdeckung"]) & (g["Prüfung n"] >= min_anteil * n["Prüfung"])]
        if len(g) < 2:
            continue
        best, worst = g.loc[g["Entdeckung Ø"].idxmax()], g.loc[g["Entdeckung Ø"].idxmin()]
        z = {"Merkmal": m, "gut": best["Bereich"], "schlecht": worst["Bereich"]}
        for per in PERIODEN:
            z[f"Unterschied {per}"] = best[f"{per} Ø"] - worst[f"{per} Ø"]
            z[f"gut {per}"] = best[f"{per} Ø"]
        zeilen.append(z)
    r = pd.DataFrame(zeilen)
    r["hält in Prüfung"] = r["Unterschied Prüfung"] > 0
    r["hält im Oktober"] = r["Unterschied Oktober"] > 0
    r["Stärke"] = r[["Unterschied Entdeckung", "Unterschied Prüfung"]].min(axis=1)
    return r.sort_values("Stärke", ascending=False)


def regel_maske(d: pd.DataFrame, tab: pd.DataFrame, merkmal: str, bereich, nur: bool) -> np.ndarray:
    grenzen = tab.loc[tab["Merkmal"] == merkmal, "Grenzen"].iloc[0]
    g = gruppen(d, merkmal, grenzen)
    return ((g == bereich) if nur else (g != bereich)).to_numpy()


def filter_suche(d: pd.DataFrame, tab: pd.DataFrame, schritte: int = 3, min_anteil: float = 0.15) -> list[dict]:
    """Schrittweise je eine Regel ("nur Bereich X" / "ohne Bereich Y"), die in der ENTDECKUNG den Schnitt je
    Trade am meisten hebt. Prüfung und Oktober werden nur angesehen, nie zur Auswahl genutzt."""
    ent = (d["periode"] == "Entdeckung").to_numpy()
    maske = np.ones(len(d), dtype=bool)
    verlauf = [{"Regel": "Ausgangslage: alle Divergenzen mit Auslöser", "maske": maske.copy()}]
    benutzt: set[str] = set()
    for _ in range(schritte):
        beste = None
        for m, b in tab[["Merkmal", "Bereich"]].itertuples(index=False):
            if m in benutzt:
                continue
            for nur in (True, False):
                neu = maske & regel_maske(d, tab, m, b, nur)
                if (neu & ent).sum() < min_anteil * ent.sum():
                    continue
                wert = d.loc[neu & ent, "netto_eur"].mean()
                if beste is None or wert > beste[0]:
                    beste = (wert, f"{m}: {'nur' if nur else 'ohne'} {b}", neu, m)
        if beste is None:
            break
        maske = beste[2]
        benutzt.add(beste[3])
        verlauf.append({"Regel": "+ " + beste[1], "maske": maske.copy()})
    return verlauf


def stufen_zeilen(d: pd.DataFrame, verlauf: list[dict]) -> list[list[str]]:
    zeilen = []
    for v in verlauf:
        z = [v["Regel"]]
        for per in PERIODEN:
            t = d[v["maske"] & (d["periode"] == per).to_numpy()]
            z.append(f"{len(t)}: {eur(t['netto_eur'].mean())} ({de(100 * t['gewinn'].mean(), 0)} %)" if len(t) else "0")
        t = d[v["maske"] & (d["periode"] == "Oktober").to_numpy()]
        z.append(eur(KAPITAL + konto_mit_kapital(t, KAPITAL, MARGE)["pnl"]) if len(t) else "–")
        zeilen.append(z)
    return zeilen


def main() -> None:
    hl_kerzen = pd.read_csv(ERGEBNISSE / f"{DATENSATZ}_kerzen.csv.gz")
    coins = pd.read_csv(ERGEBNISSE / f"{DATENSATZ}_coins.csv")
    slip = dict(zip(coins["coin"], coins["slippage"]))
    d_hl = datensatz(hl_kerzen, slip, pd.read_csv(ERGEBNISSE / f"{DATENSATZ}_btc.csv.gz"))
    mitte = d_hl["signal_zeit"].min() + (d_hl["signal_zeit"].max() - d_hl["signal_zeit"].min()) / 2
    d_hl["periode"] = np.where(d_hl["signal_zeit"] < mitte, "Entdeckung", "Prüfung")
    d_okx = datensatz(pd.read_csv(ERGEBNISSE / "merkmale_okx_oktober_5m_kerzen.csv.gz"), slip,
                      pd.read_csv(ERGEBNISSE / "merkmale_okx_oktober_5m_btc.csv.gz"))
    d_okx["periode"] = "Oktober"
    d = pd.concat([d_hl, d_okx], ignore_index=True)
    merkmale_liste = [c for c in d.columns if c not in KEINE_MERKMALE]
    n = {per: int((d["periode"] == per).sum()) for per in PERIODEN}
    tab = merkmal_tabelle(d, merkmale_liste)
    rang = rangliste(tab, n)

    def spanne(t: pd.DataFrame) -> str:
        a = pd.Timestamp(t["signal_zeit"].min()).tz_convert(BERLIN)
        b = pd.Timestamp(t["signal_zeit"].max()).tz_convert(BERLIN)
        return f"{a:%d.%m.} – {b:%d.%m.}"

    md = ["# Merkmale von Gewinner- und Verlierer-Trades", "",
          "31 Coins mit 10x Hebel, 5-Minuten-Chart, alle regulären Divergenzen mit Auslöser (Musterbuch-Basis, "
          "0–7 Checklisten-Punkte), Stop am Pivot, Ziel 2 × Stop, Kosten wie auf Hyperliquid (Taker 0,045 %, "
          "Slippage je Coin aus dem Orderbuch), 1.000 € Margin bei 10x. Alle Merkmale zum Signalzeitpunkt, ohne "
          "Blick in die Zukunft.", "",
          tabelle(["Zeitraum", "Daten", "Rolle", "Trades", "mit Gewinn", "Ø je Trade netto", "ohne Kosten"],
                  [[f"{per} ({spanne(d[d['periode'] == per])})",
                    "OKX-Kurse" if per == "Oktober" else "Hyperliquid",
                    {"Entdeckung": "Merkmale und Filter werden hier gesucht",
                     "Prüfung": "kontrolliert, ob es hält",
                     "Oktober": "unabhängige Gegenprobe"}[per],
                    str(n[per]), de(100 * d.loc[d["periode"] == per, "gewinn"].mean(), 0) + " %",
                    eur(d.loc[d["periode"] == per, "netto_eur"].mean()),
                    eur(d.loc[d["periode"] == per, "brutto_eur"].mean())] for per in PERIODEN]), ""]

    md += ["## Gewinner gegen Verlierer (alle drei Zeiträume zusammen, Median bzw. Anteil)", ""]
    zeilen = []
    for m in merkmale_liste:
        g, v = d.loc[d["gewinn"], m], d.loc[~d["gewinn"], m]
        zeilen.append([m, de(100 * g.mean(), 0) + " %", de(100 * v.mean(), 0) + " %"] if d[m].dtype == bool
                      else [m, de(g.median()), de(v.median())])
    md += [tabelle(["Merkmal", "Gewinner", "Verlierer"], zeilen), ""]

    md += ["## Rangliste: trennt das Merkmal gute von schlechten Trades – auch später noch?", "",
           "Je Merkmal der beste und der schlechteste Bereich (Drittel bzw. ja/nein) in der Entdeckung. Daneben der "
           "Unterschied (Ø je Trade gut minus schlecht) in allen drei Zeiträumen und der Ø des guten Bereichs. "
           "Bereiche mit weniger als 15 % der Trades zählen nicht.", ""]
    md += [tabelle(["Merkmal", "guter Bereich", "schlechter Bereich", "Unterschied Entdeckung", "Unterschied Prüfung",
                    "Unterschied Oktober", "guter Bereich: Ø Prüfung / Oktober", "hält?"],
                   [[r["Merkmal"], str(r["gut"]), str(r["schlecht"]), eur(r["Unterschied Entdeckung"]),
                     eur(r["Unterschied Prüfung"]), eur(r["Unterschied Oktober"]),
                     f"{eur(r['gut Prüfung'])} / {eur(r['gut Oktober'])}",
                     "beide" if r["hält in Prüfung"] and r["hält im Oktober"]
                     else "nur Prüfung" if r["hält in Prüfung"] else "nur Oktober" if r["hält im Oktober"] else "nein"]
                    for _, r in rang.iterrows()]), ""]

    md += ["## Automatisch gesuchter Filter (nur mit der Entdeckung ausgewählt)", ""]
    kopf = ["Schritt", *[f"{per}: Trades, Ø netto (Treffer)" for per in PERIODEN], "Konto 10.000 € im Oktober"]
    md += [tabelle(kopf, stufen_zeilen(d, filter_suche(d, tab))), ""]

    bestaetigt = rang[rang["hält in Prüfung"]].head(3)
    verlauf = [{"Regel": "Ausgangslage", "maske": np.ones(len(d), dtype=bool)}]
    for _, r in bestaetigt.iterrows():
        verlauf.append({"Regel": f"+ {r['Merkmal']}: nur {r['gut']}",
                        "maske": verlauf[-1]["maske"] & regel_maske(d, tab, r["Merkmal"], r["gut"], True)})
    md += ["## Die drei Merkmale, die Entdeckung und Prüfung überstanden haben, im Oktober", "",
           "Ausgewählt mit Entdeckung und Prüfung; der Oktober war dabei nie im Spiel.", ""]
    md += [tabelle(kopf, stufen_zeilen(d, verlauf)), ""]

    md += ["## Alle Bereiche im Detail (n / Treffer / Ø netto)", ""]
    md += [tabelle(["Merkmal", "Bereich", "Grenzen", *PERIODEN],
                   [[r["Merkmal"], str(r["Bereich"]),
                     "–" if r["Grenzen"] is None else f"{de(r['Grenzen'][0])} / {de(r['Grenzen'][1])}",
                     *[f"{int(r[f'{per} n'])} / {de(r[f'{per} Treffer'], 0)} % / {eur(r[f'{per} Ø'])}"
                       for per in PERIODEN]]
                    for _, r in tab.iterrows()]), ""]

    text = "\n".join(md) + "\n"
    (ERGEBNISSE / "merkmale_2026-11-10.md").write_text(text, encoding="utf-8")
    aus = d.copy()
    for s in ("signal_zeit", "einstieg_zeit", "ausstieg_zeit"):
        aus[s] = aus[s].dt.tz_convert(BERLIN).dt.strftime("%Y-%m-%d %H:%M")
    aus.to_csv(ERGEBNISSE / "merkmale_2026-11-10_trades.csv", index=False)
    print(text)


if __name__ == "__main__":
    main()
