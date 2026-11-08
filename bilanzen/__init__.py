"""Bilanz-Radar: Jahresabschlüsse direkt aus dem Unternehmensregister abrufen, auswerten und eine Branche bewerten.

Module:
  unternehmensregister.py  Suche, Trefferliste, Blättern und Veröffentlichungen im Unternehmensregister (gesteuerter Browser)
  modelle.py               gemeinsame Datenklassen (Treffer, Seite, Dokument, Sicherheitsabfrage)
  htmlbaum.py              kleiner HTML-Baum auf Basis der Standardbibliothek (html.parser)
  parser.py                Bilanz- und GuV-Posten aus einem Jahresabschluss (HTML) herauslesen
  kennzahlen.py            Kennzahlen, Score und Begründung je Unternehmen
  bewertung.py             Branchenurteil über viele Unternehmen
  vorreiter.py             Rangliste der Vorreiter einer Branche
  csv_import.py            Kennzahlen aus CSV-Dateien
  speicher.py              SQLite-Ablage
  auftraege.py             Hintergrundaufträge mit Pause und Stopp an der Sicherheitsabfrage
  server.py                HTTP-Server und JSON-API für die Oberfläche in static/
"""
