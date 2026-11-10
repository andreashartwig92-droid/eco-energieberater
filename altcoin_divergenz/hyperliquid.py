"""Marktdaten von der öffentlichen Hyperliquid-Info-API (Perpetuals, Kerzen, Orderbuch).

Hyperliquid stellt nur die jüngsten rund 5.000 Kerzen je Intervall bereit: bei 1 Minute ~3,5 Tage,
bei 5 Minuten ~17 Tage.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

URL = "https://api.hyperliquid.xyz/info"
AUSSCHLUSS = {"BTC", "ETH", "PAXG", "XAUT", "USDC", "USDT", "USDE"}
_letzte_anfrage = 0.0


def _post(nutzlast: dict, abstand: float = 0.3) -> object:
    """POST an die Info-API. `abstand` hält das Gewichtslimit (1.200 / Minute) ein."""
    global _letzte_anfrage
    for versuch in range(6):
        warte = _letzte_anfrage + abstand - time.monotonic()
        if warte > 0:
            time.sleep(warte)
        _letzte_anfrage = time.monotonic()
        lauf = subprocess.run(["curl", "-sS", "-m", "30", "-X", "POST", URL, "-H", "Content-Type: application/json",
                               "-d", json.dumps(nutzlast), "-w", "\n%{http_code}"], capture_output=True, text=True)
        text, _, status = lauf.stdout.rpartition("\n")
        if status == "200":
            return json.loads(text)
        time.sleep(15 * (versuch + 1) if status == "429" else 2 ** versuch)
    raise RuntimeError(f"Hyperliquid nicht erreichbar ({nutzlast.get('type')})")


def top_altcoins(anzahl: int = 100) -> pd.DataFrame:
    """Die `anzahl` Altcoin-Perps mit dem höchsten 24-h-Umsatz, mit maximal erlaubtem Hebel."""
    meta, kontexte = _post({"type": "metaAndAssetCtxs"})
    zeilen = []
    for a, k in zip(meta["universe"], kontexte):
        if a.get("isDelisted") or a["name"] in AUSSCHLUSS:
            continue
        zeilen.append({"coin": a["name"], "umsatz_24h_usd": float(k["dayNtlVlm"]),
                       "max_hebel": int(a["maxLeverage"]), "mid": float(k["midPx"] or k["markPx"])})
    df = pd.DataFrame(zeilen).sort_values("umsatz_24h_usd", ascending=False)
    return df.head(anzahl).reset_index(drop=True)


SCHRITT_MS = {"1m": 60_000, "5m": 300_000, "10m": 600_000, "15m": 900_000, "1h": 3_600_000}
# Hyperliquid liefert 10 Minuten nicht selbst; diese Kerzen werden aus zwei 5-Minuten-Kerzen gebaut.
ZUSAMMENGESETZT = {"10m": "5m"}


def zusammenfassen(df: pd.DataFrame, schritt: int, teil: int) -> pd.DataFrame:
    """Feinere Kerzen zu Kerzen der Länge `schritt` zusammenfassen; unvollständige Kerzen am Rand entfallen."""
    gruppe = df["ts"] // schritt * schritt
    g = df.groupby(gruppe)
    neu = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "vol_usd": g["vol_usd"].sum(), "anzahl": g.size()})
    neu = neu[neu["anzahl"] == schritt // teil].drop(columns="anzahl")
    return neu.rename_axis("ts").reset_index()


def maerkte(namen: list[str]) -> pd.DataFrame:
    """Ausgewählte Märkte, auch von HIP-3-Börsen (Schreibweise "dex:NAME", z. B. "xyz:EUR")."""
    zeilen = []
    for dex in sorted({n.split(":")[0] if ":" in n else "" for n in namen}):
        meta, kontexte = _post({"type": "metaAndAssetCtxs", "dex": dex} if dex else {"type": "metaAndAssetCtxs"})
        for a, k in zip(meta["universe"], kontexte):
            if a["name"] in namen:
                zeilen.append({"coin": a["name"], "umsatz_24h_usd": float(k["dayNtlVlm"]),
                               "max_hebel": int(a["maxLeverage"]), "mid": float(k["midPx"] or k["markPx"]),
                               "growth_mode": a.get("growthMode") == "enabled"})
    df = pd.DataFrame(zeilen)
    fehlt = set(namen) - set(df["coin"])
    if fehlt:
        raise ValueError(f"Auf Hyperliquid nicht gefunden: {', '.join(sorted(fehlt))}")
    return df.set_index("coin").loc[namen].reset_index()


def lade_kerzen(coin: str, start_ms: int, ende_ms: int, intervall: str = "1m") -> pd.DataFrame:
    """Kerzen mit start_ms <= t < ende_ms. Zeiträume ohne Umsatz fehlen bei Hyperliquid;
    sie werden als flache Kerze zum letzten Schlusskurs ergänzt."""
    schritt = SCHRITT_MS[intervall]
    if intervall in ZUSAMMENGESETZT:
        basis = ZUSAMMENGESETZT[intervall]
        return zusammenfassen(lade_kerzen(coin, start_ms, ende_ms, basis), schritt, SCHRITT_MS[basis])
    gewicht = 20 + (ende_ms - start_ms) / schritt / 60  # Gewicht ~20 + 1 je 60 Kerzen, Limit 1.200 / Minute
    roh = _post({"type": "candleSnapshot",
                 "req": {"coin": coin, "interval": intervall, "startTime": start_ms, "endTime": ende_ms}},
                abstand=gewicht / 1200 * 60 * 1.1)
    if not roh:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "vol_usd"])
    df = pd.DataFrame(roh)
    df = pd.DataFrame({"ts": df["t"].astype("int64"), "open": df["o"].astype(float), "high": df["h"].astype(float),
                       "low": df["l"].astype(float), "close": df["c"].astype(float),
                       "vol_usd": df["v"].astype(float) * df["c"].astype(float)})
    df = df[(df["ts"] >= start_ms) & (df["ts"] < ende_ms)].drop_duplicates("ts").set_index("ts").sort_index()
    raster = np.arange(df.index[0], df.index[-1] + 1, schritt)
    df = df.reindex(raster)
    df["close"] = df["close"].ffill()
    for s in ("open", "high", "low"):
        df[s] = df[s].fillna(df["close"])
    df["vol_usd"] = df["vol_usd"].fillna(0.0)
    return df.rename_axis("ts").reset_index()


def slippage(coin: str, betrag_usd: float) -> float:
    """Kosten einer Market-Order über `betrag_usd` gegenüber dem Mittelkurs, gemittelt über Kauf und
    Verkauf, aus dem aktuellen Orderbuch (20 Stufen je Seite). Momentaufnahme."""
    buch = _post({"type": "l2Book", "coin": coin})
    bids, asks = buch["levels"]
    mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
    kosten = []
    for seite in (asks, bids):
        rest, wert, menge = betrag_usd, 0.0, 0.0
        for stufe in seite:
            px, sz = float(stufe["px"]), float(stufe["sz"])
            nimm = min(sz, rest / px)
            wert += nimm * px
            menge += nimm
            rest -= nimm * px
            if rest <= 1e-9:
                break
        if rest > 1e-9:  # Buch zu dünn: Rest zum schlechtesten sichtbaren Kurs plus 0,5 %
            px = float(seite[-1]["px"]) * (1.005 if seite is asks else 0.995)
            wert += rest
            menge += rest / px
        kosten.append(abs(wert / menge - mid) / mid)
    return float(np.mean(kosten))


def lade_alle(coins: list[str], start_ms: int, ende_ms: int, cache: Path,
              intervall: str = "1m") -> dict[str, pd.DataFrame]:
    cache.mkdir(parents=True, exist_ok=True)
    daten = {}
    for i, coin in enumerate(coins, 1):
        datei_coin = coin.replace(":", "-")
        name = (f"hl_{datei_coin}_{start_ms}_{ende_ms}" if intervall == "1m"
                else f"hl_{datei_coin}_{intervall}_{start_ms}_{ende_ms}")
        datei = cache / f"{name}.csv.gz"
        if datei.exists():
            daten[coin] = pd.read_csv(datei)
            continue
        daten[coin] = lade_kerzen(coin, start_ms, ende_ms, intervall)
        daten[coin].to_csv(datei, index=False)
        print(f"  {i}/{len(coins)} {coin}: {len(daten[coin])} Kerzen", flush=True)
    return daten
