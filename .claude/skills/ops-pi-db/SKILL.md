---
name: pi-db
description: Kjør SQLite-spørringer mot drivstoffpriser-databasen på Raspberry Pi
disable-model-invocation: true
allowed-tools: Bash, Write
---

Kjør SQLite-spørringer mot drivstoffpriser-databasen på Raspberry Pi.

**VIKTIG:** Bruk alltid scp+docker cp-mønsteret. Aldri inline SQL/Python via SSH — quoting feiler konsekvent med norske tegn og nesting.

## Infrastruktur

- SSH: `kjetil@raspberrypi`
- Container: `drivstoffpriser-drivstoffpriser-1`
- DB i container: `/app/data/drivstoff.db`

## Kommandomønster

**Steg 1:** Skriv Python-script til `/tmp/pi_db_op.py` med Write-verktøyet.

**Steg 2:** Kjør i én kommando:
```bash
scp /tmp/pi_db_op.py kjetil@raspberrypi:/tmp/pi_db_op.py && \
ssh kjetil@raspberrypi "docker cp /tmp/pi_db_op.py drivstoffpriser-drivstoffpriser-1:/tmp/pi_db_op.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/pi_db_op.py"
```

## Mal for Python-script

```python
import sqlite3

conn = sqlite3.connect("/app/data/drivstoff.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# --- operasjon her ---
cur.execute("SELECT ...")
for row in cur.fetchall():
    print(dict(row))

conn.commit()
conn.close()
```

## Relevante tabeller

- `stasjoner` — bensinstasjonene (id, navn, kjede, lat, lon, osm_id, ...)
- `priser` — prisregistreringer (id, stasjon_id, pris, drivstoff_type, ts, bruker_id, ...)
- `brukere` — (id, brukernavn, passord_hash, er_admin, opprettet, kallenavn)
- `api_nøkler` — (id, partner, nøkkel, aktiv)
- `visninger` — trafikk (id, ip, device_id, user_agent, ts)

## Vanlige operasjoner

**Ny API-nøkkel:**
```python
import sqlite3, uuid

KEY = str(uuid.uuid4())
conn = sqlite3.connect("/app/data/drivstoff.db")
conn.execute("INSERT INTO api_nøkler (partner, nøkkel) VALUES (?, ?)", ("<navn>", KEY))
conn.commit()
print(f"Nøkkel: {KEY}")
row = conn.execute("SELECT * FROM api_nøkler WHERE partner=?", ("<navn>",)).fetchone()
print(row)
conn.close()
```

**List API-nøkler:**
```python
import sqlite3
conn = sqlite3.connect("/app/data/drivstoff.db")
for row in conn.execute("SELECT id, partner, nøkkel, aktiv FROM api_nøkler"):
    print(row)
conn.close()
```

**Deaktiver API-nøkkel:**
```python
import sqlite3
conn = sqlite3.connect("/app/data/drivstoff.db")
conn.execute("UPDATE api_nøkler SET aktiv=0 WHERE partner=?", ("<navn>",))
conn.commit()
row = conn.execute("SELECT partner, aktiv FROM api_nøkler WHERE partner=?", ("<navn>",)).fetchone()
print(row)
conn.close()
```

## Bruk

Argumentet ($ARGUMENTS) er en beskrivelse av hva som skal gjøres, f.eks.:
- `ny nøkkel til mort`
- `list alle nøkler`
- `deaktiver nøkkel til andre`
- `hvor mange stasjoner har pris siste 24t`
- `vis siste 10 prisregistreringer`

Bygg riktig Python-script for oppgaven, bruk parameteriserte spørringer (?) for alle verdier — aldri string-interpolasjon i SQL. Vis alltid resultatet. For INSERT/UPDATE: bekreft med SELECT etterpå.

Oppgave: $ARGUMENTS
