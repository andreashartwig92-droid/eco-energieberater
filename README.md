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
