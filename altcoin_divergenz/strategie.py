"""RSI, MACD und klare reguläre Divergenzen – ohne Blick in die Zukunft.

Ein Pivot-Tief an Kerze i gilt erst als bestätigt, wenn danach `rechts` Kerzen kein tieferes Tief
gebracht haben. Das Signal entsteht also frühestens am Schluss von Kerze i + rechts, der Einstieg
erfolgt zur Eröffnung der Kerze danach. So sieht der Backtest nur, was ein Trader live auch sähe.

Klare bullische Divergenz (Long):
  Kurs macht ein tieferes Tief, der RSI ein deutlich höheres Tief (mind. `rsi_abstand` Punkte),
  der RSI war beim ersten Tief überverkauft (<= `rsi_ueberverkauft`) und das MACD-Histogramm
  bestätigt (negativ beim ersten Tief, beim zweiten Tief höher).
Klare bärische Divergenz (Short): spiegelbildlich an Pivot-Hochs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Parameter:
    rsi_laenge: int = 14
    macd_schnell: int = 12
    macd_langsam: int = 26
    macd_signal: int = 9
    links: int = 5             # Kerzen links vom Pivot, die höher (Tief) bzw. tiefer (Hoch) liegen müssen
    rechts: int = 3            # Kerzen rechts vom Pivot bis zur Bestätigung
    min_abstand: int = 5       # Mindestabstand der beiden Pivots in Kerzen
    max_abstand: int = 60      # Höchstabstand der beiden Pivots in Kerzen
    rsi_abstand: float = 2.0   # RSI-Unterschied der beiden Pivots in Punkten
    rsi_ueberverkauft: float = 35.0
    rsi_ueberkauft: float = 65.0
    macd_bestaetigung: bool = True  # MACD-Histogramm muss die Divergenz mittragen


def rsi(close: pd.Series, laenge: int = 14) -> pd.Series:
    """RSI nach Wilder."""
    diff = close.diff()
    auf = diff.clip(lower=0).ewm(alpha=1 / laenge, adjust=False, min_periods=laenge).mean()
    ab = (-diff.clip(upper=0)).ewm(alpha=1 / laenge, adjust=False, min_periods=laenge).mean()
    rs = auf / ab
    return (100 - 100 / (1 + rs)).where(ab > 0, 100.0)


def macd(close: pd.Series, schnell: int = 12, langsam: int = 26, signal: int = 9) -> pd.DataFrame:
    linie = close.ewm(span=schnell, adjust=False).mean() - close.ewm(span=langsam, adjust=False).mean()
    sig = linie.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": linie, "signal": sig, "hist": linie - sig})


def indikatoren(kerzen: pd.DataFrame, p: Parameter = Parameter()) -> pd.DataFrame:
    df = kerzen.copy()
    df["rsi"] = rsi(df["close"], p.rsi_laenge)
    df = df.join(macd(df["close"], p.macd_schnell, p.macd_langsam, p.macd_signal))
    return df


def pivots(werte: np.ndarray, links: int, rechts: int, tief: bool) -> np.ndarray:
    """Indizes der Pivot-Tiefs (tief=True) bzw. Pivot-Hochs. Links strikt, rechts nicht-strikt."""
    v = -werte if not tief else werte
    treffer = []
    for i in range(links, len(v) - rechts):
        if v[i] < v[i - links:i].min() and v[i] <= v[i + 1:i + rechts + 1].min():
            treffer.append(i)
    return np.array(treffer, dtype=int)


def divergenzen(df: pd.DataFrame, p: Parameter = Parameter()) -> list[dict]:
    """Alle klaren Divergenz-Signale. `df` braucht Spalten aus `indikatoren`."""
    signale = []
    for richtung, tief in (("long", True), ("short", False)):
        preis = (df["low"] if tief else df["high"]).to_numpy()
        r = df["rsi"].to_numpy()
        h = df["hist"].to_numpy()
        piv = pivots(preis, p.links, p.rechts, tief)
        for k in range(1, len(piv)):
            p2 = piv[k]
            # jüngstes vorheriges Pivot im erlaubten Abstand
            p1 = next((q for q in piv[:k][::-1] if p.min_abstand <= p2 - q <= p.max_abstand), None)
            if p1 is None or np.isnan(r[p1]) or np.isnan(r[p2]):
                continue
            if tief:
                klar = (preis[p2] < preis[p1] and r[p2] >= r[p1] + p.rsi_abstand
                        and r[p1] <= p.rsi_ueberverkauft
                        and (not p.macd_bestaetigung or (h[p1] < 0 and h[p2] > h[p1])))
            else:
                klar = (preis[p2] > preis[p1] and r[p2] <= r[p1] - p.rsi_abstand
                        and r[p1] >= p.rsi_ueberkauft
                        and (not p.macd_bestaetigung or (h[p1] > 0 and h[p2] < h[p1])))
            if klar:
                signale.append({
                    "richtung": richtung,
                    "pivot1": int(p1),
                    "pivot2": int(p2),
                    "signal_idx": int(p2 + p.rechts),  # Schlusskurs dieser Kerze bestätigt das Pivot
                    "pivot_preis": float(preis[p2]),
                    "rsi1": float(r[p1]),
                    "rsi2": float(r[p2]),
                })
    return sorted(signale, key=lambda s: s["signal_idx"])
