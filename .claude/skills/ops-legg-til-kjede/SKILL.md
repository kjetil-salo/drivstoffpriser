---
name: legg-til-kjede
description: Legg til en ny kjede i drivstoffpriser — logo, farger, kjede.js og alle dropdowns alfabetisk
allowed-tools: Bash, Read, Edit, Write, WebFetch, Glob, Grep
---

Legg til en ny drivstoffkjede i drivstoffprisene.no.

Argument: $ARGUMENTS (kjedenavn og eventuelt URL til hjemmeside)

## Steg 1: Samle info

Hvis $ARGUMENTS er tomt, spør:
- Hva heter kjeden? (eksakt navn som skal vises)
- URL til hjemmesiden deres? (for å hente logo og farge)

## Steg 2: Hent logo

Bruk WebFetch på hjemmesiden og finn logo-URL:
- Se etter `<img>` med "logo" i src/class/alt
- Sjekk schema.org-markup (`"logo":` i JSON-LD)
- Prøv `/wp-content/uploads/` eller `/assets/` for kjente mønstre
- Prøv favicon som siste utvei: `/favicon.ico` eller `<link rel="icon">`

Last ned logoen med `curl -sL <URL> -o public/img/kjeder/<filnavn>.<ext>` og bekreft med `file`.

Filnavnet skal være kjedenavnet i lowercase, uten mellomrom og spesialtegn (f.eks. "Circle K" → `circlek`, "Trønder Oil" → `tronder-oil`).

Hvis logo ikke finnes: fortsett uten — appen viser initialer som fallback.

## Steg 3: Finn primærfarge

Fra hjemmesiden: se etter CSS-variabler (`--color-primary`, `--brand-color`), bakgrunnsfarger på header/navbar, eller logo-dominantfarge.

Velg en hex-farge som representerer kjeden. Unngå farger som allerede er i bruk for andre kjeder.

## Steg 4: Oppdater kjede.js

Fil: `public/js/kjede.js`

**KJEDE_NAVN**: Legg til den nye kjeden og sorter hele listen alfabetisk.

**KJEDE_DOMENER**: Legg til entry på riktig alfabetisk plass:
```js
{ match: ['<navn>', '<variant>'], logo: '<filnavn>', farge: '<hex>' },
```
- `match`: lowercase-varianter av kjedenavnet (inkluder varianter uten mellomrom/bindestrek)
- `logo`: filnavn uten sti. Hvis filen har .svg eller .webp, inkluder extension. Hvis .png, skriv bare filnavn uten extension.
- Utelat `logo`-feltet helt hvis ingen logo ble lastet ned (ikke legg inn et filnavn som ikke finnes)

## Steg 5: Oppdater alle dropdowns

Oppdater **alle 6 dropdowns** (3 i `public/index.html`, 3 i `public/kart2.html`):
- `#add-station-kjede`
- `#sheet-kjede-select`
- `#forslag-kjede-select`

Legg til `<option value="<navn>"><navn></option>` på riktig **alfabetisk plass** i hver dropdown.

Sørg for at alle 6 dropdowns har **identisk og komplett** liste (ingen skal mangle kjeder).

## Steg 6: Bekreft og oppsummer

Vis hva som ble gjort:
- Logofil lastet ned (eller ikke funnet)
- Farge valgt
- Lagt til i kjede.js
- Lagt til i N dropdowns

Minn brukeren på å:
1. Se over endringene
2. Deploye (`/deploy`)
3. Pushe til GitHub
