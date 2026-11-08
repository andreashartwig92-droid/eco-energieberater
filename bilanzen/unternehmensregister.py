"""Direkter Zugriff auf das Unternehmensregister (www.unternehmensregister.de) über einen gesteuerten Browser.

Seit dem 1. August 2022 werden Jahresabschlüsse im Unternehmensregister offengelegt; die Suche dort zeigt auch die
älteren Veröffentlichungen aus dem Bundesanzeiger. Die Seite ist eine JavaScript-Anwendung, deshalb bedient ein
Chromium-Browser (Playwright) sie wie ein Mensch:

1. Suchseite „Rechnungslegung / Finanzberichte“ öffnen, Cookie-Hinweis mit „Nur technisch notwendige Cookies
   akzeptieren“ schließen, Firmenname eintragen, „Suchen“.
2. Trefferliste lesen: je Firma ein Kopf (Name, Amtsgericht, HRB), darunter je Veröffentlichung eine Zeile mit
   Titel („Jahresabschluss zum Geschäftsjahr vom … bis zum …“), Datum und Herkunft. Blättern über „Springe eine
   Seite weiter“ bzw. den Parameter `from` der Ergebnisadresse.
3. Veröffentlichung öffnen. Davor steht die Sicherheitsabfrage des Registers („Ich bin ein Mensch“). Sie wird nicht
   automatisch bestätigt: Das Modul reicht ein Bild der Abfrage an die Oberfläche weiter (`CaptchaNoetig`,
   art="bestaetigen"), ein Mensch bestätigt dort, erst dann klickt der Browser das Kästchen und lädt das Dokument.

Voraussetzungen: `pip install -r requirements-bilanzen.txt` und ein Chromium (`playwright install chromium` oder
`BILANZ_CHROMIUM=/usr/bin/chromium`). Ohne Playwright meldet `verfuegbar()` den Grund.

`python -m bilanzen diagnose "Begriff"` legt Bildschirmfotos und Seitenquelltexte jedes Schritts ab, falls das
Register seine Seite ändert und etwas nicht mehr erkannt wird.
"""

import base64
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path

from .modelle import CaptchaNoetig, Dokument, Seite, Treffer

log = logging.getLogger("bilanzen.unternehmensregister")

BASIS = "https://www.unternehmensregister.de"
SUCHE_URL = BASIS + "/de/suche/rechnungslegung"
QUELLE = "unternehmensregister"

