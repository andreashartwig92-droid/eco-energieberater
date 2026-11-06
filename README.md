# eco-energieberater

## Heizlastberechnung und hydraulischer Abgleich

Raumweise Norm-Heizlast in Anlehnung an DIN EN 12831-1 / DIN/TS 12831-1 (vereinfachtes Verfahren)
und hydraulischer Abgleich nach Verfahren B, ausgelegt auf Wärmepumpen mit Bestandsheizkörpern.
Ergebnis ist ein PDF-Bericht zur Prüfung durch den Energieberater.

```bash
python3 -m heizlast beispiele/musterhaus.json
# erzeugt beispiele/musterhaus_bericht.html und .pdf (PDF über Chromium)
```

Tests: `python3 -m unittest discover -s tests`

### Eingabedatei (JSON)

`beispiele/musterhaus.json` ist ein **fiktives Muster** und zeigt alle Felder:

| Abschnitt | Inhalt |
| --- | --- |
| `klima` | Norm-Außentemperatur `theta_e`, Jahresmittel `theta_m_e` (DIN/TS 12831-1, nach PLZ) |
| `lueftung` | `n50`, `epsilon`, Mindestluftwechsel `n_min_standard` |
| `waermebruecken` | pauschaler Zuschlag `delta_U` |
| `bauteile` | Katalog: Kürzel → Bezeichnung und U-Wert |
| `angrenzend` | unbeheizte Bereiche mit Temperatur-Korrekturfaktor `b_u` |
| `raeume` | je Raum `theta_i`, Fläche `A`, lichte Höhe `h`, Abschirmung `e`, Bauteile |
| `hydraulik` | Ziel-Vorlauf, Auslegungsspreizung, Rohrnetz-Kennwerte, Mindest-Δp am Ventil |
| `heizkoerper` | je Heizkörper Raum, Normleistung `phi_N` (75/65/20), Exponent `n`, Leitungslänge `L_einfach` |

Bauteile eines Raums: Fläche als `A` oder `l` × `h`; Fenster und Türen als `oeffnungen` (werden von der
Wandfläche abgezogen). `an` ist `"aussen"` (Standard), der Name eines unbeheizten Bereichs, `"erdreich"`
oder die Temperatur eines beheizten Nachbarraums als Zahl.

Heizkörper, die für den Ziel-Vorlauf zu klein sind, werden als Tausch markiert und mit der nötigen
Normleistung weitergerechnet (`"tausch_kritische": false` rechnet stattdessen mit allen Bestandsheizkörpern).

## US-Musterunterlagen (Einfamilienhaus)

Zwei englische Musterunterlagen für ein fiktives US-Einfamilienhaus (New Jersey, Klimazone 5A), Format US Letter:

| Datei | Inhalt |
| --- | --- |
| `beispiele/usa_musterhaus_hvac_design.pdf` | HVAC Design Package: raumweise Lasten (Aufbau ACCA Manual J), Geräteauswahl Wärmepumpe mit Bivalenzpunkt (Manual S), Kanalnetz mit Reibungsrate und Grundriss (Manual D), Lüftung nach ASHRAE 62.2 |
| `beispiele/usa_musterhaus_energy_report.pdf` | Energy Code Compliance Report nach IECC 2021 R405: Entwurf gegen Standard Reference Design, Jahresenergie und -kosten, Verbesserungsoptionen, Prüfliste für die Abnahme |

```bash
python3 -m usa beispiele/usa_musterhaus.json
```

Die Rechnung ist vereinfacht (pauschale CLTD- und Solarfaktoren, Einzonen-Stundenmodell mit synthetischem Wetterjahr)
und zeigt Aufbau und Inhalt der Unterlagen. Für Bauanträge werden die Berechnungen mit ACCA-anerkannter bzw. vom
Code Official zugelassener Software und Standortdaten erstellt.

## KI-Assistent zum Selbsthosten

`assistent/` ist eine eigene KI-Beraterin für die Website des Büros: eine Chat-Oberfläche auf
Deutsch, die mit dem Wissen des Büros antwortet und die Heizlastberechnung aus diesem Repository
als Werkzeug benutzt. Sie läuft auf dem eigenen Webserver (Docker oder systemd); das Sprachmodell
wird über die Claude-API von Anthropic angesprochen. Das Modell selbst steht also nicht auf dem
Server, aber alles, was die KI ausmacht, schon: Rolle, Wissen, Werkzeuge, Oberfläche und Daten.

```
assistent/
  server.py      HTTP-Server (Standardbibliothek): Oberfläche, /api/chat als Streaming, Passwort, Rate-Limit
  ki.py          Gespräch mit Claude: Streaming, Werkzeugschleife, Verlauf
  werkzeuge.py   Werkzeuge der KI: heizlast_berechnen, heizkoerper_leistung, musterprojekt_abrufen
  wissen.py      lädt wissen/*.md und wissen/*.txt in den Systemprompt
  konfig.py      Einstellungen aus Umgebungsvariablen (KI_*)
  static/        Chat-Oberfläche (eine HTML-Datei)
wissen/          Wissensbasis des Büros – hier eigene Texte ablegen
deploy/          Dockerfile, docker-compose.yml, systemd-Dienst, nginx-Beispiel, .env.beispiel
```

