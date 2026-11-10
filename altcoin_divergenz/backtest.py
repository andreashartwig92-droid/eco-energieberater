"""Trade-Simulation mit Hebel, Gebühren, Slippage, Stop-Loss, Take-Profit und Zeitstopp."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Handel:
    hebel: float = 10.0
    gebuehr: float = 0.0005      # OKX-Taker-Gebühr je Seite, bezogen auf die Positionsgröße
    slippage: float = 0.0002     # je Market-Order (Einstieg, Stop, Zeitstopp)
    crv: float = 2.0             # Take-Profit = 2 x Stop-Abstand (Chance-Risiko-Verhältnis 1:2)
    stop_puffer: float = 0.0005  # Stop 0,05 % jenseits des Divergenz-Pivots
    min_stop: float = 0.002      # engere Stops werden auf 0,2 % aufgeweitet
    max_stop: float = 0.03       # weitere Stops (> 3 %, also > 30 % der Margin) -> kein Trade
    max_halten: int = 60         # Zeitstopp nach 60 Minuten
    wartungsmarge: float = 0.005  # für den Liquidationspreis (isolierte Margin)


def simuliere(df: pd.DataFrame, einstieg: int, richtung: int, stop: float, h: Handel) -> dict | None:
    """Einen Trade ab Eröffnung der Kerze `einstieg` simulieren. richtung: +1 long, -1 short.

    Innerhalb einer Kerze wird bei Stop und Ziel gleichzeitig konservativ der Stop angenommen.
    """
    n = len(df)
    if einstieg >= n:
        return None
    o = df["open"].to_numpy()
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    roh = o[einstieg]
    abstand = richtung * (roh - stop) / roh
    # Ein Stop jenseits des Liquidationspreises wäre sinnlos -> solche Trades werden nicht eröffnet.
    liq_abstand = 1 / h.hebel - h.wartungsmarge
    if abstand <= 0 or abstand > min(h.max_stop, liq_abstand):
        return None
    if abstand < h.min_stop:
        abstand = h.min_stop
        stop = roh * (1 - richtung * abstand)
    ziel = roh * (1 + richtung * h.crv * abstand)

    ende = min(einstieg + h.max_halten, n)
    sl = slice(einstieg, ende)
    gegen = lo[sl] if richtung > 0 else hi[sl]
    mit = hi[sl] if richtung > 0 else lo[sl]
    stop_hit = richtung * (gegen - stop) <= 0
    ziel_hit = richtung * (mit - ziel) >= 0
    i_stop = int(np.argmax(stop_hit)) if stop_hit.any() else None
    i_ziel = int(np.argmax(ziel_hit)) if ziel_hit.any() else None

    if i_stop is not None and (i_ziel is None or i_stop <= i_ziel):
        j = einstieg + i_stop
        # Kurslücke über den Stop hinweg: Ausführung zur Eröffnung
        aus_roh = o[j] if richtung * (o[j] - stop) < 0 else stop
        grund, markt = "Stop-Loss", True
    elif i_ziel is not None:
        j = einstieg + i_ziel
        aus_roh, grund, markt = ziel, "Take-Profit", False
    else:
        j = ende - 1
        aus_roh, markt = c[j], True
        grund = "Zeitstopp" if ende - einstieg == h.max_halten else "offen (letzter Kurs)"

    ein = roh * (1 + richtung * h.slippage)
    aus = aus_roh * (1 - richtung * h.slippage) if markt else aus_roh
    brutto = richtung * (aus_roh - roh) / roh
    netto = richtung * (aus - ein) / ein - h.gebuehr * (1 + aus / ein)
    return {
        "einstieg_idx": einstieg,
        "ausstieg_idx": j,
        "einstieg": ein,
        "stop": stop,
        "ziel": ziel,
        "ausstieg": aus,
        "grund": grund,
        "stop_abstand_pct": abstand * 100,
        "minuten": j - einstieg + 1,
        "kurs_brutto_pct": brutto * 100,
        "marge_brutto_pct": max(-100.0, brutto * h.hebel * 100),
        "marge_netto_pct": max(-100.0, netto * h.hebel * 100),
    }


def trades_fuer_coin(coin: str, df: pd.DataFrame, signale: list[dict], ab_idx: int, h: Handel) -> list[dict]:
    """Signale ab Kerze `ab_idx` handeln; je Coin höchstens eine offene Position."""
    frei_ab = ab_idx
    trades = []
    for s in signale:
        e = s["signal_idx"] + 1
        if s["signal_idx"] < ab_idx or e < frei_ab:
            continue
        richtung = 1 if s["richtung"] == "long" else -1
        stop = s["pivot_preis"] * (1 - richtung * h.stop_puffer)
        t = simuliere(df, e, richtung, stop, h)
        if t is None:
            continue
        frei_ab = t["ausstieg_idx"] + 1
        t.update({
            "coin": coin,
            "richtung": s["richtung"],
            "signal_zeit": pd.to_datetime(df["ts"].iat[s["signal_idx"]], unit="ms", utc=True),
            "einstieg_zeit": pd.to_datetime(df["ts"].iat[e], unit="ms", utc=True),
            "ausstieg_zeit": pd.to_datetime(df["ts"].iat[t["ausstieg_idx"]], unit="ms", utc=True),
            "rsi1": s["rsi1"],
            "rsi2": s["rsi2"],
        })
        trades.append(t)
    return trades


def zufallstrades(daten: dict[str, pd.DataFrame], ab: dict[str, int], vorbild: pd.DataFrame, h: Handel,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Kontrollgruppe: gleich viele Trades mit gleichen Stop-Abständen, aber zufälligem Coin,
    zufälligem Zeitpunkt (ab Kerze `ab[coin]`) und zufälliger Richtung.
    Zeigt, was mit denselben Regeln für Stop, Ziel, Hebel und Kosten ganz ohne Signal herauskommt."""
    coins = [c for c in ab if len(daten[c]) > ab[c] + 2]
    zeilen = []
    for abstand in vorbild["stop_abstand_pct"].to_numpy() / 100:
        coin = coins[rng.integers(len(coins))]
        df = daten[coin]
        e = int(rng.integers(ab[coin], len(df) - 1))
        richtung = 1 if rng.random() < 0.5 else -1
        t = simuliere(df, e, richtung, df["open"].iat[e] * (1 - richtung * abstand), h)
        if t:
            zeilen.append(t)
    return pd.DataFrame(zeilen)


