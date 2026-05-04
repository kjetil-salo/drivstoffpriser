---
name: send-epost
description: Send epost til en bruker på drivstoffprisene.no via Resend API
allowed-tools: Bash
---

Send en epost via Resend API (noreply@ksalo.no) til en valgfri mottaker.

Argumentet ($ARGUMENTS) kan inneholde mottakers epostadresse, emne og/eller meldingstekst — tolk konteksten og spør om det som mangler.

## Fremgangsmåte

### Steg 1: Avklar innhold

Hvis $ARGUMENTS ikke allerede spesifiserer alle tre feltene, spør brukeren om:
1. **Mottaker** — epostadresse
2. **Emne** — kortfattet og vennlig
3. **Melding** — ren tekst, skriv den i HTML (enkle `<p>`-tagger holder)

Formuler gjerne et utkast basert på kontekst, og be om godkjenning.

### Steg 2: Send via Resend

Kjør direkte i prod-containeren:

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 -c \"
import resend, os
resend.api_key = os.environ['RESEND_API_KEY']
r = resend.Emails.send({
    'from': 'Drivstoffpriser <noreply@ksalo.no>',
    'to': '<mottaker>',
    'subject': '<emne>',
    'html': '<html-melding>',
})
print(r)
\""
```

**Viktig:**
- Avsender er alltid `Drivstoffpriser <noreply@ksalo.no>`
- Bruk enkle `<p>`-tagger i HTML, avslutt alltid med `Hilsen Kjetil<br>Drivstoffprisene.no`
- Pass på quoting: bruk triple-backslash `\\\"` for inner quotes i python-strengen hvis nødvendig, eller bruk en tmpfil ved kompleks HTML

### Steg 3: Bekreft

Sjekk at responsen inneholder et `id`-felt. Vis bekreftelse til brukeren.
