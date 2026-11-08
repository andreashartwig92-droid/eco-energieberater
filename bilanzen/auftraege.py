"""Hintergrundaufträge: Suchbegriffe im Unternehmensregister abfragen, Jahresabschlüsse laden, auswerten, speichern.

Ein Arbeiter-Thread arbeitet die Aufträge nacheinander ab (eine Browsersitzung, eine Anfrage nach der anderen).
Verlangt das Register eine Sicherheitsabfrage, bleibt der Auftrag im Zustand `captcha` stehen, bis ein Mensch sie
über `captcha_beantworten` bestätigt (Kästchen „Ich bin ein Mensch“) bzw. die Zeichen eingibt. Der Zustand jedes
Auftrags ist über `als_dict()` für die Oberfläche abrufbar.
"""

import base64
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from .modelle import CaptchaNoetig, geschaeftsjahr_aus_titel
from .unternehmensregister import UnternehmensregisterFehler

QUELLE = "unternehmensregister"
QUELLEN_NAMEN = {"unternehmensregister": "Unternehmensregister"}
QUELLEN_FEHLER = (UnternehmensregisterFehler,)

log = logging.getLogger("bilanzen.auftraege")

ZUSTAENDE = ("wartet", "sucht", "laedt", "captcha", "fertig", "fehler", "abgebrochen")


@dataclass
class Auftrag:
    begriffe: list
    max_seiten: int = 5
    nur_neue: bool = True
    nur_liste: bool = False  # nur Treffer zählen/anzeigen, keine Dokumente laden
    ab_jahr: int = 0  # nur Geschäftsjahre ab diesem Jahr laden (0 = alle); spart Bestätigungen für sehr alte Abschlüsse
    nur_juengster: bool = False  # je Firma nur den jüngsten Jahresabschluss laden (eine Bestätigung je Firma)
    _firmen_erledigt: set = field(default_factory=set)
    quelle: str = QUELLE
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    zustand: str = "wartet"
    erstellt: float = field(default_factory=time.time)
    begonnen: float | None = None
    beendet: float | None = None
    aktueller_begriff: str = ""
    seiten_gelesen: int = 0
    seiten_gesamt: int = 0
    treffer_gesamt: int = 0  # Veröffentlichungen laut Register
    treffer_gesehen: int = 0
    geladen: int = 0
    uebersprungen: int = 0
    fehler: int = 0
    captcha_versuche: int = 0
    meldung: str = ""
    protokoll: deque = field(default_factory=lambda: deque(maxlen=200))
    treffer_liste: list = field(default_factory=list)  # bei nur_liste
    captcha: CaptchaNoetig | None = None
    captcha_treffer: str = ""  # welche Veröffentlichung gerade auf die Bestätigung wartet
    _captcha_loesung: str | None = None
    _ereignis: threading.Event = field(default_factory=threading.Event)
    abbruch: bool = False

    def log(self, text):
        self.protokoll.append({"zeit": time.time(), "text": text})
        log.info("[%s] %s", self.id, text)

    def als_dict(self):
        d = {
            "id": self.id, "begriffe": self.begriffe, "max_seiten": self.max_seiten, "nur_neue": self.nur_neue, "nur_liste": self.nur_liste,
            "ab_jahr": self.ab_jahr, "nur_juengster": self.nur_juengster, "quelle": self.quelle, "zustand": self.zustand, "erstellt": self.erstellt, "begonnen": self.begonnen, "beendet": self.beendet,
            "aktueller_begriff": self.aktueller_begriff, "seiten_gelesen": self.seiten_gelesen, "seiten_gesamt": self.seiten_gesamt,
            "treffer_gesamt": self.treffer_gesamt, "treffer_gesehen": self.treffer_gesehen, "geladen": self.geladen,
            "uebersprungen": self.uebersprungen, "fehler": self.fehler, "captcha_versuche": self.captcha_versuche, "meldung": self.meldung,
            "protokoll": list(self.protokoll)[-40:], "treffer_liste": self.treffer_liste[-500:],
        }
        if self.zustand == "captcha" and self.captcha is not None:
            d["captcha_bild"] = f"data:{self.captcha.bild_typ};base64," + base64.b64encode(self.captcha.bild).decode("ascii")
            d["captcha_art"] = self.captcha.art
            d["captcha_treffer"] = self.captcha_treffer
        return d