def kennzahlen(trades: pd.DataFrame, spalte: str = "marge_netto_pct") -> dict:
    if trades.empty:
        return {"trades": 0}
    r = trades[spalte].to_numpy()
    gewinne, verluste = r[r > 0], r[r <= 0]
    rng = np.random.default_rng(1)
    boot = rng.choice(r, size=(2000, len(r))).mean(axis=1) if len(r) > 1 else r
    return {
        "trades": len(r),
        "trefferquote_pct": 100 * len(gewinne) / len(r),
        "schnitt_gewinn_pct": gewinne.mean() if len(gewinne) else 0.0,
        "schnitt_verlust_pct": verluste.mean() if len(verluste) else 0.0,
        "profit_faktor": gewinne.sum() / -verluste.sum() if verluste.sum() < 0 else float("inf"),
        "erwartung_pct": r.mean(),
        "ki95_unten": float(np.percentile(boot, 2.5)),
        "ki95_oben": float(np.percentile(boot, 97.5)),
    }


def konto(trades: pd.DataFrame, marge_je_trade: float, max_parallel: int | None,
          spalte: str = "marge_netto_pct") -> dict:
    """Festes Margin-Budget je Trade (kein Zinseszins). Bei vollen Slots wird das Signal übersprungen."""
    t = trades.sort_values("einstieg_zeit")
    offen: list[pd.Timestamp] = []
    genommen = []
    for _, z in t.iterrows():
        offen = [a for a in offen if a >= z["einstieg_zeit"]]
        if max_parallel is not None and len(offen) >= max_parallel:
            continue
        offen.append(z["ausstieg_zeit"])
        genommen.append(z)
    g = pd.DataFrame(genommen)
    if g.empty:
        return {"trades": 0, "pnl_eur": 0.0, "max_drawdown_eur": 0.0, "max_parallel": 0}
    g = g.sort_values("ausstieg_zeit")
    pnl = g[spalte].to_numpy() / 100 * marge_je_trade
    kurve = np.cumsum(pnl)
    drawdown = np.max(np.maximum.accumulate(np.concatenate([[0], kurve])) - np.concatenate([[0], kurve]))
    # höchste Zahl gleichzeitig offener Positionen
    ereignisse = sorted([(x, 1) for x in g["einstieg_zeit"]] + [(x, -1) for x in g["ausstieg_zeit"]],
                        key=lambda e: (e[0], -e[1]))
    stand = spitze = 0
    for _, d in ereignisse:
        stand += d
        spitze = max(spitze, stand)
    return {"trades": len(g), "pnl_eur": float(kurve[-1]), "max_drawdown_eur": float(drawdown),
            "max_parallel": spitze}
