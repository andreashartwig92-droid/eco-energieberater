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

## KI-Assistent zum Selbsthosten (ohne fremde API)

`assistent/` ist eine eigene KI-Beraterin für die Website des Büros: eine Chat-Oberfläche auf
Deutsch, die mit dem Wissen des Büros antwortet und die Heizlastberechnung aus diesem Repository
als Werkzeug benutzt. Sie läuft komplett auf dem eigenen Server: Das Sprachmodell ist ein
Open-Source-Modell, das [Ollama](https://ollama.com) lokal ausführt. Es gehen keine Daten an
Dritte, es fallen keine Kosten pro Anfrage an. Optional lässt sich stattdessen die Claude-API
anschließen (`KI_BACKEND=claude`).

```
assistent/
  server.py      HTTP-Server (Standardbibliothek): Oberfläche, /api/chat als Streaming, Passwort, Rate-Limit
  ki_lokal.py    Gespräch mit dem lokalen Modell über Ollama (Streaming, Werkzeugschleife)
  ki.py          Alternative: Gespräch über die Claude-API
  werkzeuge.py   Werkzeuge der KI: heizlast_berechnen, heizkoerper_leistung, musterprojekt_abrufen
  prompt.py      Rolle und Regeln der KI (Systemprompt)
  wissen.py      lädt wissen/*.md und wissen/*.txt in den Systemprompt
  konfig.py      Einstellungen aus Umgebungsvariablen (KI_*)
  static/        Chat-Oberfläche (eine HTML-Datei)
wissen/          Wissensbasis des Büros – hier eigene Texte ablegen
deploy/          docker-compose.yml (Ollama + Assistent), Dockerfile, systemd-Dienst, nginx-Beispiel, .env.beispiel
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

### Was der Server dafür braucht

Das Sprachmodell läuft auf Ihrer Hardware. Ein gewöhnliches Shared-Webhosting reicht nicht; nötig ist
ein eigener Server oder VPS, auf dem Sie Docker oder Dienste installieren dürfen.

| Modell | Speicherbedarf | Erfahrung |
| --- | --- | --- |
| `qwen3:8b` (Standard) | ca. 6 GB RAM, besser 8 GB VRAM | gutes Deutsch, zuverlässige Werkzeugaufrufe; auf CPU einige Wörter pro Sekunde, mit GPU flüssig |
| `llama3.1:8b` | ca. 6 GB | Alternative mit ähnlichem Profil |
| `qwen3:14b` | ca. 10 GB | spürbar bessere Antworten, GPU empfohlen |
| `qwen3:32b`, `mistral-small` | ab 20 GB VRAM | nahe an Cloud-Qualität, braucht eine GPU |

Ohne GPU funktioniert alles, ist aber langsam (ein 8B-Modell auf 4 CPU-Kernen: rund 20 bis 60 Sekunden
für eine Antwort, die Heizlast eines ganzen Hauses mit Werkzeugaufrufen entsprechend länger). Für eine
öffentliche Website mit mehreren gleichzeitigen Besuchern ist eine GPU (ab 8 GB VRAM) sinnvoll. Die
Modellwahl hängt an Ihrem Server; Qwen3 8B ist der verbreitete Einstieg für Werkzeugaufrufe auf kleiner
Hardware ([Quelle](https://localaimaster.com/blog/best-ollama-models-tool-calling)), Llama 3.1 8B wird
für Deutsch genannt ([Quelle](https://www.siliconflow.com/articles/best-open-source-llm-for-german)).
Testen Sie zwei Modelle mit Ihren eigenen Fragen, bevor Sie sich festlegen.

### Lokal ausprobieren

```bash
curl -fsSL https://ollama.com/install.sh | sh     # Ollama installieren (Linux); macOS/Windows: Download von ollama.com
ollama pull qwen3:8b                              # Modell einmalig laden (ca. 5 GB)
python3 -m assistent                              # http://127.0.0.1:8080 (lokal ohne Passwort erlaubt)
python3 -m assistent --terminal                   # oder im Terminal chatten
python3 -m assistent --frage "Welche Unterlagen brauche ich für eine Heizlastberechnung?"
```

Beim Start meldet der Server, ob Ollama erreichbar ist und das Modell vorliegt; die Oberfläche zeigt
es oben rechts an. Es werden keine Python-Pakete benötigt.

### Eigenes Wissen hinterlegen

Jede `.md`- oder `.txt`-Datei in `wissen/` wird Teil des Systemprompts, alphabetisch sortiert
(Zahlenpräfix steuert die Reihenfolge). Die mitgelieferten Dateien sind Vorlagen mit Platzhaltern:

| Datei | Inhalt |
| --- | --- |
| `wissen/00_buero.md` | Name, Leistungen, Kontakt, Preise des Büros (bitte ausfüllen) |
| `wissen/10_waermepumpe_bestand.md` | Vorgehen, Faustregeln, Förderhinweise mit Stand |
| `wissen/20_haeufige_fragen.md` | Antwortbausteine für häufige Fragen |

Die Wissensbasis wird beim Start gelesen; nach Änderungen den Dienst neu starten. Beim lokalen Modell
muss sie zusammen mit Werkzeugen und Gespräch ins Kontextfenster passen (`KI_NUM_CTX`, Standard 16.384
Token, das entspricht grob 40.000 Zeichen Wissen plus Gespräch). Kleine Modelle werden mit sehr langen
Wissensbasen ungenauer: lieber knapp und konkret schreiben.

### Auf dem eigenen Webserver betreiben

**Mit Docker** (empfohlen, startet Ollama und den Assistenten zusammen):

```bash
cp deploy/.env.beispiel deploy/.env       # KI_PASSWORT eintragen, Modell prüfen
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml logs -f modell-laden   # einmaliger Download des Modells
curl http://127.0.0.1:8080/api/info        # "bereit": true, sobald das Modell geladen ist
```

Der Container hört nur auf `127.0.0.1:8080`. Davor gehört ein Reverse-Proxy mit HTTPS,
Beispiel in `deploy/nginx.conf.beispiel` (wichtig: `proxy_buffering off`, sonst kommt die Antwort
erst am Ende statt Wort für Wort). Caddy funktioniert genauso mit `reverse_proxy 127.0.0.1:8080`.
Für eine NVIDIA-GPU den auskommentierten `deploy:`-Block beim Dienst `ollama` aktivieren.

**Ohne Docker** als systemd-Dienst: Anleitung steht als Kommentar oben in `deploy/eco-assistent.service`.
Für PDF-Berichte muss Chromium installiert sein (`apt install chromium`), sonst entstehen nur
HTML-Berichte.

### Einstellungen (Umgebungsvariablen)

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `KI_BACKEND` | `lokal` | `lokal` = eigenes Modell über Ollama, `claude` = Claude-API |
| `KI_MODELL` | `qwen3:8b` bzw. `claude-opus-5-5` | Modellname |
| `KI_PASSWORT` | leer | Pflicht, sobald `KI_HOST` nicht `127.0.0.1` ist. Zugang zur Oberfläche |
| `KI_HOST`, `KI_PORT` | `127.0.0.1`, `8080` | Adresse des Servers |
| `KI_OLLAMA_URL` | `http://127.0.0.1:11434` | Adresse von Ollama (in Docker `http://ollama:11434`) |
| `KI_NUM_CTX` | `16384` | Kontextfenster des lokalen Modells in Token |
| `KI_DENKEN` | `aus` | Denkmodus des Modells: `aus` schneller, `an` gründlicher, `auto` Modellstandard |
| `KI_KEEP_ALIVE` | `30m` | wie lange das Modell nach einer Antwort geladen bleibt |
| `KI_ZEITLIMIT` | `600` | Sekunden je Modellantwort |
| `KI_MAX_TOKENS` | `16000` | Längenlimit je Antwort |
| `KI_LIMIT_PRO_STUNDE` | `60` | Anfragen pro Stunde und IP, `0` schaltet ab |
| `KI_VERTRAUE_PROXY` | `0` | `1` hinter nginx/Caddy, damit das Limit die echte Client-IP sieht |
| `KI_NAME` | `eco Energieberater-KI` | Titel in der Oberfläche |
| `KI_WISSEN`, `KI_BERICHTE` | `wissen/`, `berichte/` | Ordner für Wissen und erzeugte Berichte |
| `ANTHROPIC_API_KEY`, `KI_EFFORT`, `KI_FALLBACK` | – | nur für `KI_BACKEND=claude`; dafür `pip install -r requirements-claude.txt` |

### Sicherheit und Datenschutz

- Alles bleibt auf Ihrem Server: Modell, Wissen, Gespräche. Der Gesprächsverlauf liegt im Browser der
  Nutzer (localStorage), der Server speichert nichts. Erzeugte Berichte liegen in `berichte/` und sind
  nur mit Passwort abrufbar; bei Bedarf regelmäßig löschen.
- Passwort und Rate-Limit schützen die Rechenleistung des Servers vor Fremdnutzung.
- Kundendaten gehören nicht in `wissen/`; die KI bekommt nur, was Nutzer eingeben.

Tests: `python3 -m unittest tests.test_assistent` (laufen ohne Ollama und ohne API-Schlüssel).

## Bilanz-Radar: Jahresabschlüsse aus dem Bundesanzeiger auswerten (intern)

`bilanzen/` ist ein internes Werkzeug für die Frage „Wie läuft das Geschäft bei den Wettbewerbern, und lohnt
sich der Einstieg in dieses Geschäftsfeld?“. Es sucht im [Bundesanzeiger](https://www.bundesanzeiger.de) nach
Unternehmen zu Suchbegriffen (z. B. „Energieberatung“), lädt deren veröffentlichte Jahresabschlüsse, liest
Bilanz und – soweit veröffentlicht – Gewinn- und Verlustrechnung aus, berechnet Kennzahlen je Unternehmen
und verdichtet alles zu einem Branchenbild mit Urteil („attraktiv“, „bedingt attraktiv“, „wenig attraktiv“).
Nur Python-Standardbibliothek, Ablage in SQLite.

```bash
python3 -m bilanzen                                  # Oberfläche auf http://127.0.0.1:8081
python3 -m bilanzen suche "Energieberatung" --seiten 3   # dasselbe im Terminal (Captcha als Bilddatei)
python3 -m bilanzen import abschluss.html --suchbegriff Energieberatung   # Datei aus dem Unternehmensregister
python3 -m bilanzen bericht --suchbegriff Energieberatung                 # Branchenbild im Terminal
python3 -m bilanzen export --suchbegriff Energieberatung > bilanzen.csv
```

```
bilanzen/
  bundesanzeiger.py  Suche, Trefferlisten, Seitenwechsel, Dokumentabruf, Captcha-Erkennung (ohne automatisches Lösen)
  parser.py          Bilanz-/GuV-Posten aus dem HTML (Tabellen und Fließtext, EUR/TEUR, Fehlbeträge, Größenklasse, Mitarbeiter)
  kennzahlen.py      EK-Quote, Renditen, Liquidität, Wachstum, Score 0–100 mit Ampel und Begründung je Unternehmen
  bewertung.py       Branchenbild: Gewinnanteil, Margen, Wachstum, Krisenanteil, Einstiegshürden, Urteil
  speicher.py        SQLite (Firmen, Abschlüsse mit Originaldokument, Kennzahlen, übersprungene Treffer)
  auftraege.py       Hintergrundaufträge mit Pause zwischen Anfragen und Captcha-Stopp
  server.py          HTTP-Server und JSON-API, static/index.html ist die Oberfläche
```

### So läuft eine Auswertung

1. Suchbegriffe eingeben (eine Branche oder ein Namensbestandteil je Zeile) und Trefferseiten je Begriff wählen
   (20 Treffer je Seite; „Energieberatung“ liefert im Bereich Rechnungslegung rund 760 Treffer).
2. Der Auftrag läuft im Hintergrund und wartet zwischen zwei Anfragen (`BILANZ_PAUSE`, Standard 2 s).
3. Vor dem ersten Jahresabschluss zeigt der Bundesanzeiger eine **Sicherheitsabfrage (Captcha)**. Das Bild erscheint
   im Auftrag; Sie tippen die Zeichen ein, der Auftrag läuft weiter. Das Werkzeug löst Captchas absichtlich nicht
   automatisch – das ist der Schutz des Bundesanzeigers vor Massenabrufen, und so bleibt die Nutzung im Rahmen
   dessen, was dort einem menschlichen Nutzer offensteht.
4. Jedes Dokument wird gespeichert (Original einsehbar), ausgelesen und bewertet. Die Firmenliste ist sortier- und
   filterbar, ein Klick öffnet Posten, Kennzahlen, Einschätzung und das Originaldokument. CSV-Export für Excel.
5. Das Branchenbild fasst alle Unternehmen eines Suchbegriffs zusammen; die Begründung nennt die Zahlen, auf denen
   das Urteil beruht, und die Einschränkungen (Stichprobengröße, fehlende GuV, Datenstand).

### Was die Zahlen aussagen – und was nicht

- **Kleinst- und kleine Kapitalgesellschaften** (die Mehrheit der Energieberater-GmbHs/UGs) veröffentlichen nur
  eine verkürzte Bilanz ohne GuV. Umsatz und Marge sind dann nicht ablesbar; das Werkzeug schätzt das Jahresergebnis
  aus der Veränderung des Eigenkapitals (Untergrenze, da Ausschüttungen nicht sichtbar sind) und kennzeichnet das.
- **Zeitverzug:** Abschlüsse werden bis zu zwölf Monate nach Geschäftsjahresende veröffentlicht.
- **Zwei Quellen:** Seit dem 1. August 2022 werden Jahresabschlüsse im
  [Unternehmensregister](https://www.unternehmensregister.de) offengelegt; im Bundesanzeiger stehen die
  Veröffentlichungen bis dahin (Geschäftsjahre bis etwa 2021, Nachzügler auch später). Für ein aktuelles Bild
  gehören beide Quellen zusammen: Bundesanzeiger für die Jahre bis 2021, Unternehmensregister ab 2022 (siehe unten).
  Daneben lassen sich einzelne Abschlüsse als HTML-Datei importieren („Importieren“ oder `python3 -m bilanzen import`).
- **Wer fehlt:** Einzelunternehmer, Freiberufler und GbRs veröffentlichen nicht. Das Bild zeigt die
  Kapitalgesellschaften der Branche.
- Der Parser ist auf die üblichen Formen der Veröffentlichung ausgelegt (Tabellen mit Berichts- und Vorjahresspalte,
  Fließtext, EUR oder TEUR). Bei ungewöhnlichen Dokumenten fehlen Posten; die Firma zeigt dann Hinweise und die
  Datenlage „eingeschränkt“ oder „gering“. Nach Parser-Verbesserungen wertet „Neu auswerten“ alle gespeicherten
  Dokumente erneut aus, ohne sie neu zu laden.

### Quelle Unternehmensregister (ab Geschäftsjahr 2022)

Das Unternehmensregister ist eine reine JavaScript-Anwendung: Suche und Trefferliste entstehen erst im Browser,
Veröffentlichungen stehen hinter einer Sicherheitsabfrage, und zu viele Abrufe sperren die IP-Adresse. Das
Werkzeug bedient die Seite deshalb mit einem gesteuerten Chromium (Playwright) genauso wie ein Mensch: Formular
ausfüllen, blättern, Veröffentlichung öffnen, Captcha-Bild in die Oberfläche durchreichen. Einrichtung:

```bash
pip install -r requirements-bilanzen.txt
playwright install chromium            # oder: BILANZ_CHROMIUM=/usr/bin/chromium (Docker-Image hat es bereits)
python3 -m bilanzen diagnose "Energieberatung" --sichtbar
```

`diagnose` spielt Suche, erste Trefferseite und die erste Veröffentlichung bis zur Sicherheitsabfrage durch und legt
je Schritt Bildschirmfoto und Seitenquelltext in `daten/diagnose/` ab (`bericht.txt` fasst zusammen). Mit `--sichtbar`
sehen Sie dem Browser zu. In der Oberfläche wählen Sie dann oben bei „Neue Suche“ die Quelle; die Oberfläche zeigt
an, ob Playwright und Chromium bereitstehen. Treffer aus dem Unternehmensregister tragen die Marke „UReg“, das
Branchenbild rechnet beide Quellen zusammen (je Firma zählt der jüngste Abschluss).

Hinweise: Die Erkennung von Trefferliste, Veröffentlichung und Captcha arbeitet mit sichtbaren Texten und
Barrierefreiheits-Beschriftungen der Seite („Sicherheitsabfrage“, „Springe eine Seite weiter“, Links mit
„Jahresabschluss“), weil das Register seine Seitenstruktur bei jedem Neubau ändert. Ändert sich die Seite so, dass
etwas nicht mehr erkannt wird, zeigt `diagnose`, wo es hakt. Hinterlegte (nicht veröffentlichte) Abschlüsse von
Kleinstkapitalgesellschaften sind im Unternehmensregister kostenpflichtig und werden übersprungen. Die
Tests dieses Teils laufen gegen eine lokale Nachbildung der Seite (`tests/fixtures/bilanzen/ureg/`), nicht gegen das
Register selbst; der Ablauf auf der echten Seite ist mit `diagnose` auf Ihrem Rechner zu prüfen.

### Betrieb

Lokal ohne Passwort (`python3 -m bilanzen`). Auf einem Server `BILANZ_PASSWORT` setzen und wie beim Assistenten
einen Reverse-Proxy mit HTTPS davorschalten; das Werkzeug ist nur für das Büro gedacht, nicht für Kunden.
Docker: Dienst `bilanzen` in `deploy/docker-compose.yml` (Port 8081, Datenbank im Volume `bilanzdaten`).
systemd: `deploy/eco-bilanzen.service`.

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `BILANZ_HOST`, `BILANZ_PORT` | `127.0.0.1`, `8081` | Adresse des Servers |
| `BILANZ_PASSWORT` | leer | Pflicht, sobald `BILANZ_HOST` nicht `127.0.0.1` ist |
| `BILANZ_DATENBANK` | `daten/bilanzen.sqlite` | SQLite-Datei (enthält auch die Originaldokumente) |
| `BILANZ_PAUSE` | `2` | Sekunden zwischen zwei Anfragen an den Bundesanzeiger (mindestens 1) |
| `BILANZ_MAX_SEITEN` | `5` | Vorgabe für Trefferseiten je Suchbegriff in der Oberfläche (0 = alle) |
| `BILANZ_VERTRAUE_PROXY` | `0` | `1` hinter nginx/Caddy (echte Client-IP im Protokoll) |
| `BILANZ_CHROMIUM` | leer | Pfad zu einem Chromium für das Unternehmensregister (leer = von `playwright install` installiertes) |

Tests: `python3 -m unittest tests.test_bilanzen` (laufen ohne Netz; Trefferliste und Captcha-Seite liegen als
Fixtures in `tests/fixtures/bilanzen/`; der Browser-Test wird übersprungen, wenn Playwright oder Chromium fehlen).
