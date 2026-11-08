"""Zugriff auf die öffentliche Suche des Bundesanzeigers (www.bundesanzeiger.de), nur Standardbibliothek.

Ablauf wie im Browser: Startseite aufrufen (Sitzung), Suchformular absenden, Trefferliste seitenweise
durchgehen, Veröffentlichung öffnen. Jahresabschlüsse schützt der Bundesanzeiger mit einer
Sicherheitsabfrage (Captcha). Dieses Modul löst sie **nicht** automatisch: Es liefert das Bild zurück
(`CaptchaNoetig`), ein Mensch liest es, und `captcha_loesen` schickt die Lösung ab.

Zwischen zwei Anfragen wartet der Client (`pause`), damit der Server nicht belastet wird.

Hinweis: Seit dem 1. August 2022 werden neue Jahresabschlüsse im Unternehmensregister offengelegt;
im Bundesanzeiger liegen die Veröffentlichungen bis dahin (Geschäftsjahre bis etwa 2021, Nachzügler auch
später). Neuere Abschlüsse lassen sich über `python -m bilanzen import` einlesen.
"""

import http.cookiejar
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .htmlbaum import parse

log = logging.getLogger("bilanzen.bundesanzeiger")

BASIS = "https://www.bundesanzeiger.de"
START = BASIS + "/pub/de/start?0"
BEREICH_RECHNUNGSLEGUNG = "22"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0 eco-bilanzradar/1.0"


class BundesanzeigerFehler(Exception):
    pass


@dataclass
class Treffer:
    name: str
    ort: str
    titel: str
    link: str  # leer bei Hinterlegungen ohne einsehbares Dokument
    datum: str  # Veröffentlichungsdatum TT.MM.JJJJ
    bereich: str = ""
    quelle: str = "bundesanzeiger"  # oder "unternehmensregister"

    @property
    def ist_jahresabschluss(self):
        if self.quelle == "openregister":  # Treffer sind Firmen mit Finanzdaten, link = company_id
            return bool(self.link)
        t = self.titel.lower()
        return bool(self.link) and ("jahresabschluss" in t or "konzernabschluss" in t or "jahresfinanzbericht" in t)


@dataclass
class Seite:
    treffer: list
    nummer: int
    anzahl_treffer: int
    naechste_url: str  # leer auf der letzten Seite
    url: str


@dataclass
class Dokument:
    html: str
    url: str
    text: str = ""


@dataclass
class CaptchaNoetig(Exception):
    """Die Veröffentlichung ist hinter einer Sicherheitsabfrage. `bild` zeigen, Lösung an `captcha_loesen`."""

    bild: bytes
    bild_typ: str
    formular_url: str
    seite_url: str
    versuch: int = 1
    felder: dict = field(default_factory=dict)

    def __str__(self):
        return "Sicherheitsabfrage (Captcha) des Bundesanzeigers muss gelöst werden"


