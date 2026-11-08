"""Zugriff auf das Unternehmensregister (www.unternehmensregister.de) über einen gesteuerten Browser.

Das Unternehmensregister ist seit dem 1. August 2022 die Stelle, an der Jahresabschlüsse offengelegt werden
(Geschäftsjahre ab 2022). Die Seite ist eine reine JavaScript-Anwendung: Suche und Trefferliste entstehen
erst im Browser, Veröffentlichungen stehen hinter einer Sicherheitsabfrage (Captcha), und zu viele Abrufe
führen zur Sperre der IP-Adresse. Dieses Modul bedient die Seite deshalb genauso wie ein Mensch: ein echter
Chromium-Browser (Playwright) füllt das Suchformular aus, blättert, öffnet Veröffentlichungen und reicht
das Captcha-Bild zur Lösung an die Oberfläche weiter. Es gibt keine automatische Captcha-Lösung.

Voraussetzungen: `pip install -r requirements-bilanzen.txt` und ein Chromium (`playwright install chromium`
oder `BILANZ_CHROMIUM=/usr/bin/chromium`). Ohne Playwright meldet `verfuegbar()` den Grund.

Die Schnittstelle entspricht `bundesanzeiger.Client` (suche, naechste_seite, dokument, captcha_loesen), so
dass `auftraege.Verwalter` beide Quellen gleich behandelt.

Die Erkennung von Trefferliste, Veröffentlichung und Captcha arbeitet mit Texten und Rollen der Seite
(„Sicherheitsabfrage“, „Springe eine Seite weiter“, Links mit „Jahresabschluss“), nicht mit festen
CSS-Klassen, weil die Seite diese bei jedem Neubau ändert. `python -m bilanzen diagnose "Begriff"` legt
Bildschirmfotos und Seitenquelltexte jedes Schritts ab, falls etwas nicht erkannt wird.
"""

import logging
import os
import re
import time
import urllib.parse
from pathlib import Path

from .bundesanzeiger import CaptchaNoetig, Dokument, Seite, Treffer

log = logging.getLogger("bilanzen.unternehmensregister")

BASIS = "https://www.unternehmensregister.de"
SUCHE_URL = BASIS + "/de/suche/rechnungslegung"
USER_AGENT_ZUSATZ = "eco-bilanzradar/1.0"
QUELLE = "unternehmensregister"

# JavaScript, das im Browser die Trefferliste in eine einfache Liste verwandelt.
JS_TREFFER = r"""
() => {
  const main = document.querySelector('main') || document.body;
  const muster = /jahresabschluss|konzernabschluss|jahresfinanzbericht|rechnungslegung|offenlegung/i;
  const datum = /\b(\d{2}\.\d{2}\.\d{4})\b/;
  const ergebnis = [];
  const gesehen = new Set();
  const links = Array.from(main.querySelectorAll('a[href]')).filter(a => muster.test(a.textContent || ''));
  for (const a of links) {
    const titel = (a.textContent || '').replace(/\s+/g, ' ').trim();
    // Nächster Vorfahr, der außer dem Link noch eine Überschrift oder einen hervorgehobenen Namen enthält
    let block = a.parentElement; let name = ''; let tiefe = 0;
    while (block && block !== main && tiefe < 8) {
      const kandidaten = Array.from(block.querySelectorAll('h2,h3,h4,h5,strong,b,[class*="ompany"],[class*="name"],[class*="title"],[class*="headline"]'))
        .map(e => (e.textContent || '').replace(/\s+/g, ' ').trim())
        .filter(t => t && t !== titel && !muster.test(t) && t.length < 200);
      if (kandidaten.length) { name = kandidaten[0]; break; }
      block = block.parentElement; tiefe++;
    }
    if (!block || block === main) block = a.closest('li,article,tr,section,div') || a.parentElement;
    const text = (block.textContent || '').replace(/\s+/g, ' ').trim();
    const d = text.match(datum);
    let ort = '';
    const ortTreffer = text.match(/(?:Sitz|Ort|Niederlassung)\s*:?\s*([A-ZÄÖÜ][\wäöüß\-\. ]{2,60}?)(?=\s(?:Veröffentlich|Bereich|Jahres|Rechnungs|\d{2}\.\d{2}\.)|$)/);
    if (ortTreffer) ort = ortTreffer[1].trim();
    const schluessel = name + '|' + titel + '|' + a.href;
    if (gesehen.has(schluessel)) continue;
    gesehen.add(schluessel);
    ergebnis.push({ name, ort, titel, href: a.href, datum: d ? d[1] : '' });
  }
  const sichtbar = (main.innerText || '').replace(/\s+/g, ' ');
  const zaehler = sichtbar.match(/(\d[\d\.]*)\s*(?:Treffer|Ergebnisse|Suchergebnisse)/);
  const weiter = main.querySelector('[aria-label*="Seite weiter"], [title*="Seite weiter"], a[rel="next"], [aria-label*="ächste"]');
  const aktiv = main.querySelector('[aria-label*="Aktuell ausgewählte Seite"], [aria-current="page"]');
  const aktivNr = aktiv ? parseInt((aktiv.getAttribute('aria-label') || aktiv.textContent || '').replace(/\D+/g, ''), 10) : NaN;
  const zuViele = /Zu viele Suchergebnisse/i.test(sichtbar);
  const gesperrt = /IP-Adresse gesperrt|Nutzersitzung abgelaufen/i.test((document.body.innerText || '').replace(/\s+/g, ' '));
  const formular = !!main.querySelector('input[name="companyName"]') && ergebnis.length === 0;
  return { treffer: ergebnis, anzahl: zaehler ? parseInt(zaehler[1].replace(/\./g, ''), 10) : ergebnis.length,
           weiter: !!(weiter && !weiter.hasAttribute('disabled') && weiter.getAttribute('aria-disabled') !== 'true'),
           seite: isNaN(aktivNr) ? null : aktivNr, zuViele, gesperrt, formular, leer: sichtbar.trim().length < 40, url: location.href };
}
"""

