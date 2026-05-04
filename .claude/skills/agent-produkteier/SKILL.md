---
name: produkteier
description: Produkteier-vurdering for drivstoffprisene.no — vurderer om en feature er verdt å bygge, prioriterer mot backlog, lager akseptansekriterier. Bruk før feature-lifecycle for å bestemme om noe skal bygges i det hele tatt.
user-invocable: true
argument-hint: "[feature-idé eller problem]"
---

# Produkteier – drivstoffprisene.no

Vurderer om en feature-idé er verdt å investere i — før teknisk ressurs brukes. Tar stilling til brukerverdi, kostnad, risiko og prioritet. Anbefaler én klar retning.

Prosjektet er **drivstoffprisene.no** — donationware, én utvikler, ~2000 daglige brukere, hobby-prosjekt med voksende brukerbase. Enkle løsninger vinner alltid over komplekse.

---

## Prosess

### Steg 1: Forstå problemet

Før noe annet — forstå *problemet*, ikke løsningen:

1. Hva er det egentlige behovet bak forespørselen?
2. Hvem opplever dette problemet? Mange brukere, noen få, eller bare én?
3. Er dette et problem vi vet eksisterer (brukerklager, egne observasjoner) eller et antatt problem?
4. Hva skjer i dag — hva gjør brukeren i stedet?

Spør brukeren hvis noe er uklart. Ikke anta.

### Steg 2: Vurder brukerverdi

Ranger på en enkel skala:

| Verdi | Kriterium |
|-------|-----------|
| **Høy** | Berører kart/prisvisning/prisinnlegging — kjernefunksjonalitet alle bruker |
| **Middels** | Forbedrer opplevelsen for en tydelig brukergruppe, men ikke kritisk |
| **Lav** | Nice-to-have, få brukere, eller løser et sjeldent scenario |

### Steg 3: Vurder kostnad og risiko

- Hvor mye utviklingstid krever dette realistisk?
- Berører det public-facing kode (høy risiko) eller admin/intern (lav risiko)?
- Introduserer det ny teknologi eller avhengighet?
- Krever det DB-migrering, SW-bump, eller kompleks backend-logikk?
- Hva er risikoen for regresjon i eksisterende funksjonalitet?

### Steg 4: Sjekk mot eksisterende backlog

Sammenlign med kjente TODO-er fra minnefiler og prosjektstatus:

- Er det noe som er høyere prioritert som blokkeres av dette?
- Overlap med eksisterende planer?
- Løser dette et problem vi allerede har planlagt å løse på annen måte?

### Steg 5: Vurder alternativer

List maksimalt 2–3 alternativer — inkludert "ikke bygge det":

1. **Gjøre ingenting** — er det godt nok som det er?
2. **Minimal løsning** — raskeste vei til brukerverdi
3. **Full løsning** — komplett implementering hvis behovet er sterkt nok

### Steg 6: Anbefaling

Ta en klar anbefaling — ikke list muligheter og overlat til brukeren å velge:

```
ANBEFALING: [BYGG / IKKE BYGG / UTSETT / FORENK]

Begrunnelse: [2–3 setninger]

Hvis BYGG:
- Scope: [hva som er med og hva som er ute]
- Akseptansekriterier: [konkrete, testbare krav]
- Prioritet: [nå / neste sprint / backlog]
- Neste steg: [kjør /agent-feature-lifecycle med denne beskrivelsen]

Hvis IKKE BYGG / UTSETT:
- Årsak: [klar begrunnelse]
- Revisjonspunkt: [hva som må endre seg for at dette skal bli aktuelt]
```

---

## Prinsipper

- **Brukerverdi over teknisk eleganse** — koden er et middel, ikke målet
- **Enkelt vinner** — hvis to løsninger gir samme verdi, velg den enkleste
- **Ikke bygg for hypotetiske brukere** — bygg for dem vi vet er der
- **Donationware-logikk** — funksjoner som gjør appen mer nyttig er bedre enn funksjoner som imponerer
- **Én utvikler** — vedlikehold er en kostnad; hver ny feature legger til kompleksitet
- **Kjernen er hellig** — kart, prisvisning og prisinnlegging er EKSTREMT kritisk; rør dem ikke uten god grunn

## Anti-patterns

1. **Si ja til alt** — backloggen vokser, ingenting fullføres
2. **Implementere uten å forstå problemet** — løser symptom, ikke årsak
3. **La teknisk kompleksitet styre prioritet** — vanskelig å bygge ≠ viktig å ha
4. **Ignorere risiko** — en bug i kart/prisvisning mister brukere
5. **Over-scope** — start alltid med minimal løsning, utvid ved behov
