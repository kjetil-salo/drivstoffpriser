"""
Dumper alle stasjoner fra Drivstoffappen til tools/drivstoffappen_stasjoner.json.

Kjøres manuelt ved behov (f.eks. når en ny stasjon ikke finnes i filen):
    python3 tools/drivstoffappen_dump.py

Henter alle stasjoner i ett kall via /api/v1/stations (ingen ID-scanning).
Typisk kjøretid: under 5 sekunder.
"""

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://api.drivstoffappen.no"
CLIENT_ID = "com.raskebiler.drivstoff.appen.ios"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivstoffappen_stasjoner.json")


def _hent_token() -> str:
    req = urllib.request.Request(f"{BASE_URL}/api/v1/authorization-sessions")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["token"]


def _utled_api_nøkkel(token: str) -> str:
    b = bytearray(token, "utf-8")
    return hashlib.md5(b[1:] + b[:1]).hexdigest()


def dump():
    print("Henter token...")
    token = _hent_token()
    api_key = _utled_api_nøkkel(token)
    headers = {"X-API-KEY": api_key, "X-CLIENT-ID": CLIENT_ID}

    print("Henter alle stasjoner...")
    req = urllib.request.Request(f"{BASE_URL}/api/v1/stations", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    alle = [
        {
            "id": s["id"],
            "name": s.get("name"),
            "brand": (s.get("brand") or {}).get("name"),
            "lat": (s.get("coordinates") or {}).get("latitude"),
            "lng": (s.get("coordinates") or {}).get("longitude"),
        }
        for s in data
    ]
    alle.sort(key=lambda s: s["id"])

    resultat = {
        "generert": datetime.now(timezone.utc).isoformat(),
        "antall": len(alle),
        "stasjoner": alle,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)

    print(f"Ferdig: {len(alle)} stasjoner lagret i {OUTPUT}")


if __name__ == "__main__":
    dump()
