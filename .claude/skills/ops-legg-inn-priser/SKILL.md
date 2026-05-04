---
name: legg-inn-priser
description: Tolk pris-screenshots og legg inn priser direkte i prod-DB (bruker_id=NULL)
allowed-tools: Read, Write, Bash
---

Tolk screenshots med drivstoffpriser og legg dem inn i prod-databasen for brukeren bensin1@vikebo.com.

## Steg 0: Les klokkeslett fra screenshotet

Se øverst til venstre i bildet — der vises klokkeslettet da screenshotet ble tatt (f.eks. "08:50" eller "18:30").
**Dette klokkeslettet er referansepunktet for ALLE prisene i listen.** Det er alltid samme dag.

Bruk screenshot-klokkeslettet direkte til å beregne når hver enkelt pris ble satt:
- "1 t siden" ved 18:30 → prisen ble satt kl. 17:30
- "14 min siden" ved 18:30 → prisen ble satt kl. 18:16
- "5 min siden" ved 08:50 → prisen ble satt kl. 08:45

`alder_i_app_min` = antall minutter mellom pris-tidspunkt og screenshot-tidspunkt.

`bilde_alder_minutter` = minutter fra screenshot-tidspunkt til nå (nå - screenshot_tid). Hvis klokkeslettet ikke er lesbart, spør brukeren.

`total_alder_min` = bilde_alder_minutter + alder_i_app_min

**Filtrer bort priser der total_alder_min > 18 × 60 (18 timer).**
Skip stille uten å nevne det — bare ta med de åpenbare, ferske prisene.

## Steg 1: Tolk bildet

### DrivstoffAppen (gjenkjennes på mørk bakgrunn, søkefelt øverst, kjedelogoer til venstre)
Dette er det vanligste screenshot-formatet. Layout:
- **Drivstofftype**: øverst i midten — filter-knapp med dråpe-ikon og tall (f.eks. "95", "Diesel"). Dette er drivstofftypen for ALLE prisene i listen.
- **Stasjon**: navn i fet skrift (f.eks. "Hosteland"), kjede + avstand under (f.eks. "YX • 6,7 km")
- **Pris**: til høyre, format "XX,XX KR"
- **Alder**: under prisen, f.eks. "3 t siden", "1 min siden"

### Andre app-formater
Ekstraher for hver stasjon: stasjonsnavn, kjede, pris, drivstofftype, alder.

### Avstandsbasert geolokasjon (viktig for å løse tvetydige stasjonsnavn)

Hvis en stasjon har et unikt navn (f.eks. "Hosteland"), søk etter den i DB og finn koordinatene.
Bruk disse koordinatene som brukerens posisjon (justert for avstand fra screenshotet).
Når det er flere DB-treff på samme stasjonsnavn, velg den som er geografisk nærmest den utledede posisjonen.

Eksempel: "Hosteland YX 6,7 km" → finn "Hosteland" i DB → koordinater (60.5, 5.3) → bruker er ca. 6,7 km unna → bruk dette til å disambiguere "Lindås YX 14,6 km" og "Eidsbotn Circle K 15,6 km" hvis det finnes flere treff.

**Kjede-normalisering:**
- "Circle K Automat" → "Circle K"
- "St1" (uansett casing)
- "Bunker Oil" / "BunkerOil" → "Bunker Oil"
- "Uno-X" / "UnoX" → "Uno-X"
- Gyldige kjeder: Best, Bunker Oil, Circle K, Driv, Esso, Haltbakk Express, Haslestad Energi, Knapphus, MH24, Oljeleverandøren, Preem, Shell, St1, Tanken, Trønder Oil, Uno-X, YX

Vis en tabell over tolkede priser (stasjon, kjede, pris, drivstofftype, total alder) og spør om bekreftelse FØR du går videre.

## Steg 2: Skriv script

Skriv et Python-script til `/tmp/legg_inn_priser.py`:

