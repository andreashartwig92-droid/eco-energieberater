# Altcoin-Divergenz-Konzept: Prüfung per Backtest

**Konzept:** 100 Altcoins auf dem 1-Minuten-Chart beobachten und nur dann handeln, wenn eine klare bullische
oder bärische Divergenz zwischen Kurs, RSI und MACD auftritt. Gehandelt wird mit 10x Hebel, das Kapital ist 1.000 €.

Das Skript holt echte 1-Minuten-Kerzen von der öffentlichen OKX-API, sucht die Signale ohne Blick in die
Zukunft und rechnet jeden Trade mit Gebühren und Slippage durch. Es werden **keine echten Orders** platziert.

```bash
python3 -m altcoin_divergenz live              # letzte 2 Stunden (plus 5 h Vorlauf für die Indikatoren)
python3 -m altcoin_divergenz robust --tage 7   # dieselben Regeln über 7 Tage
python3 -m altcoin_divergenz live --kerzen altcoin_divergenz/ergebnisse/live_2026-11-10_2113_kerzen.csv.gz
```

Ergebnisse landen in `altcoin_divergenz/ergebnisse/` (Bericht `.md`, Tradeliste `.csv`, beim Live-Lauf auch
die Kerzen zum exakten Wiederholen). Tests: `python3 -m unittest tests.test_altcoin_divergenz`.

## Regeln

| | |
| --- | --- |
| Coins | die 100 Krypto-USDT-Perpetuals mit dem höchsten 24-h-Umsatz auf OKX, ohne BTC, ETH, Stablecoins, Gold-Token, Aktien und Rohstoffe |
| Chart | 1 Minute, nur abgeschlossene Kerzen |
| Indikatoren | RSI 14 (Wilder), MACD 12/26/9 |
| Pivot | Tief/Hoch, das 5 Kerzen links und 3 Kerzen rechts nicht unter-/überboten wird; bestätigt erst nach diesen 3 Kerzen |
| Bullische Divergenz (Long) | Kurs: tieferes Tief. RSI: mindestens 2 Punkte höheres Tief, erstes Tief ≤ 35. MACD-Histogramm: beim ersten Tief negativ, beim zweiten höher. Abstand der Tiefs 5–60 Kerzen |
| Bärische Divergenz (Short) | spiegelbildlich an den Hochs, RSI beim ersten Hoch ≥ 65 |
| Einstieg | Eröffnung der Kerze nach der Bestätigung, Market-Order |
| Stop-Loss | 0,05 % hinter dem zweiten Pivot, mindestens 0,2 %, höchstens 3 % Abstand (sonst kein Trade) |
| Take-Profit | 2 × Stop-Abstand (CRV 1:2) |
| Zeitstopp | 60 Minuten; was am Ende des Testfensters noch offen ist, wird zum letzten Kurs bewertet |
| Kosten | OKX-Taker-Gebühr 0,05 % je Seite, Slippage 0,02 % je Market-Order. Bei 10x Hebel sind das ≈ 1,4 % der Margin je Trade |
| Positionen | je Coin höchstens eine gleichzeitig. Liegt beim gleichen Kerzenhoch Stop und Ziel, zählt der Stop |

Kapitalaufteilung (1.000 €, kein Zinseszins), beide Varianten werden ausgewiesen:

1. **10 € Margin je Coin** (1.000 € / 100 Coins) → 100 € Position je Trade, alle Coins können gleichzeitig laufen.
2. **100 € Margin je Trade** → 1.000 € Position, höchstens 10 Trades gleichzeitig, weitere Signale verfallen.

Zur Einordnung läuft jedes Mal eine **Zufalls-Kontrollgruppe**: gleich viele Trades mit denselben
Stop-Abständen, Zielen, Kosten und Hebel, aber zufälligem Coin, Zeitpunkt und Richtung. Eine Strategie mit
echtem Vorteil muss diese Kontrollgruppe klar schlagen.

## Ergebnisse (10.11.2026)