JS_SEITE_ART = r"""
() => {
  const main = document.querySelector('main') || document.body;
  const text = (main.innerText || '').replace(/\s+/g, ' ');
  const captchaText = /Sicherheitsabfrage/i.test(text) && /lösen Sie bitte|Zeichen|Sicherheitsabfrage/i.test(text);
  let bild = null;
  if (captchaText) {
    const bilder = Array.from(main.querySelectorAll('img')).filter(i => i.naturalWidth > 60 && i.naturalHeight > 20 && !/logo/i.test(i.src + ' ' + (i.alt || '')));
    bild = bilder.length ? bilder[0] : null;
  }
  const eingabe = captchaText ? main.querySelector('input[type="text"], input:not([type]), input[name*="aptcha"], input[name*="olution"], input[name*="ösung"]') : null;
  const gesperrt = /IP-Adresse gesperrt/i.test(text);
  const fehler = /Ein Fehler ist aufgetreten|Fehlercode/i.test(text) && !/Jahresabschluss|Bilanz/i.test(text);
  const dokument = /Bilanz|Aktiva|Passiva|Jahresabschluss|Gewinn- und Verlustrechnung|Anhang/i.test(text) && !captchaText;
  const iframe = main.querySelector('iframe');
  const dateien = Array.from(main.querySelectorAll('a[href]')).map(a => a.href).filter(h => /\.(xhtml|xml|html?)(\?|$)/i.test(h));
  return { captcha: !!(captchaText && (bild || eingabe)), hatBild: !!bild, hatEingabe: !!eingabe, gesperrt, fehler, dokument,
           iframe: iframe ? iframe.src : null, dateien, url: location.href, titel: document.title };
}
"""

JS_CAPTCHA_BILD = r"""
() => {
  const main = document.querySelector('main') || document.body;
  const bilder = Array.from(main.querySelectorAll('img')).filter(i => i.naturalWidth > 60 && i.naturalHeight > 20 && !/logo/i.test(i.src + ' ' + (i.alt || '')));
  if (!bilder.length) return null;
  const i = bilder[0];
  const c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight;
  try { c.getContext('2d').drawImage(i, 0, 0); return c.toDataURL('image/png'); } catch (e) { return null; }
}
"""


class UnternehmensregisterFehler(Exception):
    pass


