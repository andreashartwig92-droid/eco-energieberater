# Divergenzen auf dem 1-Minuten-Chart (Hyperliquid)

Zeitraum: 07.11. 12:59 – 10.11. 21:55 Uhr (MEZ), 3,4 Tage, 1-Minuten-Kerzen. Märkte: xyz:EUR (max. 50x), xyz:JPY (max. 50x), xyz:GBP (max. 50x), laufend parallel geprüft.

Konto 10.000 €, je Trade 1.000 € Margin × 10 = 10.000 € Position, höchstens so viele Trades gleichzeitig, wie freie Margin da ist. Taker-Gebühr 0,0090 % je Seite, Slippage je Markt aus dem Orderbuch für eine 10.000 €-Order (xyz:EUR 0,015 %, xyz:JPY 0,015 %, xyz:GBP 0,046 %).

Regeln in Kerzen: Pivot 5 links / 3 rechts, Stop 0,05 % hinter dem Pivot (0,05–3 %), Ziel 2 × Stop, Zeitstopp nach 60 Kerzen (1 h). Einfache klare Divergenz = Regeln aus dem ersten OKX-Test (RSI ≤ 35 / ≥ 65, 2 Punkte, MACD-Histogramm bestätigt, Einstieg nach Pivot-Bestätigung). Musterbuch = 7-Punkte-Checkliste plus Schlusskurs-Auslöser (siehe muster.py).

## Ergebnis

|  | Trades (Signale / im Konto) | mit Gewinn | Ø je Trade netto (95-%-Bereich) | Ø ohne Kosten | Profit-Faktor | Summe aller Signale | Konto 10.000 € am Ende |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz, alle Märkte | 55 / 55 | 5 (9 %) | -7 € (-8 € … -5 €) | -1 € | 0,06 | -375 € | 9.625 € |
| Musterbuch nahe 100 % (≥ 6/7), alle Märkte | 11 / 11 | 0 (0 %) | -8 € (-10 € … -5 €) | -3 € | 0,00 | -86 € | 9.914 € |
| Musterbuch 100 % (7/7), alle Märkte | 1 / 1 | 0 (0 %) | -9 € (-9 € … -9 €) | -4 € | 0,00 | -9 € | 9.991 € |

## Je Markt (Ø je Trade netto, Anteil Gewinner)

Wochenende = Samstag und Sonntag (MEZ); der echte Devisenmarkt ist dann geschlossen.

| Markt | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| xyz:EUR | 22 Trades: -6 € (9 %); davon Wochenende 8: -7 € (12 %) | 3 Trades: -7 € (0 %); davon Wochenende 1: -9 € (0 %) | 1 Trades: -9 € (0 %); davon Wochenende 1: -9 € (0 %) |
| xyz:JPY | 25 Trades: -6 € (8 %); davon Wochenende 7: -7 € (0 %) | 8 Trades: -8 € (0 %); davon Wochenende 2: -13 € (0 %) | – |
| xyz:GBP | 8 Trades: -11 € (12 %); davon Wochenende 5: -8 € (20 %) | – | – |

## Kosten und Haltedauer

|  | Ø Stop-Abstand | Ø Risiko je Trade | Ø Kosten je Trade | Kosten in % des Risikos | Ø Haltedauer | Ausstiege |
| --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | 0,07 % | 7 € | 6 € | 83 % | 49 min | Zeitstopp 36, Stop-Loss 15, Take-Profit 2, offen (letzter Kurs) 2 |
| Musterbuch nahe 100 % (≥ 6/7) | 0,09 % | 9 € | 5 € | 55 % | 53 min | Zeitstopp 8, Stop-Loss 3 |
| Musterbuch 100 % (7/7) | 0,13 % | 13 € | 5 € | 37 % | 60 min | Zeitstopp 1 |

## Gegenproben (Ø je Trade netto, Anteil Gewinner)

|  | Original | ohne Kosten | Umkehr Spiegel | Umkehr gleiche Regeln | Zufall (100 Läufe) |
| --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | -7 € (9 %) | -1 € (35 %) | -4 € (25 %) | -6 € (16 %) | -6 € (besser als Signal: 80 %) |
| Musterbuch nahe 100 % (≥ 6/7) | -8 € (0 %) | -3 € (27 %) | -1 € (36 %) | -2 € (36 %) | -5 € (besser als Signal: 89 %) |
| Musterbuch 100 % (7/7) | -9 € (0 %) | -4 € (0 %) | -0 € (0 %) | -0 € (0 %) | -4 € (besser als Signal: 80 %) |

## Konto je Tag (Ergebnis der im Konto gehandelten Trades, Anzahl in Klammern)

| Tag | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| 07.11. (Sat) | -36 € (5) | – | – |
| 08.11. (Sun) | -103 € (15) | -36 € (3) | -9 € (1) |
| 09.11. (Mon) | -111 € (20) | -40 € (5) | – |
| 10.11. (Tue) | -124 € (15) | -11 € (3) | – |

## Alle Musterbuch-100-%-Trades

| Coin | Richtung | Einstieg | Kurs inkl. Slippage | Stop | Ziel | Ausstieg | Zeit | Kurs Δ | Ergebnis netto | im Konto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xyz:EUR | long | 08.11. 21:19 | 1.11667 | 1.11504 | 1.11942 | Zeitstopp | 08.11. 22:18 | -0,04 % | -9 € | ja |

