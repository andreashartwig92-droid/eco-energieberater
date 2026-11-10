"""Umkehr-Test: gegen das Divergenz-Signal handeln (Short-Signal -> Long, Long-Signal -> Short).

  python3 -m altcoin_divergenz umkehr

Wertet dieselben Datensätze wie die bisherigen Tests aus (OKX 2 Stunden, OKX 7 Tage, Hyperliquid
Musterbuch 7/7) und vergleicht je drei Varianten:
  Original   wie signalisiert, Stop am Pivot, Ziel 2 × Stop
  Spiegel    exakt der Gegen-Trade: altes Ziel = neuer Stop, alter Stop = neues Ziel (CRV 2:1)
  Gleich     Gegenrichtung mit denselben Regeln: Stop im gleichen Abstand auf der anderen Seite, Ziel 2 × Stop
Konto wie zuletzt besprochen: 10.000 €, je Trade 1.000 € Margin mit 10x Hebel.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import musterbuch, okx
from .__main__ import lauf as okx_lauf
from .backtest import Handel, kennzahlen, konto_mit_kapital
from .strategie import Parameter

ORDNER = Path(__file__).resolve().parent
ERGEBNISSE = ORDNER / "ergebnisse"
KAPITAL, MARGE = 10_000.0, 1_000.0
VARIANTEN = [("Original (wie signalisiert)", ""), ("Umgekehrt – Spiegel (CRV 2:1)", "spiegel"),
             ("Umgekehrt – gleiche Regeln (CRV 1:2)", "gleich")]


def de(x: float, n: int = 0) -> str:
    if x == float("inf"):
        return "∞"
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def okx_daten(stempel: str, minuten: int, kerzen: Path | None = None) -> tuple[dict, int]:
    if kerzen is not None:
        alle = pd.read_csv(kerzen)
        daten = {c: g.drop(columns="coin").reset_index(drop=True) for c, g in alle.groupby("coin", sort=False)}
        ende = int(alle["ts"].max()) + 60_000
    else:  # 7-Tage-Lauf: Kerzen aus dem Cache bzw. erneut von OKX (gleiches Zeitfenster)
        coins = pd.read_csv(ERGEBNISSE / f"{stempel}_coins.csv")
        ende = pd.to_datetime(stempel.split("_", 1)[1], format="%Y-%m-%d_%H%M").tz_localize("Europe/Berlin")
        ende = int(ende.tz_convert("UTC").value // 1_000_000)
        start = ende - (minuten + 300) * 60_000
        roh = okx.lade_alle(coins["inst_id"].tolist(), start, ende, cache=ORDNER / "cache")
        daten = {c: roh[i] for c, i in zip(coins["coin"], coins["inst_id"])}
    return daten, ende - minuten * 60_000


def zeile(name: str, t: pd.DataFrame) -> list[str]:
    k = kennzahlen(t)
    kb = kennzahlen(t, "marge_brutto_pct")
    kk = konto_mit_kapital(t.sort_values("einstieg_zeit", kind="stable"), KAPITAL, MARGE)
    pos = int((t["marge_netto_pct"] > 0).sum())
    stand = KAPITAL + kk["pnl"]
    return [name, str(len(t)), f"{pos} ({de(100 * pos / len(t))} %)", de(k["erwartung_pct"] * MARGE / 100) + " €",
            de(kb["erwartung_pct"] * MARGE / 100) + " €", de(k["profit_faktor"], 2),
            de(t["marge_netto_pct"].sum() * MARGE / 100) + " €",
            f"{de(stand)} € ({kk['trades']} Trades)" + (" – keine Margin mehr frei" if kk["tiefster_stand"] < MARGE else "")]


KOPF = ["", "Trades", "davon mit Gewinn", "Ø je Trade netto", "Ø je Trade ohne Kosten", "Profit-Faktor",
        "Summe aller Signale", "Konto 10.000 € am Ende (max. 10 gleichzeitig)"]


def main() -> None:
    p, h_okx = Parameter(), Handel()
    abschnitte = []

    daten, ab = okx_daten("live_2026-11-10_2113", 120, ERGEBNISSE / "live_2026-11-10_2113_kerzen.csv.gz")
    zeilen = [zeile(n, okx_lauf(daten, ab, p, replace(h_okx, umkehr=u))[0]) for n, u in VARIANTEN]
    abschnitte.append(("OKX, letzte 2 Stunden (10.11. 19:13–21:13 MEZ), einfache klare Divergenz", zeilen))

    daten, ab = okx_daten("robust_2026-11-10_2114", 7 * 1440)
    zeilen = [zeile(n, okx_lauf(daten, ab, p, replace(h_okx, umkehr=u))[0]) for n, u in VARIANTEN]
    abschnitte.append(("OKX, 7 Tage (03.11.–10.11.), einfache klare Divergenz", zeilen))

    kerzen = ERGEBNISSE / "hyperliquid_2026-11-10_2126_kerzen.csv.gz"
    daten, coins, _, _ = musterbuch.laden(kerzen)
    ind, sig = musterbuch.signale_alle(daten, musterbuch.Muster())
    zehnfach = set(coins.loc[coins["max_hebel"] >= 10, "coin"]) & set(ind)
    for titel, auswahl in (("alle 100 Coins (10x angenommen)", set(ind)), ("nur 31 Coins mit 10x", zehnfach)):
        zeilen = [zeile(n, musterbuch.handeln(ind, sig, coins, replace(musterbuch.BASIS, umkehr=u), 7, auswahl))
                  for n, u in VARIANTEN]
        abschnitte.append((f"Hyperliquid, 3,4 Tage, 100 % Musterbuch, {titel}", zeilen))

    md = ["# Umkehr-Test: gegen das Divergenz-Signal handeln", "",
          "Gleiche Signale, gleiche Einstiegszeitpunkte, gleiche Kosten wie in den bisherigen Tests – nur die Richtung "
          "ist umgedreht. Beträge bei 1.000 € Margin und 10x Hebel (10.000 € Position); Konto 10.000 €, "
          "höchstens so viele Trades gleichzeitig, wie freie Margin da ist.", "",
          "- **Spiegel**: exakt der Gegen-Trade. Das alte Ziel wird zum Stop, der alte Stop zum Ziel. Ohne Kosten "
          "ist das Ergebnis genau das Negative des Originals.",
          "- **Gleiche Regeln**: Gegenrichtung, Stop im gleichen Abstand auf der anderen Seite, Ziel 2 × Stop.", ""]
    for titel, zeilen in abschnitte:
        md += [f"## {titel}", "", "| " + " | ".join(KOPF) + " |", "| " + " | ".join("---" for _ in KOPF) + " |"]
        md += ["| " + " | ".join(z) + " |" for z in zeilen] + [""]
    text = "\n".join(md) + "\n"
    (ERGEBNISSE / "umkehr_2026-11-10.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
