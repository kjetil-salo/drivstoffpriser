---
name: rekrutter-fb
description: Generer Facebook-rekrutteringsmelding for å verve bidragsytere til drivstoffprisene.no fra Facebook-grupper
allowed-tools: []
---

Generer en ferdig Facebook-melding for å verve bidragsytere til drivstoffprisene.no.

Argumentet ($ARGUMENTS) kan inneholde fritekst-kontekst, gruppenøkkel og valgfritt stasjonsnavn.

Gruppenøkler:
- `dagens` → gruppen "Dagens bensin og diesel priser der du bor"
- `vestlandet` → gruppen "Drivstoffprisene på Vestlandet"

Valgfrie tillegg (kan nevnes i fritekst):
- Stedsnavn/område (f.eks. "Jæren", "Stavanger", "Åsane") — gjør meldingen mer personlig
- Stasjonsnavn (f.eks. "Circle K Bryne") — gjør meldingen enda mer konkret

## Fremgangsmåte

### Steg 1: Tolk input

Parse $ARGUMENTS som fritekst:
- Finn gruppenøkkelen (`dagens` eller `vestlandet`)
- Finn eventuelt stedsnavn/område (by, region, kommune)
- Finn eventuelt stasjonsnavn

### Steg 2: Generer melding

Bygg meldingen slik at den føles personlig. Bruk stedsnavn og/eller stasjonsnavn der de er oppgitt.

**Med stasjonsnavn og/eller stedsnavn:**

For `dagens`:
```
Hei! Ser du legger inn priser i Dagens bensin og diesel priser der du bor — [stasjonsnavn/stedsnavn-referanse] er registrert hos oss også! Hadde vært flott om du ville bidra hos oss. Vi er nye og trenger bidragsytere. 🚗 drivstoffprisene.no er et gratis, dugnadsbasert alternativ til drivstoffappen. Ingen reklame, ingen kommersielle interesser — bare frivillige som deler priser.
```

Eksempel med kun stedsnavn (f.eks. Jæren):
```
Hei! Ser du legger inn priser på Jæren i Dagens bensin og diesel priser der du bor — hadde vært flott om du ville bidra hos oss også! Vi er nye og trenger bidragsytere. 🚗 drivstoffprisene.no er et gratis, dugnadsbasert alternativ til drivstoffappen. Ingen reklame, ingen kommersielle interesser — bare frivillige som deler priser.
```

Stedsnavnet skal brukes til å bekrefte *hvor han legger inn*, ikke til å si at vi har dekning der. Ikke skriv "vi har stasjoner på X".

For `vestlandet`: tilsvarende, men nevn "Drivstoffprisene på Vestlandet" som gruppenavn.

**Uten stedsnavn eller stasjonsnavn:**

For `dagens`:
```
Hei! Ser du legger inn priser i Dagens bensin og diesel priser der du bor — hadde vært flott om du ville bidra hos oss også! Vi er nye og trenger bidragsytere. 🚗 drivstoffprisene.no er et gratis, dugnadsbasert alternativ til drivstoffappen. Ingen reklame, ingen kommersielle interesser — bare frivillige som deler priser.
```

For `vestlandet`:
```
Hei! Ser du legger inn priser i Drivstoffprisene på Vestlandet — hadde vært flott om du ville bidra hos oss også! Vi er nye og trenger bidragsytere. 🚗 drivstoffprisene.no er et gratis, dugnadsbasert alternativ til drivstoffappen. Ingen reklame, ingen kommersielle interesser — bare frivillige som deler priser.
```

### Steg 3: Vis resultatet

Vis meldingen i en kodeblokk slik at den er enkel å kopiere, og ønsker lykke til med rekrutteringen.
