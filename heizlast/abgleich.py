"""Hydraulischer Abgleich nach Verfahren B (raumweise Heizlast, VdZ).

Heizkörperleistung (DIN EN 442):
  Phi = Phi_N * (dT_log / dT_log_N) ** n,  dT_log_N = 49,83 K (75/65/20 °C)
  dT_log = (theta_V - theta_R) / ln((theta_V - theta_i) / (theta_R - theta_i))

Ablauf:
  1. Raumheizlast anteilig nach Normleistung auf die Heizkörper verteilen.
  2. Je Heizkörper die nötige Vorlauftemperatur bei Auslegungsspreizung ermitteln.
     Der ungünstigste Heizkörper bestimmt die Systemvorlauftemperatur.
     Heizkörper, die über dem Ziel-Vorlauf (Wärmepumpe) liegen, werden als Tausch
     markiert und mit der nötigen Normleistung weitergerechnet (abschaltbar).
  3. Bei Systemvorlauf je Heizkörper die Rücklauftemperatur und den Volumenstrom bestimmen.
  4. Rohrnetz-Druckverlust abschätzen: dp = 2 * L * R * (1 + Z).
  5. Ventil-Differenzdruck und kv-Wert je Heizkörper, Pumpenförderhöhe.
"""

import math
from dataclasses import dataclass

from .zahlen import de

C_WASSER = 1.163  # Wh/(kg·K)


def dt_log(theta_V, theta_R, theta_i):
    a = theta_V - theta_i
    b = theta_R - theta_i
    if a <= 0 or b <= 0:
        raise ValueError("Vor- und Rücklauf müssen über der Raumtemperatur liegen")
    if abs(a - b) < 1e-9:
        return a
    return (a - b) / math.log(a / b)


DT_LOG_N = dt_log(75.0, 65.0, 20.0)  # 49,83 K


def leistung(phi_N, n, theta_V, theta_R, theta_i):
    return phi_N * (dt_log(theta_V, theta_R, theta_i) / DT_LOG_N) ** n


def dt_log_erforderlich(phi_soll, phi_N, n):
    return DT_LOG_N * (phi_soll / phi_N) ** (1.0 / n)


def _bisektion(fn, lo, hi, ziel, it=200):
    """fn monoton steigend auf [lo, hi]."""
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        if fn(mid) < ziel:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def vorlauf_erforderlich(dT_req, spreizung, theta_i):
    """Vorlauftemperatur, bei der ein Heizkörper mit fester Spreizung dT_req erreicht."""
    return _bisektion(
        lambda tv: dt_log(tv, tv - spreizung, theta_i),
        theta_i + spreizung + 1e-9,
        theta_i + spreizung + 300.0,
        dT_req,
    )


def ruecklauf_bei_vorlauf(dT_req, theta_V, theta_i):
    """Rücklauftemperatur, bei der ein Heizkörper bei gegebenem Vorlauf dT_req erreicht."""
    if dT_req >= theta_V - theta_i:
        return None  # Heizkörper zu klein für diesen Vorlauf
    return _bisektion(
        lambda tr: dt_log(theta_V, tr, theta_i),
        theta_i + 1e-9,
        theta_V - 1e-9,
        dT_req,
    )


@dataclass
class HKErgebnis:
    id: str
    raum: str
    beschreibung: str
    theta_i: float
    phi_N: float  # Normleistung Bestand (75/65/20)
    n: float
    phi_soll: float
    theta_V_erf: float  # nötiger Vorlauf des Bestandsheizkörpers bei Auslegungsspreizung
    L: float
    phi_N_ausl: float = 0.0  # Normleistung, mit der gerechnet wird (Bestand oder Tausch)
    getauscht: bool = False
    theta_R: float = 0.0
    spreizung: float = 0.0
    m: float = 0.0  # kg/h, ~ l/h
    dp_rohr: float = 0.0  # Pa
    dp_ventil: float = 0.0  # Pa
    kv: float = 0.0
    hinweise: tuple = ()


@dataclass
class AbgleichErgebnis:
    heizkoerper: list
    theta_V: float  # Auslegungsvorlauf, mit dem abgeglichen wurde
    theta_V_bestand: float  # nötiger Vorlauf, wenn alle Bestandsheizkörper bleiben
    theta_V_ziel: float
    spreizung_ausl: float
    tausch: bool
    kritisch: list
    theta_R_misch: float
    m_gesamt: float
    dp_verfuegbar: float
    dp_erzeuger: float
    foerderhoehe_m: float


def normleistung_fuer(phi_soll, n, theta_V, spreizung, theta_i):
    """Nötige Normleistung (75/65/20), damit ein Heizkörper bei theta_V/theta_V-spreizung phi_soll liefert."""
    return phi_soll / (dt_log(theta_V, theta_V - spreizung, theta_i) / DT_LOG_N) ** n


