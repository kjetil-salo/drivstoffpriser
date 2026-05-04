---
name: nye-stasjoner
description: Sjekk siste ukes nye stasjoner for kvalitet — korrekte, brukerfeil eller sabotasje — drivstoffprisene.no
allowed-tools: Bash, Read, WebFetch
---

Hent alle nye stasjoner fra siste 7 dager og vurder kvaliteten på hver enkelt. Målet er å identifisere:
- **Korrekte** stasjoner (riktig navn, kjede, plassering)
- **Brukerfeil** (feil navn, feil kjede, duplikat, feil plassering)
- **Sabotasje** (tull-stasjoner, ugyldige steder)

## Steg 1: Hent nye stasjoner

Skriv følgende til `/tmp/nye_stasjoner.py`:

```python
import sqlite3, json

DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)

rows = conn.execute("""
    SELECT s.id, s.navn, s.kjede, s.lat, s.lon, s.sist_oppdatert, s.godkjent,
           s.lagt_til_av, b.brukernavn,
           (SELECT COUNT(*) FROM priser WHERE stasjon_id = s.id) AS antall_priser,
           (SELECT GROUP_CONCAT(
               COALESCE(bensin,'') || '/' || COALESCE(diesel,'') || '/' || COALESCE(bensin98,''),
               ' | '
           ) FROM (SELECT bensin, diesel, bensin98 FROM priser WHERE stasjon_id = s.id ORDER BY tidspunkt DESC LIMIT 3)) AS siste_priser
    FROM stasjoner s
    LEFT JOIN brukere b ON b.id = s.lagt_til_av
    WHERE s.sist_oppdatert >= datetime('now', '-7 days')
      AND s.lagt_til_av IS NOT NULL
    ORDER BY s.sist_oppdatert DESC
""").fetchall()

# Sjekk for mulige duplikater (stasjoner innen 100m med lignende navn)
for r in rows:
    sid, navn, kjede, lat, lon = r[0], r[1], r[2], r[3], r[4]
    dupes = conn.execute("""
        SELECT id, navn, kjede, lat, lon,
               ROUND((lat - ?) * 111000, 0) AS dy,
               ROUND((lon - ?) * 111000 * 0.6, 0) AS dx
        FROM stasjoner
        WHERE id != ?
          AND ABS(lat - ?) < 0.002
          AND ABS(lon - ?) < 0.002
    """, (lat, lon, sid, lat, lon)).fetchall()

    print(f"\n=== Stasjon {sid}: {navn} ({kjede or 'ukjent kjede'}) ===")
    print(f"  Posisjon: {lat:.6f}, {lon:.6f}")
    print(f"  Godkjent: {'Ja' if r[6] else 'Nei'}")
    print(f"  Lagt til av: {r[8] or 'ukjent'} (id {r[7]})")
    print(f"  Oppdatert: {r[5]}")
    print(f"  Antall priser: {r[9]}")
    print(f"  Siste priser (bensin/diesel/98): {r[10] or 'ingen'}")

    # Sjekk om posisjon er i Norge (grov sjekk)
    if lat < 57.5 or lat > 71.5 or lon < 4.0 or lon > 31.5:
        print(f"  !! ADVARSEL: Posisjon utenfor Norge!")

    # Sjekk om priser er realistiske (bensin 15-30, diesel 15-30)
    pris_rows = conn.execute("""
        SELECT bensin, diesel, bensin98 FROM priser
        WHERE stasjon_id = ? ORDER BY tidspunkt DESC LIMIT 3
    """, (sid,)).fetchall()
    for p in pris_rows:
        for val, typ in [(p[0], 'bensin'), (p[1], 'diesel'), (p[2], 'bensin98')]:
            if val is not None and (val < 10 or val > 35):
                print(f"  !! ADVARSEL: Urealistisk {typ}-pris: {val}")

    if dupes:
        print(f"  Nærliggende stasjoner ({len(dupes)} stk):")
        for d in dupes:
            dist = ((d[5] or 0)**2 + (d[6] or 0)**2) ** 0.5
            print(f"    - #{d[0]}: {d[1]} ({d[2] or '?'}) ~{dist:.0f}m unna")

conn.close()
```

Kopier og kjør:
```bash
scp /tmp/nye_stasjoner.py raspberrypi:/tmp/ && \
ssh raspberrypi "docker cp /tmp/nye_stasjoner.py drivstoffpriser-drivstoffpriser-1:/tmp/ && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/nye_stasjoner.py"
```

## Steg 2: Verifiser mot kart

For hver stasjon, bruk WebFetch til å slå opp posisjonen mot Nominatim for å sjekke om adressen er realistisk:

```
https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=18&accept-language=no
```

Husk User-Agent-header. Vent 1 sekund mellom hvert oppslag (Nominatim rate limit). Gjør maks 10 oppslag — prioriter stasjoner som har advarsler eller mangler godkjenning.

## Steg 3: Presenter resultat

Presenter en oversiktlig tabell i markdown med vurdering per stasjon:

| # | Stasjon | Kjede | Lagt til av | Priser | Vurdering |
|---|---------|-------|-------------|--------|-----------|

Vurderingskategorier:
- **OK** — alt ser riktig ut (navn matcher adresse, realistiske priser, kjede stemmer)
- **Sannsynlig OK** — ser greit ut men noe usikkert (f.eks. litt rart navn, men posisjon stemmer)
- **Mulig brukerfeil** — feil kjede, duplikat av eksisterende, feil plassering, osv.
- **Mistenkelig** — tullenavn, posisjon utenfor Norge, helt urealistiske priser

Avslutt med en kort oppsummering: totalt antall, fordeling per kategori, og eventuelle anbefalinger (f.eks. «stasjon X bør sjekkes manuelt»).

Viktig: Vær optimistisk i vurderingen — de fleste stasjoner er korrekte. Flagg kun det som faktisk ser feil ut.
