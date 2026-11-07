"""Bilanz-Radar: Jahresabschlüsse aus dem Bundesanzeiger abrufen, auswerten und eine Branche bewerten.

Module:
  htmlbaum.py        kleiner HTML-Baum auf Basis der Standardbibliothek (html.parser)
  bundesanzeiger.py  Suche im Bundesanzeiger, Trefferlisten, Dokumentabruf, Captcha-Erkennung
  parser.py          Bilanz- und GuV-Posten aus einem Jahresabschluss (HTML) herauslesen
  kennzahlen.py      Kennzahlen, Score und Begründung je Unternehmen
  bewertung.py       Branchenbild über viele Unternehmen und Urteil zur Attraktivität
  speicher.py        SQLite-Ablage
  auftraege.py       Hintergrundaufträge (Suchen + Laden) mit Captcha-Pause
  server.py          HTTP-Server und JSON-API für die Oberfläche in static/
"""
