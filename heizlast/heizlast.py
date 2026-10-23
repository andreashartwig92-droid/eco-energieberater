"""Raumweise Norm-Heizlast in Anlehnung an DIN EN 12831-1 / DIN/TS 12831-1.

Vereinfachtes Verfahren:
  Transmission  Phi_T = sum(A * (U + dU_WB) * f) * (theta_i - theta_e)
  Lüftung       Phi_V = 0,34 * max(V_inf, V_min) * (theta_i - theta_e)
                V_inf = 2 * V * n50 * e * eps,  V_min = n_min * V
  Heizlast      Phi_HL = Phi_T + Phi_V + Phi_RH

Räume mit "phi_HL_vorgabe" (W) werden nicht berechnet; der Wert geht direkt in Abgleich und
Gebäude-Heizlast ein (Summe, ohne Abminderung).

Temperatur-Korrekturfaktor f je Bauteil:
  aussen           f = 1
  unbeheizt (Zone) f = b_u
  Erdreich         f = f_g1 * f_g2 * G_w,  f_g2 = (theta_i - theta_m_e) / (theta_i - theta_e)
  beheizter Nachbar (andere Temperatur)
                   f = (theta_i - theta_n) / (theta_i - theta_e), ohne Wärmebrückenzuschlag
"""

from dataclasses import dataclass, field

RHO_CP_LUFT = 0.34  # Wh/(m³·K)
F_G1 = 1.45  # jährliche Schwankung der Außentemperatur (Erdreich)


@dataclass
class BauteilErgebnis:
    typ: str
    text: str
    an: str
    A: float
    U: float
    dU: float
    f: float
    H: float
    phi: float
    intern: bool


@dataclass
class RaumErgebnis:
    name: str
    geschoss: str
    theta_i: float
    A: float
    V: float
    bauteile: list = field(default_factory=list)
    H_T: float = 0.0
    phi_T: float = 0.0
    phi_T_gebaeude: float = 0.0  # ohne Wärmeströme zu beheizten Nachbarräumen
    V_inf: float = 0.0
    V_min: float = 0.0
    V_ausl: float = 0.0
    H_V: float = 0.0
    phi_V: float = 0.0
    phi_V_gebaeude: float = 0.0
    phi_RH: float = 0.0
    phi_HL: float = 0.0
    vorgabe: bool = False  # Raumheizlast vorgegeben statt aus Bauteilen berechnet
    vorgabe_quelle: str = ""

    @property
    def spez(self):
        return self.phi_HL / self.A if self.A else 0.0


def _flaeche(bt):
    if "A" in bt:
        return float(bt["A"])
    return float(bt["l"]) * float(bt["h"])


def _korrektur(an, theta_i, theta_e, projekt):
    """Liefert (f, Wärmebrückenzuschlag anwenden?, intern?, Beschreibung)."""
    if isinstance(an, (int, float)):
        f = (theta_i - an) / (theta_i - theta_e)
        return f, False, True, f"beheizt {an:g} °C"
    if an == "aussen":
        return 1.0, True, False, "außen"
    if an == "erdreich":
        erd = projekt.get("erdreich", {})
        theta_m_e = projekt["klima"]["theta_m_e"]
        f_g2 = (theta_i - theta_m_e) / (theta_i - theta_e)
        g_w = erd.get("G_w", 1.0)
        return F_G1 * f_g2 * g_w, True, False, "Erdreich"
    zonen = projekt.get("angrenzend", {})
    if an in zonen:
        return float(zonen[an]["b_u"]), True, False, an
    raise ValueError(f"Unbekannte Angrenzung: {an!r}")


def _raum_aus_vorgabe(raum):
    """Raumheizlast liegt vor (z. B. aus einer Fremdberechnung): keine Bauteilrechnung."""
    A = float(raum["A"])
    r = RaumErgebnis(raum["name"], raum.get("geschoss", ""), float(raum["theta_i"]), A,
                     A * float(raum.get("h", 2.5)))
    r.phi_HL = float(raum["phi_HL_vorgabe"])
    r.vorgabe = True
    r.vorgabe_quelle = raum.get("quelle", "")
    return r


