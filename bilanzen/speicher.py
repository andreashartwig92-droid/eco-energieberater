"""SQLite-Ablage für Unternehmen, Abschlüsse (mit Rohdokument), Posten und Kennzahlen.

Eine Firma wird über Name + Ort erkannt. Je Firma und Geschäftsjahresende gibt es höchstens einen
Abschluss; ein erneuter Abruf ersetzt ihn (z. B. nach einer Parser-Verbesserung).
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from . import kennzahlen as _kz
from .parser import parse_jahresabschluss

SCHEMA = """
CREATE TABLE IF NOT EXISTS firmen (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ort TEXT NOT NULL DEFAULT '',
    rechtsform TEXT NOT NULL DEFAULT '',
    suchbegriffe TEXT NOT NULL DEFAULT '',       -- JSON-Liste der Suchbegriffe, über die die Firma gefunden wurde
    erstellt TEXT NOT NULL,
    UNIQUE(name, ort)
);
CREATE TABLE IF NOT EXISTS abschluesse (
    id INTEGER PRIMARY KEY,
    firma_id INTEGER NOT NULL REFERENCES firmen(id) ON DELETE CASCADE,
    titel TEXT NOT NULL DEFAULT '',
    gj_von TEXT NOT NULL DEFAULT '',
    gj_bis TEXT NOT NULL DEFAULT '',
    veroeffentlicht TEXT NOT NULL DEFAULT '',
    quelle TEXT NOT NULL DEFAULT 'bundesanzeiger', -- bundesanzeiger | import
    quelle_url TEXT NOT NULL DEFAULT '',
    roh_html TEXT NOT NULL DEFAULT '',
    abschluss_json TEXT NOT NULL DEFAULT '{}',
    kennzahlen_json TEXT NOT NULL DEFAULT '{}',
    geladen TEXT NOT NULL,
    UNIQUE(firma_id, gj_bis)
);
CREATE TABLE IF NOT EXISTS uebersprungen (
    id INTEGER PRIMARY KEY,
    suchbegriff TEXT NOT NULL,
    name TEXT NOT NULL,
    ort TEXT NOT NULL DEFAULT '',
    titel TEXT NOT NULL DEFAULT '',
    grund TEXT NOT NULL,
    zeit TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_abschluesse_firma ON abschluesse(firma_id, gj_bis DESC);
"""


def _jetzt():
    return datetime.now().isoformat(timespec="seconds")


class Speicher:
    def __init__(self, pfad):
        self.pfad = Path(pfad) if str(pfad) != ":memory:" else pfad
        if isinstance(self.pfad, Path):
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self._sperre = threading.RLock()
        self._db = sqlite3.connect(str(self.pfad), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def schliessen(self):
        self._db.close()

    def __del__(self):
        try:
            self._db.close()
        except Exception:  # noqa: BLE001 – beim Aufräumen ist nichts mehr zu retten
            pass

    # --- Firmen ------------------------------------------------------------

    def firma_anlegen(self, name, ort="", rechtsform="", suchbegriff=""):
        """Liefert die Firmen-ID; legt die Firma an, wenn es sie noch nicht gibt, und merkt den Suchbegriff."""
        name = name.strip()
        ort = ort.strip()
        with self._sperre:
            zeile = self._db.execute("SELECT id, suchbegriffe, rechtsform FROM firmen WHERE name = ? AND ort = ?", (name, ort)).fetchone()
            if zeile is None:
                begriffe = [suchbegriff] if suchbegriff else []
                cur = self._db.execute("INSERT INTO firmen (name, ort, rechtsform, suchbegriffe, erstellt) VALUES (?, ?, ?, ?, ?)",
                                       (name, ort, rechtsform, json.dumps(begriffe, ensure_ascii=False), _jetzt()))
                self._db.commit()
                return cur.lastrowid
            begriffe = json.loads(zeile["suchbegriffe"] or "[]")
            geaendert = False
            if suchbegriff and suchbegriff not in begriffe:
                begriffe.append(suchbegriff)
                geaendert = True
            if rechtsform and not zeile["rechtsform"]:
                geaendert = True
            if geaendert:
                self._db.execute("UPDATE firmen SET suchbegriffe = ?, rechtsform = COALESCE(NULLIF(rechtsform, ''), ?) WHERE id = ?",
                                 (json.dumps(begriffe, ensure_ascii=False), rechtsform, zeile["id"]))
                self._db.commit()
            return zeile["id"]

    def hat_abschluss(self, name, ort, gj_bis):
        with self._sperre:
            z = self._db.execute("SELECT a.id FROM abschluesse a JOIN firmen f ON f.id = a.firma_id WHERE f.name = ? AND f.ort = ? AND a.gj_bis = ?",
                                 (name.strip(), ort.strip(), gj_bis)).fetchone()
            return z is not None

    def hat_abschluss_quelle(self, name, ort, quelle):
        with self._sperre:
            z = self._db.execute("SELECT a.id FROM abschluesse a JOIN firmen f ON f.id = a.firma_id WHERE f.name = ? AND f.ort = ? AND a.quelle = ? LIMIT 1",
                                 (name.strip(), ort.strip(), quelle)).fetchone()
            return z is not None

    # --- Abschlüsse ----------------------------------------------------------

    def abschluss_speichern(self, firma_id, abschluss, roh_html="", titel="", veroeffentlicht="", quelle="bundesanzeiger", quelle_url=""):
        k = _kz.berechne(abschluss)
        daten = abschluss.als_dict()
        with self._sperre:
            self._db.execute(
                """INSERT INTO abschluesse (firma_id, titel, gj_von, gj_bis, veroeffentlicht, quelle, quelle_url, roh_html, abschluss_json, kennzahlen_json, geladen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(firma_id, gj_bis) DO UPDATE SET titel = excluded.titel, gj_von = excluded.gj_von,
                   veroeffentlicht = excluded.veroeffentlicht, quelle = excluded.quelle, quelle_url = excluded.quelle_url,
                   roh_html = excluded.roh_html, abschluss_json = excluded.abschluss_json, kennzahlen_json = excluded.kennzahlen_json, geladen = excluded.geladen""",
                (firma_id, titel or abschluss.titel, abschluss.gj_von, abschluss.gj_bis, veroeffentlicht, quelle, quelle_url, roh_html,
                 json.dumps(daten, ensure_ascii=False), json.dumps(k, ensure_ascii=False), _jetzt()))
            if abschluss.rechtsform:
                self._db.execute("UPDATE firmen SET rechtsform = ? WHERE id = ? AND rechtsform = ''", (abschluss.rechtsform, firma_id))
            self._db.commit()
            z = self._db.execute("SELECT id FROM abschluesse WHERE firma_id = ? AND gj_bis = ?", (firma_id, abschluss.gj_bis)).fetchone()
            return z["id"]

    def dokument_speichern(self, name, ort, html, titel="", veroeffentlicht="", suchbegriff="", quelle="bundesanzeiger", quelle_url=""):
        """HTML parsen und ablegen; liefert (firma_id, abschluss_id, Abschluss)."""
        abschluss = parse_jahresabschluss(html, titel=titel, firma=name)
        if not abschluss.gj_bis:
            from .bundesanzeiger import geschaeftsjahr_aus_titel
            abschluss.gj_von, abschluss.gj_bis = geschaeftsjahr_aus_titel(titel)
        firma_id = self.firma_anlegen(name or abschluss.firma, ort, abschluss.rechtsform, suchbegriff)
        abschluss_id = self.abschluss_speichern(firma_id, abschluss, html, titel, veroeffentlicht, quelle, quelle_url)
        return firma_id, abschluss_id, abschluss

    def uebersprungen_merken(self, suchbegriff, treffer, grund):
        with self._sperre:
            self._db.execute("INSERT INTO uebersprungen (suchbegriff, name, ort, titel, grund, zeit) VALUES (?, ?, ?, ?, ?, ?)",
                             (suchbegriff, treffer.name, treffer.ort, treffer.titel, grund, _jetzt()))
            self._db.commit()

    def neu_berechnen(self):
        """Alle Abschlüsse mit dem aktuellen Parser neu auswerten (nach Parser-Änderungen)."""
        with self._sperre:
            zeilen = self._db.execute("SELECT id, firma_id, titel, veroeffentlicht, quelle, quelle_url, roh_html FROM abschluesse WHERE roh_html != ''").fetchall()
            for z in zeilen:
                firma = self._db.execute("SELECT name FROM firmen WHERE id = ?", (z["firma_id"],)).fetchone()
                a = parse_jahresabschluss(z["roh_html"], titel=z["titel"], firma=firma["name"])
                self.abschluss_speichern(z["firma_id"], a, z["roh_html"], z["titel"], z["veroeffentlicht"], z["quelle"], z["quelle_url"])
            return len(zeilen)

    # --- Abfragen ------------------------------------------------------------

    def suchbegriffe(self):
        with self._sperre:
            alle = {}
            for z in self._db.execute("SELECT suchbegriffe FROM firmen"):
                for b in json.loads(z["suchbegriffe"] or "[]"):
                    alle[b] = alle.get(b, 0) + 1
            return dict(sorted(alle.items(), key=lambda kv: (-kv[1], kv[0])))

    def firmen(self, suchbegriff=None):
        """Je Firma der jüngste Abschluss mit Kennzahlen (für Tabelle und Branchenbild)."""
        with self._sperre:
            zeilen = self._db.execute(
                """SELECT f.id, f.name, f.ort, f.rechtsform, f.suchbegriffe, a.id AS abschluss_id, a.gj_bis, a.quelle, a.kennzahlen_json, a.abschluss_json,
                          (SELECT COUNT(*) FROM abschluesse x WHERE x.firma_id = f.id) AS anzahl_abschluesse
                   FROM firmen f
                   LEFT JOIN abschluesse a ON a.id = (SELECT id FROM abschluesse y WHERE y.firma_id = f.id ORDER BY gj_bis DESC, id DESC LIMIT 1)
                   ORDER BY f.name""").fetchall()
            verlaeufe = {}
            for v in self._db.execute("SELECT firma_id, gj_bis, kennzahlen_json FROM abschluesse ORDER BY gj_bis"):
                k = json.loads(v["kennzahlen_json"] or "{}")
                verlaeufe.setdefault(v["firma_id"], []).append({
                    "gj_bis": v["gj_bis"], "bilanzsumme": k.get("bilanzsumme"), "eigenkapital": k.get("eigenkapital"), "umsatz": k.get("umsatz"),
                    "jahresueberschuss": k.get("jahresueberschuss"), "mitarbeiter": k.get("mitarbeiter"), "score": k.get("score"),
                })
        ergebnis = []
        for z in zeilen:
            begriffe = json.loads(z["suchbegriffe"] or "[]")
            if suchbegriff and suchbegriff not in begriffe:
                continue
            k = json.loads(z["kennzahlen_json"]) if z["kennzahlen_json"] else None
            a = json.loads(z["abschluss_json"]) if z["abschluss_json"] else {}
            ergebnis.append({
                "id": z["id"], "name": z["name"], "ort": z["ort"], "rechtsform": z["rechtsform"] or a.get("rechtsform", ""),
                "suchbegriffe": begriffe, "abschluss_id": z["abschluss_id"], "gj_bis": z["gj_bis"], "quelle": z["quelle"],
                "anzahl_abschluesse": z["anzahl_abschluesse"], "groessenklasse": a.get("groessenklasse", ""),
                "kennzahlen": k, "verlauf": verlaeufe.get(z["id"], []),
            })
        return ergebnis

    def firma(self, firma_id):
        with self._sperre:
            f = self._db.execute("SELECT * FROM firmen WHERE id = ?", (firma_id,)).fetchone()
            if f is None:
                return None
            abschluesse = self._db.execute(
                "SELECT id, titel, gj_von, gj_bis, veroeffentlicht, quelle, quelle_url, abschluss_json, kennzahlen_json, geladen, LENGTH(roh_html) AS roh_laenge "
                "FROM abschluesse WHERE firma_id = ? ORDER BY gj_bis DESC", (firma_id,)).fetchall()
        return {
            "id": f["id"], "name": f["name"], "ort": f["ort"], "rechtsform": f["rechtsform"], "suchbegriffe": json.loads(f["suchbegriffe"] or "[]"),
            "abschluesse": [{
                "id": a["id"], "titel": a["titel"], "gj_von": a["gj_von"], "gj_bis": a["gj_bis"], "veroeffentlicht": a["veroeffentlicht"],
                "quelle": a["quelle"], "quelle_url": a["quelle_url"], "geladen": a["geladen"], "roh_vorhanden": bool(a["roh_laenge"]),
                "abschluss": json.loads(a["abschluss_json"]), "kennzahlen": json.loads(a["kennzahlen_json"]),
            } for a in abschluesse],
        }

    def roh_html(self, abschluss_id):
        with self._sperre:
            z = self._db.execute("SELECT roh_html FROM abschluesse WHERE id = ?", (abschluss_id,)).fetchone()
            return z["roh_html"] if z else None

    def firma_loeschen(self, firma_id):
        with self._sperre:
            self._db.execute("DELETE FROM firmen WHERE id = ?", (firma_id,))
            self._db.commit()

    def statistik(self):
        with self._sperre:
            f = self._db.execute("SELECT COUNT(*) AS n FROM firmen").fetchone()["n"]
            a = self._db.execute("SELECT COUNT(*) AS n FROM abschluesse").fetchone()["n"]
            u = self._db.execute("SELECT COUNT(*) AS n FROM uebersprungen").fetchone()["n"]
        return {"firmen": f, "abschluesse": a, "uebersprungen": u, "suchbegriffe": self.suchbegriffe()}

    def uebersprungene(self, suchbegriff=None, limit=200):
        with self._sperre:
            if suchbegriff:
                zeilen = self._db.execute("SELECT * FROM uebersprungen WHERE suchbegriff = ? ORDER BY id DESC LIMIT ?", (suchbegriff, limit)).fetchall()
            else:
                zeilen = self._db.execute("SELECT * FROM uebersprungen ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(z) for z in zeilen]