### Was die KI kann

- Fragen zu Wärmepumpe im Bestand, Heizlast, hydraulischem Abgleich, Dämmung, Förderung und zum Büro
  beantworten – auf Basis der Dateien in `wissen/`.
- Mit `heizlast_berechnen` ein komplettes Gebäude rechnen (raumweise Heizlast, Vorlauftemperatur,
  Heizkörpertausch, Pumpe) und auf Wunsch den PDF/HTML-Bericht erzeugen, der dann in der Oberfläche
  zum Download angeboten wird.
- Mit `heizkoerper_leistung` einzelne Heizkörper bei beliebigen Temperaturen prüfen.
- Sie fragt fehlende Daten nach, benennt Annahmen, erfindet keine Fördersätze oder Preise und
  verweist bei verbindlichen Aussagen an das Büro.

### Lokal ausprobieren

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # https://platform.claude.com
python3 -m assistent                     # http://127.0.0.1:8080 (lokal ohne Passwort erlaubt)
python3 -m assistent --terminal          # oder im Terminal chatten
python3 -m assistent --frage "Welche Unterlagen brauche ich für eine Heizlastberechnung?"
```

### Eigenes Wissen hinterlegen

Jede `.md`- oder `.txt`-Datei in `wissen/` wird Teil des Systemprompts, alphabetisch sortiert
(Zahlenpräfix steuert die Reihenfolge). Die mitgelieferten Dateien sind Vorlagen mit Platzhaltern:

| Datei | Inhalt |
| --- | --- |
| `wissen/00_buero.md` | Name, Leistungen, Kontakt, Preise des Büros (bitte ausfüllen) |
| `wissen/10_waermepumpe_bestand.md` | Vorgehen, Faustregeln, Förderhinweise mit Stand |
| `wissen/20_haeufige_fragen.md` | Antwortbausteine für häufige Fragen |

Die Wissensbasis wird beim Start gelesen und bei jeder Anfrage per Prompt-Caching
wiederverwendet. Nach Änderungen den Dienst neu starten. Ab etwa 400.000 Zeichen warnt der Server,
weil jede Anfrage dann spürbar teurer wird.

### Auf dem eigenen Webserver betreiben

**Mit Docker** (empfohlen):

```bash
cp deploy/.env.beispiel deploy/.env       # ANTHROPIC_API_KEY und KI_PASSWORT eintragen
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1:8080/gesund          # {"status": "ok"}
```

Der Container hört nur auf `127.0.0.1:8080`. Davor gehört ein Reverse-Proxy mit HTTPS,
Beispiel in `deploy/nginx.conf.beispiel` (wichtig: `proxy_buffering off`, sonst kommt die Antwort
erst am Ende statt Wort für Wort). Caddy funktioniert genauso mit `reverse_proxy 127.0.0.1:8080`.

**Ohne Docker** als systemd-Dienst: Anleitung steht als Kommentar oben in `deploy/eco-assistent.service`.
Für PDF-Berichte muss Chromium installiert sein (`apt install chromium`), sonst entstehen nur
HTML-Berichte.

### Einstellungen (Umgebungsvariablen)

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | – | Pflicht. API-Schlüssel |
| `KI_PASSWORT` | leer | Pflicht, sobald `KI_HOST` nicht `127.0.0.1` ist. Zugang zur Oberfläche |
| `KI_HOST`, `KI_PORT` | `127.0.0.1`, `8080` | Adresse des Servers |
| `KI_MODELL` | `claude-opus-5-5` | Claude-Modell |
| `KI_EFFORT` | `medium` | Denktiefe `low` … `max`; `low` ist schneller und günstiger, `high` gründlicher |
| `KI_MAX_TOKENS` | `16000` | Längenlimit je Antwort |
| `KI_FALLBACK` | `1` | Server-seitiger Fallback auf ein anderes Claude-Modell, wenn ein Sicherheitsfilter ablehnt (Beta) |
| `KI_LIMIT_PRO_STUNDE` | `60` | Anfragen pro Stunde und IP, `0` schaltet ab |
| `KI_VERTRAUE_PROXY` | `0` | `1` hinter nginx/Caddy, damit das Limit die echte Client-IP sieht |
| `KI_NAME` | `eco Energieberater-KI` | Titel in der Oberfläche |
| `KI_WISSEN`, `KI_BERICHTE` | `wissen/`, `berichte/` | Ordner für Wissen und erzeugte Berichte |

### Sicherheit und Kosten

- Der Gesprächsverlauf liegt im Browser der Nutzer (localStorage), der Server speichert nichts.
  Erzeugte Berichte liegen in `berichte/` und sind nur mit Passwort abrufbar; sie bei Bedarf
  regelmäßig löschen.
- Jede Anfrage kostet Geld bei Anthropic. Passwort, Rate-Limit und ein Ausgabenlimit in der
  Anthropic-Console schützen vor Missbrauch. Die Kosten je Antwort stehen als Token-Zahlen im Log.
- Die KI bekommt nur die Daten, die Nutzer eingeben. Kundendaten gehören nicht in `wissen/`.

Tests: `python3 -m unittest tests.test_assistent` (laufen ohne API-Schlüssel).
