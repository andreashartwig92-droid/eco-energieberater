# 03 Intake Form (Vorlage für Tally oder Typeform)

Kundensprache Englisch. Felder in dieser Reihenfolge anlegen. Pflichtfelder sind mit * markiert.
Der Auftrag gilt erst als vollständig, wenn alle Pflichtfelder und Uploads da sind. Ab dann läuft die Lieferzeit.

---

## Load Pack Design – New Order

*One order per house or per dwelling type. A house with two systems is one order that uses two systems from your pack.*

### 1. Account

| Field | Type | Notes |
| --- | --- | --- |
| Company name * | text | |
| Contact name * | text | |
| Email * | email | Reports are sent here |
| Phone | phone | |
| Pack ID * | text | Shown on your pack confirmation, e.g. P20-0142 |
| Your project reference | text | Lot number, job number or plan name |

### 2. Project location

| Field | Type | Notes |
| --- | --- | --- |
| Project street address * | text | Needed for design conditions |
| City, state, ZIP * | text | |
| Building department (AHJ) * | text | e.g. City of Houston, Orange County FL |
| Code edition, if known | select | IECC 2015 / 2018 / 2021 / 2024, FBC 8th ed., NCRC 2024, Not sure |
| Project type * | select | New construction, Addition, Equipment replacement, Multifamily unit type |
| Front of house faces * | select | N, NE, E, SE, S, SW, W, NW |
| Additional orientations for the same plan | multi-select | Each extra orientation is $40 |

### 3. Drawings (uploads)

| Field | Type | Notes |
| --- | --- | --- |
| Floor plans with dimensions * | file (PDF/DWG) | All floors, scaled |
| Elevations * | file | Window and door heights |
| Sections or wall details | file | Ceiling heights, vaulted areas |
| Window and door schedule | file | Or fill in section 4 |
| Energy report, if any | file | REScheck, R405 or HERS projected rating |

### 4. Envelope

| Field | Type | Notes |
| --- | --- | --- |
| Window U-factor * | number | e.g. 0.30 |
| Window SHGC * | number | e.g. 0.25 |
| Wall insulation * | text | e.g. 2x4 R-13 + R-5 continuous |
| Ceiling / attic insulation * | text | e.g. R-38 blown, vented attic |
| Floor / foundation * | select | Slab on grade, Crawlspace vented, Crawlspace sealed, Basement conditioned, Basement unconditioned, Over garage |
| Slab or floor insulation | text | |
| Roof color / radiant barrier | text | |
| Infiltration target * | select | 3 ACH50, 5 ACH50, Builder value (enter), Not known (we use code maximum) |
| Builder ACH50 value | number | |

### 5. Equipment

| Field | Type | Notes |
| --- | --- | --- |
| Number of systems * | number | One per piece of equipment serving one zone |
| Area served by each system * | text | e.g. System 1: first floor, System 2: second floor |
| Equipment type * | select | Heat pump split, Gas furnace + AC, Ductless mini-split, Dual fuel, Hydronic, Other |
| Preferred brand and series | text | Needed for Manual S. If blank we select from AHRI data |
| Fuel available | select | Electric only, Natural gas, Propane |
| Backup heat | select | Electric strip, Gas, None, Your choice |
| Air handler / furnace location * | select | Attic, Conditioned closet, Garage, Crawlspace, Basement |
| Duct location * | select | Attic, Conditioned space, Crawlspace, Mixed |
| Ventilation strategy | select | Exhaust only, Supply (fresh air duct), ERV/HRV, Not decided (we recommend) |
| Zoning | select | No, Yes (describe) |

### 6. Occupancy and special loads

| Field | Type | Notes |
| --- | --- | --- |
| Bedrooms * | number | Occupants = bedrooms + 1 per Manual J |
| Special internal loads | text | Home theater, server, large kitchen equipment |
| Rooms with extra glass or skylights | text | |

### 7. Delivery

| Field | Type | Notes |
| --- | --- | --- |
| Rush delivery (48 hours, $50) | yes/no | Free once per Pack 20, twice per Pack 30 |
| IECC compliance input package for a HERS rater ($60) | yes/no | |
| Notes for the designer | long text | |
| I confirm that a licensed contractor, builder or engineer will review and submit the report * | checkbox | Required |
| I accept the Terms of Service * | checkbox | Link to Terms |

---

## Automatische Bestätigung an den Kunden

```
Subject: Order received – <project reference>

Thanks, we received your order for <address>.

Status: <Complete – delivery by <date>> / <Missing items: list>
Systems used from your pack: <n>. Remaining balance: <n>.

If anything changes before delivery, reply to this email.
```

## Interne Ablage je Auftrag

```
/Auftraege/<Kunde>/<JJJJ-MM-TT>_<Projektreferenz>/
  01_Eingang/        Uploads unverändert
  02_Modell/         Wrightsoft-Datei
  03_Bericht/        PDF-Paket, Versionen R1, R2 …
  04_Korrespondenz/  Mails, Behördenkommentare
  Pruefliste.md      ausgefüllte 08_Qualitaetspruefung
```