Vollständige Berichte: [`ergebnisse/live_2026-11-10_2113.md`](ergebnisse/live_2026-11-10_2113.md) (mit allen
68 Trades) und [`ergebnisse/robust_2026-11-10_2114.md`](ergebnisse/robust_2026-11-10_2114.md).

| | Letzte 2 Stunden (19:13–21:13 MEZ) | 7 Tage (03.11.–10.11.) |
| --- | --- | --- |
| Klare Divergenz-Signale / gehandelt | 73 / 68 | 7.230 / 6.694 (≈ 950 Trades pro Tag) |
| Trefferquote | 43 % | 36 % |
| Ø je Trade **ohne** Kosten (Margin) | +0,62 % | +0,28 % (95 %: +0,12 … +0,45) |
| Ø je Trade **mit** Kosten (Margin) | −0,71 % | −1,06 % (95 %: −1,22 … −0,89) |
| Profit-Faktor netto | 0,74 | 0,67 |
| Zufalls-Kontrollgruppe netto | −1,26 % | −1,30 % |
| 1.000 €, 10 € Margin je Coin | −4,81 € | −710 €, jeder einzelne Tag im Minus |
| 1.000 €, 100 € Margin je Trade, max. 10 | −60,39 € | Konto am 06.11. um 04:26 Uhr aufgebraucht (nach 1.343 Trades) |

**Bewertung:**

- Die Divergenzen haben einen **messbaren, aber winzigen Vorteil**: ohne Kosten +0,28 % der Margin je Trade, das
  sind 0,03 % Kursbewegung. Gegen die Zufallsgruppe ist das über 7 Tage eindeutig, über 2 Stunden nicht unterscheidbar.
- Die **Kosten sind fünfmal so groß wie der Vorteil**: 0,14 % Kurs je Trade (Gebühren + Slippage) = 1,4 % der
  Margin bei 10x. Bei den häufigen 0,2-%-Stops wird aus dem geplanten CRV 1:2 netto +2,8 % gegen −3,4 %, also nur
  noch 1:0,8. Die nötige Trefferquote steigt bei diesen Trades von 33 % auf rund 55 %.
- **Kein Parameter rettet das**: CRV 1, 1,5 oder 3, strengere RSI-Grenzen (30/70) oder ohne MACD-Filter liegen
  alle bei etwa −1 % je Trade. Selbst mit Maker-Gebühr 0,02 % und ohne Slippage (in der Praxis nicht
  erreichbar, weil Stops Market-Orders sind) bleibt es bei −0,12 %.
- **100 Coins sind keine 100 unabhängigen Wetten**: Die 1-Minuten-Renditen der Coins korrelieren im Mittel mit 0,4.
  In den 2 Stunden fielen 27 der 41 Longs in zwei Fünf-Minuten-Fenster (20:25 und 20:40 Uhr). Das ist eine
  einzige Wette auf eine Erholung des ganzen Altcoin-Markts, verteilt auf viele Coins.
- Der Hebel ändert am Vorzeichen nichts, er vergrößert nur Gewinne, Verluste und Kosten im gleichen Verhältnis.

## Grenzen des Tests

- Die Coin-Auswahl beruht auf dem heutigen 24-h-Umsatz und wurde für die 7 Tage beibehalten.
- Slippage ist pauschal angesetzt. Bei kleinen Coins und Stops in schnellen Bewegungen ist sie real eher höher.
- Funding-Gebühren fehlen; bei Haltedauern von Ø 21 Minuten fallen sie kaum ins Gewicht.
- Innerhalb einer 1-Minuten-Kerze ist die Reihenfolge von Hoch und Tief unbekannt. Liegen Stop und Ziel in
  derselben Kerze, zählt der Stop (konservativ).
- 7 Tage sind ein einzelnes Marktumfeld. Für ein abschließendes Urteil wären mehrere Monate nötig, das
  Ergebnis netto liegt aber so deutlich im Minus, dass sich daran wenig ändern dürfte.