# Liest die Trefferliste. Bevorzugt die data-testid-Attribute der Registerseite, sonst allgemeine Erkennung über Links.
JS_TREFFER = r"""
() => {
  const main = document.querySelector('main') || document.body;
  const sichtbar = (main.innerText || '').replace(/\s+/g, ' ');
  const sauber = (t) => (t || '').replace(/­/g, '').replace(/\s+/g, ' ').trim();
  const muster = /jahresabschluss|konzernabschluss|jahresfinanzbericht/i;
  const ergebnis = [];
  const tabelle = main.querySelector('[data-testid="searchResultTable"]');
  if (tabelle) {
    let kopf = { name: '', register: '' };
    for (const tr of tabelle.querySelectorAll('tbody tr')) {
      if (tr.getAttribute('data-testid') === 'companyHeader') {
        const ps = Array.from(tr.querySelectorAll('th:first-child p')).map(p => sauber(p.textContent)).filter(Boolean);
        kopf = { name: sauber((tr.querySelector('[data-testid="company-name"]') || {}).textContent),
                 register: ps.filter(t => /^Amtsgericht|^(HRB|HRA|GnR|PR|VR)\b/.test(t)).join(' ') };
        continue;
      }
      const firmaZelle = sauber((tr.querySelector('[data-testid="company"]') || {}).textContent);
      const info = Array.from(tr.querySelectorAll('[data-testid="information"] span')).map(s => sauber(s.textContent));
      for (const a of tr.querySelectorAll('[data-testid="label"] a[href]')) {
        const block = a.parentElement;
        const datum = sauber((block.querySelector('[data-cy="searchResult-date"]') || {}).textContent).replace(/^Datum:\s*/, '');
        let name = kopf.name, ort = '';
        const komma = firmaZelle.lastIndexOf(',');
        if (komma > 0) { ort = firmaZelle.slice(komma + 1).trim(); if (!name) name = firmaZelle.slice(0, komma).trim(); }
        else if (!name) name = firmaZelle;
        ergebnis.push({ name, ort, titel: sauber(a.textContent), href: a.href, datum, register: kopf.register,
                        bereich: info[0] || '', herkunft: info[1] || '' });
      }
    }
  } else {
    for (const a of main.querySelectorAll('a[href]')) {
      if (!muster.test(a.textContent || '')) continue;
      const block = a.closest('li,article,tr') || a.parentElement;
      const text = sauber(block.textContent);
      const name = sauber((block.querySelector('h2,h3,h4,strong,b') || {}).textContent);
      const d = text.match(/\b(\d{2}\.\d{2}\.\d{4})\b(?!.*bis zum)/);
      const o = text.match(/Sitz:?\s*([^·|]+?)(?=\s(?:Bereich|Veröffentlicht|Datum)|$)/);
      ergebnis.push({ name, ort: o ? o[1].trim() : '', titel: sauber(a.textContent), href: a.href, datum: d ? d[1] : '',
                      register: '', bereich: '', herkunft: '' });
    }
  }
  const seitenText = sichtbar.match(/(\d[\d\.]*)\s+Seiten?\b/);
  const zaehler = sichtbar.match(/(\d[\d\.]*)\s*(?:Treffer|Ergebnisse\b|Veröffentlichungen gefunden)/);
  const weiter = main.querySelector('[aria-label="Springe eine Seite weiter"], [aria-label*="Seite weiter"], a[rel="next"]');
  const weiterAktiv = !!(weiter && !weiter.disabled && !weiter.hasAttribute('disabled') && weiter.getAttribute('aria-disabled') !== 'true');
  const aktiv = main.querySelector('[aria-label^="Aktuell ausgewählte Seite"], [aria-current="page"]');
  const aktivNr = aktiv ? parseInt((aktiv.getAttribute('aria-label') || aktiv.textContent || '').replace(/\D+/g, ''), 10) : NaN;
  return {
    treffer: ergebnis,
    seiten: seitenText ? parseInt(seitenText[1].replace(/\./g, ''), 10) : null,
    anzahl: zaehler ? parseInt(zaehler[1].replace(/\./g, ''), 10) : null,
    weiter: weiterAktiv, seite: isNaN(aktivNr) ? null : aktivNr,
    zuViele: /Zu viele Suchergebnisse/i.test(sichtbar),
    keine: /keine (Treffer|Ergebnisse|Veröffentlichungen) gefunden|Ihre Suche ergab keine/i.test(sichtbar),
    gesperrt: /IP-Adresse gesperrt|Nutzersitzung abgelaufen/i.test((document.body.innerText || '').replace(/\s+/g, ' ')),
    formular: !!main.querySelector('input[name="companyName"]') && !tabelle && ergebnis.length === 0 && !/Suchergebnis/i.test(sichtbar),
    laedt: sichtbar.trim().length < 40,
    url: location.href,
  };
}
"""

