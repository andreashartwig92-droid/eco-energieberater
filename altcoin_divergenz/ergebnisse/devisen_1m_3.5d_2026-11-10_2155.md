# Divergenzen auf dem 1-Minuten-Chart (Hyperliquid)

Zeitraum: 07.11. 12:59 – 10.11. 21:55 Uhr (MEZ), 3,4 Tage, 1-Minuten-Kerzen. Märkte: xyz:EUR (max. 50x), xyz:JPY (max. 50x), xyz:GBP (max. 50x), laufend parallel geprüft.

Konto 10.000 €, je Trade 1.000 € Margin × 10 = 10.000 € Position, höchstens so viele Trades gleichzeitig, wie freie Margin da ist. Taker-Gebühr 0,0090 % je Seite, Slippage je Markt aus dem Orderbuch für eine 10.000 €-Order (xyz:EUR 0,015 %, xyz:JPY 0,015 %, xyz:GBP 0,046 %).

Regeln in Kerzen: Pivot 5 links / 3 rechts, Stop 0,05 % hinter dem Pivot (0,20–3 %), Ziel 2 × Stop, Zeitstopp nach 60 Kerzen (1 h). Einfache klare Divergenz = Regeln aus dem ersten OKX-Test (RSI ≤ 35 / ≥ 65, 2 Punkte, MACD-Histogramm bestätigt, Einstieg nach Pivot-Bestätigung). Musterbuch = 7-Punkte-Checkliste plus Schlusskurs-Auslöser (siehe muster.py).

## Ergebnis

|  | Trades (Signale / im Konto) | mit Gewinn | Ø je Trade netto (95-%-Bereich) | Ø ohne Kosten | Profit-Faktor | Summe aller Signale | Konto 10.000 € am Ende |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz, alle Märkte | 52 / 52 | 3 (6 %) | -7 € (-9 € … -5 €) | -1 € | 0,04 | -364 € | 9.636 € |
| Musterbuch nahe 100 % (≥ 6/7), alle Märkte | 11 / 11 | 0 (0 %) | -8 € (-11 € … -6 €) | -3 € | 0,00 | -89 € | 9.911 € |
| Musterbuch 100 % (7/7), alle Märkte | 1 / 1 | 0 (0 %) | -9 € (-9 € … -9 €) | -4 € | 0,00 | -9 € | 9.991 € |

## Je Markt (Ø je Trade netto, Anteil Gewinner)

Wochenende = Samstag und Sonntag (MEZ); der echte Devisenmarkt ist dann geschlossen.

| Markt | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| xyz:EUR | 21 Trades: -6 € (5 %); davon Wochenende 7: -6 € (0 %) | 3 Trades: -7 € (0 %); davon Wochenende 1: -9 € (0 %) | 1 Trades: -9 € (0 %); davon Wochenende 1: -9 € (0 %) |
| xyz:JPY | 23 Trades: -6 € (4 %); davon Wochenende 7: -6 € (0 %) | 8 Trades: -9 € (0 %); davon Wochenende 2: -11 € (0 %) | – |
| xyz:GBP | 8 Trades: -12 € (12 %); davon Wochenende 5: -8 € (20 %) | – | – |

## Kosten und Haltedauer

|  | Ø Stop-Abstand | Ø Risiko je Trade | Ø Kosten je Trade | Kosten in % des Risikos | Ø Haltedauer | Ausstiege |
| --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | 0,20 % | 20 € | 6 € | 29 % | 57 min | Zeitstopp 48, Stop-Loss 2, offen (letzter Kurs) 2 |
| Musterbuch nahe 100 % (≥ 6/7) | 0,20 % | 20 € | 5 € | 24 % | 60 min | Zeitstopp 11 |
| Musterbuch 100 % (7/7) | 0,20 % | 20 € | 5 € | 24 % | 60 min | Zeitstopp 1 |

## Gegenproben (Ø je Trade netto, Anteil Gewinner)

|  | Original | ohne Kosten | Umkehr Spiegel | Umkehr gleiche Regeln | Zufall (100 Läufe) |
| --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | -7 € (6 %) | -1 € (37 %) | -5 € (15 %) | -4 € (16 %) | -6 € (besser als Signal: 81 %) |
| Musterbuch nahe 100 % (≥ 6/7) | -8 € (0 %) | -3 € (27 %) | -2 € (36 %) | -2 € (36 %) | -5 € (besser als Signal: 91 %) |
| Musterbuch 100 % (7/7) | -9 € (0 %) | -4 € (0 %) | -0 € (0 %) | -0 € (0 %) | -5 € (besser als Signal: 80 %) |

## Konto je Tag (Ergebnis der im Konto gehandelten Trades, Anzahl in Klammern)

| Tag | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| 07.11. (Sat) | -31 € (4) | – | – |
| 08.11. (Sun) | -100 € (14) | -32 € (3) | -9 € (1) |
| 09.11. (Mon) | -91 € (19) | -47 € (5) | – |
| 10.11. (Tue) | -142 € (15) | -11 € (3) | – |

## Alle Musterbuch-100-%-Trades

| Coin | Richtung | Einstieg | Kurs inkl. Slippage | Stop | Ziel | Ausstieg | Zeit | Kurs Δ | Ergebnis netto | im Konto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xyz:EUR | long | 08.11. 21:19 | 1.11667 | 1.11427 | 1.12097 | Zeitstopp | 08.11. 22:18 | -0,04 % | -9 € | ja |