def berechne_raum(raum, projekt):
    if "phi_HL_vorgabe" in raum:
        return _raum_aus_vorgabe(raum)
    theta_e = projekt["klima"]["theta_e"]
    theta_i = float(raum["theta_i"])
    dU_wb = projekt.get("waermebruecken", {}).get("delta_U", 0.10)
    kat = projekt["bauteile"]
    lue = projekt.get("lueftung", {})

    A = float(raum["A"])
    V = A * float(raum["h"])
    r = RaumErgebnis(raum["name"], raum.get("geschoss", ""), theta_i, A, V)

    dT = theta_i - theta_e
    for bt in raum["bauteile"]:
        an = bt.get("an", "aussen")
        f, mit_wb, intern, an_text = _korrektur(an, theta_i, theta_e, projekt)
        elemente = []
        A_brutto = _flaeche(bt)
        A_oeff = 0.0
        for oe in bt.get("oeffnungen", []):
            A_o = _flaeche(oe) * oe.get("anzahl", 1)
            A_oeff += A_o
            elemente.append((oe["typ"], oe.get("text", ""), A_o))
        if A_oeff > A_brutto:
            raise ValueError(f"{raum['name']}: Öffnungen größer als Wandfläche")
        elemente.insert(0, (bt["typ"], bt.get("text", ""), A_brutto - A_oeff))

        for typ, text, A_el in elemente:
            U = float(kat[typ]["U"])
            dU = dU_wb if mit_wb else 0.0
            H = A_el * (U + dU) * f
            phi = H * dT
            r.bauteile.append(BauteilErgebnis(typ, text, an_text, A_el, U, dU, f, H, phi, intern))
            r.H_T += H
            r.phi_T += phi
            if not intern:
                r.phi_T_gebaeude += phi

    n50 = lue.get("n50", 4.0)
    eps = lue.get("epsilon", 1.0)
    e = raum.get("e", 0.02)
    n_min = raum.get("n_min", lue.get("n_min_standard", 0.5))
    r.V_inf = 2.0 * V * n50 * e * eps
    r.V_min = n_min * V
    r.V_ausl = max(r.V_inf, r.V_min)
    r.H_V = RHO_CP_LUFT * r.V_ausl
    r.phi_V = r.H_V * dT
    # Gebäude: nur die Hälfte der Räume gleichzeitig mit Infiltration
    r.phi_V_gebaeude = RHO_CP_LUFT * max(0.5 * r.V_inf, r.V_min) * dT

    r.phi_RH = A * float(raum.get("f_RH", projekt.get("aufheizzuschlag_W_m2", 0.0)))
    r.phi_HL = r.phi_T + r.phi_V + r.phi_RH
    return r


@dataclass
class GebaeudeErgebnis:
    raeume: list
    phi_T: float
    phi_V: float
    phi_RH: float
    phi_HL: float
    A: float
    summe_raumheizlasten: float

    @property
    def spez(self):
        return self.phi_HL / self.A if self.A else 0.0


def berechne_gebaeude(projekt):
    raeume = [berechne_raum(r, projekt) for r in projekt["raeume"]]
    phi_T = sum(r.phi_T_gebaeude for r in raeume)
    phi_V = sum(r.phi_V_gebaeude for r in raeume)
    phi_RH = sum(r.phi_RH for r in raeume)
    phi_vorgabe = sum(r.phi_HL for r in raeume if r.vorgabe)
    return GebaeudeErgebnis(
        raeume=raeume,
        phi_T=phi_T,
        phi_V=phi_V,
        phi_RH=phi_RH,
        phi_HL=phi_T + phi_V + phi_RH + phi_vorgabe,
        A=sum(r.A for r in raeume),
        summe_raumheizlasten=sum(r.phi_HL for r in raeume),
    )
