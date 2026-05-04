---
name: blogg
description: Skriv ukentlig prisanalyse-blogg for drivstoffprisene.no — henter data fra DB og norske nyheter
allowed-tools: Write, Bash, WebFetch, Read, Edit
---

Generer en ukentlig prisanalyse-blogg basert på data fra prod-DB og aktuelle norske nyheter.

Argumentet ($ARGUMENTS) kan inneholde spesifikke vinklinger eller temaer å fokusere på. Tomt = fri analyse av siste uke.

## Steg 1: Hent prisdata fra DB

Skriv Python-script til `/tmp/blogg_data.py`:

```python
import sqlite3, json
from datetime import datetime, timedelta

db = sqlite3.connect("/app/data/drivstoff.db")
db.row_factory = sqlite3.Row
nå = datetime.now()
uke_siden = (nå - timedelta(days=7)).isoformat()
to_uker_siden = (nå - timedelta(days=14)).isoformat()

# Snitt siste uke vs. forrige uke
snitt_denne = db.execute("""
    SELECT drivstoff_type, ROUND(AVG(pris),2) as snitt, COUNT(*) as antall
    FROM priser WHERE ts >= ? GROUP BY drivstoff_type
""", (uke_siden,)).fetchall()

snitt_forrige = db.execute("""
    SELECT drivstoff_type, ROUND(AVG(pris),2) as snitt
    FROM priser WHERE ts >= ? AND ts < ? GROUP BY drivstoff_type
""", (to_uker_siden, uke_siden)).fetchall()

# Snitt per kjede siste uke (bensin 95, min 5 registreringer)
per_kjede = db.execute("""
    SELECT s.kjede, ROUND(AVG(p.pris),2) as snitt, COUNT(*) as antall
    FROM priser p JOIN stasjoner s ON p.stasjon_id = s.id
    WHERE p.ts >= ? AND p.drivstoff_type = 'bensin_95'
    GROUP BY s.kjede HAVING COUNT(*) >= 5
    ORDER BY snitt
""", (uke_siden,)).fetchall()

# Billigste og dyreste stasjon akkurat nå (siste pris per stasjon)
billigst = db.execute("""
    SELECT s.navn, s.kjede, p.pris, p.ts
    FROM priser p JOIN stasjoner s ON p.stasjon_id = s.id
    WHERE p.drivstoff_type = 'bensin_95'
    AND p.ts = (SELECT MAX(ts) FROM priser WHERE stasjon_id = p.stasjon_id AND drivstoff_type = 'bensin_95')
    AND p.ts >= ?
    ORDER BY p.pris ASC LIMIT 5
""", (uke_siden,)).fetchall()

dyreste = db.execute("""
    SELECT s.navn, s.kjede, p.pris, p.ts
    FROM priser p JOIN stasjoner s ON p.stasjon_id = s.id
    WHERE p.drivstoff_type = 'bensin_95'
    AND p.ts = (SELECT MAX(ts) FROM priser WHERE stasjon_id = p.stasjon_id AND drivstoff_type = 'bensin_95')
    AND p.ts >= ?
    ORDER BY p.pris DESC LIMIT 5
""", (uke_siden,)).fetchall()

# Stasjoner med størst prisendring siste uke (maks - min)
prishopp = db.execute("""
    SELECT s.navn, s.kjede,
           ROUND(MAX(p.pris) - MIN(p.pris), 2) as spenn,
           ROUND(MIN(p.pris),2) as min_pris,
           ROUND(MAX(p.pris),2) as max_pris,
           COUNT(*) as antall_registreringer
    FROM priser p JOIN stasjoner s ON p.stasjon_id = s.id
    WHERE p.ts >= ? AND p.drivstoff_type = 'bensin_95'
    GROUP BY p.stasjon_id HAVING COUNT(*) >= 3
    ORDER BY spenn DESC LIMIT 5
""", (uke_siden,)).fetchall()

# Totalt antall registreringer og unike bidragsytere siste uke
aktivitet = db.execute("""
    SELECT COUNT(*) as registreringer,
           COUNT(DISTINCT bruker_id) as bidragsytere,
           COUNT(DISTINCT stasjon_id) as stasjoner
    FROM priser WHERE ts >= ?
""", (uke_siden,)).fetchone()

# Regionale snitt (by/fylke via stasjonsnavn-heuristikk er upålitelig, bruk lat/lon-soner)
# Bergen: lat 60.2-60.5, lon 5.2-5.5 | Oslo: lat 59.8-60.0, lon 10.6-10.9
bergen = db.execute("""
    SELECT ROUND(AVG(p.pris),2) as snitt, COUNT(*) as antall
    FROM priser p JOIN stasjoner s ON p.stasjon_id = s.id
    WHERE p.ts >= ? AND p.drivstoff_type = 'bensin_95'
    AND s.lat BETWEEN 60.2 AND 60.5 AND s.lon BETWEEN 5.2 AND 5.5
""", (uke_siden,)).fetchone()

oslo = db.execute("""
    SELECT ROUND(AVG(p.pris),2) as snitt, COUNT(*) as antall
    FROM priser p JOIN stasjoner s ON p.stasjon_id = s.id
    WHERE p.ts >= ? AND p.drivstoff_type = 'bensin_95'
    AND s.lat BETWEEN 59.8 AND 60.0 AND s.lon BETWEEN 10.6 AND 10.9
""", (uke_siden,)).fetchone()

data = {
    "periode": {"fra": uke_siden[:10], "til": nå.strftime("%Y-%m-%d")},
    "snitt_denne_uke": [dict(r) for r in snitt_denne],
    "snitt_forrige_uke": [dict(r) for r in snitt_forrige],
    "per_kjede": [dict(r) for r in per_kjede],
    "billigst": [dict(r) for r in billigst],
    "dyreste": [dict(r) for r in dyreste],
    "prishopp": [dict(r) for r in prishopp],
    "aktivitet": dict(aktivitet),
    "byer": {"bergen": dict(bergen), "oslo": dict(oslo)},
}
print(json.dumps(data, ensure_ascii=False, indent=2))
db.close()
```