JS_SEITE_ART = r"""
() => {
  const main = document.querySelector('main') || document.body;
  const text = (main.innerText || '').replace(/\s+/g, ' ');
  const fox = main.querySelector('#fox-widget, [id^="fox-captcha"], .captcha_captcha__G6EkL, [class*="captcha_captcha"]');
  const kaestchen = main.querySelector('#fox-captcha-checkbox, input[type="checkbox"][id*="aptcha"]');
  const zeichenBild = Array.from(main.querySelectorAll('img')).find(i => /captcha|sicherheit/i.test((i.alt || '') + ' ' + i.src) && i.naturalWidth > 60);
  const zeichenFeld = main.querySelector('input[name*="olution"], input[name*="aptcha"][type="text"], input[name*="ösung"]');
  const captchaText = /Sicherheitsabfrage/i.test(text) && /lösen Sie bitte|Ich bin ein Mensch|Zeichen/i.test(text);
  let art = '';
  if (fox || kaestchen) art = 'bestaetigen';
  else if (captchaText && (zeichenBild || zeichenFeld)) art = 'text';
  const geloest = !!main.querySelector('[class*="captcha-solved"], [class*="solved-indicator"]:not([hidden])') && !!kaestchen && kaestchen.checked;
  const fehlgeschlagen = /Captcha-Fehler|Prüfung fehlgeschlagen/i.test(text);
  const gesperrt = /IP-Adresse gesperrt/i.test(text);
  const fehler = /Ein Fehler ist aufgetreten|Fehlercode/i.test(text) && !/Jahresabschluss|Bilanz/i.test(text);
  const dokument = !art && /Bilanz|Aktiva|Passiva|Jahresabschluss|Gewinn- und Verlustrechnung|Anhang/i.test(text);
  const iframe = main.querySelector('iframe');
  return { art, geloest, fehlgeschlagen, gesperrt, fehler, dokument, iframe: iframe ? iframe.src : null, url: location.href, titel: document.title };
}
"""

