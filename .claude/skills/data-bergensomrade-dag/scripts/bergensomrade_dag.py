#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

EXCLUDE_USERS = (1, 5, 2422, 3998)
TARGET_MUNICIPALITIES = {
    "Bergen",
    "Askøy",
    "Øygarden",
    "Alver",
    "Vaksdal",
    "Samnanger",
    "Bjørnafjorden",
}
BBOX = {
    "lat_min": 60.15,
    "lat_max": 60.75,
    "lon_min": 4.45,
    "lon_max": 5.80,
}
CACHE_PATH = Path("/tmp/bergensomrade_geocache.json")


def load_cache():
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return {}


def save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def reverse_geocode(lat, lon):
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
        {
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "zoom": 10,
            "addressdetails": 1,
        }
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "drivstoffpriser-bergensomrade/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    addr = data.get("address", {})
    return (
        addr.get("municipality")
        or addr.get("city")
        or addr.get("town")
        or addr.get("county")
        or ""
    )


def station_municipality(station, cache):
    cache_key = str(station["stasjon_id"])
    cached = cache.get(cache_key)
    if cached:
        return cached
    municipality = reverse_geocode(station["lat"], station["lon"])
    cache[cache_key] = municipality
    save_cache(cache)
    time.sleep(1)
    return municipality


def build_result(target_date):
    con = sqlite3.connect("/app/data/drivstoff.db")
    con.row_factory = sqlite3.Row
    cache = load_cache()

    station_rows = [
        dict(r)
        for r in con.execute(
            """
            SELECT DISTINCT p.stasjon_id, s.navn, s.lat, s.lon
            FROM priser p
            JOIN stasjoner s ON s.id = p.stasjon_id
            WHERE date(p.tidspunkt, 'localtime') = ?
              AND p.bruker_id IS NOT NULL
              AND p.bruker_id NOT IN (?, ?, ?, ?)
              AND s.lat BETWEEN ? AND ?
              AND s.lon BETWEEN ? AND ?
            ORDER BY s.id
            """,
            (
                target_date,
                *EXCLUDE_USERS,
                BBOX["lat_min"],
                BBOX["lat_max"],
                BBOX["lon_min"],
                BBOX["lon_max"],
            ),
        )
    ]

    matching_stations = []
    for row in station_rows:
        municipality = station_municipality(row, cache)
        row["kommune"] = municipality
        if municipality in TARGET_MUNICIPALITIES:
            matching_stations.append(row)

    station_ids = [row["stasjon_id"] for row in matching_stations]
    if not station_ids:
        return {
            "date": target_date,
            "assumption": sorted(TARGET_MUNICIPALITIES),
            "stations": [],
            "totals": {"contributors": 0, "updates": 0, "stations": 0},
            "contributors": [],
            "station_updates": [],
        }

    marks = ",".join("?" for _ in station_ids)

    contributor_rows = [
        dict(r)
        for r in con.execute(
            f"""
            SELECT
                p.bruker_id,
                COALESCE(NULLIF(TRIM(b.kallenavn), ''), NULLIF(TRIM(b.brukernavn), ''), 'ukjent') AS contributor,
                COUNT(*) AS updates,
                COUNT(DISTINCT p.stasjon_id) AS stations
            FROM priser p
            LEFT JOIN brukere b ON b.id = p.bruker_id
            WHERE date(p.tidspunkt, 'localtime') = ?
              AND p.bruker_id IS NOT NULL
              AND p.bruker_id NOT IN (?, ?, ?, ?)
              AND p.stasjon_id IN ({marks})
            GROUP BY p.bruker_id, contributor
            ORDER BY updates DESC, stations DESC, p.bruker_id
            """
            ,
            (target_date, *EXCLUDE_USERS, *station_ids),
        )
    ]

    station_update_rows = [
        dict(r)
        for r in con.execute(
            f"""
            SELECT
                p.stasjon_id,
                s.navn,
                COUNT(*) AS updates,
                COUNT(DISTINCT p.bruker_id) AS contributors
            FROM priser p
            JOIN stasjoner s ON s.id = p.stasjon_id
            WHERE date(p.tidspunkt, 'localtime') = ?
              AND p.bruker_id IS NOT NULL
              AND p.bruker_id NOT IN (?, ?, ?, ?)
              AND p.stasjon_id IN ({marks})
            GROUP BY p.stasjon_id, s.navn
            ORDER BY updates DESC, contributors DESC, s.navn
            """,
            (target_date, *EXCLUDE_USERS, *station_ids),
        )
    ]

    per_municipality = {}
    for station in matching_stations:
        per_municipality.setdefault(station["kommune"], 0)
        per_municipality[station["kommune"]] += 1

    return {
        "date": target_date,
        "assumption": sorted(TARGET_MUNICIPALITIES),
        "stations": matching_stations,
        "totals": {
            "contributors": len(contributor_rows),
            "updates": sum(r["updates"] for r in contributor_rows),
            "stations": len(station_ids),
        },
        "contributors": contributor_rows,
        "station_updates": station_update_rows,
        "stations_per_municipality": per_municipality,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Dato i YYYY-MM-DD")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    result = build_result(args.date)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return
    if args.compact:
        top_contributor = result["contributors"][0]["contributor"] if result["contributors"] else "-"
        top_station = result["station_updates"][0]["navn"] if result["station_updates"] else "-"
        print(
            json.dumps(
                {
                    "date": result["date"],
                    "contributors": result["totals"]["contributors"],
                    "updates": result["totals"]["updates"],
                    "stations": result["totals"]["stations"],
                    "top_contributor": top_contributor,
                    "top_station": top_station,
                },
                ensure_ascii=False,
            )
        )
        return

    print("=" * 80)
    print("BERGENSOMRADE DAG")
    print(f"Dato: {result['date']}")
    print("Kommuner: " + ", ".join(result["assumption"]))
    print("=" * 80)
    print()
    print(f"Andre enn Kjetil: {result['totals']['contributors']} bidragsytere")
    print(f"Oppdateringer: {result['totals']['updates']}")
    print(f"Stasjoner: {result['totals']['stations']}")

    print("\n## Mest aktive bidragsytere")
    for row in result["contributors"][:10]:
        print(f"{row['updates']:>3} | {row['stations']} stasjoner | {row['contributor']} ({row['bruker_id']})")

    print("\n## Mest aktive stasjoner")
    for row in result["station_updates"][:10]:
        print(f"{row['updates']:>3} | {row['contributors']} bidragsytere | {row['navn']} ({row['stasjon_id']})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