Kjør:
```bash
scp /tmp/blogg_data.py kjetil@raspberrypi:/tmp/blogg_data.py && \
ssh kjetil@raspberrypi "docker cp /tmp/blogg_data.py drivstoffpriser-drivstoffpriser-1:/tmp/blogg_data.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/blogg_data.py"
```

## Steg 2: Hent norske nyheter

Hent RSS-feeds og finn relevante nyheter om drivstoff, bensin, diesel, oljepris siste 7 dager:

- E24 energi: `https://e24.no/rss/energi`
- NRK nyheter: `https://www.nrk.no/toppsaker.rss`
- E24 generelt: `https://e24.no/rss`

Søk etter titler/ingresser som inneholder: bensin, diesel, drivstoff, oljepris, råolje, veibruksavgift, OPEC.

Merk: RSS-titler gir kontekst — bruk dem til å forklare *hvorfor* prisene beveget seg slik de gjorde.

## Steg 2b: Verifiser prishopp-data

Før prishopp brukes i teksten, verifiser alltid at de er troverdige. Skriv et verifiseringsskript som henter alle enkeltregistreringer og antall unike brukere per stasjon:

```python
import sqlite3
from datetime import datetime, timedelta

db = sqlite3.connect("/app/data/drivstoff.db")
db.row_factory = sqlite3.Row
uke_siden = (datetime.now() - timedelta(days=7)).isoformat()

for navn in [<stasjonsnavn fra prishopp-listen>]:
    stasjon = db.execute("SELECT id FROM stasjoner WHERE navn = ?", (navn,)).fetchone()
    rader = db.execute("""
        SELECT p.bensin, p.tidspunkt, p.bruker_id FROM priser p
        WHERE p.stasjon_id = ? AND p.tidspunkt >= ? AND p.bensin IS NOT NULL
        ORDER BY p.tidspunkt
    """, (stasjon["id"], uke_siden)).fetchall()
    unike = len(set(r["bruker_id"] for r in rader))
    print(f"{navn} ({len(rader)} reg., {unike} unike brukere):")
    for r in rader:
        print(f"  {r['tidspunkt']}  {r['bensin']} kr  bruker {r['bruker_id']}")
db.close()
```

**Forkast et prishopp hvis:**
- Én bruker registrerte høy og lav pris med få sekunders mellomrom (= feilregistrering som ble rettet)
- Bare én unik bruker har registrert på stasjonen
- Maksprisen bare er registrert av én bruker og ingen andre har bekreftet den

**Bruk kun prishopp som er bekreftet av minst 2 uavhengige brukere, eller der mønsteret er åpenbart (f.eks. alle registreringer før/etter 1. april).**

## Steg 3: Analyser og skriv utkast

Bruk dataene og nyhetsbildet til å skrive en engasjerende analyse. Retningslinjer:

**Tone og stil:**
- Journalistisk, konkret, faktabasert — som priser-mars-2026.html
- Norsk bokmål
- Unngå klisjeer ("I en tid der...", "Prisene har beveget seg...")
- Start med det mest interessante funnet, ikke en oppsummering
- Bruk tall aktivt — ikke "prisene falt" men "bensin falt 1,20 kr til 21,50 kr"

**Struktur:**
- Tittel: konkret og søkbar (f.eks. "Bensinprisen under 20 kr i Bergen — første gang siden 2021")
- Ingress/manchet (1-2 setninger)
- 3-4 seksjoner med h2
- Tall-kort (aktivitetsdata)
- Eventuell faktaboks ved viktige hendelser (avgiftsendringer, politiske vedtak)
- CTA til slutt

**Nyhetskobling:**
- Hvis råoljeprisen falt/steg: koble til internasjonal nyhet
- Hvis én kjede skiller seg ut: nevn det eksplisitt
- Hvis politisk relevant (avgifter, Stortinget): inkluder faktaboks

## Steg 4: Vis utkast til brukeren

Vis den genererte teksten (ikke HTML, bare innholdet) og spør:
- Er tonen og vinklingen riktig?
- Er det noe som bør endres, legges til eller kuttes?
- Hva skal slug/filnavn være? (forslag: `priser-[måned]-[år].html`)

Vent på godkjenning eller justeringer. Gjør endringer etter tilbakemelding.

## Steg 5: Generer HTML og skriv til disk

Bruk HTML-strukturen fra `public/blogg/priser-mars-2026.html` som mal — samme inline CSS og komponentklasser (`.tall-rad`, `.tall-kort`, `.faktaboks`, `.cta` osv.).

Skriv ferdig HTML til `/Users/kjetil/git/drivstoffpriser/public/blogg/<slug>.html`.

Oppdater `public/blogg/index.html`: legg ny artikkel **øverst** i `.artikkel-liste` med dato, overskrift og sammendrag (2 setninger).

## Steg 6: Avslutt

Si til brukeren:
> "Bloggartikkelen er skrevet til `public/blogg/<slug>.html` og index.html er oppdatert.
>
> Neste steg:
> 1. Bump SW cache og kjør `./deploy.sh prod`
> 2. Sett nyhet-splash: `/sett-nyhet 'Ny prisanalyse: <tittel> → drivstoffprisene.no/blogg/<slug>.html'`"