JS_DOKUMENT = r"""
() => {
  const main = document.querySelector('main') || document.body;
  // Bevorzugt den eigentlichen Veröffentlichungsteil; Suchformular, Navigation und Knöpfe weglassen
  const kandidaten = Array.from(main.querySelectorAll('[class*="publication"], [class*="Publication"], [data-testid*="publication"], article, section'))
    .filter(e => /Bilanz|Aktiva|Passiva|Gewinn- und Verlustrechnung|Jahresabschluss/i.test(e.innerText || ''))
    .sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
  const ziel = kandidaten.find(e => (e.querySelectorAll('table').length > 0 || (e.innerText || '').length > 400) && !e.querySelector('form[role="search"]')) || main;
  const kopie = ziel.cloneNode(true);
  kopie.querySelectorAll('form[role="search"], nav, button, script, style, [class*="breadcrumb"], [class*="searchForm"]').forEach(e => e.remove());
  return kopie.innerHTML;
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
    """Bedient das Unternehmensregister mit Playwright: suche, naechste_seite, dokument, captcha_loesen."""

    def __init__(self, pause=2.0, chromium_pfad=None, sichtbar=False, diagnose_ordner=None, zeitlimit=45, captcha_zeitlimit=90):
        self.pause = pause
        self.chromium_pfad = chromium_pfad or os.environ.get("BILANZ_CHROMIUM") or os.environ.get("CHROMIUM") or None
        self.sichtbar = sichtbar
        self.zeitlimit_ms = int(zeitlimit * 1000)
        self.captcha_zeitlimit = captcha_zeitlimit
        self.diagnose_ordner = Path(diagnose_ordner) if diagnose_ordner else None
        self.anfragen = 0
        self._schritt = 0
        self._pw = self._browser = self._kontext = self._seite = None
        self._letzte_anfrage = 0.0
        self._cookies_erledigt = False
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

    def _cookie_hinweis(self):
        """Cookie-Dialog mit „Nur technisch notwendige Cookies akzeptieren“ schließen (nur einmal je Sitzung)."""
        if self._cookies_erledigt:
            return
        for muster in (r"nur technisch notwendige", r"nur notwendige", r"ablehnen"):
            try:
                knopf = self._seite.get_by_role("button", name=re.compile(muster, re.I)).first
                if knopf.count() and knopf.is_visible(timeout=1500):
                    knopf.click()
                    self._seite.wait_for_timeout(800)  # das Formular wird danach neu gezeichnet
                    break
            except Exception:  # noqa: BLE001
                continue
        self._cookies_erledigt = True

    # --- Suche --------------------------------------------------------------

    def suche(self, begriff, bereich=None):
        self._starten()
        self._warte()
        self._seite.goto(self.suche_url, wait_until="domcontentloaded")
        self._nach_aktion("suchformular")
        self._cookie_hinweis()
        feld = self._seite.locator('input[name="companyName"]')
        try:
            feld.first.wait_for(state="visible", timeout=min(self.zeitlimit_ms, 20000))
        except Exception:  # noqa: BLE001
            self._pruefe_sperre()
            raise UnternehmensregisterFehler("Suchformular nicht gefunden (Feld „Firmenname“) – Seite nicht geladen oder geändert; "
                                             "`python -m bilanzen diagnose` legt Bildschirmfotos ab.")
        for _ in range(3):  # nach dem Cookie-Dialog zeichnet die Seite das Formular neu und kann die Eingabe verlieren
            feld.first.fill(begriff)
            self._seite.wait_for_timeout(300)
            if feld.first.input_value() == begriff:
                break
        start_url = self._seite.url
        self._seite.locator('button[name="search"], form[role="search"] button[type="submit"]').first.click()
        try:
            self._seite.wait_for_function("u => location.href !== u", arg=start_url, timeout=min(self.zeitlimit_ms, 20000))
        except Exception:  # noqa: BLE001
            feld.first.press("Enter")
        self._nach_aktion("trefferliste")
        self._begriff = begriff
        return self._trefferseite(erwartet=1)

    def naechste_seite(self, seite):
        if not seite.naechste_url:
            return None
        self._warte()
        if self._seite.url != seite.url:
            # nach dem Öffnen von Veröffentlichungen zurück zur Trefferliste
            self._seite.goto(seite.url, wait_until="domcontentloaded")
            self._nach_aktion("trefferliste_zurueck")
            daten = self._lies_treffer()
            if not daten["treffer"]:
                # Suchsitzung abgelaufen: neu suchen und zur gewünschten Seite springen
                self.suche(getattr(self, "_begriff", ""))
        weiter = self._seite.locator('[aria-label="Springe eine Seite weiter"], [aria-label*="Seite weiter"], a[rel="next"]').first
        try:
            weiter.wait_for(state="attached", timeout=min(self.zeitlimit_ms, 20000))
        except Exception:  # noqa: BLE001
            if not self._lies_treffer().get("weiter"):
                return None
            raise UnternehmensregisterFehler("Knopf „Seite weiter“ nicht gefunden, obwohl weitere Seiten angezeigt werden.")
        while self._aktuelle_seite() < seite.nummer:
            self._blaettern(weiter, self._aktuelle_seite() + 1)
        self._blaettern(weiter, seite.nummer + 1)
        return self._trefferseite(erwartet=seite.nummer + 1)

    def _blaettern(self, weiter, ziel):
        """Eine Seite weiter und warten, bis die Trefferliste wirklich Seite `ziel` zeigt."""
        weiter.click()
        try:
            self._seite.wait_for_function(
                """z => { const e = document.querySelector('[aria-label^="Aktuell ausgewählte Seite"], [aria-current="page"]');
                          return !e || parseInt((e.getAttribute('aria-label') || e.textContent || '').replace(/\\D+/g, ''), 10) >= z; }""",
                arg=ziel, timeout=min(self.zeitlimit_ms, 30000))
        except Exception:  # noqa: BLE001 – wird beim Lesen der Seite erkannt
            pass
        self._nach_aktion("trefferliste")

    def _aktuelle_seite(self):
        d = self._lies_treffer()
        return d.get("seite") or 1

    def _lies_treffer(self):
        return self._seite.evaluate(JS_TREFFER)

    def _trefferseite(self, erwartet):
        # Die Trefferliste entsteht erst im Browser: warten, bis Inhalt da ist (höchstens das Zeitlimit)
        ende = time.monotonic() + self.zeitlimit_ms / 1000
        while True:
            self._seite.wait_for_timeout(500)
            daten = self._lies_treffer()
            if daten["treffer"] or daten.get("zuViele") or daten.get("gesperrt") or daten.get("keine") or daten.get("formular") \
                    or (daten.get("seiten") and not daten.get("laedt")):
                break
            if time.monotonic() > ende:
                raise UnternehmensregisterFehler("Die Trefferliste wurde nicht geladen (Seite bleibt leer). `python -m bilanzen diagnose` "
                                                 "legt Bildschirmfotos ab.")
        if daten.get("gesperrt"):
            raise UnternehmensregisterFehler("Das Unternehmensregister meldet eine Sperre oder abgelaufene Sitzung. Bitte später erneut versuchen "
                                             "und BILANZ_PAUSE erhöhen.")
        if daten.get("zuViele"):
            raise UnternehmensregisterFehler("Zu viele Suchergebnisse – das Unternehmensregister verlangt eine engere Suche.")
        if daten.get("formular") and not daten["treffer"]:
            raise UnternehmensregisterFehler("Die Suche hat nicht reagiert: Die Seite zeigt weiter das Suchformular. "
                                             "`python -m bilanzen diagnose` legt Bildschirmfotos ab.")
        treffer = [Treffer(name=t["name"], ort=t["ort"], titel=t["titel"], link=t["href"], datum=t["datum"],
                           bereich=t.get("bereich") or "Rechnungslegung/Finanzberichte", quelle=QUELLE,
                           register=t.get("register", ""), herkunft=t.get("herkunft", "")) for t in daten["treffer"]]
        seiten = daten.get("seiten") or 0
        anzahl = daten.get("anzahl") or (seiten * max(len(treffer), 1) if seiten else len(treffer))
        return Seite(treffer=treffer, nummer=daten.get("seite") or erwartet, anzahl_treffer=anzahl,
                     naechste_url=daten["url"] + "#weiter" if daten.get("weiter") else "", url=daten["url"], anzahl_seiten=seiten)

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
        """Erst aufrufen, wenn ein Mensch die Sicherheitsabfrage in der Oberfläche bestätigt bzw. die Zeichen eingegeben hat."""
        self._warte()
        if captcha.art == "bestaetigen":
            kaestchen = self._seite.locator('label[for="fox-captcha-checkbox"], #fox-captcha-checkbox, input[type="checkbox"][id*="aptcha"]').first
            if kaestchen.count() == 0:
                raise UnternehmensregisterFehler("Kästchen der Sicherheitsabfrage nicht gefunden.")
            kaestchen.click()
            # Die Abfrage rechnet danach einige Sekunden im Browser und gibt dann die Veröffentlichung frei
            ende = time.monotonic() + self.captcha_zeitlimit
            while time.monotonic() < ende:
                self._seite.wait_for_timeout(1000)
                art = self._seite.evaluate(JS_SEITE_ART)
                if not art.get("art") or art.get("fehlgeschlagen"):
                    break
            self._nach_aktion("nach_sicherheitsabfrage")
        else:
            eingabe = self._seite.locator('main input[type="text"], main input:not([type]), input[name*="aptcha"], input[name*="olution"]').first
            if eingabe.count() == 0:
                raise UnternehmensregisterFehler("Eingabefeld der Sicherheitsabfrage nicht gefunden.")
            eingabe.fill((loesung or "").strip())
            knopf = self._seite.locator('main button[type="submit"], main input[type="submit"]')
            if knopf.count():
                knopf.first.click()
            else:
                eingabe.press("Enter")
            self._nach_aktion("nach_sicherheitsabfrage")
        return self._dokument_oder_captcha(versuch=captcha.versuch + 1)

    def _dokument_oder_captcha(self, versuch):
        ende = time.monotonic() + min(self.zeitlimit_ms / 1000, 20)
        while True:
            self._seite.wait_for_timeout(500)
            art = self._seite.evaluate(JS_SEITE_ART)
            if art.get("art") or art.get("dokument") or art.get("gesperrt") or art.get("fehler") or time.monotonic() > ende:
                break
        if art.get("gesperrt"):
            raise UnternehmensregisterFehler("Das Unternehmensregister hat diese IP-Adresse gesperrt. Pause erhöhen und später erneut versuchen.")
        if art.get("art"):
            raise CaptchaNoetig(bild=self._captcha_bild(art["art"]), bild_typ="image/png", formular_url=art["url"], seite_url=art["url"],
                                versuch=versuch, art=art["art"])
        if art.get("fehler"):
            raise UnternehmensregisterFehler("Fehlerseite statt Veröffentlichung.")
        html = self._inhalt(art)
        if not html or not re.search(r"Bilanz|Aktiva|Passiva|Jahresabschluss", re.sub(r"<[^>]+>", " ", html)):
            raise UnternehmensregisterFehler("Veröffentlichung ohne lesbaren Abschluss (eventuell nur PDF oder kostenpflichtige Hinterlegung).")
        return Dokument(html=f'<div class="publication_container">{html}</div>', url=art["url"], text=re.sub(r"<[^>]+>", " ", html))

    def _captcha_bild(self, art):
        """Bild der Abfrage für die Oberfläche: bei Zeichen-Captchas das Bild selbst, sonst ein Ausschnitt der Abfrage."""
        if art == "text":
            daten = self._seite.evaluate(r"""() => {
              const i = Array.from(document.querySelectorAll('main img')).find(i => /captcha|sicherheit/i.test((i.alt||'') + ' ' + i.src));
              if (!i) return null; const c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight;
              try { c.getContext('2d').drawImage(i, 0, 0); return c.toDataURL('image/png'); } catch (e) { return null; } }""")
            if daten and daten.startswith("data:image/png;base64,"):
                return base64.b64decode(daten.split(",", 1)[1])
        bereich = self._seite.locator('[class*="captcha_captcha"], #fox-widget, #captcha').first
        try:
            return (bereich if bereich.count() else self._seite.locator("main").first).screenshot()
        except Exception:  # noqa: BLE001
            return self._seite.screenshot()

    def _inhalt(self, art):
        if art.get("iframe"):
            for frame in self._seite.frames:
                if frame != self._seite.main_frame and frame.url and frame.url.rstrip("/") == str(art["iframe"]).rstrip("/"):
                    try:
                        return frame.content()
                    except Exception:  # noqa: BLE001
                        break
        try:
            return self._seite.evaluate(JS_DOKUMENT)
        except Exception:  # noqa: BLE001
            main = self._seite.locator("main").first
            return main.inner_html() if main.count() else ""


def diagnose(begriff, ordner, chromium_pfad=None, sichtbar=False, pause=2.0):
    """Suche, erste Trefferseite und erste Veröffentlichung bis zur Sicherheitsabfrage durchspielen; alles im Ordner ablegen."""
    ordner = Path(ordner)
    client = BrowserClient(pause=pause, chromium_pfad=chromium_pfad, sichtbar=sichtbar, diagnose_ordner=ordner)
    bericht = []
    try:
        seite = client.suche(begriff)
        bericht.append(f"Suche „{begriff}“: {seite.anzahl_seiten or '?'} Seiten, {len(seite.treffer)} Veröffentlichungen auf Seite {seite.nummer}, "
                       f"weitere Seiten: {'ja' if seite.naechste_url else 'nein'}")
        for t in seite.treffer[:10]:
            bericht.append(f"  - {t.name or '?'} ({t.ort or '?'}, {t.register or '?'}): {t.titel} [{t.datum}, {t.herkunft or '?'}]")
        erster = next((t for t in seite.treffer if t.ist_jahresabschluss), None)
        if erster is None:
            bericht.append("Kein Treffer mit aufrufbarem Jahresabschluss erkannt – bitte 02_trefferliste.html prüfen.")
        else:
            try:
                dok = client.dokument(erster)
                bericht.append(f"Veröffentlichung geladen ohne Sicherheitsabfrage ({len(dok.html)} Zeichen).")
                (ordner / "veroeffentlichung.html").write_text(dok.html, encoding="utf-8")
            except CaptchaNoetig as c:
                (ordner / "sicherheitsabfrage.png").write_bytes(c.bild)
                bericht.append(f"Sicherheitsabfrage erschienen (Art: {c.art}, Bild → sicherheitsabfrage.png). Der Ablauf funktioniert bis hierhin; "
                               "ab hier bestätigt ein Mensch in der Oberfläche.")
    except (UnternehmensregisterFehler, CaptchaNoetig) as e:
        bericht.append(f"Abbruch: {e}")
    finally:
        client.schliessen()
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "bericht.txt").write_text("\n".join(bericht) + "\n", encoding="utf-8")
    return bericht
