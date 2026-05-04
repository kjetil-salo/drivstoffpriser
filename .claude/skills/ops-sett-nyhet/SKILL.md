---
name: sett-nyhet
description: Sett nyhet-splash til brukerne i drivstoffpriser prod-DB
allowed-tools: Write, Bash
---

Sett en nyhet-splash som vises én gang per bruker i drivstoffpriser.

Argumentet ($ARGUMENTS) er meldingsteksten. Kan inneholde norske tegn og linjeskift.

## Fremgangsmåte

### Steg 1: Bekreft meldingen

Vis meldingsteksten til brukeren og spør:
1. Ser teksten riktig ut?
2. Skal meldingen inkludere "Ser du ikke det nye valget? Lukk appen helt og åpne den på nytt." — legg dette til KUN hvis nyheten handler om en ny funksjon eller UI-endring som krever SW-cache-refresh. Ikke i velkomst- eller takkemeldinger.
3. Utløpsdato (standard: 14 dager fra i dag)

### Steg 2: Skriv script

Skriv Python-script til `/tmp/sett_nyhet.py` med Write-verktøyet:

```python
import sqlite3, datetime

tekst = """<meldingsteksten her — bruk triple-quotes, bevar linjeskift>"""

utloper = (datetime.datetime.now() + datetime.timedelta(days=14)).strftime('%Y-%m-%dT%H:%M')

db = sqlite3.connect('/app/data/drivstoff.db')
db.execute('INSERT OR REPLACE INTO innstillinger (noekkel, verdi) VALUES (?, ?)', ('nyhet_tekst', tekst))
db.execute('INSERT OR REPLACE INTO innstillinger (noekkel, verdi) VALUES (?, ?)', ('nyhet_utloper', utloper))
db.commit()

# Bekreft
rad = db.execute("SELECT noekkel, verdi FROM innstillinger WHERE noekkel IN ('nyhet_tekst', 'nyhet_utloper')").fetchall()
for r in rad:
    print(r)
db.close()
```

**Viktig:**
- Kolonnen heter `noekkel` (dobbel e) — ikke `nøkkel`
- Kun ren tekst, ingen HTML/markdown
- Triple-quotes håndterer æøå og linjeskift uten quoting-problemer

### Steg 3: Kjør

```bash
scp /tmp/sett_nyhet.py kjetil@raspberrypi:/tmp/sett_nyhet.py && \
ssh kjetil@raspberrypi "docker cp /tmp/sett_nyhet.py drivstoffpriser-drivstoffpriser-1:/tmp/sett_nyhet.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/sett_nyhet.py"
```

### Steg 4: Avslutt

Vis resultatet og si til brukeren:
> "Nyheten er satt. Husk å lukke og åpne appen for å se den."