def verfuegbar(chromium_pfad=None):
    """(True, '') oder (False, Grund) – ob Playwright und ein Chromium bereitstehen."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, "Python-Paket playwright fehlt: pip install -r requirements-bilanzen.txt"
    pfad = chromium_pfad or os.environ.get("BILANZ_CHROMIUM") or os.environ.get("CHROMIUM")
    if pfad and not Path(pfad).exists():
        return False, f"Chromium nicht gefunden unter {pfad} (BILANZ_CHROMIUM prüfen)"
    return True, ""


class BrowserClient:
    """Bedient das Unternehmensregister mit Playwright. Gleiche Methoden wie bundesanzeiger.Client."""

    def __init__(self, pause=2.0, chromium_pfad=None, sichtbar=False, diagnose_ordner=None, zeitlimit=45):
        self.pause = pause
        self.chromium_pfad = chromium_pfad or os.environ.get("BILANZ_CHROMIUM") or os.environ.get("CHROMIUM") or None
        self.sichtbar = sichtbar
        self.zeitlimit_ms = int(zeitlimit * 1000)
        self.diagnose_ordner = Path(diagnose_ordner) if diagnose_ordner else None
        self.anfragen = 0
        self._schritt = 0
        self._pw = self._browser = self._kontext = self._seite = None
        self._letzte_anfrage = 0.0
        self.suche_url = SUCHE_URL

    # --- Browser ------------------------------------------------------------

    def _starten(self):
        if self._seite is not None:
            return
        ok, grund = verfuegbar(self.chromium_pfad)
        if not ok:
            raise UnternehmensregisterFehler(grund)
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        optionen = {"headless": not self.sichtbar}
        if self.chromium_pfad:
            optionen["executable_path"] = self.chromium_pfad
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        ziel = urllib.parse.urlparse(self.suche_url).hostname or ""
        if proxy and ziel not in ("localhost", "127.0.0.1", "::1"):  # Tests gegen eine lokale Nachbildung laufen ohne Proxy
            optionen["proxy"] = {"server": proxy}
        self._browser = self._pw.chromium.launch(**optionen)
        self._kontext = self._browser.new_context(locale="de-DE", viewport={"width": 1280, "height": 1000})
        self._seite = self._kontext.new_page()
        self._seite.set_default_timeout(self.zeitlimit_ms)

    def schliessen(self):
        for teil in (self._kontext, self._browser):
            try:
                if teil is not None:
                    teil.close()
            except Exception:  # noqa: BLE001 – Aufräumen darf nicht scheitern
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._pw = self._browser = self._kontext = self._seite = None

    def _warte(self):
        rest = self.pause - (time.monotonic() - self._letzte_anfrage)
        if rest > 0:
            time.sleep(rest)

    def _nach_aktion(self, name):
        self._letzte_anfrage = time.monotonic()
        self.anfragen += 1
        try:
            self._seite.wait_for_load_state("networkidle", timeout=self.zeitlimit_ms)
        except Exception:  # noqa: BLE001 – langsame Seite ist kein Fehler
            pass
        self._diagnose(name)

    def _diagnose(self, name):
        if not self.diagnose_ordner:
            return
        self.diagnose_ordner.mkdir(parents=True, exist_ok=True)
        self._schritt += 1
        basis = self.diagnose_ordner / f"{self._schritt:02d}_{name}"
        try:
            self._seite.screenshot(path=str(basis.with_suffix(".png")), full_page=True)
            basis.with_suffix(".html").write_text(self._seite.content(), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.warning("Diagnose %s nicht gespeichert: %s", basis, e)

    def _cookie_banner(self):
        for text in ("Alle akzeptieren", "Akzeptieren", "Nur notwendige", "Zustimmen", "Einverstanden"):
            try:
                knopf = self._seite.get_by_role("button", name=re.compile(text, re.I)).first
                if knopf.is_visible(timeout=500):
                    knopf.click()
                    return
            except Exception:  # noqa: BLE001
                continue

    # --- Suche --------------------------------------------------------------

    def suche(self, begriff, bereich=None):
        self._starten()
        self._warte()
        self._seite.goto(self.suche_url, wait_until="domcontentloaded")
        self._nach_aktion("suchformular")
        self._cookie_banner()
        feld = self._seite.locator('input[name="companyName"]')
        if feld.count() == 0:
            self._pruefe_sperre()
            raise UnternehmensregisterFehler("Suchformular nicht gefunden (Feld companyName) – Seite geändert oder nicht geladen; "
                                             "`python -m bilanzen diagnose` hilft weiter.")
        feld.first.fill(begriff)
        knopf = self._seite.locator('button[name="search"], button[type="submit"]').first
        knopf.click()
        try:
            self._seite.wait_for_url(re.compile(r"/(suche|search)\?|ergebnis|result"), timeout=min(self.zeitlimit_ms, 15000))
        except Exception:  # noqa: BLE001 – wird gleich an der Seite selbst erkannt
            pass
        self._nach_aktion("trefferliste")
        return self._trefferseite(erwartet=1)

    def naechste_seite(self, seite):
        if not seite.naechste_url:
            return None
        self._warte()
        weiter = self._seite.locator('[aria-label*="Seite weiter"], [title*="Seite weiter"], a[rel="next"], [aria-label*="ächste"]').first
        if weiter.count() == 0:
            return None
        weiter.click()
        self._nach_aktion("trefferliste")
        return self._trefferseite(erwartet=seite.nummer + 1)

    def _trefferseite(self, erwartet):
        # Die Trefferliste entsteht erst im Browser: warten, bis Inhalt da ist (höchstens das Zeitlimit)
        ende = time.monotonic() + self.zeitlimit_ms / 1000
        while True:
            self._seite.wait_for_timeout(500)
            daten = self._seite.evaluate(JS_TREFFER)
            if daten["treffer"] or daten.get("zuViele") or daten.get("gesperrt") or daten.get("formular") or not daten.get("leer"):
                break
            if time.monotonic() > ende:
                raise UnternehmensregisterFehler("Die Trefferliste wurde nicht geladen (Seite bleibt leer). Meist sind die Skripte des "
                                                 "Unternehmensregisters im Browser nicht angekommen (Netz/Proxy); `python -m bilanzen diagnose` "
                                                 "legt Bildschirmfotos ab.")
        if daten.get("gesperrt"):
            raise UnternehmensregisterFehler("Das Unternehmensregister meldet eine Sperre oder abgelaufene Sitzung. Bitte später erneut versuchen "
                                             "und BILANZ_PAUSE erhöhen.")
        if daten.get("zuViele"):
            raise UnternehmensregisterFehler("Zu viele Suchergebnisse – das Unternehmensregister verlangt eine engere Suche.")
        if daten.get("formular"):
            raise UnternehmensregisterFehler("Die Suche hat nicht reagiert: Die Seite zeigt weiter das Suchformular. Meist sind die Skripte des "
                                             "Unternehmensregisters im Browser nicht geladen worden (Netz/Proxy); `python -m bilanzen diagnose` "
                                             "legt Bildschirmfotos ab.")
        treffer = [Treffer(name=t["name"], ort=t["ort"], titel=t["titel"], link=t["href"], datum=t["datum"],
                           bereich="Rechnungslegung/Finanzberichte", quelle=QUELLE) for t in daten["treffer"]]
        return Seite(treffer=treffer, nummer=daten.get("seite") or erwartet, anzahl_treffer=daten.get("anzahl") or len(treffer),
                     naechste_url=daten["url"] + "#weiter" if daten.get("weiter") else "", url=daten["url"])

    def _pruefe_sperre(self):
        art = self._seite.evaluate(JS_SEITE_ART)
        if art.get("gesperrt"):
            raise UnternehmensregisterFehler("Das Unternehmensregister hat diese IP-Adresse gesperrt. Pause erhöhen und später erneut versuchen.")
        if art.get("fehler"):
            raise UnternehmensregisterFehler("Das Unternehmensregister zeigt eine Fehlerseite (Skripte nicht geladen oder technischer Fehler).")

    # --- Veröffentlichung ---------------------------------------------------

    def dokument(self, treffer):
        if not treffer.link:
            raise UnternehmensregisterFehler("Zu diesem Treffer gibt es keine aufrufbare Veröffentlichung.")
        self._starten()
        self._warte()
        self._seite.goto(treffer.link, wait_until="domcontentloaded")
        self._nach_aktion("veroeffentlichung")
        return self._dokument_oder_captcha(versuch=1)

    def captcha_loesen(self, captcha, loesung):
        self._warte()
        eingabe = self._seite.locator('main input[type="text"], main input:not([type]), input[name*="aptcha"], input[name*="olution"]').first
        if eingabe.count() == 0:
            raise UnternehmensregisterFehler("Eingabefeld der Sicherheitsabfrage nicht gefunden.")
        eingabe.fill(loesung.strip())
        knopf = self._seite.locator('main button[type="submit"], main input[type="submit"]')
        if knopf.count() == 0:
            knopf = self._seite.get_by_role("button", name=re.compile(r"^(OK|Absenden|Bestätigen|Weiter|Prüfen|Anzeigen)$", re.I))
        if knopf.count():
            knopf.first.click()
        else:
            eingabe.press("Enter")
        self._nach_aktion("nach_captcha")
        return self._dokument_oder_captcha(versuch=captcha.versuch + 1)

    def _dokument_oder_captcha(self, versuch):
        self._seite.wait_for_timeout(500)
        art = self._seite.evaluate(JS_SEITE_ART)
        if art.get("gesperrt"):
            raise UnternehmensregisterFehler("Das Unternehmensregister hat diese IP-Adresse gesperrt. Pause erhöhen und später erneut versuchen.")
        if art.get("captcha"):
            bild = self._captcha_bild()
            raise CaptchaNoetig(bild=bild, bild_typ="image/png", formular_url=art["url"], seite_url=art["url"], versuch=versuch)
        if art.get("fehler"):
            raise UnternehmensregisterFehler("Fehlerseite statt Veröffentlichung.")
        html = self._inhalt(art)
        if not html:
            raise UnternehmensregisterFehler("Veröffentlichung ohne lesbaren Inhalt (eventuell nur PDF oder kostenpflichtige Hinterlegung).")
        return Dokument(html=f'<div class="publication_container">{html}</div>', url=art["url"],
                        text=re.sub(r"<[^>]+>", " ", html))

    def _captcha_bild(self):
        daten = self._seite.evaluate(JS_CAPTCHA_BILD)
        if daten and daten.startswith("data:image/png;base64,"):
            import base64
            return base64.b64decode(daten.split(",", 1)[1])
        # Rückfall: Bildschirmfoto des Hauptbereichs
        main = self._seite.locator("main").first
        return (main if main.count() else self._seite).screenshot()

    def _inhalt(self, art):
        if art.get("iframe"):
            for frame in self._seite.frames:
                if frame != self._seite.main_frame and frame.url and frame.url.rstrip("/") == str(art["iframe"]).rstrip("/"):
                    try:
                        return frame.content()
                    except Exception:  # noqa: BLE001
                        break
        if art.get("dokument"):
            main = self._seite.locator("main").first
            if main.count():
                return main.inner_html()
        for url in art.get("dateien") or []:
            try:
                antwort = self._seite.request.get(url)
                if antwort.ok:
                    return antwort.text()
            except Exception:  # noqa: BLE001
                continue
        main = self._seite.locator("main").first
        return main.inner_html() if main.count() and art.get("dokument") else ""


def diagnose(begriff, ordner, chromium_pfad=None, sichtbar=False, pause=2.0):
    """Suche, erste Trefferseite und erste Veröffentlichung bis zum Captcha durchspielen; alles im Ordner ablegen."""
    ordner = Path(ordner)
    client = BrowserClient(pause=pause, chromium_pfad=chromium_pfad, sichtbar=sichtbar, diagnose_ordner=ordner)
    bericht = []
    try:
        seite = client.suche(begriff)
        bericht.append(f"Suche „{begriff}“: {seite.anzahl_treffer} Treffer gemeldet, {len(seite.treffer)} auf Seite {seite.nummer}, "
                       f"weitere Seiten: {'ja' if seite.naechste_url else 'nein'}")
        for t in seite.treffer[:10]:
            bericht.append(f"  - {t.name or '?'} ({t.ort or '?'}): {t.titel} [{t.datum}] → {t.link}")
        erster = next((t for t in seite.treffer if t.ist_jahresabschluss), None)
        if erster is None:
            bericht.append("Kein Treffer mit aufrufbarem Jahresabschluss erkannt – bitte 02_trefferliste.html prüfen.")
        else:
            try:
                dok = client.dokument(erster)
                bericht.append(f"Veröffentlichung geladen ohne Captcha ({len(dok.html)} Zeichen).")
                (ordner / "veroeffentlichung.html").write_text(dok.html, encoding="utf-8")
            except CaptchaNoetig as c:
                (ordner / "captcha.png").write_bytes(c.bild)
                bericht.append(f"Sicherheitsabfrage erschienen (Bild {len(c.bild)} Bytes → captcha.png). Ablauf bis hierhin funktioniert.")
    except (UnternehmensregisterFehler, CaptchaNoetig) as e:
        bericht.append(f"Abbruch: {e}")
    finally:
        client.schliessen()
    (ordner / "bericht.txt").write_text("\n".join(bericht) + "\n", encoding="utf-8")
    return bericht


def ist_unternehmensregister_url(url):
    return urllib.parse.urlparse(url).netloc.endswith("unternehmensregister.de")