class Client:
    def __init__(self, pause=2.0, user_agent=USER_AGENT, zeitlimit=60, oeffner=None):
        self.pause = pause
        self.zeitlimit = zeitlimit
        self.cookies = http.cookiejar.CookieJar()
        self.oeffner = oeffner or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.oeffner.addheaders = [
            ("User-Agent", user_agent),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"),
            ("Accept-Language", "de-DE,de;q=0.9,en;q=0.5"),
        ]
        self._letzte_anfrage = 0.0
        self._sitzung_bereit = False
        self.anfragen = 0

    # --- HTTP ---------------------------------------------------------------

    def _warte(self):
        rest = self.pause - (time.monotonic() - self._letzte_anfrage)
        if rest > 0:
            time.sleep(rest)

    def _hole(self, url, daten=None, referer=None):
        """GET (daten=None) oder POST (daten=dict); liefert (endgültige URL, Inhalt als bytes, Content-Type)."""
        self._warte()
        rumpf = urllib.parse.urlencode(daten).encode("utf-8") if daten is not None else None
        anfrage = urllib.request.Request(url, data=rumpf)
        if referer:
            anfrage.add_header("Referer", referer)
        if rumpf is not None:
            anfrage.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.oeffner.open(anfrage, timeout=self.zeitlimit) as antwort:
                inhalt = antwort.read()
                typ = antwort.headers.get("Content-Type", "")
                end_url = antwort.geturl()
        except urllib.error.HTTPError as e:
            raise BundesanzeigerFehler(f"HTTP {e.code} bei {url}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise BundesanzeigerFehler(f"Keine Verbindung zum Bundesanzeiger: {e}") from e
        finally:
            self._letzte_anfrage = time.monotonic()
            self.anfragen += 1
        return end_url, inhalt, typ

    def _hole_text(self, url, daten=None, referer=None):
        end_url, inhalt, _ = self._hole(url, daten, referer)
        return end_url, inhalt.decode("utf-8", errors="replace")

    def _sitzung(self):
        if not self._sitzung_bereit:
            self._start_url, self._start_html = self._hole_text(START)
            self._sitzung_bereit = True

    # --- Suche --------------------------------------------------------------

    def suche(self, begriff, bereich=BEREICH_RECHNUNGSLEGUNG):
        """Erste Trefferseite zu einem Suchbegriff (Volltext, Bereich Rechnungslegung/Finanzberichte)."""
        self._sitzung()
        baum = parse(self._start_html)
        formular_feld = None
        for eingabe in baum.suche("input", type="hidden"):
            name = eingabe.attr("name") or ""
            if "card-form" in name:
                formular_feld = name
                break
        if not formular_feld:
            raise BundesanzeigerFehler("Suchformular auf der Startseite nicht gefunden – Seitenaufbau geändert?")
        felder = {formular_feld: "", "fulltext": begriff, "area_select": bereich, "search_button": "Suchen"}
        url = BASIS + "/pub/de/start?" + urllib.parse.urlencode(felder)
        end_url, html = self._hole_text(url, referer=self._start_url)
        return parse_trefferseite(html, end_url)

    def naechste_seite(self, seite):
        if not seite.naechste_url:
            return None
        end_url, html = self._hole_text(seite.naechste_url, referer=seite.url)
        return parse_trefferseite(html, end_url, erwartet=seite.nummer + 1)

    def alle_treffer(self, begriff, max_seiten=5, bereich=BEREICH_RECHNUNGSLEGUNG, rueckmeldung=None):
        """Alle Treffer über bis zu `max_seiten` Seiten (0 = ohne Grenze). `rueckmeldung(seite)` je Seite."""
        seite = self.suche(begriff, bereich)
        gesehen = 0
        while seite is not None:
            if rueckmeldung:
                rueckmeldung(seite)
            for t in seite.treffer:
                yield t
            gesehen += 1
            if max_seiten and gesehen >= max_seiten:
                return
            seite = self.naechste_seite(seite)

    # --- Veröffentlichung ---------------------------------------------------

    def dokument(self, treffer):
        """Veröffentlichung öffnen. Liefert `Dokument` oder wirft `CaptchaNoetig`."""
        if not treffer.link:
            raise BundesanzeigerFehler("Zu diesem Treffer gibt es kein einsehbares Dokument (nur hinterlegt).")
        end_url, html = self._hole_text(treffer.link)
        return self._dokument_oder_captcha(html, end_url)

    def captcha_loesen(self, captcha, loesung):
        """Lösung der Sicherheitsabfrage abschicken; danach `Dokument` oder erneut `CaptchaNoetig`."""
        felder = dict(captcha.felder)
        felder.update({"solution": loesung.strip(), "confirm-button": "OK"})
        end_url, html = self._hole_text(captcha.formular_url, felder, referer=captcha.seite_url)
        return self._dokument_oder_captcha(html, end_url, versuch=captcha.versuch + 1)

    def _dokument_oder_captcha(self, html, url, versuch=1):
        baum = parse(html)
        inhalt = baum.erster("div", klasse="publication_container")
        if inhalt is not None:
            return Dokument(html=html, url=url, text=inhalt.text("\n"))
        captcha = erkenne_captcha(baum, url)
        if captcha is None:
            raise BundesanzeigerFehler("Weder Dokument noch Sicherheitsabfrage erkannt – Seitenaufbau geändert?")
        bild_url = urllib.parse.urljoin(url, captcha["bild_url"])
        _, bild, typ = self._hole(bild_url, referer=url)
        raise CaptchaNoetig(bild=bild, bild_typ=typ.split(";")[0] or "image/png", formular_url=captcha["formular_url"],
                            seite_url=url, versuch=versuch, felder=captcha["felder"])


# --- Parser für die Seiten ------------------------------------------------------------------------

def parse_trefferseite(html, url, erwartet=None):
    baum = parse(html)
    behaelter = baum.erster("div", klasse="result_container")
    treffer = []
    if behaelter is not None:
        for zeile in behaelter.suche("div", klasse="row"):
            if zeile.hat_klasse("result_header"):
                continue
            erster = zeile.erster("div", klasse="first")
            if erster is None:
                continue
            name_zeilen = erster.zeilen()
            info = zeile.erster("div", klasse="info")
            link_knoten = info.erster("a") if info is not None else None
            datum = zeile.erster("div", klasse="date")
            bereich = zeile.erster("div", klasse="part")
            treffer.append(Treffer(
                name=name_zeilen[0] if name_zeilen else "",
                ort=" ".join(name_zeilen[1:]) if len(name_zeilen) > 1 else "",
                titel=(link_knoten.text() if link_knoten is not None else (info.text() if info is not None else "")),
                link=urllib.parse.urljoin(url, link_knoten.attr("href")) if link_knoten is not None and link_knoten.attr("href") else "",
                datum=datum.text() if datum is not None else "",
                bereich=bereich.text() if bereich is not None else "",
            ))
    m = re.search(r"\(([\d.]+)\s*Treffer\)", html)
    anzahl = int(m.group(1).replace(".", "")) if m else len(treffer)

    nummer = erwartet or 1
    for a in baum.suche("a"):
        titel = a.attr("title") or ""
        if a.hat_klasse("active") and titel.startswith("Zur Seite "):
            try:
                nummer = int(titel.split()[-1])
            except ValueError:
                pass
            break
    naechste = ""
    for a in baum.suche("a", klasse="page-nav"):
        if (a.attr("title") or "") == "Zur nächsten Seite" and a.attr("href"):
            naechste = urllib.parse.urljoin(url, a.attr("href"))
            break
    return Seite(treffer=treffer, nummer=nummer, anzahl_treffer=anzahl, naechste_url=naechste, url=url)


def erkenne_captcha(baum, url):
    """Captcha-Formular finden: Bild-URL, Formularziel und versteckte Felder; None, wenn keins da ist."""
    huelle = baum.erster("div", klasse="captcha_wrapper")
    if huelle is None:
        return None
    bild = huelle.erster("img")
    formular = huelle
    while formular is not None and formular.tag != "form":
        formular = formular.eltern
    if bild is None or formular is None:
        return None
    felder = {}
    for eingabe in formular.suche("input", type="hidden"):
        if eingabe.attr("name"):
            felder[eingabe.attr("name")] = eingabe.attr("value") or ""
    return {
        "bild_url": bild.attr("src"),
        "formular_url": urllib.parse.urljoin(url, formular.attr("action") or url),
        "felder": felder,
    }


def geschaeftsjahr_aus_titel(titel):
    """'Jahresabschluss zum Geschäftsjahr vom 01.01.2021 bis zum 31.12.2021' → ('2021-01-01', '2021-12-31')."""
    daten = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", titel)
    iso = [f"{j}-{m}-{t}" for t, m, j in daten]
    if len(iso) >= 2:
        return iso[0], iso[1]
    if len(iso) == 1:
        return "", iso[0]
    m = re.search(r"\b(19|20)(\d{2})\b", titel)
    return ("", f"{m.group(0)}-12-31") if m else ("", "")
