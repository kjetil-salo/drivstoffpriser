---
name: deploy
description: Deploy drivstoffpriser til Pi (prod/staging) eller Fly.io — med SW cache-bump og sanity-sjekk
allowed-tools: Bash, Read, Edit
---

Deploy drivstoffpriser til valgt miljø.

## Miljøer

- `prod` — Raspberry Pi, port 3002
- `staging` — Raspberry Pi, port 3003 (anbefalt første steg)
- `fly` — Fly.io (backup-instans)
- `all` — Pi prod + Fly.io

Argument: $ARGUMENTS (tomt = spør brukeren)

## Fremgangsmåte

### Steg 1: Finn ut hva som skal deployes

Hvis $ARGUMENTS er tomt, spør: "Hvor vil du deploye? (staging / prod / fly / all)"

### Steg 2: Sjekk om SW cache må bumpes

Les `public/sw.js` og se på gjeldende `CACHE_VERSION`.

Spør brukeren: "Har du endret frontend-filer (JS, CSS, HTML)? I så fall bør CACHE_VERSION bumpes (nå: vXX)."

Hvis svaret er ja (eller brukeren sa det på forhånd i $ARGUMENTS), bump versjonen:
- Les gjeldende verdi
- Inkrementer tallet (f.eks. v42 → v43)
- Oppdater `CACHE_VERSION` i `public/sw.js` med Edit

### Steg 3: Kjør deploy

**For staging og fly:**
```bash
cd /Users/kjetil/git/drivstoffpriser && ./deploy.sh <miljø>
```

**For prod og all:**
Ikke kjør deploy.sh selv. Si til brukeren:
> "Klar for prod. Kjør selv: `./deploy.sh prod`"

Prod-deploy skal alltid initieres av brukeren i terminalen — deploy.sh krever interaktiv bekreftelse og den sperren skal respekteres.

### Steg 4: Verifiser

Etter deploy:
- For **staging**: minn brukeren på å teste på http://raspberrypi:3004 før prod
- For **prod/all**: be brukeren bekrefte at https://drivstoffprisene.no ser OK ut
- For **fly**: be brukeren bekrefte at https://drivstoffpriser.fly.dev ser OK ut
- Minn brukeren på å pushe til GitHub: `git push`

## Viktig

- Aldri skip tester (--no-verify e.l.)
- SW cache-bump er kritisk ved frontend-endringer — uten det sitter brukere med gammel cache
- Staging før prod er god praksis, spesielt ved usikre endringer