class Verwalter:
    def __init__(self, speicher, client_fabrik=None, pause=2.0, chromium_pfad=None):
        """`client_fabrik` ersetzt den Browser-Client (für Tests); ohne Angabe wird das Unternehmensregister im Browser bedient."""
        self.speicher = speicher
        self._eigene_fabrik = client_fabrik is not None
        if client_fabrik is None:
            def client_fabrik():
                from .unternehmensregister import BrowserClient
                return BrowserClient(pause=pause, chromium_pfad=chromium_pfad)
        self.client_fabrik = client_fabrik
        self.chromium_pfad = chromium_pfad
        self.auftraege = {}
        self._reihe = deque()
        self._sperre = threading.Lock()
        self._weckruf = threading.Event()
        self._thread = threading.Thread(target=self._schleife, name="bilanzen-arbeiter", daemon=True)
        self._laeuft = True
        self._thread.start()

    def stoppen(self):
        self._laeuft = False
        self._weckruf.set()

    # --- Schnittstelle ---------------------------------------------------------

    def anlegen(self, begriffe, max_seiten=5, nur_neue=True, nur_liste=False, ab_jahr=0, nur_juengster=False, **_):
        begriffe = [b.strip() for b in begriffe if b and b.strip()]
        if not begriffe:
            raise ValueError("Mindestens ein Suchbegriff ist nötig.")
        if not self._eigene_fabrik:
            from .unternehmensregister import verfuegbar
            ok, grund = verfuegbar(self.chromium_pfad)
            if not ok:
                raise ValueError(f"Unternehmensregister nicht nutzbar: {grund}")
        a = Auftrag(begriffe=begriffe, max_seiten=max(0, int(max_seiten)), nur_neue=bool(nur_neue), nur_liste=bool(nur_liste),
                    ab_jahr=max(0, int(ab_jahr or 0)), nur_juengster=bool(nur_juengster))
        with self._sperre:
            self.auftraege[a.id] = a
            self._reihe.append(a.id)
        a.log(f"Auftrag angelegt: {', '.join(begriffe)} (bis {a.max_seiten or 'alle'} Seiten je Begriff"
              f"{f', Geschäftsjahre ab {a.ab_jahr}' if a.ab_jahr else ''}{', nur jüngster Abschluss je Firma' if a.nur_juengster else ''})")
        self._weckruf.set()
        return a

    def liste(self):
        with self._sperre:
            return [a.als_dict() for a in sorted(self.auftraege.values(), key=lambda a: -a.erstellt)]

    def holen(self, auftrag_id):
        return self.auftraege.get(auftrag_id)

    def captcha_beantworten(self, auftrag_id, loesung):
        """Ein Mensch hat die Sicherheitsabfrage bestätigt (loesung "bestaetigt") bzw. die Zeichen eingegeben."""
        a = self.auftraege.get(auftrag_id)
        if a is None:
            raise KeyError(auftrag_id)
        if a.zustand != "captcha":
            raise ValueError("Für diesen Auftrag ist gerade keine Sicherheitsabfrage offen.")
        a._captcha_loesung = (loesung or "").strip()
        a._ereignis.set()

    def abbrechen(self, auftrag_id):
        a = self.auftraege.get(auftrag_id)
        if a is None:
            raise KeyError(auftrag_id)
        a.abbruch = True
        a._ereignis.set()
        if a.zustand == "wartet":
            a.zustand = "abgebrochen"
            a.beendet = time.time()

    # --- Arbeiter --------------------------------------------------------------

    def _schleife(self):
        while self._laeuft:
            auftrag = None
            with self._sperre:
                while self._reihe:
                    kandidat = self.auftraege.get(self._reihe.popleft())
                    if kandidat is not None and kandidat.zustand == "wartet":
                        auftrag = kandidat
                        break
            if auftrag is None:
                self._weckruf.wait(timeout=1.0)
                self._weckruf.clear()
                continue
            try:
                self._ausfuehren(auftrag)
            except Exception as e:  # noqa: BLE001 – der Arbeiter soll weiterlaufen
                log.exception("Auftrag %s abgebrochen", auftrag.id)
                auftrag.zustand = "fehler"
                auftrag.meldung = f"Unerwarteter Fehler: {e}"
                auftrag.beendet = time.time()

    def _ausfuehren(self, a):
        a.begonnen = time.time()
        try:
            client = self.client_fabrik()
        except QUELLEN_FEHLER as e:
            a.zustand, a.meldung, a.beendet = "fehler", str(e), time.time()
            a.log(f"Unternehmensregister nicht nutzbar: {e}")
            return
        try:
            self._durchlaufen(a, client)
        finally:
            if hasattr(client, "schliessen"):
                try:
                    client.schliessen()
                except Exception:  # noqa: BLE001
                    pass

    def _durchlaufen(self, a, client):
        for begriff in a.begriffe:
            if a.abbruch:
                break
            a.aktueller_begriff = begriff
            a.zustand = "sucht"
            a.log(f"Suche „{begriff}“ im Unternehmensregister (Rechnungslegung/Finanzberichte) …")
            try:
                seite = client.suche(begriff)
            except QUELLEN_FEHLER as e:
                a.fehler += 1
                a.log(f"Suche fehlgeschlagen: {e}")
                continue
            a.treffer_gesamt += seite.anzahl_treffer
            a.seiten_gesamt += getattr(seite, "anzahl_seiten", 0) or 0
            a.log(f"{getattr(seite, 'anzahl_seiten', 0) or '?'} Seiten mit Veröffentlichungen gefunden.")
            while seite is not None and not a.abbruch:
                a.seiten_gelesen += 1
                for treffer in seite.treffer:
                    if a.abbruch:
                        break
                    a.treffer_gesehen += 1
                    self._treffer_bearbeiten(a, client, begriff, treffer)
                if a.max_seiten and seite.nummer >= a.max_seiten:
                    break
                a.zustand = "sucht"
                try:
                    seite = client.naechste_seite(seite)
                except QUELLEN_FEHLER as e:
                    a.fehler += 1
                    a.log(f"Nächste Seite fehlgeschlagen: {e}")
                    break
        a.zustand = "abgebrochen" if a.abbruch else "fertig"
        a.beendet = time.time()
        a.meldung = (f"{a.geladen} Abschlüsse geladen, {a.uebersprungen} übersprungen, {a.fehler} Fehler, "
                     f"{client.anfragen} Seitenaufrufe im Unternehmensregister.")
        a.log("Fertig. " + a.meldung)

    def _treffer_bearbeiten(self, a, client, begriff, treffer):
        gj_von, gj_bis = geschaeftsjahr_aus_titel(treffer.titel)
        if a.nur_liste:
            a.treffer_liste.append({"name": treffer.name, "ort": treffer.ort, "titel": treffer.titel, "datum": treffer.datum,
                                    "gj_bis": gj_bis, "einsehbar": bool(treffer.link), "register": treffer.register,
                                    "herkunft": treffer.herkunft,
                                    "vorhanden": self.speicher.hat_abschluss(treffer.name, treffer.ort, gj_bis)})
            return
        if a.ab_jahr and gj_bis and int(gj_bis[:4]) < a.ab_jahr:
            a.uebersprungen += 1
            return
        firma = (treffer.name.strip().lower(), treffer.ort.strip().lower())
        if a.nur_juengster and treffer.ist_jahresabschluss and firma in a._firmen_erledigt:
            a.uebersprungen += 1  # die Trefferliste nennt je Firma den jüngsten Abschluss zuerst
            return
        if not treffer.ist_jahresabschluss:
            a.uebersprungen += 1
            grund = "kein einsehbares Dokument (nur hinterlegt)" if not treffer.link else f"kein Jahresabschluss: {treffer.titel[:60]}"
            self.speicher.uebersprungen_merken(begriff, treffer, grund)
            return
        if a.nur_neue and self.speicher.hat_abschluss(treffer.name, treffer.ort, gj_bis):
            a._firmen_erledigt.add(firma)
            a.uebersprungen += 1
            # Firma trotzdem dem Suchbegriff zuordnen
            self.speicher.firma_anlegen(treffer.name, treffer.ort, suchbegriff=begriff)
            return
        a.zustand = "laedt"
        a.log(f"Lade: {treffer.name} – {treffer.titel}")
        try:
            dokument = self._dokument_mit_captcha(a, client, treffer)
        except QUELLEN_FEHLER as e:
            a.fehler += 1
            a.log(f"Fehler: {e}")
            self.speicher.uebersprungen_merken(begriff, treffer, f"Fehler: {e}")
            return
        if dokument is None:  # abgebrochen
            return
        a._firmen_erledigt.add(firma)
        _, _, abschluss = self.speicher.dokument_speichern(
            treffer.name, treffer.ort, dokument.html, titel=treffer.titel, veroeffentlicht=treffer.datum,
            suchbegriff=begriff, quelle=a.quelle, quelle_url=dokument.url)
        a.geladen += 1
        if abschluss.warnungen:
            a.log(f"  Hinweis: {'; '.join(abschluss.warnungen)}")

    def _dokument_mit_captcha(self, a, client, treffer):
        try:
            return client.dokument(treffer)
        except CaptchaNoetig as c:
            captcha = c
        while not a.abbruch:
            a.captcha = captcha
            a.captcha_treffer = f"{treffer.name} – {treffer.titel}"
            a.zustand = "captcha"
            a._captcha_loesung = None
            a._ereignis.clear()
            a.log("Sicherheitsabfrage des Unternehmensregisters – bitte in der Oberfläche bestätigen.")
            while not a._ereignis.wait(timeout=1.0):
                if a.abbruch or not self._laeuft:
                    return None
            if a.abbruch:
                return None
            loesung = a._captcha_loesung or ""
            a.captcha_versuche += 1
            a.zustand = "laedt"
            try:
                dokument = client.captcha_loesen(captcha, loesung)
                a.captcha = None
                a.log("Sicherheitsabfrage bestätigt, Veröffentlichung geladen.")
                return dokument
            except CaptchaNoetig as c:
                captcha = c
                a.log("Sicherheitsabfrage noch offen – bitte erneut bestätigen.")
        return None
