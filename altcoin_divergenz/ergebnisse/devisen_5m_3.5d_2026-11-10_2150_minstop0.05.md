# Divergenzen auf dem 5-Minuten-Chart (Hyperliquid)

Zeitraum: 07.11. 09:50 – 10.11. 21:50 Uhr (MEZ), 3,5 Tage, 5-Minuten-Kerzen. Märkte: xyz:EUR (max. 50x), xyz:JPY (max. 50x), xyz:GBP (max. 50x), laufend parallel geprüft.

Konto 10.000 €, je Trade 1.000 € Margin × 10 = 10.000 € Position, höchstens so viele Trades gleichzeitig, wie freie Margin da ist. Taker-Gebühr 0,0090 % je Seite, Slippage je Markt aus dem Orderbuch für eine 10.000 €-Order (xyz:EUR 0,014 %, xyz:JPY 0,015 %, xyz:GBP 0,032 %).

Regeln in Kerzen: Pivot 5 links / 3 rechts, Stop 0,05 % hinter dem Pivot (0,05–3 %), Ziel 2 × Stop, Zeitstopp nach 60 Kerzen (5 h). Einfache klare Divergenz = Regeln aus dem ersten OKX-Test (RSI ≤ 35 / ≥ 65, 2 Punkte, MACD-Histogramm bestätigt, Einstieg nach Pivot-Bestätigung). Musterbuch = 7-Punkte-Checkliste plus Schlusskurs-Auslöser (siehe muster.py).

## Ergebnis

|  | Trades (Signale / im Konto) | mit Gewinn | Ø je Trade netto (95-%-Bereich) | Ø ohne Kosten | Profit-Faktor | Summe aller Signale | Konto 10.000 € am Ende |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz, alle Märkte | 14 / 14 | 4 (29 %) | -6 € (-13 € … 3 €) | -1 € | 0,40 | -80 € | 9.920 € |
| Musterbuch nahe 100 % (≥ 6/7), alle Märkte | 3 / 3 | 2 (67 %) | 8 € (-19 € … 41 €) | 13 € | 2,24 | 23 € | 10.023 € |
| Musterbuch 100 % (7/7), alle Märkte | 1 / 1 | 0 (0 %) | -19 € (-19 € … -19 €) | -10 € | 0,00 | -19 € | 9.981 € |

## Je Markt (Ø je Trade netto, Anteil Gewinner)

Wochenende = Samstag und Sonntag (MEZ); der echte Devisenmarkt ist dann geschlossen.

| Markt | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| xyz:EUR | 8 Trades: -4 € (25 %); davon Wochenende 2: -16 € (0 %) | 1 Trades: 41 € (100 %) | – |
| xyz:JPY | 3 Trades: -7 € (33 %); davon Wochenende 1: 0 € (100 %) | 1 Trades: 1 € (100 %); davon Wochenende 1: 1 € (100 %) | – |
| xyz:GBP | 3 Trades: -9 € (33 %); davon Wochenende 1: 11 € (100 %) | 1 Trades: -19 € (0 %); davon Wochenende 1: -19 € (0 %) | 1 Trades: -19 € (0 %); davon Wochenende 1: -19 € (0 %) |

## Kosten und Haltedauer

|  | Ø Stop-Abstand | Ø Risiko je Trade | Ø Kosten je Trade | Kosten in % des Risikos | Ø Haltedauer | Ausstiege |
| --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | 0,10 % | 10 € | 5 € | 53 % | 163 min | Stop-Loss 6, Zeitstopp 5, Take-Profit 2, offen (letzter Kurs) 1 |
| Musterbuch nahe 100 % (≥ 6/7) | 0,22 % | 22 € | 6 € | 27 % | 287 min | Zeitstopp 2, Take-Profit 1 |
| Musterbuch 100 % (7/7) | 0,30 % | 30 € | 8 € | 28 % | 300 min | Zeitstopp 1 |

## Gegenproben (Ø je Trade netto, Anteil Gewinner)

|  | Original | ohne Kosten | Umkehr Spiegel | Umkehr gleiche Regeln | Zufall (100 Läufe) |
| --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | -6 € (29 %) | -1 € (29 %) | -5 € (50 %) | -5 € (43 %) | -5 € (besser als Signal: 51 %) |
| Musterbuch nahe 100 % (≥ 6/7) | 8 € (67 %) | 13 € (67 %) | -19 € (33 %) | -12 € (33 %) | -6 € (besser als Signal: 5 %) |
| Musterbuch 100 % (7/7) | -19 € (0 %) | -10 € (0 %) | 2 € (100 %) | 2 € (100 %) | -8 € (besser als Signal: 77 %) |

## Konto je Tag (Ergebnis der im Konto gehandelten Trades, Anzahl in Klammern)

| Tag | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| 08.11. (Sun) | -20 € (4) | -17 € (2) | -19 € (1) |
| 09.11. (Mon) | -52 € (5) | – | – |
| 10.11. (Tue) | -8 € (5) | 41 € (1) | – |

## Alle Musterbuch-100-%-Trades

| Coin | Richtung | Einstieg | Kurs inkl. Slippage | Stop | Ziel | Ausstieg | Zeit | Kurs Δ | Ergebnis netto | im Konto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xyz:GBP | short | 08.11. 09:20 | 1.33377 | 1.33817 | 1.32626 | Zeitstopp | 08.11. 14:15 | -0,10 % | -19 € | ja |

