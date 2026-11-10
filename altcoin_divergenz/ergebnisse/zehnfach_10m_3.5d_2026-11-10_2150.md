# Divergenzen auf dem 10-Minuten-Chart (Hyperliquid)

Zeitraum: 07.11. 09:50 – 10.11. 21:50 Uhr (MEZ), 3,5 Tage, 10-Minuten-Kerzen. Märkte: ZEC (max. 10x), HYPE (max. 10x), SOL (max. 20x), XRP (max. 20x), NEAR (max. 10x), kPEPE (max. 10x), PUMP (max. 10x), AVAX (max. 10x), UNI (max. 10x), AAVE (max. 10x), SUI (max. 10x), DOGE (max. 10x), ARB (max. 10x), ENA (max. 10x), BNB (max. 10x), WLD (max. 10x), ADA (max. 10x), LINK (max. 10x), ONDO (max. 10x), JUP (max. 10x), TRUMP (max. 10x), XPL (max. 10x), CRV (max. 10x), FARTCOIN (max. 10x), BCH (max. 10x), DOT (max. 10x), LTC (max. 10x), TRX (max. 10x), APT (max. 10x), kSHIB (max. 10x), kBONK (max. 10x), laufend parallel geprüft.

Konto 10.000 €, je Trade 1.000 € Margin × 10 = 10.000 € Position, höchstens so viele Trades gleichzeitig, wie freie Margin da ist. Taker-Gebühr 0,0450 % je Seite, Slippage je Markt aus dem Orderbuch für eine 10.000 €-Order (Median 0,029 %).

Regeln in Kerzen: Pivot 5 links / 3 rechts, Stop 0,05 % hinter dem Pivot (0,20–3 %), Ziel 2 × Stop, Zeitstopp nach 60 Kerzen (10 h). Einfache klare Divergenz = Regeln aus dem ersten OKX-Test (RSI ≤ 35 / ≥ 65, 2 Punkte, MACD-Histogramm bestätigt, Einstieg nach Pivot-Bestätigung). Musterbuch = 7-Punkte-Checkliste plus Schlusskurs-Auslöser (siehe muster.py).

## Ergebnis

|  | Trades (Signale / im Konto) | mit Gewinn | Ø je Trade netto (95-%-Bereich) | Ø ohne Kosten | Profit-Faktor | Summe aller Signale | Konto 10.000 € am Ende |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz, alle Märkte | 80 / 79 | 34 (42 %) | 11 € (-20 € … 41 €) | 27 € | 1,22 | 894 € | 10.925 € |
| Musterbuch nahe 100 % (≥ 6/7), alle Märkte | 20 / 20 | 5 (25 %) | -56 € (-103 € … -12 €) | -40 € | 0,29 | -1.112 € | 8.888 € |
| Musterbuch 100 % (7/7), alle Märkte | 5 / 5 | 2 (40 %) | -58 € (-173 € … 55 €) | -42 € | 0,38 | -291 € | 9.709 € |

## Kosten und Haltedauer

|  | Ø Stop-Abstand | Ø Risiko je Trade | Ø Kosten je Trade | Kosten in % des Risikos | Ø Haltedauer | Ausstiege |
| --- | --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | 0,82 % | 82 € | 17 € | 21 % | 188 min | Stop-Loss 46, Take-Profit 27, Zeitstopp 6, offen (letzter Kurs) 1 |
| Musterbuch nahe 100 % (≥ 6/7) | 0,88 % | 88 € | 16 € | 18 % | 166 min | Stop-Loss 15, Take-Profit 2, Zeitstopp 2, offen (letzter Kurs) 1 |
| Musterbuch 100 % (7/7) | 1,18 % | 118 € | 18 € | 15 % | 102 min | Stop-Loss 3, Take-Profit 1, offen (letzter Kurs) 1 |

## Gegenproben (Ø je Trade netto, Anteil Gewinner)

|  | Original | ohne Kosten | Umkehr Spiegel | Umkehr gleiche Regeln | Zufall (100 Läufe) |
| --- | --- | --- | --- | --- | --- |
| Einfache klare Divergenz | 11 € (42 %) | 27 € (42 %) | -45 € (57 %) | -37 € (24 %) | -15 € (besser als Signal: 4 %) |
| Musterbuch nahe 100 % (≥ 6/7) | -56 € (25 %) | -40 € (25 %) | 2 € (72 %) | 2 € (37 %) | -16 € (besser als Signal: 96 %) |
| Musterbuch 100 % (7/7) | -58 € (40 %) | -42 € (40 %) | -28 € (50 %) | 11 € (40 %) | -24 € (besser als Signal: 70 %) |

## Konto je Tag (Ergebnis der im Konto gehandelten Trades, Anzahl in Klammern)

| Tag | Einfache klare Divergenz | Musterbuch nahe 100 % (≥ 6/7) | Musterbuch 100 % (7/7) |
| --- | --- | --- | --- |
| 07.11. (Sat) | -450 € (17) | -204 € (8) | 126 € (1) |
| 08.11. (Sun) | 1.644 € (23) | -19 € (4) | -205 € (2) |
| 09.11. (Mon) | -29 € (15) | -84 € (1) | – |
| 10.11. (Tue) | -239 € (24) | -805 € (7) | -212 € (2) |

## Alle Musterbuch-100-%-Trades

| Coin | Richtung | Einstieg | Kurs inkl. Slippage | Stop | Ziel | Ausstieg | Zeit | Kurs Δ | Ergebnis netto | im Konto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FARTCOIN | long | 07.11. 17:20 | 0.116123 | 0.115242 | 0.117695 | Take-Profit | 07.11. 19:10 | 1,41 % | 126 € | ja |
| ENA | long | 08.11. 06:20 | 0.154221 | 0.153113 | 0.156253 | Stop-Loss | 08.11. 10:20 | -0,68 % | -85 € | ja |
| WLD | long | 08.11. 14:20 | 0.328088 | 0.324548 | 0.334815 | Stop-Loss | 08.11. 14:40 | -1,04 % | -120 € | ja |
| AVAX | long | 10.11. 15:40 | 8.42513 | 8.20989 | 8.85101 | Stop-Loss | 10.11. 16:30 | -2,54 % | -266 € | ja |
| APT | long | 10.11. 21:00 | 0.55908 | 0.553423 | 0.569254 | offen (letzter Kurs) | 10.11. 21:40 | 0,77 % | 54 € | ja |

