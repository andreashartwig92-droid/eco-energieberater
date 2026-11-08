"""Quelle OpenRegister (api.openregister.de): strukturierte Bilanzdaten aus dem Bundesanzeiger per Schnittstelle.

OpenRegister ist ein Datenanbieter, der die veröffentlichten Jahresabschlüsse bereits ausgelesen hat und über eine
dokumentierte API liefert: Firmensuche nach Unternehmensgegenstand, Name, Ort oder Branchencode, je Firma Bilanz
und GuV für alle verfügbaren Geschäftsjahre, Kennzahlen je Jahr, dazu das Originaldokument. Kein Captcha, kein
Browser – dafür ein API-Schlüssel (kostenlos: 500 Punkte im Monat; eine Suchseite kostet 10 Punkte, die Finanzdaten
einer Firma 10 Punkte). Dokumentation: https://docs.openregister.de

Schlüssel: Umgebungsvariable OPENREGISTER_API_KEY (oder BILANZ_OPENREGISTER_KEY). Nur Standardbibliothek.

Die Klasse `Client` passt in `auftraege.Verwalter`: `suche`/`naechste_seite` liefern Treffer, `abschluesse(treffer)`
liefert fertige `parser.Abschluss`-Objekte (eines je Geschäftsjahr) statt eines HTML-Dokuments.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .bundesanzeiger import Seite, Treffer
from .parser import Abschluss, erkenne_rechtsform

log = logging.getLogger("bilanzen.openregister")

BASIS = "https://api.openregister.de"
QUELLE = "openregister"
PUNKTE_SUCHE = 10
PUNKTE_FINANZEN = 10
PUNKTE_AUTOCOMPLETE = 1

# Kennzahlen der API (in Cent) → Posten des Parsers (in Euro)
POSTEN_MAP = {
    "balance_sheet_total": "bilanzsumme", "equity": "eigenkapital", "revenue": "umsatz", "net_income": "jahresueberschuss",
    "cash": "liquide_mittel", "fixed_assets": "anlagevermoegen", "tangible_assets": "sachanlagen", "current_assets": "umlaufvermoegen",
    "receivables": "forderungen", "trade_receivables": "forderungen_lul", "inventory": "vorraete", "provisions": "rueckstellungen",
    "liabilities": "verbindlichkeiten", "bank_debt": "verbindlichkeiten_kreditinstitute", "trade_payables": "verbindlichkeiten_lul",
    "shareholder_liabilities": "verbindlichkeiten_gesellschafter", "salaries": "personalaufwand", "materials": "materialaufwand",
    "operating_depreciation": "abschreibungen", "other_operating_expenses": "sonstige_betriebliche_aufwendungen",
    "other_operating_income": "sonstige_betriebliche_ertraege", "interest_expense": "zinsaufwand", "interest_income": "zinsertrag",
    "taxes": "steuern_ertrag", "other_taxes": "sonstige_steuern", "gross_profit": "rohergebnis", "capital_reserves": "kapitalruecklage",
    "retained_earnings": "gewinnruecklagen", "profit_carryforward": "gewinnvortrag", "active_accruals": "rechnungsabgrenzung_aktiv",
    "passive_accruals": "rechnungsabgrenzung_passiv",
}
# Aufwandsposten liefert die API als positive Beträge; der Parser kennt sie aus den Veröffentlichungen als negative Werte
AUFWAND = {"personalaufwand", "materialaufwand", "abschreibungen", "sonstige_betriebliche_aufwendungen", "zinsaufwand", "steuern_ertrag", "sonstige_steuern"}
RECHTSFORM_MAP = {"gmbh": "GmbH", "ug": "UG (haftungsbeschränkt)", "ag": "AG", "kg": "KG", "ohg": "OHG", "ek": "e.K.", "eg": "eG", "ev": "e.V.",
                  "se": "SE", "kgaa": "KGaA", "ggmbh": "gGmbH", "gbr": "GbR", "foundation": "Stiftung", "llp": "LLP", "ewiv": "EWIV"}


class OpenRegisterFehler(Exception):
    pass


@dataclass
class Kontingent:
    """Grobe Schätzung des Punkteverbrauchs eines Clients (die API meldet den Stand im Dashboard)."""
    suchen: int = 0
    finanzen: int = 0

    @property
    def punkte(self):
        return self.suchen * PUNKTE_SUCHE + self.finanzen * PUNKTE_FINANZEN


def api_schluessel():
    return os.environ.get("OPENREGISTER_API_KEY") or os.environ.get("BILANZ_OPENREGISTER_KEY") or ""


def verfuegbar():
    if api_schluessel():
        return True, ""
    return False, "OPENREGISTER_API_KEY fehlt – kostenlosen Schlüssel unter https://openregister.de/keys anlegen und als Umgebungsvariable setzen"


class Client:
    """suche(begriff) → Seite mit Treffern (link = company_id); abschluesse(treffer) → Liste von Abschluss-Objekten."""

    def __init__(self, api_key=None, pause=0.5, zeitlimit=60, pro_seite=50, suchfeld="zweck", nur_aktive=True, ort="",
                 mit_dokument=True, oeffner=None, basis=BASIS):
        self.api_key = api_key or api_schluessel()
        if not self.api_key:
            raise OpenRegisterFehler(verfuegbar()[1])
        self.pause = pause
        self.zeitlimit = zeitlimit
        self.pro_seite = max(1, min(int(pro_seite), 100))
        self.suchfeld = suchfeld  # "zweck" (Unternehmensgegenstand), "name" (Firmenname, Volltext) oder "branche" (WZ-Code)
        self.nur_aktive = nur_aktive
        self.ort = ort
        self.mit_dokument = mit_dokument
        self.oeffner = oeffner or urllib.request.build_opener()
        self.basis = basis.rstrip("/")
        self.kontingent = Kontingent()
        self.anfragen = 0
        self._letzte = 0.0

    # --- HTTP ---------------------------------------------------------------

    def _anfrage(self, methode, pfad, daten=None, roh=False, basis=None):
        rest = self.pause - (time.monotonic() - self._letzte)
        if rest > 0:
            time.sleep(rest)
        url = (basis or self.basis) + pfad
        rumpf = json.dumps(daten).encode("utf-8") if daten is not None else None
        anfrage = urllib.request.Request(url, data=rumpf, method=methode)
        anfrage.add_header("Authorization", f"Bearer {self.api_key}")
        anfrage.add_header("Accept", "application/json" if not roh else "*/*")
        anfrage.add_header("User-Agent", "eco-bilanzradar/1.0")
        if rumpf is not None:
            anfrage.add_header("Content-Type", "application/json")
        try:
            with self.oeffner.open(anfrage, timeout=self.zeitlimit) as antwort:
                inhalt = antwort.read()
        except urllib.error.HTTPError as e:
            text = ""
            try:
                text = json.loads(e.read().decode("utf-8", errors="replace")).get("message", "")
            except Exception:  # noqa: BLE001
                pass
            if e.code == 401:
                raise OpenRegisterFehler(f"API-Schlüssel abgelehnt ({text or 'unauthorized'}).") from e
            if e.code == 402:
                raise OpenRegisterFehler("Punktekontingent bei OpenRegister aufgebraucht (402). Nächsten Monat abwarten oder Tarif erhöhen.") from e
            if e.code == 429:
                raise OpenRegisterFehler(f"OpenRegister bremst ({text or 'rate limit'}). Pause erhöhen und später fortsetzen.") from e
            if e.code == 404:
                raise OpenRegisterFehler("Nicht gefunden (404).") from e
            raise OpenRegisterFehler(f"HTTP {e.code} von OpenRegister: {text}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise OpenRegisterFehler(f"Keine Verbindung zu OpenRegister: {e}") from e
        finally:
            self._letzte = time.monotonic()
            self.anfragen += 1
        if roh:
            return inhalt
        try:
            return json.loads(inhalt.decode("utf-8"))
        except ValueError as e:
            raise OpenRegisterFehler("Antwort von OpenRegister ist kein JSON.") from e

    # --- Suche --------------------------------------------------------------

    def _filter(self, begriff):
        filter_liste = []
        anfrage = {}
        if self.suchfeld == "name":
            anfrage["query"] = {"value": begriff}
        elif self.suchfeld == "branche":
            filter_liste.append({"field": "industry_codes", "values": [b.strip() for b in begriff.split(",") if b.strip()]})
        else:
            woerter = [w.strip() for w in begriff.replace(";", ",").split(",") if w.strip()]
            filter_liste.append({"field": "purpose", "keywords": woerter or [begriff]})
        if self.nur_aktive:
            filter_liste.append({"field": "status", "value": "active"})
        if self.ort:
            filter_liste.append({"field": "city", "values": [o.strip() for o in self.ort.split(",") if o.strip()]})
        if filter_liste:
            anfrage["filters"] = filter_liste
        return anfrage

    def suche(self, begriff, bereich=None, seite=1):
        anfrage = self._filter(begriff)
        anfrage["pagination"] = {"page": seite, "per_page": self.pro_seite}
        daten = self._anfrage("POST", "/v1/search/company", anfrage)
        self.kontingent.suchen += 1
        treffer = [self._treffer(e) for e in daten.get("results", [])]
        pag = daten.get("pagination") or {}
        nummer = pag.get("page", seite)
        gesamt = pag.get("total_results", len(treffer))
        weitere = nummer < pag.get("total_pages", nummer)
        s = Seite(treffer=treffer, nummer=nummer, anzahl_treffer=gesamt, naechste_url=f"openregister:{begriff}:{nummer + 1}" if weitere else "",
                  url=f"{self.basis}/v1/search/company?page={nummer}")
        s.begriff = begriff
        return s

    def naechste_seite(self, seite):
        if not seite.naechste_url:
            return None
        return self.suche(getattr(seite, "begriff", ""), seite=seite.nummer + 1)

    def _treffer(self, e):
        adresse = e.get("address") or {}
        return Treffer(name=e.get("name", ""), ort=adresse.get("city", "") or "", titel="Jahresabschlüsse (OpenRegister)",
                       link=e.get("company_id", ""), datum="", bereich="Rechnungslegung/Finanzberichte", quelle=QUELLE)

    # --- Finanzdaten ----------------------------------------------------------

    def abschluesse(self, treffer):
        """Alle Geschäftsjahre einer Firma als Abschluss-Objekte; (Abschluss, roh_html, quelle_url) je Jahr, jüngstes zuerst."""
        daten = self._anfrage("GET", f"/v1/company/{urllib.parse.quote(treffer.link)}/financials")
        self.kontingent.finanzen += 1
        ergebnis = abschluesse_aus_antwort(daten, firma=treffer.name)
        if self.mit_dokument and ergebnis:
            html = self._dokument(daten, ergebnis[0][0].gj_bis)
            if html:
                a, _, url = ergebnis[0]
                ergebnis[0] = (a, html, url)
        return ergebnis

    def _dokument(self, daten, gj_bis):
        for bericht in daten.get("reports") or []:
            if bericht.get("report_end_date") == gj_bis:
                for quelle in bericht.get("sources") or []:
                    url = quelle.get("html_url")
                    if url:
                        try:
                            return self._anfrage("GET", "", roh=True, basis=url).decode("utf-8", errors="replace")
                        except OpenRegisterFehler as e:
                            log.info("Originaldokument nicht geladen: %s", e)
                            return ""
        return ""

    def schliessen(self):
        pass


def _euro(cent):
    return None if cent is None else cent / 100.0


def abschluesse_aus_antwort(daten, firma=""):
    """Antwort von /financials → [(Abschluss, roh_html, quelle_url)], jüngstes Jahr zuerst. Vorjahreswerte aus dem Vorjahreseintrag."""
    indikatoren = sorted((i for i in (daten.get("indicators") or []) if i.get("date")), key=lambda i: i["date"])
    berichte = {b.get("report_id"): b for b in (daten.get("reports") or [])}
    schaetzungen = daten.get("estimates") or {}
    ergebnis = []
    vorher = None
    for ind in indikatoren:
        a = Abschluss(firma=firma, gj_bis=ind["date"], einheit="EUR")
        bericht = berichte.get(ind.get("report_id")) or {}
        a.gj_von = bericht.get("report_start_date") or ""
        a.titel = f"Jahresabschluss zum {ind['date']} (OpenRegister)"
        for api_feld, posten in POSTEN_MAP.items():
            wert = _euro(ind.get(api_feld))
            if wert is None:
                continue
            vorjahr = _euro(vorher.get(api_feld)) if vorher and vorher.get("date", "")[:4] == str(int(ind["date"][:4]) - 1) else None
            if posten in AUFWAND:
                wert = -abs(wert)
                vorjahr = None if vorjahr is None else -abs(vorjahr)
            a.posten[posten] = [wert, vorjahr]
        a.mitarbeiter = ind.get("employees")
        a.guv_vorhanden = ind.get("revenue") is not None or ind.get("net_income") is not None
        a.zeilen_erkannt = len(a.posten)
        a.rechtsform = erkenne_rechtsform(firma)
        a.hinweise.append("Kennzahlen über die OpenRegister-Schnittstelle aus dem veröffentlichten Abschluss übernommen.")
        if ind.get("short_year"):
            a.hinweise.append("Rumpfgeschäftsjahr (kürzer als zwölf Monate).")
        if bericht.get("consolidated"):
            a.hinweise.append("Konzernabschluss.")
        if not a.guv_vorhanden:
            a.hinweise.append("Keine Gewinn- und Verlustrechnung veröffentlicht; Umsatz und Ergebnis nicht direkt ablesbar.")
            umsatz = schaetzungen.get("revenue")
            if umsatz and umsatz.get("date") == ind["date"]:
                a.hinweise.append(f"OpenRegister schätzt den Umsatz auf etwa {umsatz['value'] / 100:,.0f} € "
                                  f"(80-%-Spanne {umsatz['min'] / 100:,.0f} bis {umsatz['max'] / 100:,.0f} €, Verlässlichkeit {umsatz.get('confidence')}); "
                                  "die Schätzung fließt nicht in die Kennzahlen ein.".replace(",", "."))
        if "bilanzsumme" not in a.posten:
            a.warnungen.append("Bilanzsumme nicht geliefert.")
        if "eigenkapital" not in a.posten:
            a.warnungen.append("Eigenkapital nicht geliefert.")
        quelle_url = ""
        for q in bericht.get("sources") or []:
            if q.get("html_url"):
                quelle_url = q["html_url"].split("?", 1)[0]
                break
        ergebnis.append((a, "", quelle_url or f"openregister:{ind.get('report_id', '')}"))
        vorher = ind
    ergebnis.reverse()
    return ergebnis


def rechtsform_aus_api(kuerzel):
    return RECHTSFORM_MAP.get((kuerzel or "").lower(), "")
