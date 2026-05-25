---
name: ops-partner-ny-region
description: Legg til et nytt partner1-distrikt i drivstoffappen_sync.py. Finner stasjoner via REGIONER_RECT-bbox, matcher mot Drivstoffappen-dump, legger til mapping og oppdaterer ops-partner-region-skillen.
allowed-tools: Bash, Read, Edit
---

Legg til en ny manuell partner1-region.

Argument: $ARGUMENTS (regionsnavn fra REGIONER_RECT, f.eks. "Kristiansand")

## Prosessen

### 1. Hent bbox fra REGIONER_RECT

Bboxene er definert i `routes_admin.py`:

```python
REGIONER_RECT = [
    ("Bergen",              "#2196F3", 60.10, 60.88, 4.70, 5.75),
    ("Haugalandet",         "#9C27B0", 59.08, 59.65, 5.05, 5.60),
    ("Stavanger",           "#E91E63", 58.75, 59.15, 5.40, 6.05),
    ("Grenland",            "#FF5722", 58.95, 59.40, 9.35, 9.90),
    ("Kongsberg",           "#795548", 59.55, 59.80, 9.50, 9.85),
    ("Drammen",             "#607D8B", 59.55, 59.85, 10.00, 10.40),
    ("Oslo",                "#F44336", 59.75, 60.05, 10.35, 11.00),
    ("Romerike/Akershus",   "#FF9800", 59.85, 60.20, 10.80, 11.20),
    ("Fredrikstad/Østfold", "#4CAF50", 59.05, 59.45, 10.80, 11.35),
    ("Vestfold",            "#00BCD4", 58.95, 59.55, 9.95, 10.55),
    ("Kristiansand",        "#8BC34A", 57.95, 58.25, 7.75, 8.20),
    ("Trondheim",           "#3F51B5", 63.25, 63.55, 10.10, 10.70),
    ("Bodø/Nordland",       "#009688", 67.10, 67.45, 14.25, 14.70),
    ("Tromsø/Troms",        "#673AB7", 69.45, 69.80, 18.70, 19.30),
]
```

### 2. Finn våre stasjoner i bbox på Pi

SSH til Pi og kjør mot prod-DB med bbox fra REGIONER_RECT:

```bash
cat > /tmp/finn_stasjoner.py << 'PYEOF'
import sqlite3
conn = sqlite3.connect('/app/data/drivstoff.db')
rows = conn.execute('''
    SELECT id, navn, kjede, lat, lon
    FROM stasjoner
    WHERE lat BETWEEN ? AND ?
      AND lon BETWEEN ? AND ?
      AND godkjent = 1
    ORDER BY navn
''', (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX)).fetchall()
for r in rows:
    print(f'{r[0]:8d}  {r[1]:<40s}  {r[2]:<20s}  {r[3]:.4f}  {r[4]:.4f}')
print(f'Totalt: {len(rows)} stasjoner')
conn.close()
PYEOF
# Erstatt LAT_MIN, LAT_MAX, LON_MIN, LON_MAX med faktiske verdier
scp /tmp/finn_stasjoner.py raspberrypi:/tmp/
ssh raspberrypi "docker cp /tmp/finn_stasjoner.py drivstoffpriser-drivstoffpriser-1:/tmp/ && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/finn_stasjoner.py"
```

### 3. Match mot Drivstoffappen-dump

Dumpen ligger på Pi: `/app/data/drivstoffappen_live.json`

Matcher på lat/lon-nærhet (≤ 0.5 km) og navn. Kjør matcher-script:

```bash
cat > /tmp/match_region.py << 'PYEOF'
import json, sqlite3, math

def avstand(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

with open('/app/data/drivstoffappen_live.json') as f:
    dump = json.load(f)

alle = dump['stasjoner']

conn = sqlite3.connect('/app/data/drivstoff.db')
våre = conn.execute('''
    SELECT id, navn, lat, lon FROM stasjoner
    WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND slettet IS NULL
    ORDER BY navn
''', (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX)).fetchall()

print(f'{"Vår ID":>8}  {"Vår navn":<40}  {"Drivstoff-ID":>12}  {"Drivstoff-navn":<40}  {"Avstand":>8}')
print('-' * 120)
for vid, vnavn, vlat, vlon in våre:
    beste = None
    beste_avst = 999
    for s in alle:
        slat = s.get('latitude') or s.get('lat')
        slon = s.get('longitude') or s.get('lon')
        if slat is None or slon is None:
            continue
        d = avstand(vlat, vlon, slat, slon)
        if d < beste_avst:
            beste_avst = d
            beste = s
    if beste and beste_avst < 0.5:
        print(f'{vid:8d}  {vnavn:<40}  {beste["id"]:12d}  {beste["name"]:<40}  {beste_avst:.3f} km')
    else:
        print(f'{vid:8d}  {vnavn:<40}  {"INGEN MATCH":>12}  {"":<40}  {beste_avst:.3f} km')
conn.close()
PYEOF
# Erstatt LAT_MIN, LAT_MAX, LON_MIN, LON_MAX
scp /tmp/match_region.py raspberrypi:/tmp/
ssh raspberrypi "docker cp /tmp/match_region.py drivstoffpriser-drivstoffpriser-1:/tmp/ && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/match_region.py"
```

### 4. Rediger drivstoffappen_sync.py

Legg til ny mapping-dict etter de andre STASJON_MAPPING_*-diktene:

```python
STASJON_MAPPING_KRISTIANSAND = {
    # <vår_id>: <drivstoffappen_id>,  # Stasjonsnavn
}
```

Oppdater `REGIONER`-dict:

```python
REGIONER = {
    'haugalandet':  STASJON_MAPPING_HAUGALANDET,
    'stavanger':    STASJON_MAPPING_STAVANGER,
    'kristiansand': STASJON_MAPPING_KRISTIANSAND,
}
```

`argparse`-parameteren oppdateres automatisk siden den bruker `list(REGIONER)`.

### 5. Legg til i admin-HTML (routes_admin.py)

Legg til ny `distrikt-rad` i Partner 1-seksjonen i `routes_admin.py`, etter siste eksisterende region:

```html
  <div class="distrikt-rad">
    <span class="distrikt-navn">Regionsnavn</span>
    <input class="prosent-input" id="prosent-regionsnøkkel" type="number" min="1" max="100" placeholder="100">
    <button class="sync-btn" id="btn-regionsnøkkel" onclick="sync(\'regionsnøkkel\', \'regionsnøkkel\')">Sync</button>
    <span class="sync-status" id="status-regionsnøkkel"></span>
  </div>
```

Oppdater også `gyldige_regioner`-settet (ca. 5 linjer under `def kjor_partner_sync`):

```python
gyldige_regioner = {None, ..., 'ny_region'}
```

### 6. Oppdater ops-partner-region/SKILL.md

Legg til ny seksjon med stasjonstabell (samme format som Bergen/Haugalandet/Stavanger). Oppdater også antall i overskriften og legg til regionsnavnet i `description`-feltet øverst i filen.

### 7. Deploy

```bash
# Kjør ops-deploy for å publisere endringen til Pi
```

### 7. Test manuell sync

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 /app/tools/drivstoffappen_sync.py --region kristiansand"
```

## Stasjoner som ikke matches (dokumenter her)

Stasjoner uten god Drivstoffappen-match (avstand > 0.5 km eller feil brand) skal listes i ops-partner-region/SKILL.md under "Stasjonene som IKKE er med".

## Oppgave

$ARGUMENTS
