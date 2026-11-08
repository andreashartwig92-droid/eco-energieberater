"""Ein sehr kleiner HTML-Baum (nur Standardbibliothek), ausreichend für veröffentlichte Jahresabschlüsse.

    baum = parse(html)
    for zeile in baum.suche("div", klasse="row"):
        print(zeile.text())
"""

import html as _html
import re
from html.parser import HTMLParser

_LEER = ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr")
_BLOCK = ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article", "ul", "ol")
_ZELLE = ("td", "th")


class Knoten:
    __slots__ = ("tag", "attrs", "kinder", "eltern")

    def __init__(self, tag, attrs=None, eltern=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.kinder = []
        self.eltern = eltern

    # --- Zugriff -----------------------------------------------------------

    def attr(self, name, standard=None):
        return self.attrs.get(name, standard)

    @property
    def klassen(self):
        return (self.attrs.get("class") or "").split()

    def hat_klasse(self, name):
        return name in self.klassen

    def alle(self):
        """Alle Element-Knoten unterhalb (Tiefensuche, Dokumentreihenfolge)."""
        stapel = list(reversed(self.kinder))
        while stapel:
            k = stapel.pop()
            if isinstance(k, Knoten):
                yield k
                stapel.extend(reversed(k.kinder))

    def suche(self, tag=None, klasse=None, **attrs):
        """Alle Nachfahren mit Tag, CSS-Klasse und/oder Attributwerten."""
        for k in self.alle():
            if tag and k.tag != tag:
                continue
            if klasse and not k.hat_klasse(klasse):
                continue
            if any(k.attrs.get(a) != w for a, w in attrs.items()):
                continue
            yield k

    def erster(self, tag=None, klasse=None, **attrs):
        for k in self.suche(tag, klasse, **attrs):
            return k
        return None

    def text(self, trenner=" "):
        """Sichtbarer Text, Blockelemente durch `trenner` getrennt, Leerraum zusammengefasst."""
        teile = []
        self._text(teile, trenner)
        return re.sub(r"[ \t\r\f\v]+", " ", "".join(teile)).strip()

    def _text(self, teile, trenner):
        for k in self.kinder:
            if isinstance(k, str):
                teile.append(k)
            elif k.tag in ("script", "style"):
                continue
            else:
                if k.tag in _BLOCK:
                    teile.append(trenner)
                elif k.tag in _ZELLE:
                    teile.append(" ")
                k._text(teile, trenner)
                if k.tag in _BLOCK:
                    teile.append(trenner)
                elif k.tag in _ZELLE:
                    teile.append(" ")

    def zeilen(self):
        """Text als Liste von Zeilen (Blockelemente trennen Zeilen)."""
        return [z.strip() for z in self.text("\n").split("\n") if z.strip()]

    def __repr__(self):
        return f"<{self.tag} {self.attrs}>"


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.wurzel = Knoten("#dokument")
        self.aktuell = self.wurzel

    def handle_starttag(self, tag, attrs):
        knoten = Knoten(tag, attrs, self.aktuell)
        self.aktuell.kinder.append(knoten)
        if tag not in _LEER:
            self.aktuell = knoten

    def handle_startendtag(self, tag, attrs):
        self.aktuell.kinder.append(Knoten(tag, attrs, self.aktuell))

    def handle_endtag(self, tag):
        k = self.aktuell
        while k is not None and k.tag != tag:
            k = k.eltern
        if k is not None and k.eltern is not None:
            self.aktuell = k.eltern

    def handle_data(self, daten):
        if daten:
            self.aktuell.kinder.append(daten)


def parse(html):
    p = _Parser()
    p.feed(html)
    p.close()
    return p.wurzel


def entkomme(text):
    return _html.escape(text, quote=True)
