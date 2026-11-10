"""Musterbuch-Divergenzen: reguläre Divergenz nur dann, wenn sie wie im Lehrbuch aussieht.

Pflicht (sonst ist es gar keine Divergenz):
  Zwei bestätigte Swing-Pivots im Abstand von 8–60 Kerzen; Kurs tieferes Tief und RSI höheres Tief
  (Long) bzw. Kurs höheres Hoch und RSI tieferes Hoch (Short).

Musterbuch-Checkliste (7 Punkte, für "100 %" müssen alle erfüllt sein):
  M1  RSI am ersten Pivot in der Extremzone (≤ 30 bzw. ≥ 70)
  M2  RSI-Divergenz deutlich: mindestens 5 Punkte
  M3  MACD-Histogramm bestätigt (erstes Pivot jenseits der Nulllinie, zweites schwächer)
  M4  MACD-Linie bestätigt ebenfalls
  M5  saubere RSI-Verbindungslinie: kein RSI-Wert zwischen den Pivots durchbricht sie
  M6  saubere Kurs-Verbindungslinie: kein Kerzentief/-hoch zwischen den Pivots durchbricht sie
  M7  zwei getrennte Swings: der RSI erholt sich zwischen den Pivots um mindestens 10 Punkte

Auslöser (Pflicht für den Einstieg): Schlusskurs über dem Hoch der zweiten Pivot-Kerze (Long) bzw.
unter ihrem Tief (Short), frühestens bei der Bestätigung des Pivots und höchstens 5 Kerzen danach,
ohne dass das Pivot vorher unterschritten bzw. überschritten wurde. Einstieg zur nächsten Eröffnung.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .strategie import pivots

KRITERIEN = ["M1 Extremzone", "M2 deutlich", "M3 MACD-Histogramm", "M4 MACD-Linie", "M5 RSI-Linie sauber",
             "M6 Kurslinie sauber", "M7 zwei Swings"]


@dataclass(frozen=True)
class Muster:
    links: int = 5
    rechts: int = 3
    min_abstand: int = 8
    max_abstand: int = 60
    rsi_extrem: float = 30.0
    rsi_abstand: float = 5.0
    rsi_erholung: float = 10.0
    ausloeser_kerzen: int = 5


def _linie_sauber(werte: np.ndarray, a: int, b: int, oben: bool) -> bool:
    """True, wenn alle Werte zwischen a und b auf der richtigen Seite der Linie (a, werte[a]) – (b, werte[b])
    liegen: bei Tiefs (oben=True) darüber, bei Hochs darunter."""
    if b - a < 2:
        return True
    i = np.arange(a + 1, b)
    linie = werte[a] + (werte[b] - werte[a]) * (i - a) / (b - a)
    return bool(np.all(werte[i] >= linie) if oben else np.all(werte[i] <= linie))


def musterdivergenzen(df: pd.DataFrame, m: Muster = Muster()) -> list[dict]:
    """Alle Divergenzen mit erfülltem Auslöser, je mit Checkliste und Erfüllungsgrad.
    `df` braucht open/high/low/close sowie rsi, macd, hist (siehe strategie.indikatoren)."""
    hi, lo, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    r, ml, h = df["rsi"].to_numpy(), df["macd"].to_numpy(), df["hist"].to_numpy()
    n = len(df)
    signale = []
    for richtung, tief in (("long", True), ("short", False)):
        preis = lo if tief else hi
        s = 1 if tief else -1  # dreht alle Vergleiche für Shorts um
        piv = pivots(preis, m.links, m.rechts, tief)
        for k in range(1, len(piv)):
            p2 = piv[k]
            p1 = next((q for q in piv[:k][::-1] if m.min_abstand <= p2 - q <= m.max_abstand), None)
            if p1 is None or np.isnan(r[p1]) or np.isnan(r[p2]):
                continue
            if not (s * (preis[p2] - preis[p1]) < 0 and s * (r[p2] - r[p1]) > 0):
                continue
            zwischen = r[p1 + 1:p2]
            erholung = (zwischen.max() - max(r[p1], r[p2])) if tief else (min(r[p1], r[p2]) - zwischen.min())
            checkliste = [
                r[p1] <= m.rsi_extrem if tief else r[p1] >= 100 - m.rsi_extrem,
                s * (r[p2] - r[p1]) >= m.rsi_abstand,
                s * h[p1] < 0 and s * (h[p2] - h[p1]) > 0,
                s * (ml[p2] - ml[p1]) > 0,
                _linie_sauber(r, p1, p2, oben=tief),
                _linie_sauber(preis, p1, p2, oben=tief),
                len(zwischen) > 0 and erholung >= m.rsi_erholung,
            ]
            # Auslöser: Schluss jenseits der Pivot-Kerze, bevor das Pivot verletzt wird
            ausloeser = None
            for t in range(p2 + m.rechts, min(p2 + m.rechts + m.ausloeser_kerzen + 1, n - 1)):
                if s * (preis[t] - preis[p2]) < 0:
                    break
                if s * (c[t] - (hi[p2] if tief else lo[p2])) > 0:
                    ausloeser = t
                    break
            if ausloeser is None:
                continue
            signale.append({
                "richtung": richtung,
                "pivot1": int(p1),
                "pivot2": int(p2),
                "signal_idx": int(ausloeser),  # Einstieg zur Eröffnung der Folgekerze
                "pivot_preis": float(preis[p2]),
                "rsi1": float(r[p1]),
                "rsi2": float(r[p2]),
                "erfuellt": int(sum(checkliste)),
                "fehlt": ", ".join(name for name, ok in zip(KRITERIEN, checkliste) if not ok),
            })
    return sorted(signale, key=lambda x: x["signal_idx"])
