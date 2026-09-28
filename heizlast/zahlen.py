"""Zahlenformat nach deutscher Schreibweise (1.234,5)."""


def de(x, stellen=0):
    if x is None:
        return "–"
    s = f"{x:,.{stellen}f}"
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")
