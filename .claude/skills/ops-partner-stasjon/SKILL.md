---
name: ops-partner-stasjon
description: Legg til én eller flere stasjoner i partner-sync (Drivstoffappen/partner1). Finn vår DB-id og Drivstoffappens egne ID (ikke OSM), og oppdater STASJON_MAPPING i tools/drivstoffappen_sync.py.
allowed-tools: Bash, Read, Edit, Write
---

Legg til stasjoner i `tools/drivstoffappen_sync.py` sin `STASJON_MAPPING`.

Argument: $ARGUMENTS (stasjonsnavn, f.eks. "ST1 Nygård, Esso Hundvåg")

## Bakgrunn

Partner1 er en automatisk synk-bruker som henter priser fra **Drivstoffappen** (api.drivstoffappen.no).
Drivstoffappen bruker **sine egne ID-er** — ikke OSM-IDer. Mappingen er:

```
Vår stasjon-ID → Drivstoffappens stasjon-ID
```

Filen: `tools/drivstoffappen_sync.py`, dict `STASJON_MAPPING`.

## Steg 1: Finn vår stasjon-ID

Kjør spørring i prod-DB via Docker på Pi:

```python
# Skriv til /tmp/lookup_st.py, scp til Pi, docker cp + exec
import sqlite3
conn = sqlite3.connect("/app/data/drivstoff.db")
rows = conn.execute(
    "SELECT id, navn FROM stasjoner WHERE LOWER(navn) LIKE LOWER('%<søk>%') ORDER BY navn"
).fetchall()
for r in rows: print(r)
conn.close()
```

Bruk `scp` + `docker cp` + `docker exec`-mønsteret (se memory: Docker SQL-spørringer på Pi):
```bash
# Skriv script lokalt, kopier til Pi, kjør i container
cat > /tmp/lookup.py << 'EOF'
... script ...
EOF
scp /tmp/lookup.py raspberrypi:/tmp/
ssh raspberrypi "docker cp /tmp/lookup.py drivstoffpriser-drivstoffpriser-1:/tmp/ && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/lookup.py"
```

Hvis stasjonen ikke finnes i DB: stopp og informer brukeren — den må legges til som stasjon først.

## Steg 2: Finn Drivstoffappens stasjon-ID

Drivstoffappen har **egne IDer** som ikke samsvarer med OSM eller vår DB.
Søk ved å batch-skanne ID-ranges og filtrere på navn:

```python
import hashlib, json, urllib.request, time

BASE_URL = "https://api.drivstoffappen.no"
CLIENT_ID = "com.raskebiler.drivstoff.appen.ios"

def hent_token():
    req = urllib.request.Request(f"{BASE_URL}/api/v1/authorization-sessions")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())['token']

def utled_api_nøkkel(token):
    b = bytearray(token, 'utf-8')
    return hashlib.md5(b[1:] + b[:1]).hexdigest()

token = hent_token()
api_key = utled_api_nøkkel(token)
headers = {'X-API-KEY': api_key, 'X-CLIENT-ID': CLIENT_ID}

BATCH = 50
# Søk fra 1 til ca. 30000 (kjente ID-er er <5000 for norske stasjoner)
# Begrens til relevante ranges basert på kjente ID-er i STASJON_MAPPING
alle_ids = list(range(1, 5000))

søk_navn = ["hundvåg", "nygård"]  # lowercase søkeord

for start in range(0, len(alle_ids), BATCH):
    batch = alle_ids[start:start+BATCH]
    ids_str = ','.join(str(i) for i in batch)
    url = f"{BASE_URL}/api/v1/stations?ids={ids_str}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        for s in data:
            n = (s.get('name') or '').lower()
            if any(søk in n for søk in søk_navn):
                print(f"FUNNET: id={s['id']} navn={s.get('name')} brand={s.get('brand',{}).get('name')}")
    except Exception as e:
        print(f"Batch {batch[0]}-{batch[-1]}: {e}")
    time.sleep(0.15)
```

Kjøres **lokalt** (ikke på Pi). Kan ta 1–2 min for full scan av 1–5000.

## Steg 3: Bekreft funnet stasjon

Hent detaljer for de fundne ID-ene og verifiser:

```python
url = f"{BASE_URL}/api/v1/stations?ids={funnet_id}"
```

Sjekk at:
- `brand.name` stemmer med forventet kjede (f.eks. "Esso", "ST1")
- `prices` inneholder aktive priser (ikke bare `deleted: 1`)
- Priser er innenfor gyldig range (14–37 kr/l)

Hvis brand ikke stemmer — spør brukeren om dette er riktig stasjon.

## Steg 4: Oppdater STASJON_MAPPING

Fil: `tools/drivstoffappen_sync.py`

Legg til på slutten av dict, før `}`:

```python
    <vaar_id>: <drivstoffappen_id>,   # <Stasjonsnavn>
```

Eksempel:
```python
    36: 2093,   # St1 Nygård
    5690: 468,  # Esso Hundvåg
```

Sortering: ID-er er ikke alltid sortert — legg ny linje etter siste eksisterende.

## Steg 5: Oppsummer og neste steg

Vis:
- Stasjonsnavn + vår ID + Drivstoffappens ID
- Eksempel på aktuelle priser fra Drivstoffappen (bensin/diesel)

Minn brukeren på:
1. Deploye (`/deploy`)
2. Pushe til GitHub (`git push`)
3. Neste cron-kjøring skjer `0 5-23 * * *` (hver time kl. 5–23)

## Feilhåndtering

**Stasjon ikke funnet i Drivstoffappen:**
- Prøv med kortere søkeord (bare stedsnavn, uten kjede)
- Prøv å søke bredere range (opp til 30000)
- Stasjon kan mangle i Drivstoffappen — informer bruker

**Søk returnerer feil stasjon:**
- Sjekk brand-navn
- Sjekk koordinater om de er tilgjengelige
- Spør brukeren om å bekrefte

**Stasjon finnes ikke i vår DB:**
- Stoppp! Si til brukeren at stasjonen må legges til via admin-grensesnittet først
