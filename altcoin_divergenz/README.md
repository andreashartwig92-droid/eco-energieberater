# Altcoin-Divergenz-Konzept: Prüfung per Backtest

**Konzept:** 100 Altcoins auf dem 1-Minuten-Chart beobachten und nur dann handeln, wenn eine klare bullische
oder bärische Divergenz zwischen Kurs, RSI und MACD auftritt. Gehandelt wird mit 10x Hebel, das Kapital ist 1.000 €.

Das Skript holt echte 1-Minuten-Kerzen von der öffentlichen OKX-API, sucht die Signale ohne Blick in die
Zukunft und rechnet jeden Trade mit Gebühren und Slippage durch. Es werden **keine echten Orders** platziert.

```bash
python3 -m altcoin_divergenz live              # letzte 2 Stunden (plus 5 h Vorlauf für die Indikatoren)
python3 -m altcoin_divergenz robust --tage 7   # dieselben Regeln über 7 Tage
python3 -m altcoin_divergenz live --kerzen altcoin_divergenz/ergebnisse/live_2026-11-10_2113_kerzen.csv.gz
python3 -m altcoin_divergenz muster            # nur Musterbuch-Divergenzen, Hyperliquid, 10.000 € Konto
```

Zweiter Test weiter unten: [Musterbuch-Divergenzen auf Hyperliquid](#musterbuch-divergenzen-auf-hyperliquid).

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

## Musterbuch-Divergenzen auf Hyperliquid

**Fragestellung:** Alle 100 Altcoins laufend parallel auf dem 1-Minuten-Chart prüfen, aber nur traden, wenn die
Divergenz wie aus dem Lehrbuch aussieht. Gibt es kein Musterbuch-Signal, wird nicht gehandelt. Konto 10.000 €, jeder
Trade 1.000 € Margin mit 10x Hebel (= 10.000 € Position), damit höchstens 10 Trades gleichzeitig.

Daten: Hyperliquid-Perpetuals, die 100 umsatzstärksten Altcoins (ohne BTC, ETH, PAXG), 1-Minuten-Kerzen über die
gesamte Historie, die Hyperliquid herausgibt (die jüngsten 5.000 Minuten = 07.11. 12:36 bis 10.11. 21:26 Uhr MEZ).
Gebühr: Taker 0,045 % je Seite. Slippage je Coin aus dem Orderbuch für eine 10.000-€-Order gemessen
(Momentaufnahme 10.11. abends).

**Musterbuch-Checkliste** (`muster.py`). Pflicht ist eine reguläre Divergenz aus zwei sauberen Swing-Pivots im Abstand
von 8–60 Kerzen und ein Auslöser: Schlusskurs über dem Hoch (Long) bzw. unter dem Tief (Short) der zweiten
Pivot-Kerze. Dazu sieben Prüfpunkte:

| | Long (bullisch) – Short spiegelbildlich |
| --- | --- |
| M1 | RSI am ersten Tief ≤ 30 (überverkauft) |
| M2 | RSI-Tief mindestens 5 Punkte höher |
| M3 | MACD-Histogramm am ersten Tief negativ, am zweiten höher |
| M4 | MACD-Linie am zweiten Tief ebenfalls höher |
| M5 | RSI-Verbindungslinie sauber, kein RSI-Wert dazwischen darunter |
| M6 | Kurs-Verbindungslinie sauber, keine Kerze dazwischen darunter |
| M7 | zwei getrennte Swings: RSI erholt sich dazwischen um mindestens 10 Punkte |

„100 % Musterbuch“ = 7/7, „nahe 100 %“ = mindestens 6/7. Beispiele im Chart:
[`ergebnisse/hyperliquid_2026-11-10_2126_beispiele.png`](ergebnisse/hyperliquid_2026-11-10_2126_beispiele.png).

**Ergebnis** (Bericht mit allen Trades: [`ergebnisse/hyperliquid_2026-11-10_2126.md`](ergebnisse/hyperliquid_2026-11-10_2126.md)):

| 3,4 Tage, 10.000 € Konto | Trades | Treffer | Ø je Trade | Konto am Ende | ohne Kosten |
| --- | --- | --- | --- | --- | --- |
| 100 % Musterbuch, alle 100 Coins (10x angenommen) | 220 | 28 % | −35 € | 1.564 € (−8.436 €) | −379 € |
| 100 % Musterbuch, nur die 31 Coins mit 10x auf Hyperliquid | 76 | 26 % | −21 € | 8.412 € (−1.588 €) | −403 € |
| ≥ 6/7, alle Coins | 253 | 31 % | −33 € | 952 €, danach keine Margin mehr | +1.600 € |
| ≥ 6/7, nur 10x-Coins | 232 | 32 % | −16 € | 6.415 € (−3.585 €) | +3 € |

- Musterbuch-Signale sind seltener, aber nicht selten: rund **85 pro Tag** über 100 Coins (4 % aller Divergenzen).
- Sie sind **nicht besser als Zufall**. Ohne jede Kosten liegt der Schnitt bei −1 € je Trade (95 %: −7 … +4 €).
  Trades mit zufälligem Coin, Zeitpunkt und Richtung kommen netto auf −34 €, Musterbuch auf −35 €.
- Die Kosten fressen den Rest: Ø 38 € je Trade, davon 9 € Gebühren, der Rest Slippage. Bei kleinen Coins kostet eine
  10.000-€-Market-Order bis zu 1 % je Seite.
- **Hebel:** Nur 31 der 100 Coins erlauben auf Hyperliquid 10x, 36 nur 5x, 33 nur 3x. Für die übrigen 69 Coins ist
  das Konzept dort gar nicht umsetzbar.
- Jeder einzelne Tag endete im Minus.


## Umkehr-Test: gegen das Signal handeln

`python3 -m altcoin_divergenz umkehr` – Bericht: [`ergebnisse/umkehr_2026-11-10.md`](ergebnisse/umkehr_2026-11-10.md).

Idee: Bei 36 % Trefferquote einfach umgekehrt handeln (Short-Signal → Long, Long-Signal → Short). Getestet mit
denselben Signalen, Einstiegen und Kosten wie oben, in zwei Formen:

- **Spiegel:** exakt der Gegen-Trade. Altes Ziel = neuer Stop, alter Stop = neues Ziel (CRV 2:1).
- **Gleiche Regeln:** Gegenrichtung, Stop im gleichen Abstand auf der anderen Seite, Ziel 2 × Stop (CRV 1:2).

| Ø je Trade netto (1.000 € Margin, 10x) | Original | Spiegel | gleiche Regeln |
| --- | --- | --- | --- |
| OKX, 2 Stunden | −7 € (43 % Gewinner) | −20 € (49 %) | −11 € (26 %) |
| OKX, 7 Tage | −11 € (36 %) | −16 € (59 %) | −15 € (33 %) |
| Hyperliquid Musterbuch, alle Coins | −35 € (28 %) | −31 € (46 %) | −35 € (29 %) |
| Hyperliquid Musterbuch, 10x-Coins | −21 € (26 %) | −9 € (63 %) | −20 € (28 %) |

Die Umkehr hilft nicht. Beim Spiegel steigt die Trefferquote, aber jeder Gewinn ist nur halb so groß wie jeder
Verlust. Ohne Kosten ist der Spiegel genau das Negative des Originals, also ebenfalls rund null. Die Kosten fallen
aber bei jedem Trade an, egal in welche Richtung. Umkehren lohnt sich nur, wenn das Original **vor** Kosten deutlich
verliert, und zwar um mehr als die Kosten (≈ 14 € je Trade auf OKX). Das Original liegt vor Kosten aber bei
+3 € (OKX) bzw. −1 € bis −5 € (Hyperliquid), also praktisch bei null.

## 5-Minuten-Chart (Hyperliquid, 100 Altcoins, 3,5 Tage)

`python3 -m altcoin_divergenz zeitrahmen` – Bericht: [`ergebnisse/zeitrahmen_5m_2026-11-10_2145.md`](ergebnisse/zeitrahmen_5m_2026-11-10_2145.md).
Zum direkten Vergleich wurde dasselbe Skript auf die 1-Minuten-Daten angewendet:
[`ergebnisse/zeitrahmen_1m_2026-11-10_2126.md`](ergebnisse/zeitrahmen_1m_2026-11-10_2126.md).

Dieselben Regeln, gezählt in Kerzen (Zeitstopp 60 Kerzen = 5 Stunden), dieselben Coins, Gebühren, Slippage aus dem
Orderbuch und 10.000 € Konto mit 1.000 € Margin je Trade bei 10x. Zeitraum 07.11. 09:45 – 10.11. 21:45 Uhr MEZ.

| Ø je Trade netto (Anteil Gewinner) · Konto am Ende | 1 Minute | 5 Minuten |
| --- | --- | --- |
| Einfache klare Divergenz, alle Coins | −35 € (30 %) · 802 €, Konto leer | −29 € (36 %) · 3.233 € |
| Einfache klare Divergenz, nur 10x-Coins | −13 € (33 %) · 2.605 € | −8 € (40 %) · 8.518 € |
| Musterbuch 100 %, alle Coins | −35 € (28 %) · 1.564 € | −25 € (35 %) · 9.421 € |
| Musterbuch 100 %, nur 10x-Coins | −21 € (26 %) · 8.412 € | +5 € (40 %) · 10.054 € (nur 10 Trades) |
| Signale (einfach / Musterbuch 100 %) | 3.133 / 274 | 664 / 23 |
| Kosten in % des Risikos je Trade | 113–127 % | 50–66 % |

- Auf 5 Minuten sind die Stops etwa doppelt so weit (Ø 0,6–0,7 % statt 0,3 %). Die Kosten je Trade bleiben gleich,
  fressen aber nur noch die Hälfte statt mehr als das ganze Risiko. Die Verluste werden dadurch kleiner, verschwinden
  aber nicht.
- Vor Kosten liegen alle Signalarten leicht im Plus (+6 bis +8 € je Trade), statistisch aber nicht von null zu
  unterscheiden (einfache Divergenz, alle Coins: 95 % zwischen −1 € und +18 €). Nach Kosten sind es −8 bis −29 €.
- Die einzige positive Zeile (Musterbuch 100 %, 10x-Coins) beruht auf 10 Trades, von denen zwei Gewinner das Ergebnis
  tragen. Der 95-%-Bereich reicht von −48 € bis +64 € je Trade, die Zeile sagt also nichts.
- Umkehren hilft auch auf 5 Minuten nicht (einfache Divergenz: −40 € bzw. −45 € statt −29 € je Trade).

## Devisenpaare auf Hyperliquid

Hyperliquid führt genau drei Devisenpaare, alle auf der HIP-3-Börse „xyz“ mit bis zu 50x Hebel: `xyz:EUR`
(EUR/USD), `xyz:JPY` (USD/JPY) und `xyz:GBP` (GBP/USD). Alles andere dort sind Krypto-Coins, Aktien, Indizes und
Rohstoffe. Das Konzept „100 Paare parallel“ lässt sich mit Devisen also nicht umsetzen, es bleiben drei.

```bash
python3 -m altcoin_divergenz zeitrahmen --name devisen --maerkte xyz:EUR,xyz:JPY,xyz:GBP --gebuehr 0.009 --intervall 5m --tage 3.5
```

Gleiche Signale und Regeln, 10.000 € Konto, 1.000 € Margin bei 10x je Trade. Die Märkte laufen im „Growth Mode“, die
Gebühr ist daher mit 0,009 % je Seite angesetzt (10 % der Protokollgebühr plus gleich hoher Anteil des Betreibers).
Slippage aus dem Orderbuch: EUR 0,014 %, JPY 0,015 %, GBP 0,032 %. Die Märkte handeln dünn: auf 1 Minute gab es bei
EUR in 46 %, bei JPY in 70 % und bei GBP in 93 % der Minuten keinen einzigen Handel.

Ø je Trade netto, Trades in Klammern:

| | 5 min, 3,5 Tage | 5 min, 16,8 Tage | 1 min, 3,4 Tage |
| --- | --- | --- | --- |
| Einfache klare Divergenz | −8 € (14) | −9 € (66) | −7 € (52) |
| Musterbuch ≥ 6/7 | +8 € (3) | −7 € (16) | −8 € (11) |
| Musterbuch 100 % | −19 € (1) | −20 € (4) | −9 € (1) |
| Konto am Ende, einfache Divergenz | 9.888 € | 9.409 € | 9.636 € |
| dasselbe mit Mindest-Stop 0,05 % statt 0,2 % | −6 € (14) | −7 € (78) | −7 € (55) |

- Es gibt kaum Signale: auf 5 Minuten etwa 4 pro Tag über alle drei Paare, Musterbuch 100 % nur 4 in 17 Tagen.
- Vor Kosten liegt der Schnitt bei −3 € bis +1 € je Trade, also bei null. Die Divergenzen haben auch bei Devisen
  keinen erkennbaren Vorteil. Trades mit zufälligem Zeitpunkt und zufälliger Richtung schneiden gleich gut oder
  besser ab (17 Tage, einfache Divergenz: Zufall −6 €, Signal −9 € je Trade).
- Die Kosten sind mit 5–6 € je Trade viel niedriger als bei Altcoins (36–41 €). Devisen bewegen sich auf 1 und 5
  Minuten aber so wenig, dass die meisten Trades weder Stop noch Ziel erreichen und per Zeitstopp enden. Deshalb
  bleiben die Verluste klein, Gewinne entstehen aber auch nicht.
- Die einzige positive Zelle (+8 €, Musterbuch ≥ 6/7, 3,5 Tage) beruht auf 3 Trades und sagt nichts.
- Die Devisen-Perps handeln auch am Wochenende, obwohl der echte Devisenmarkt dann geschlossen ist. Ein Teil der
  Signale fällt auf Samstag und Sonntag (siehe Berichte).

Berichte: `ergebnisse/devisen_*.md` (je mit und ohne `_minstop0.05`).

## 100 % Musterbuch, nur 10x-Coins: 5 gegen 10 Minuten

Die 31 Coins mit 10x Hebel auf Hyperliquid (Liste aus dem 5-Minuten-Test). Hyperliquid liefert keine 10-Minuten-Kerzen;
sie werden aus je zwei 5-Minuten-Kerzen gebaut (`hyperliquid.zusammenfassen`). Gleiche Regeln in Kerzen, auf 10 Minuten
also Zeitstopp nach 10 Stunden. Konto 10.000 €, 1.000 € Margin bei 10x je Trade.

```bash
python3 -m altcoin_divergenz zeitrahmen --name zehnfach --maerkte ZEC,HYPE,SOL,... --intervall 10m --tage 3.5
```

| 100 % Musterbuch, 31 Coins mit 10x | 5 min, 3,5 Tage | 10 min, 3,5 Tage | 5 min, 16 Tage | 10 min, 16 Tage |
| --- | --- | --- | --- | --- |
| Trades | 10 | 5 | 46 | 20 |
| davon mit Gewinn | 4 (40 %) | 2 (40 %) | 18 (39 %) | 8 (40 %) |
| Ø je Trade netto | +5 € | −58 € | −4 € | −22 € |
| 95-%-Bereich | −48 … +64 € | −173 … +55 € | −38 … +34 € | −89 … +50 € |
| Ø je Trade ohne Kosten | +22 € | −42 € | +11 € | −6 € |
| Konto 10.000 € am Ende | 10.054 € | 9.709 € | 9.825 € | 9.565 € |

- Auf 10 Minuten gibt es 100-%-Musterbuch-Signale nur noch etwa einmal am Tag (20 in 16 Tagen über 31 Coins).
- Die Kosten sind kein Hindernis mehr (15 % des Risikos je Trade), aber vor Kosten liegt das Ergebnis bei −6 €
  je Trade. Zufällige Trades mit denselben Stops schneiden genauso ab (−18 € gegen −22 € netto).
- Über 16 Tage ist 5 Minuten (−4 €) etwas besser als 10 Minuten (−22 €); beide Bereiche schließen null ein.
  Ein Vorteil ist mit so wenigen Trades weder zu belegen noch auszuschließen.
- Nebenbefund: die einfache klare Divergenz auf 10 Minuten lag in den 3,5 Tagen bei +11 € je Trade (Konto
  10.925 €), über 16 Tage aber bei −7 € je Trade (Konto 9.928 €). Die 3,5 Tage waren ein günstiger Ausschnitt.

Berichte: `ergebnisse/zehnfach_*.md`.

## Merkmale von Gewinnern und Verlierern (Brainstorming-Grundlage)

`python3 -m altcoin_divergenz merkmale` – Bericht: [`ergebnisse/merkmale_2026-11-10.md`](ergebnisse/merkmale_2026-11-10.md),
alle Trades mit Merkmalen: `ergebnisse/merkmale_2026-11-10_trades.csv`.

31 Coins mit 10x, 5-Minuten-Chart, alle Divergenzen mit Auslöser (Musterbuch-Basis), Hyperliquid-Kosten. Je Trade
32 Merkmale zum Signalzeitpunkt: Musterbuch-Punkte M1–M7, Volumen (Auslöser-Kerze, 2. gegen 1. Pivot),
Stochastik 14/3/3 (Lage, Kreuzung, eigene Divergenz), ADX, ATR, EMA 50/200, Bollinger, RSI auf 1 Stunde, Lage in der
24-h-Spanne, BTC-Lage, Tageszeit, Wochenende, Signal-Häufung über alle Coins.

Drei Zeiträume gegen Zufallsfunde: **Entdeckung** (Hyperliquid 25.10.–02.11., 767 Trades), **Prüfung** (Hyperliquid
02.–10.11., 803 Trades) und eine unabhängige **Gegenprobe** mit denselben Coins im Oktober (OKX-Kurse 01.–24.10.,
2.381 Trades).

- Gewinner und Verlierer sehen beim Einstieg praktisch gleich aus. Beispiele (Median Gewinner / Verlierer):
  Stochastik am 2. Pivot 20,4 / 19,6; Volumen der Auslöser-Kerze 0,67 / 0,65 × Durchschnitt; RSI-Divergenz
  3,95 / 4,00 Punkte; Musterbuch-Punkte 3 / 3.
- Ein automatisch gesuchter Filter aus drei Regeln hebt die Entdeckung von −3 € auf +52 € je Trade (56 % Treffer).
  In der Prüfung bringt derselbe Filter −16 €, im Oktober −19 € je Trade: Er hat nur die Zufälle der ersten 8 Tage
  gelernt.
- Einige Merkmale zeigen in allen drei Zeiträumen in dieselbe Richtung, aber schwach, und der „gute“ Bereich bleibt
  überall im Minus: Wochenende (Oktober −6 € statt −24 €), mittlerer Pivot-Abstand 11–15 Kerzen (−7 € statt −26 €),
  Short besser als Long, mittleres Volumen der Auslöser-Kerze, keine zusätzliche Stochastik-Divergenz, *weniger*
  Musterbuch-Punkte.
- Die Stochastik bringt keinen stabilen Vorteil: tief überverkauft am 2. Pivot war in der Entdeckung +7 €, in
  Prüfung und Oktober −19 € bzw. −18 € je Trade.
- Vor Kosten liegen die Divergenzen bei +12 €, +3 € und −4 € je Trade. Ein Filter kann aus einem Signal ohne
  Vorteil keinen Vorteil machen, er wählt dann nur Zufall aus.

## Verbesserungsversuch: Trendrichtung, 15 min / 1 h, bessere Ausstiege

`python3 -m altcoin_divergenz trend` – Bericht: [`ergebnisse/trend_2026-11-10.md`](ergebnisse/trend_2026-11-10.md),
alle Kombinationen als Tabelle: `ergebnisse/trend_2026-11-10_uebersicht.csv`.

31 Coins mit 10x, OKX-Kurse mit langer Historie (15 Minuten: 11.05.–10.11.2026, 1 Stunde: 10.11.2025–10.11.2026,
Kerzen werden beim Lauf von OKX geladen), Hyperliquid-Kosten plus Funding (0,00125 % je Stunde, Longs zahlen).
Vier Signalarten × vier Ausstiege × zwei Kostenvarianten, jeder Zeitraum in zwei Hälften geteilt:

- **Signale:** reguläre Divergenz gegen den Trend (alle bzw. 100 % Musterbuch), **versteckte Divergenz in
  Trendrichtung** (`muster.trendsignale`: Aufwärtstrend, Kurs höheres Tief, RSI tieferes Tief → Long; spiegelbildlich
  Short) und als Kontrolle derselbe Rücksetzer im Trend ohne RSI-Bedingung.
- **Ausstiege:** fest (Ziel 2R), Einstand ab +1R, 2-ATR-Trailing ohne Ziel, Hälfte bei +1R plus Trailing.
- **Kosten:** alles als Market-Order bzw. Einstieg und Ziele als Limit-Order (Maker 0,015 %, ohne Slippage).

Ausgewählte Ergebnisse, Ø je Trade netto (1. Hälfte / 2. Hälfte):

| | Market-Orders | Limit-Orders für Einstieg und Ziel | ohne Kosten |
| --- | --- | --- | --- |
| 1 h, versteckt im Trend, Halb + Trailing (1.303 Trades) | −4 € (−6 / −1) | **+4 € (+1 / +6)**, Konto 12.188 € | +11 € |
| 1 h, versteckt im Trend, fest (1.251) | −6 € (−11 / −1) | +2 € (−3 / +7) | +9 € |
| 15 min, versteckt im Trend, fest (3.157) | −5 € (−10 / −1) | +3 € (−2 / +7) | +10 € |
| 1 h, regulär (alle), Trailing (2.004) | −0 € (+10 / −11) | +6 € (+17 / −4) | +16 € |
| 15 min, regulär (alle), fest (5.257) | −20 € (−20 / −19) | −12 € | −5 € |
| 1 h, Kontrolle ohne RSI, fest (4.672) | −7 € | +0 € | +7 € |

- In Trendrichtung zu handeln ist der deutlichste Fortschritt: vor Kosten +9 bis +11 € je Trade auf 15 Minuten und
  1 Stunde, gegen den Trend auf 15 Minuten −5 bis 0 €.
- Die versteckte Divergenz schlägt den gleichen Rücksetzer ohne RSI-Bedingung um 2–4 € je Trade. Die Divergenz trägt
  also etwas bei, aber wenig.
- Netto im Plus nur mit Limit-Orders, und nur eine Kombination in beiden Hälften: 1 Stunde, versteckt im Trend,
  Hälfte bei +1R und Rest mit Trailing-Stop. Der 95-%-Bereich (−6 € … +13 €) schließt null aber ein, und bei 64
  getesteten Kombinationen ist ein solcher Treffer auch durch Zufall zu erwarten.
- Die Limit-Order-Rechnung ist optimistisch: Sie nimmt an, dass jede Limit-Order zum Eröffnungskurs ausgeführt wird.
  In der Praxis werden gerade die guten Trades öfter verpasst.

## Fair Value Gaps (Strategie aus dem Video)

`python3 -m altcoin_divergenz fvg` – Bericht: [`ergebnisse/fvg_2026-11-10.md`](ergebnisse/fvg_2026-11-10.md),
alle Zahlen: `ergebnisse/fvg_2026-11-10_uebersicht.csv`.

Das Video („Mit dieser simplen Trading Strategie mache ich 4357,23€/Tag (100x-Strategie)“) war von hier nicht abrufbar
(YouTube-Captcha). Getestet sind deshalb die **Standard-Regeln für Fair Value Gaps** nach ICT, nicht zwingend genau
seine: Lücke zwischen Kerze 1 und 3, Limit-Einstieg in der Mitte der Lücke (20 Kerzen gültig), Stop hinter Kerze 1,
Ziel 2R bzw. Hälfte bei +1R plus Trailing. Varianten: alle Lücken / Standard-FVG (Lücke ≥ 0,25 ATR, kräftige
Bewegungskerze ≥ 1 ATR) / Standard-FVG plus Trendfilter. 31 Coins mit 10x, OKX-Kurse (5 min: 3 Monate, 15 min:
6 Monate, 1 h: 12 Monate), Gegenprobe auf Hyperliquid-Kerzen, Hyperliquid-Kosten mit Maker-Gebühr für Limit-Orders.

Limit-Orders auf Kerzendaten sind heikel: Eine bloße Berührung des Limitkurses heißt nicht, dass die eigene Order in
der Warteschlange drankommt. Deshalb zwei Annahmen: „Berührung reicht“ (optimistisch) und „Kurs läuft 0,05 % durch
Einstiegs- und Zielkurs“ (vorsichtig). Ø je Trade netto bei 10x und 1.000 € Margin, vorsichtige Annahme:

| | 5 min | 15 min | 1 h |
| --- | --- | --- | --- |
| Standard-FVG (mit kräftiger Bewegungskerze), Ziel 2R | −10 € | −6 € | −5 € |
| Standard-FVG + Trendfilter, Ziel 2R | −9 € | −3 € | −0 € |
| alle Lücken, Ziel 2R | −2 € | **+5 €** (beide Hälften +) | **+7 €** (beide Hälften +) |
| alle Lücken, Hälfte bei +1R + Trailing | −10 € | −8 € | −8 € |
| Kontrolle: Zufall mit gleicher Geometrie | −20 € | −24 € | −27 € |
| **100x** (alle Lücken, Ziel 2R): liquidiert / Ø je Trade | 40 % / −212 € | 61 % / −272 € | 79 % / −372 € |

- Die klassischen Fair Value Gaps nach Lehrbuch verlieren auf jedem Zeitrahmen, auch mit Trendfilter.
- Lücken insgesamt sind deutlich besser als Zufall (die Kontrolle verliert 20–27 € je Trade), der Vorteil ist aber
  klein (0,05–0,07 % je Trade) und hängt an der Ausführung: Muss der Kurs 0,1 % statt 0,05 % durchlaufen, bleiben auf
  15 Minuten −1,6 € und auf 1 Stunde +1,8 € je Trade. Bei bloßer Berührung wären es +12 € bzw. +14 €.
- Selbst mit positivem Schnitt kann das Konto pleitegehen: auf 1 Stunde mit 1.000 € Margin und bis zu 10
  gleichzeitigen Positionen am 12.01.2026 auf 843 € (größter Rückgang 13.866 €). Mit 300 € Margin je Trade überlebt
  dasselbe Konto, fällt aber zwischendurch auf 3.041 €.
- **100x funktioniert in keiner Variante:** 40–85 % der Trades laufen zwischendurch mehr als 0,5 % gegen einen und
  wären liquidiert worden. Jedes 100x-Konto ist leer.

## Nur ETH und eine Mustersuche nach Art quantitativer Fonds

`python3 -m altcoin_divergenz eth` – Bericht: [`ergebnisse/eth_2026-11-10.md`](ergebnisse/eth_2026-11-10.md).

ETH-Perpetual, OKX-Kurse (5 min: 6 Monate, 15 min: 1 Jahr, 1 h: 3 Jahre), Hyperliquid-Kosten. ETH ist sehr liquide:
Slippage nur 0,002 % je Seite für 10.000 €, bis 25x Hebel. Konto 10.000 €, 1.000 € Margin × 10, eine Position.

**Teil 1 – bisherige Strategien auf ETH** (Ø je Trade netto, 1. / 2. Hälfte):

| | 5 min | 15 min | 1 h (3 Jahre) |
| --- | --- | --- | --- |
| Divergenz regulär, fest | 0 € (+3 / −1) | −10 € | +9 € (+16 / +3), 190 Trades, 95 %: −28 … +45 € |
| Divergenz versteckt im Trend, Halb | −8 € | −9 € | +11 € (+38 / −11) |
| FVG alle Lücken, fest (vorsichtig) | −6 € | 0 € (+3 / −3) | **+5 € (+2 / +7)**, 1.607 Trades, Konto 17.247 € |
| FVG Standard, fest (vorsichtig) | −10 € | −8 € | −9 € |
| 100 % Musterbuch | 19 Trades, −8 € | 7 Trades | 3 Trades in 3 Jahren |

Wie bei den Altcoins ist nur „FVG alle Lücken, 1 h, festes Ziel“ in beiden Hälften im Plus, der 95-%-Bereich
(−4 € … +13 €) schließt null aber ein. Alles auf 5 und 15 Minuten liegt bei null oder darunter.

**Teil 2 – Mustersuche:** 8 einfache Merkmale × 3 Horizonte je Zeitrahmen, Rangkorrelation (IC) mit der späteren
Rendite in beiden Hälften, dazu ein kombiniertes Ridge-Modell, nur mit der 1. Hälfte geschätzt.

- Es gibt echte, stabile Muster: Auf 5 und 15 Minuten folgt auf steigende Kurse leicht fallende und umgekehrt
  (IC −0,04 bis −0,07 in beiden Hälften, bei 26.000–50.000 Kerzen weit über Zufall). Das ist kurzfristige
  Gegenbewegung (Mean Reversion), wie sie quantitative Fonds handeln.
- Jedes Muster ist aber winzig: oberstes gegen unterstes Zehntel bringt 0,001–0,03 % je Trade. Ein- und Ausstieg
  kosten 0,095 %. Von 72 geprüften Kombinationen liegt eine knapp über den Kosten, was bei 72 Versuchen auch Zufall
  sein kann.
- Das kombinierte Modell verdient in der 1. Hälfte, mit der es geschätzt wurde, und verliert in der 2. Hälfte fast
  überall (bis −0,13 % je Trade): Überanpassung.