def berechne_abgleich(projekt, gebaeude):
    hyd = projekt["hydraulik"]
    sigma = float(hyd.get("spreizung_auslegung", 7.0))
    theta_V_ziel = float(hyd.get("theta_V_ziel", 55.0))
    tausch = bool(hyd.get("tausch_kritische", True))
    R = float(hyd.get("R_Pa_pro_m", 100.0))
    z = float(hyd.get("zuschlag_einzelwiderstaende", 0.3))
    dp_tv_min = float(hyd.get("dp_ventil_min_mbar", 50.0)) * 100.0
    dp_erz = float(hyd.get("dp_erzeuger_mbar", 0.0)) * 100.0
    rundung = float(hyd.get("vorlauf_rundung", 0.5))

    raeume = {r.name: r for r in gebaeude.raeume}
    hk_liste = projekt["heizkoerper"]

    summe_N = {}
    for hk in hk_liste:
        if hk["raum"] not in raeume:
            raise ValueError(f"Heizkörper {hk['id']}: Raum {hk['raum']!r} unbekannt")
        summe_N[hk["raum"]] = summe_N.get(hk["raum"], 0.0) + float(hk["phi_N"])

    erg = []
    for hk in hk_liste:
        raum = raeume[hk["raum"]]
        phi_N = float(hk["phi_N"])
        n = float(hk.get("n", 1.3))
        anteil = hk.get("anteil", phi_N / summe_N[hk["raum"]])
        phi_soll = raum.phi_HL * anteil
        dT_req = dt_log_erforderlich(phi_soll, phi_N, n)
        erg.append(HKErgebnis(
            id=hk["id"],
            raum=hk["raum"],
            beschreibung=hk.get("beschreibung", ""),
            theta_i=raum.theta_i,
            phi_N=phi_N,
            n=n,
            phi_soll=phi_soll,
            theta_V_erf=vorlauf_erforderlich(dT_req, sigma, raum.theta_i),
            L=float(hk.get("L_einfach", 10.0)),
            phi_N_ausl=phi_N,
        ))

    def aufrunden(x, schritt=rundung):
        return math.ceil(x / schritt - 1e-9) * schritt

    theta_V_bestand = aufrunden(max(h.theta_V_erf for h in erg))
    kritisch = [h for h in erg if h.theta_V_erf > theta_V_ziel]
    if tausch and kritisch:
        rest = [h.theta_V_erf for h in erg if h not in kritisch]
        theta_V = aufrunden(max(rest)) if rest else theta_V_ziel
        for h in kritisch:
            h.getauscht = True
            h.phi_N_ausl = aufrunden(normleistung_fuer(h.phi_soll, h.n, theta_V, sigma, h.theta_i), 10.0)
    else:
        theta_V = theta_V_bestand

    for h in erg:
        dT_req = dt_log_erforderlich(h.phi_soll, h.phi_N_ausl, h.n)
        h.theta_R = ruecklauf_bei_vorlauf(dT_req, theta_V, h.theta_i)
        h.spreizung = theta_V - h.theta_R
        h.m = h.phi_soll / (C_WASSER * h.spreizung)
        h.dp_rohr = 2.0 * h.L * R * (1.0 + z)

    dp_verf = max(h.dp_rohr for h in erg) + dp_tv_min
    for h in erg:
        h.dp_ventil = dp_verf - h.dp_rohr
        h.kv = (h.m / 1000.0) / math.sqrt(h.dp_ventil / 1e5)
        hinweise = []
        if h.getauscht:
            hinweise.append(f"Tausch: neuer Heizkörper mit mind. {de(h.phi_N_ausl)} W Normleistung (75/65/20)")
        elif h in kritisch:
            hinweise.append(f"für {de(theta_V_ziel)} °C Vorlauf zu klein")
        if h.dp_ventil > 20000:
            hinweise.append("Ventil-Differenzdruck > 200 mbar: Geräuschgefahr")
        if h.kv < 0.03:
            hinweise.append("sehr kleiner kv-Wert – mit Ventiltyp prüfen")
        if h.spreizung > 20:
            hinweise.append("große Spreizung – Heizkörper deutlich überdimensioniert")
        h.hinweise = tuple(hinweise)

    m_ges = sum(h.m for h in erg)
    theta_R_misch = sum(h.m * h.theta_R for h in erg) / m_ges

    return AbgleichErgebnis(
        heizkoerper=erg,
        theta_V=theta_V,
        theta_V_bestand=theta_V_bestand,
        theta_V_ziel=theta_V_ziel,
        spreizung_ausl=sigma,
        tausch=tausch,
        kritisch=kritisch,
        theta_R_misch=theta_R_misch,
        m_gesamt=m_ges,
        dp_verfuegbar=dp_verf,
        dp_erzeuger=dp_erz,
        foerderhoehe_m=(dp_verf + dp_erz) / 9810.0,
    )
