# 08 Qualitätsprüfung vor jeder Auslieferung

Je Auftrag ausfüllen und in den Auftragsordner legen. Erst ausliefern, wenn alle Punkte erledigt sind.

## Eingang

- [ ] Alle Pflichtfelder und Uploads aus dem Intake-Formular vorhanden
- [ ] Pack-Guthaben ausreichend, Verbrauch gebucht
- [ ] Behörde im Register `02_Behoerden_Register.md` vorhanden, sonst vorher klären
- [ ] Fehlende Angaben beim Kunden angefragt oder als „code maximum“ angesetzt und notiert

## Manual J

- [ ] Standort und Auslegungsbedingungen (99 % Winter, 1 % Sommer) aus der Wrightsoft-Klimadatenbank für den nächsten Ort
- [ ] Innenbedingungen 70 °F Heizen, 75 °F Kühlen, 50 % relative Feuchte
- [ ] Ausrichtung gemäß Auftrag, Nordpfeil auf dem Plan geprüft
- [ ] Alle beheizten Räume einzeln erfasst, Flächen gegen Plan geprüft (Summe weicht höchstens 2 % ab)
- [ ] Fenster mit U-Wert, SHGC, Verschattung und Ausrichtung je Raum
- [ ] Wände, Decke, Boden mit den Konstruktionen aus dem Auftrag
- [ ] Infiltration gemäß Ziel oder Code-Maximum
- [ ] Kanallage und Kanaldichtheit gemäß Auftrag
- [ ] Personen = Schlafzimmer + 1, keine zusätzlichen Sicherheitszuschläge
- [ ] Mehrfamilienhaus: Trennwände und -decken zu beheizten Nachbarn ohne Last, Flure richtig zugeordnet
- [ ] Plausibilität: sq ft je Ton Kühlung im üblichen Bereich (Neubau meist 700 bis 1.200 sq ft je Ton), Heizlast je sq ft plausibel für die Klimazone

## Manual S

- [ ] Gerät aus AHRI-Verzeichnis, AHRI-Nummer im Bericht
- [ ] Gesamtkühlleistung bei Auslegungsbedingungen aus den Expanded Performance Data, nicht aus der Nennleistung
- [ ] Sensible Leistung deckt sensible Last, latente Leistung deckt latente Last
- [ ] Übergröße innerhalb der Grenzen der Manual-S-Tabellen der verwendeten Auflage (Richtwerte Kühlen: einstufig etwa 95 bis 115 %, zweistufig bis 125 %, drehzahlgeregelt bis 130 %; Wärmepumpen in heizungsdominierten Zonen mit höherer Grenze; Heizen nach eigener Tabelle)
- [ ] Wärmepumpe: Bivalenzpunkt berechnet, Zusatzheizung bemessen
- [ ] Gasgerät: Heizleistung innerhalb der Manual-S-Grenzen

## Manual D

- [ ] Verfügbarer externer Druck aus Gerätedaten, Abzüge für Filter, Spule, Gitter und Zubehör
- [ ] Wirksame Länge des längsten Strangs ermittelt, Reibungsrate im zulässigen Band
- [ ] Luftmengen je Raum proportional zur Raumlast
- [ ] Hauptkanal- und Abzweiggeschwindigkeiten innerhalb der Manual-D-Grenzen
- [ ] Rückluftwege für jedes geschlossene Zimmer (Rückluftgitter, Überströmer oder Jump Duct)
- [ ] Kanalplan auf dem Grundriss, Gitter und Durchmesser beschriftet

## Lüftung

- [ ] Mindestluftmenge nach ASHRAE 62.2 berechnet, Strategie und Gerät benannt
- [ ] Abluft Bäder und Küche nach Code

## Bericht

- [ ] Deckblatt `06_Berichtsdeckblatt.md` vollständig, Annahmen aufgeführt
- [ ] Projektadresse, Behörde, Code-Basis, Version und Datum auf dem Deckblatt
- [ ] Ersteller mit ACCA-Zertifikatsnummer, Softwareversion genannt
- [ ] Alle Seiten aus Wrightsoft enthalten (J, S, D, Kanalplan), PDF durchsucht und lesbar
- [ ] Wrightsoft-Originaldatei beigelegt
- [ ] Gegenrechnung mit dem Modul `usa/` bei neuen Bautypen, Abweichung über 15 % geklärt

## Auslieferung

- [ ] Lieferung innerhalb der zugesagten Frist
- [ ] Mail mit Bericht, Restguthaben und Hinweis auf 90 Tage Revisionsgarantie
- [ ] Zeitaufwand notiert (Ziel: unter 3 Stunden je Paket)
- [ ] Bei Behördenkommentar: Ursache notieren (eigener Fehler, Kundenangabe, Behördenpraxis) und Register ergänzen
