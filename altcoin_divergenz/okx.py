"""Marktdaten von der öffentlichen OKX-API (USDT-Perpetuals, 1-Minuten-Kerzen).

Kein API-Schlüssel nötig. Nur abgeschlossene Kerzen werden verwendet (confirm == "1").
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

BASIS = "https://www.okx.com/api/v5"
SPALTEN = ["ts", "open", "high", "low", "close", "vol", "vol_ccy", "vol_usdt", "confirm"]

# Keine Altcoins im eigentlichen Sinn: Bitcoin, Ether, Stablecoins, tokenisiertes Gold.
AUSSCHLUSS = {
    "BTC", "ETH", "USDC", "USDT", "USDE", "FDUSD", "DAI", "TUSD", "PYUSD", "USD1", "RLUSD", "USDG",
    "XAUT", "PAXG",
}


class _Drossel:
    """Einfacher Token-Bucket: höchstens `pro_sekunde` Anfragen pro Sekunde, threadsicher."""

    def __init__(self, pro_sekunde: float):
        self.abstand = 1.0 / pro_sekunde
        self.naechste = 0.0
        self.lock = threading.Lock()

    def warte(self) -> None:
        with self.lock:
            jetzt = time.monotonic()
            start = max(jetzt, self.naechste)
            self.naechste = start + self.abstand
        if start > jetzt:
            time.sleep(start - jetzt)


_DROSSEL = _Drossel(8.0)  # OKX erlaubt 20 Anfragen / 2 s für history-candles


def _get(pfad: str, **params) -> list:
    url = f"{BASIS}{pfad}?{urllib.parse.urlencode(params)}"
    for versuch in range(6):
        _DROSSEL.warte()
        # curl statt urllib: OKX (Cloudflare) weist den Standard-Client von urllib ab.
        lauf = subprocess.run(["curl", "-sS", "-m", "20", url], capture_output=True, text=True)
        try:
            daten = json.loads(lauf.stdout)
        except json.JSONDecodeError:
            time.sleep(2 ** versuch)
            continue
        if daten.get("code") == "0":
            return daten["data"]
        if daten.get("code") == "50011":  # Rate-Limit
            time.sleep(2 ** versuch)
            continue
        raise RuntimeError(f"OKX-Fehler {daten.get('code')}: {daten.get('msg')} ({url})")
    raise RuntimeError(f"OKX nicht erreichbar: {url}")


def top_altcoins(anzahl: int = 100) -> pd.DataFrame:
    """Die `anzahl` Krypto-Altcoin-Perpetuals (USDT, linear) mit dem höchsten 24-h-Umsatz in USDT."""
    instrumente = _get("/public/instruments", instType="SWAP")
    ticker = {t["instId"]: t for t in _get("/market/tickers", instType="SWAP")}
    zeilen = []
    for i in instrumente:
        if not (i["settleCcy"] == "USDT" and i["ctType"] == "linear" and i["state"] == "live"):
            continue
        if i.get("instCategory") != "1":  # 1 = Krypto (3 = Aktien, 4 = Rohstoffe)
            continue
        basis = i["instId"].split("-")[0]
        t = ticker.get(i["instId"])
        if basis in AUSSCHLUSS or t is None:
            continue
        zeilen.append({
            "inst_id": i["instId"],
            "coin": basis,
            "umsatz_24h_usdt": float(t["volCcy24h"]) * float(t["last"]),
            "max_hebel": int(float(i["lever"])),
        })
    df = pd.DataFrame(zeilen).sort_values("umsatz_24h_usdt", ascending=False)
    return df.head(anzahl).reset_index(drop=True)


def lade_kerzen(inst_id: str, start_ms: int, ende_ms: int) -> pd.DataFrame:
    """Abgeschlossene 1-Minuten-Kerzen mit start_ms <= ts < ende_ms (UTC, Millisekunden)."""
    zeilen: list[list[str]] = []
    nach = ende_ms
    while nach > start_ms:
        seite = _get("/market/history-candles", instId=inst_id, bar="1m", limit=300, after=nach)
        if not seite:
            break
        zeilen.extend(seite)
        aeltester = int(seite[-1][0])
        if aeltester >= nach:
            break
        nach = aeltester
    df = pd.DataFrame(zeilen, columns=SPALTEN)
    if df.empty:
        return df
    df = df[df["confirm"] == "1"].drop(columns=["confirm", "vol", "vol_ccy"])
    df = df.astype({"ts": "int64", "open": float, "high": float, "low": float, "close": float, "vol_usdt": float})
    df = df[(df["ts"] >= start_ms) & (df["ts"] < ende_ms)]
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def lade_alle(inst_ids: list[str], start_ms: int, ende_ms: int, cache: Path | None = None,
              threads: int = 4) -> dict[str, pd.DataFrame]:
    """Kerzen für viele Instrumente parallel laden; optional als CSV im Cache-Verzeichnis ablegen."""
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    def eins(inst_id: str) -> tuple[str, pd.DataFrame]:
        datei = cache / f"{inst_id}_{start_ms}_{ende_ms}.csv.gz" if cache else None
        if datei and datei.exists():
            return inst_id, pd.read_csv(datei)
        df = lade_kerzen(inst_id, start_ms, ende_ms)
        if datei is not None:
            df.to_csv(datei, index=False)
        return inst_id, df

    with ThreadPoolExecutor(threads) as pool:
        return dict(pool.map(eins, inst_ids))
