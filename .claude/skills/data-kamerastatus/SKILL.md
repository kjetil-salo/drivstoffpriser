---
name: kamerastatus
description: Vis OCR/kamera-statistikk inkl. suksessrate, hvem som har rollen og hvem som faktisk har brukt det — drivstoffprisene.no
allowed-tools: Bash
---

Hent og vis statistikk om kamera/OCR-bruk: suksessrate per modell, hvem som har kamera-rollen, og hvem som faktisk har brukt det.

NB: `tidspunkt` er NULL for alle rader i `ocr_statistikk` (bug i INSERT — ikke filtrer på dato).

## Steg 1: Skriv script

Skriv følgende til `/tmp/kamerastatus.py`:

```python
import sqlite3
from datetime import datetime

DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)

print("=" * 60)
print("KAMERA/OCR-STATISTIKK")
print(f"Generert: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print("=" * 60)

# --- Brukere med kamera-rolle ---
brukere = conn.execute("""
    SELECT id, kallenavn, brukernavn, roller
    FROM brukere
    WHERE ' ' || roller || ' ' LIKE '% kamera %'
       OR roller = 'kamera'
       OR roller LIKE 'kamera %'
       OR roller LIKE '% kamera'
    ORDER BY kallenavn
""").fetchall()

print(f"\n## Brukere med kamera-rolle ({len(brukere)} stk)\n")
print(f"{'ID':>6}  {'Kallenavn':<20}  {'Brukernavn':<30}  {'Roller'}")
print("-" * 80)
for b in brukere:
    print(f"{b[0]:>6}  {(b[1] or '-'):<20}  {(b[2] or '-'):<30}  {b[3]}")

# --- Hvem har faktisk brukt kamera ---
faktisk_brukt = conn.execute("""
    SELECT o.bruker_id, b.kallenavn, b.brukernavn,
           COUNT(*) AS antall,
           SUM(o.claude_ok) AS ok,
           ROUND(100.0 * SUM(o.claude_ok) / COUNT(*), 1) AS suksess_pst
    FROM ocr_statistikk o
    LEFT JOIN brukere b ON b.id = o.bruker_id
    GROUP BY o.bruker_id
    ORDER BY antall DESC
""").fetchall()

print(f"\n## Hvem har faktisk brukt kamera ({len(faktisk_brukt)} unike brukere)\n")
print(f"{'ID':>6}  {'Kallenavn':<20}  {'Brukernavn':<30}  {'Forsøk':>7}  {'OK':>5}  {'Suksess%':>9}")
print("-" * 85)
for r in faktisk_brukt:
    print(f"{(r[0] or 0):>6}  {(r[1] or '-'):<20}  {(r[2] or '-'):<30}  {r[3]:>7}  {(r[4] or 0):>5}  {(r[5] or 0):>8}%")

# --- Total OCR-statistikk per modell ---
total = conn.execute("""
    SELECT
        kilde,
        COUNT(*) AS total,
        SUM(claude_ok) AS ok,
        COUNT(*) - SUM(claude_ok) AS feil,
        ROUND(100.0 * SUM(claude_ok) / COUNT(*), 1) AS suksess_pst,
        ROUND(AVG(CASE WHEN claude_ok = 1 THEN claude_ms END), 0) AS snitt_ms_ok
    FROM ocr_statistikk
    WHERE kilde IS NOT NULL
    GROUP BY kilde
    ORDER BY total DESC
""").fetchall()

print(f"\n## Suksessrate per modell\n")
print(f"{'Modell':<12}  {'Totalt':>7}  {'OK':>5}  {'Feil':>5}  {'Suksess%':>9}  {'Snitt ms':>9}")
print("-" * 60)
for r in total:
    print(f"{(r[0] or '-'):<12}  {r[1]:>7}  {(r[2] or 0):>5}  {(r[3] or 0):>5}  {(r[4] or 0):>8}%  {(r[5] or 0):>9.0f}")

conn.close()
```

## Steg 2: Kopier og kjør

```bash
scp /tmp/kamerastatus.py raspberrypi:/tmp/ && \
ssh raspberrypi "docker cp /tmp/kamerastatus.py drivstoffpriser-drivstoffpriser-1:/tmp/ && \
docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/kamerastatus.py"
```

## Steg 3: Presenter resultatet

Formater tabellene pent i markdown. Kommenter:
- Hvor mange har rollen vs. hvor mange har faktisk brukt det
- Hvilken modell har høyest suksessrate
- Om noen brukere skiller seg ut

Husk: Pi kjører UTC, som er 2 timer bak norsk sommertid (CEST).
