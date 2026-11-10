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

## Altcoin-Divergenz-Konzept (Backtest)

Prüfung einer Trading-Idee: 100 Altcoins auf dem 1-Minuten-Chart, Trades nur bei klarer RSI/MACD-Divergenz,
10x Hebel, 1.000 € Kapital. Echte OKX-Kursdaten, Gebühren und Slippage eingerechnet, keine echten Orders.
Details und Ergebnisse: [`altcoin_divergenz/README.md`](altcoin_divergenz/README.md).

```bash
python3 -m altcoin_divergenz live              # letzte 2 Stunden
python3 -m altcoin_divergenz robust --tage 7   # dieselben Regeln über 7 Tage
```