```python
import sqlite3
import math

DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

bruker_id = None  # Priser legges inn uten bruker-tilknytning

bilde_alder_minutter = 0  # FYLL INN

# Kjent referansepunkt fra unikt stasjonsnavn (lat, lon) — sett hvis funnet
# bruker_lat, bruker_lon = None, None
# FYLL INN hvis tilgjengelig, f.eks.:
# bruker_lat, bruker_lon = 60.512, 5.283  # utledet fra Hosteland YX 6.7 km

def km_avstand(lat1, lon1, lat2, lon2):
    dlat = (float(lat2) - float(lat1)) * 111
    dlon = (float(lon2) - float(lon1)) * 111 * math.cos(math.radians(float(lat1)))
    return math.sqrt(dlat**2 + dlon**2)

# Prisdata: (stasjonsnavn, kjede, avstand_km, alder_i_app_min, bensin, diesel, bensin98)
# alder_i_app_min: antall minutter siden prisen ble satt ifølge appen (f.eks. 60 for "1 t siden")
# Sett None for drivstofftyper som ikke oppdateres, avstand_km kan være None
priser = [
    # ("Lundamo", "Esso", 0.6, 60, 21.48, None, None),   # "1 t siden"
    # ("Ler", "Haltbakk", 4.8, 14, 15.99, None, None),   # "14 min siden"
]

feil = []
ok = []
hoppet = []

for navn, kjede, avstand_km, alder_app_min, bensin, diesel, bensin98 in priser:
    total_alder = bilde_alder_minutter + alder_app_min
    if total_alder > 18 * 60:
        hoppet.append(f"  HOPPET OVER (for gammel, {total_alder} min): {navn}")
        continue
    rows = conn.execute(
        """SELECT id, navn, kjede, lat, lon FROM stasjoner
           WHERE godkjent != 0 AND LOWER(navn) LIKE ? AND LOWER(kjede) LIKE ?
           LIMIT 10""",
        (f'%{navn.lower()}%', f'%{kjede.lower()}%')
    ).fetchall()

    if len(rows) == 0:
        rows = conn.execute(
            """SELECT id, navn, kjede, lat, lon FROM stasjoner
               WHERE godkjent != 0 AND LOWER(navn) LIKE ?
               LIMIT 10""",
            (f'%{navn.lower()}%',)
        ).fetchall()

    # Disambiguer med avstand hvis flere treff og bruker-pos er kjent
    if len(rows) > 1:
        try:
            bpos = (bruker_lat, bruker_lon)
        except NameError:
            bpos = (None, None)
        if bpos[0] is not None and avstand_km is not None:
            rows_med_dist = []
            for r in rows:
                if r['lat'] and r['lon']:
                    d = km_avstand(bpos[0], bpos[1], r['lat'], r['lon'])
                    rows_med_dist.append((abs(d - avstand_km), r))
            if rows_med_dist:
                rows_med_dist.sort(key=lambda x: x[0])
                best_diff, best_row = rows_med_dist[0]
                if best_diff < 3.0:  # Maks 3 km avvik
                    rows = [best_row]

    if len(rows) == 1:
        sid = rows[0]['id']
        # Hopp over kun hvis DB har en pris nyere enn app-prisen
        siste = conn.execute(
            """SELECT id, tidspunkt FROM priser
               WHERE stasjon_id = ? AND tidspunkt > datetime('now', ?)
               ORDER BY tidspunkt DESC LIMIT 1""",
            (sid, f'-{total_alder} minutes')
        ).fetchone()
        if siste:
            hoppet.append(f"  HOPPET OVER (DB nyere): {rows[0]['navn']} ({rows[0]['kjede']}) — DB: {siste['tidspunkt']}")
            continue
        forrige = conn.execute(
            'SELECT bensin, diesel, bensin98 FROM priser WHERE stasjon_id=? ORDER BY id DESC LIMIT 1', (sid,)
        ).fetchone()
        if forrige:
            bensin = bensin if bensin is not None else forrige['bensin']
            diesel = diesel if diesel is not None else forrige['diesel']
            bensin98 = bensin98 if bensin98 is not None else forrige['bensin98']
        conn.execute(
            'INSERT INTO priser (stasjon_id, bensin, diesel, bensin98, bruker_id) VALUES (?, ?, ?, ?, ?)',
            (sid, bensin, diesel, bensin98, bruker_id)
        )
        ok.append(f"  OK: {rows[0]['navn']} ({rows[0]['kjede']}) id={sid}")
    elif len(rows) == 0:
        feil.append(f"  FEIL: Fant ingen stasjon for '{navn}' ({kjede})")
    else:
        treff = ', '.join(f"{r['navn']} ({r['kjede']}) id={r['id']}" for r in rows)
        feil.append(f"  HOPPET OVER (flertydig): '{navn}' ({kjede}) → {treff}")

conn.commit()
conn.close()

print(f"\nResultat: {len(ok)} OK, {len(hoppet)} hoppet over, {len(feil)} feil")
for l in ok: print(l)
for l in hoppet: print(l)
for l in feil: print(l)
```

**Viktig:**
- Fyll inn `priser`-listen med data fra steg 1 — inkluder `avstand_km` fra screenshotet
- Sett `bruker_lat, bruker_lon` hvis du fant koordinater fra et unikt stasjonsnavn
- For å finne koordinatene til referansestasjonen: kjør et raskt oppslag i DB først (SELECT lat, lon FROM stasjoner WHERE navn LIKE '%Hosteland%')
- `None` for drivstofftyper som ikke skal settes

## Steg 2b: Slå opp referansestasjon (hvis tvetydige treff forventes)

Hvis det er stasjonsnavn som sannsynligvis finnes flere steder (f.eks. "Lindås", "Eidsbotn"), slå opp referansestasjonen med unikt navn først:

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 -c \"
import sqlite3; c=sqlite3.connect('/app/data/drivstoff.db')
rows=c.execute(\\\"SELECT id,navn,kjede,lat,lon FROM stasjoner WHERE godkjent!=0 AND LOWER(navn) LIKE '%hosteland%'\\\").fetchall()
print(rows)
\""
```

Bruk koordinatene til å sette `bruker_lat, bruker_lon` i scriptet (juster for avstand).

## Steg 3: Kjør

```bash
scp /tmp/legg_inn_priser.py raspberrypi:/tmp/ && \
ssh raspberrypi "docker cp /tmp/legg_inn_priser.py drivstoffpriser-drivstoffpriser-1:/tmp/ && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/legg_inn_priser.py"
```

## Steg 4: Rapporter

Vis resultatet:
- Antall priser lagt inn
- Eventuelle feil
- For flertydige treff: vis alternativene og spør hvilken som er riktig

Hopp aldri over flertydig — rapporter alltid til brukeren. Tilby å kjøre nytt script med korrigeringer.
