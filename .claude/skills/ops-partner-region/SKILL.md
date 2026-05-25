---
name: ops-partner-region
description: Vis stasjoner i et partner1-distrikt (Haugalandet/Stavanger/Jæren/Grenland/Bergen/Kristiansand/Førde/BergenBy/AskøySotraØygarden/MøreRomsdal/Alver/Osterøy) og kjør manuell sync for distriktet på Pi.
allowed-tools: Bash, Read
---

Vis stasjonsliste for et distrikt og kjør partner1-sync for det distriktet på Pi.

Argument: $ARGUMENTS (regionsnavn — Haugalandet, Stavanger, Jæren, Grenland, Bergen, Kristiansand, Førde, BergenBy, AskøySotraØygarden, MøreRomsdal, Alver eller Osterøy)

## Bakgrunn

Alle stasjoner under er registrert i `STASJON_MAPPING` i `tools/drivstoffappen_sync.py` og synkes automatisk av cronjobben (`0 5-23 * * *`). Denne skillen brukes for manuell trigring eller for å se hvilke stasjoner som tilhører et distrikt.

Bbox-definisjoner (fra `routes_admin.py`):
- **Bergen**: lat 60.10–60.88, lon 4.70–5.75
- **Haugalandet**: lat 59.08–59.65, lon 5.05–5.60
- **Stavanger**: lat 58.75–59.15, lon 5.40–6.05
- **Jæren**: lat 58.60–58.82, lon 5.35–5.72
- **Grenland**: lat 58.95–59.40, lon 9.35–9.90
- **Førde**: lat 61.40–61.55, lon 5.75–6.10

## Stasjonslister per region

### Bergen (20 stasjoner)

| Vår ID | Drivstoffappen-ID | Navn |
|--------|-------------------|------|
| 1      | 433               | Esso Frekhaug |
| 2      | 2190              | Circle K Automat Knarvik |
| 3      | 88                | Esso Nyborg |
| 4      | 687               | St1 Haukås Nyborg |
| 11     | 28414             | Haltbakk Express Ostereidet |
| 12     | 791               | Circle K Viken |
| 16     | 1278              | St1 Marikollen |
| 18     | 1324              | St1 Lone |
| 19     | 25153             | Uno-X Tertnes |
| 26     | 4064              | Oljeleverandøren Hylkje |
| 30     | 76                | Circle K Ulset |
| 32     | 643               | Circle K Haukås |
| 33     | 644               | Circle K Helleveien |
| 35     | 1094              | Uno-X 7-Eleven Øyrane torg |
| 36     | 2093              | St1 Nygård |
| 42     | 49                | Uno-X Gullgruven (Åsane) |
| 43     | 121               | Uno-X 7-Eleven Nyborg |
| 45     | 1222              | St1 Isdalstø |
| 5690   | 468               | Esso Hundvåg |
| 1882   | 1351              | St1 Randabergveien |
| 1887   | 221               | Esso Tjensvollkrysset |

### Haugalandet (34 stasjoner)

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 60      | 245               | St1 Karmsundgata |
| 61      | 25150             | Uno-X Karmsundgata |
| 62      | 203               | Esso Express Avaldsnes |
| 64      | 137               | Uno-X Avaldsnes |
| 65      | 269               | Uno-X Norheim |
| 66      | 1548              | Tanken Frakkagjerd |
| 67      | 3160              | YX Bømlo |
| 68      | 136               | Uno-X Spannavegen |
| 69      | 1547              | Tanken Spannaveien |
| 70      | 3602              | Circle K Automat Karmsundgata |
| 71      | 199               | Circle K Truck Haugesund |
| 72      | 257               | Circle K Automat Spannaveien |
| 73      | 187               | Circle K Kvala |
| 75      | 4569              | Driv Ekrene |
| 76      | 216               | Esso Raglamyr |
| 77      | 207               | Esso Express Gard |
| 78      | 477               | Esso Karmsundgaten |
| 80      | 1342              | St1 Norheim |
| 82      | 25157             | Uno-X Raglamyr |
| 1236    | 1304              | St1 Haukås Sveio |
| 1247    | 4406              | Tanken Vikebygd |
| 1529655 | 8792              | Tanken Isvik |
| 2001    | 195               | Circle K Skudeneshavn |
| 2003    | 1545              | Tanken Langåker |
| 2004    | 3170              | Circle K Automat Kopervik |
| 2005    | 259               | Circle K Sævelandsvik |
| 2006    | 1311              | St1 Karmøy |
| 2007    | 246               | St1 Kopervik |
| 2008    | 265               | Uno-X Karmøy |
| 2012    | 3184              | Circle K Truck Gismarvik |
| 2110    | 1188              | St1 Aksdal |
| 2113    | 1186              | St1 Eikeskog |
| 2114    | 884               | YX Truck Aksdal |
| 19959   | 25158             | Tanken Kvala |

### Stavanger (57 stasjoner)

| Vår ID | Drivstoffappen-ID | Navn |
|--------|-------------------|------|
| 1811   | 1282              | St1 Rennesøy |
| 1815   | 474               | Esso Jørpeland |
| 1819   | 751               | Circle K Jørpeland |
| 1821   | 138               | Uno-X Tau |
| 1830   | 197               | Circle K Tau |
| 1834   | 183               | Circle K Hana |
| 1835   | 238               | St1 Forus |
| 1836   | 181               | Circle K Forus |
| 1837   | 206               | Esso Forus |
| 1838   | 145               | Uno-X Forussletta |
| 1839   | 196               | Circle K Automat Sola |
| 1840   | 191               | Circle K Lura |
| 1841   | 217               | Esso Sandnes |
| 1842   | 3691              | Circle K Automat Hafrsfjord |
| 1844   | 240               | St1 Hagakrossen |
| 1845   | 140               | Uno-X Tasta |
| 1846   | 1167              | St1 Bogafjell |
| 1847   | 3589              | Uno-X Tananger |
| 1848   | 1105              | Uno-X 7-Eleven Blåsenborg |
| 1849   | 775               | Circle K Tjelta |
| 1850   | 244               | St1 Jærveien |
| 1851   | 150               | Uno-X Kongeparken |
| 1852   | 170               | Circle K Åsedalen |
| 1853   | 28386             | Circle K Truck Ganddal |
| 1854   | 233               | St1 Ålgård |
| 1855   | 174               | Circle K Automat Mariero |
| 1856   | 248               | St1 Lura |
| 1859   | 148               | Uno-X Klepp |
| 1860   | 144               | Uno-X Forus |
| 1861   | 1542              | Esso Express Løkkeveien |
| 1871   | 147               | Uno-X Kverneland |
| 1872   | 149               | Uno-X Hove |
| 1874   | 1326              | St1 Madlakrossen |
| 1875   | 801               | Circle K Hommersåk |
| 1876   | 186               | Circle K Klepp |
| 1878   | 184               | Circle K Haugesundsgaten |
| 1879   | 169               | Circle K Ålgård |
| 1880   | 250               | St1 Solakrossen |
| 1883   | 242               | St1 Haugåsveien |
| 1884   | 219               | Esso Express Sola |
| 1885   | 544               | Esso Revheimsveien |
| 1886   | 204               | Esso Bekkefaret |
| 1890   | 453               | Esso Hillevåg |
| 1891   | 142               | Uno-X Madlaveien |
| 1892   | 141               | Uno-X Sola |
| 1893   | 139               | Uno-X Randaberg |
| 1895   | 143               | Uno-X Mariero |
| 1897   | 28648             | Circle K Truck Risavika |
| 1904   | 4063              | St1 Risavika |
| 1906   | 20813             | Circle K Automat Sandnesporten |
| 1908   | 146               | Uno-X Lura |
| 1909   | 28286             | Uno-X Hinna |
| 3091   | 194               | Circle K Randaberg |
| 5661   | 2865              | Circle K Automat Hundvåg |

## Konfigurere prosent per region

Hver region i `REGIONER`-dict i `tools/drivstoffappen_sync.py` har et `(mapping, prosent)`-tuple. Sett prosent til `None` for 100 %, eller et tall for å begrense antall stasjoner:

```python
REGIONER: dict[str, tuple[dict, float | None]] = {
    'more_romsdal': (STASJON_MAPPING_MORE_ROMSDAL, 60),  # ~60% av stasjonene
    'stavanger':    (STASJON_MAPPING_STAVANGER,    None), # alle stasjoner
}
```

Utvalget er `random.sample` — eksakt N stasjoner, ikke per-stasjon-sjanse.

## Manuell sync på Pi

Full sync for regionen:

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 /app/tools/drivstoffappen_sync.py --region <regionsnøkkel>"
```

Overstyr prosent for én kjøring (uavhengig av konfigurert prosent):

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 /app/tools/drivstoffappen_sync.py --region stavanger --prosent 20"
```

Outputtet viser SKREVET / SKIP / AVVIST per stasjon.

Etter kjøring: parse logg-linjene og vis en tabell over ALLE sjekket stasjoner med status til slutt:

| Stasjon | Bensin | Diesel | Tidspunkt | |
|---------|--------|--------|-----------|--|
| Circle K Ulset | 22,49 | 23,49 | 10:44 | ✓ |
| Esso Nyborg | 21,99 | 22,99 | 08:12 | — |

Regler:
- Én rad per stasjon som dukker opp i loggen (både `lagret` og `SKIP`-linjer)
- `lagret`-linjer: parse bensin/diesel/ts, siste kolonne = `✓`
- `SKIP`-linjer: vis navn og prisen som ble hoppet over, siste kolonne = `—`
- Avslutningsvis: `N skrevet, M hoppet over` fra siste INFO-linje

## Stasjonene som IKKE er med (tvilsomme matcher — ikke lagt til)

**Haugalandet:**
- 63 LPG Steinsvik AS (LPG-stasjon)
- 74 Circle K Truck Scania sør (nærmeste i Drivstoffappen er Mer-ladestasjon)
- 79 LPG Karmøy (ladestasjon)
- 81 Haugaland Olje Husøy (annen brand i Drivstoffappen)
- 83 Tanken Helganes (for lav confidence)
- 2010 Knapphus Bokn Føresvik (for lav confidence)
- 1475085 Knapphus Energi Avaldsnes (for lav confidence)

**Stavanger:**
- 1857 Esso Sele Servicesenter (matched til "Voll", usikker)
- 1867 Esso Express Tanke Svilands gate 33 (for lav confidence)

**Kristiansand:**
- 4300 Circle K Truck Mjåvann (ingen match, nærmeste er Veøy Kristiansand 0.546 km)
- 4289 Driv Mjåvann (ingen match, nærmeste er Veøy Kristiansand 0.503 km)
- 4297 YX Truck Rosseland (samme DS-ID 25136 som Uno-X Rosseland — duplikat)
- 1529712 Norsk Olje Barstølveien (usikker match til DS "Scania" ID 25344)
- 4288 Preem Kristiansand (usikker match til DS "Kemtek Langemyr" ID 28624)

### Grenland (40 stasjoner)

Regionsnøkkel: `grenland`. Dekker Skien, Porsgrunn, Bamble og omegn. Bounding box: lat 58.95–59.40, lon 9.35–9.90.

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 497     | 747               | Circle K Bratsberg |
| 498     | 830               | Circle K Nylende |
| 499     | 1098              | Uno-X 7-Eleven Wattenberg |
| 500     | 1321              | St1 Lasses |
| 501     | 11                | Esso Rugtvedt |
| 502     | 788               | Circle K Skjelsvik |
| 507     | 5483              | Circle K Automat Borgeåsen |
| 510     | 281               | Uno-X Herøya |
| 511     | 303               | Uno-X Vestsiden |
| 512     | 345               | Uno-X Vallermyrene |
| 514     | 278               | Uno-X Kjørbekk |
| 515     | 292               | Uno-X Bøleveien |
| 516     | 1023              | Esso Grasmyr |
| 518     | 397               | Esso Brua |
| 519     | 26581             | Circle K Automat Helgeroa |
| 520     | 526               | Esso Myren |
| 521     | 1332              | St1 Myrland Auto |
| 522     | 1535              | Tanken Stathelle |
| 524     | 2276              | Circle K Automat Stridsklev |
| 527     | 834               | Circle K Porsgrunn |
| 528     | 762               | Circle K Automat Telemarksveien |
| 529     | 832               | Circle K Jorkjend |
| 532     | 1349              | St1 Pors |
| 533     | 1171              | St1 Truck Eidanger |
| 534     | 381               | Circle K Goberg |
| 535     | 282               | Uno-X Rafnes |
| 536     | 2948              | Driv Heistad |
| 537     | 331               | Uno-X Falkum |
| 538     | 368               | Uno-X Tollnes |
| 539     | 25083             | Uno-X Heistad |
| 542     | 1471              | Driv Bamble |
| 545     | 2032              | Nilsen og Kokkersvold (Langangen i DS) |
| 547     | 25123             | Uno-X Menstad |
| 551     | 678               | Circle K Telemarksporten |
| 553     | 2961              | Circle K E18 Bamble |
| 1511453 | 28413             | Haslestad Energi Eidanger |
| 1529680 | 28652             | Esso Skjelsvik |
| 1529713 | 8705              | Rødmyr automat |
| 3839    | 917               | YX Siljan |
| 3872    | 28288             | Driv Steinsholt |

**Ikke med:**
- 494–496 Automat1 Porsgrunn/Skien — bruker eget system, ikke Drivstoffappen
- 517 LPG Kragerø — ingen match (LPG-stasjon)
- 541 VardeVed — ikke bensinstasjon
- 548 Nor bunkring Langesund — maritimt bunker
- 1529681 Feilplasert stasjon — duplikat/feil plassering
- 1529693 BLM Transport Rødmyr — industriell transportstasjon
- 3022 Driv Melum — ingen match (nærmeste 9.5 km unna)

### Jæren (9 stasjoner)

Merk: Uno-X Klepp (1859) og Circle K Klepp (1876) er også i Stavanger-mappingen.

| Vår ID | Drivstoffappen-ID | Navn |
|--------|-------------------|------|
| 1859   | 148               | Uno-X Klepp |
| 1876   | 186               | Circle K Klepp |
| 1910   | 1539              | Tanken Kåsen |
| 1881   | 230               | St1 Bryne |
| 1889   | 205               | Esso Bryne |
| 1862   | 151               | Uno-X Bryne |
| 1888   | 152               | Uno-X Nærbø |
| 1863   | 2861              | Circle K Automat Nærbø |
| 1877   | 193               | Circle K Nærbø |

### Kristiansand (28 stasjoner)

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 4247    | 3179              | Circle K Automat Brennåsen |
| 4248    | 2241              | Circle K Automat Sørlandsparken |
| 4246    | 177               | Circle K Automat Voiebyen |
| 4245    | 179               | Circle K Elvegaten |
| 4244    | 8962              | Circle K Truck Dalane |
| 1529776 | 28664             | Driv Skibåsen |
| 4293    | 6618              | Esso Express Kjuttaviga |
| 4253    | 210               | Esso Express Krossen |
| 4231    | 498               | Esso Express Vågsbygd |
| 4234    | 213               | Esso Oddemarka |
| 4239    | 218               | Esso Søgne |
| 4237    | 28368             | Høllen brygge |
| 4252    | 226               | St1 Fidjane vest |
| 4251    | 1291              | St1 Fidjane øst |
| 4222    | 1331              | St1 Mosby |
| 4221    | 1340              | St1 Nodeland |
| 4250    | 236               | St1 Sørlandsparken |
| 4226    | 1164              | St1 Truck Kristiansand |
| 4235    | 256               | St1 Valhalla |
| 4233    | 255               | St1 Vige |
| 4228    | 276               | Uno-X 7-Eleven Vågsbygd |
| 4218    | 25231             | Uno-X Hamresanden |
| 4220    | 25136             | Uno-X Rosseland |
| 4287    | 159               | Uno-X Skibåsen |
| 4229    | 158               | Uno-X Sørlandsparken |
| 4227    | 263               | YX Håneskrysset |
| 4238    | 273               | YX Søgne (automat) |
| 4292    | 28592             | YX Truck Veøy Kristiansand |

### Førde (10 stasjoner)

| Vår ID | Drivstoffappen-ID | Navn |
|--------|-------------------|------|
| 3810   | 28301             | Circle K Truck Førde |
| 3804   | 79                | Esso Førde |
| 3812   | 24503             | Knapphus Energi Øyrane |
| 3819   | 21676             | Oljeleverandøren Førde |
| 3818   | 1233              | St1 Truck Firda billag |
| 3815   | 47                | Uno-X Førde |
| 3813   | 2307              | YX Coop Førde (automat) |
| 3803   | 25194             | YX Express Hafstadvegen (automat) |
| 3805   | 117               | YX Førde |
| 3816   | 1071              | YX Jølstraholmen |

**Merk:** Esso Førde (3804) og YX Express Hafstadvegen (3803) ligger bare ~60 m fra hverandre — de er to separate stasjoner (ulike merker: Esso vs. YX), bekreftet av Drivstoffappen.

### Bergen by (37 stasjoner)

Regionsnøkkel: `bergenby`. Dekker Bergen sentrum, Sotra, Askøy og Flesland. Bounding box: lat 60.25–60.50, lon 4.85–5.45. Stasjoner i base STASJON_MAPPING (daglig cron) er ikke med her.

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 5       | 1219              | St1 Sandviken |
| 6       | 1090              | Uno-X 7-Eleven Natland |
| 7       | 3490              | Circle K Automat Sædalen |
| 8       | 1088              | Uno-X 7-Eleven Kleppestø |
| 9       | 28393             | Haltbakk express Askøy |
| 10      | 508               | St1 Storetveit |
| 13      | 66                | Circle K Ravnanger |
| 14      | 476               | Esso Kanalveien |
| 17      | 119               | Uno-X 7-Eleven Drotningsvik |
| 20      | 1383              | St1 Varden |
| 21      | 2059              | Circle K Automat Fyllingsdalen |
| 22      | 2104              | Circle K Automat Godvik |
| 29      | 50                | Uno-X Hauglandshella |
| 31      | 56                | Circle K Automat Askøy |
| 38      | 486               | Esso Laksevåg |
| 52      | 415               | Esso Express Landåstorget |
| 137     | 743               | Circle K Flesland |
| 140     | 1339              | St1 Nesttun |
| 142     | 527               | Esso Nesttun |
| 143     | 822               | Circle K Sandsli |
| 144     | 1214              | St1 Blomsterdalen |
| 149     | 25178             | Haltbakk Express Søfteland |
| 151     | 55                | Uno-X Kokstad |
| 153     | 665               | Circle K Nesttun |
| 154     | 1320              | St1 Laguneparken |
| 162     | 54                | Uno-X Søreide |
| 668911  | 4134              | Oljeleverandøren Drotningsvik |
| 1275    | 372               | Esso Ågotnes |
| 1281    | 986               | YX Skogsvåg |
| 1283    | 6143              | Circle K Skogsvåg |
| 1287    | 1027              | Uno-X 7-Eleven Kolltveit |
| 1289    | 753               | Circle K Fjell |
| 1290    | 52                | Uno-X Straume |
| 1292    | 109               | St1 Straume |
| 1529676 | 28372             | Oljeleverandøren Lønningsflaten |
| 1529716 | 28677             | Haltbakk Kokstad |
| 9500    | 28643             | Oljeleverandøren Fjøsanger |

### Askøy/Sotra/Øygarden (18 stasjoner)

Regionsnøkkel: `askoy_sotra_oygarden`. Dekker Askøy, Sotra (Fjell/Sund) og Øygarden. Bounding box: lat 60.10–60.75, lon 4.70–5.35.

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 8       | 1088              | Uno-X 7-Eleven Kleppestø (Askøy) |
| 9       | 28393             | Haltbakk express Askøy |
| 13      | 66                | Circle K Ravnanger (Askøy) |
| 29      | 50                | Uno-X Hauglandshella (Askøy) |
| 31      | 56                | Circle K Automat Askøy |
| 44      | 4133              | Fromreide (Kjerrgarden, Askøy) |
| 152     | 2258              | Spar Steinsland (Sund) |
| 1275    | 372               | Esso Ågotnes (Sotra) |
| 1281    | 986               | YX Skogsvåg (Sotra) |
| 1283    | 6143              | Circle K Skogsvåg (Sotra) |
| 1285    | 919               | YX Rong (Øygarden) |
| 1287    | 1027              | Uno-X 7-Eleven Kolltveit (Sotra) |
| 1289    | 753               | Circle K Fjell (Sotra) |
| 1290    | 52                | Uno-X Straume (Sotra) |
| 1292    | 109               | St1 Straume (Sotra) |
| 2632    | 2212              | Circle K Automat Tjeldstø (Øygarden) |
| 1529665 | 28359             | Joker Bakkasund (Sund) |
| 1529682 | 4793              | Herdla (Askøy) |

**Ikke med (ingen Drivstoffappen-match):**
- 159 Klepsvik & Sønn (båtdrivstoff, ingen match innen 1 km)
- 1293 Møvik kai (kai/marina, ingen match)
- 1529786 Oljelevrandøren Rådal (feil match — nærmeste er Laguneparken 0.95 km)

**Ikke med (muligens marinedrivstoff):**
- 1294 Bensinstasjon/Bildøy Marina
- 1278 Brattholmen marina
- 1942 Steinsland kai
- 1295 Hjeltefjorden Drivstoff (matchet mot "Blommen Marine")

### Møre og Romsdal (102 stasjoner)

Regionsnøkkel: `more_romsdal`. Dekker Kristiansund, Molde/Romsdal og Ålesund/Sunnmøre.

#### Kristiansund (11 stasjoner)

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 4411    | 1432              | Best Bremsnes (automat) |
| 4430    | 2146              | Bunker Oil Kristiansund |
| 4422    | 2179              | Circle K Truck Sødalen |
| 4420    | 795               | Circle K Viadukten |
| 4410    | 519               | Esso Express Løkkemyra |
| 1529671 | 28407             | Haltbakk Express Frei |
| 4415    | 1244              | St1 Autokrysset |
| 4427    | 3258              | Uno-X Averøya |
| 4418    | 37                | Uno-X Kongens plass |
| 4426    | 2275              | Uno-X Løkkemyra |
| 4428    | 25521             | Uno-X Truck Frei |

#### Molde og Romsdal (30 stasjoner)

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 4417    | 2144              | Bunker Oil Batnfjorden |
| 1529634 | 28564             | Bunker Oil Bud |
| 9289    | 2143              | Bunker Oil Hjelset |
| 1263472 | 25242             | Bunker Oil Hollingen |
| 7249    | 2142              | Bunker Oil Malmefjorden |
| 7240    | 3180              | Bunker Oil Nesjestranda |
| 1529701 | 2140              | Bunker Oil Vestnes |
| 4419    | 3884              | Circle K Automat Eide |
| 7242    | 838               | Circle K Automat Julsundveien |
| 7235    | 611               | Circle K Molde |
| 5261    | 605               | Circle K Åndalsnes |
| 1529724 | 21034             | Driv Elnesvågen |
| 1181647 | 25520             | Driv Tornes |
| 1163468 | 5673              | Esso Energi Malmefjorden |
| 1529695 | 5677              | Esso Energi Årødalen |
| 4425    | 576               | Esso Express Elnesvågen |
| 5262    | 513               | Esso Øran |
| 5253    | 25244             | SnarKjøp Mittet |
| 7232    | 1242              | St1 Bolsønes |
| 7233    | 1386              | St1 Vestnes |
| 5260    | 1240              | St1 Åndalsnes |
| 7237    | 22888             | Uno-X Årødalen |
| 7234    | 129               | Uno-X 7-Eleven Reknes |
| 7236    | 39                | Uno-X Moldegård |
| 7247    | 867               | Uno-X Truck Straumen |
| 7248    | 28588             | Uno-X Truck Veøy Molde |
| 5256    | 28589             | Uno-X Truck Veøy Åndalsnes |
| 1529696 | 28649             | YX Joker Eidsbygda |
| 1529704 | 3168              | YX Joker Kleive |
| 4424    | 2247              | YX Skjelvik |

#### Ålesund og Sunnmøre (61 stasjoner)

| Vår ID  | Drivstoffappen-ID | Navn |
|---------|-------------------|------|
| 7148    | 3492              | Best Eidet |
| 3673    | 2129              | Bunker Oil Breivika |
| 3663    | 2132              | Bunker Oil Ekornes |
| 1529722 | 2123              | Bunker Oil Gjerdsvika |
| 1529742 | 2103              | Bunker Oil Godøy |
| 2606    | 2128              | Bunker Oil Hessa |
| 2607    | 28658             | Bunker Oil Lerstad |
| 2603    | 2126              | Bunker Oil Mauseidvågen |
| 2605    | 2102              | Bunker Oil Nørvevika |
| 1529730 | 2133              | Bunker Oil Skodje |
| 1504329 | 2134              | Bunker Oil Stette |
| 1529734 | 2121              | Bunker Oil Sæbø |
| 1529721 | 2124              | Bunker Oil Tjørvåg |
| 1381657 | 28520             | Bunker Oil Vartdal |
| 1529720 | 2136              | Bunker Oil Vatne |
| 1529702 | 2138              | Bunker Oil Vigra |
| 7160    | 2030              | Circle K Automat Brattvåg |
| 3629    | 3661              | Circle K Automat Flisnes |
| 3633    | 2251              | Circle K Automat Fosnavåg |
| 2593    | 748               | Circle K Automat Hatlane |
| 3645    | 744               | Circle K Automat Sykkylven |
| 2589    | 3659              | Circle K Automat Valderøy |
| 7157    | 710               | Circle K Digerneset |
| 2592    | 642               | Circle K Hareid |
| 3647    | 723               | Circle K Moa |
| 104     | 28237             | Circle K Truck Furene |
| 101     | 831               | Circle K Volda |
| 97      | 65                | Circle K Ørsta |
| 1529660 | 28296             | Coop Folkestad Dalsfjord Bensin |
| 102     | 25476             | Coop Lauvstad |
| 1529778 | 25449             | Drivstoff Åsevika Rovde |
| 3653    | 564               | Esso Spjelkavik |
| 2586    | 595               | Esso Vigra |
| 1529711 | 25419             | Knapphus Energi Rysteland |
| 2604    | 3262              | MH24 Dragsund |
| 3672    | 6660              | MH24 Fosnavåg |
| 3668    | 2965              | MH24 Haugsbygda |
| 99      | 1239              | St1 Express Hovdebygda |
| 2594    | 112               | St1 Ulsteinvik |
| 2590    | 1384              | St1 Vegsund |
| 106     | 1290              | St1 Volda |
| 98      | 104               | St1 Ørsta |
| 1520542 | 22526             | Storbilservice Emdal |
| 1529779 | 6095              | Tanken Ellingsøy |
| 1529744 | 3183              | Tanken Gursken |
| 1418045 | 28309             | Tanken Jensholmen Herøy |
| 2601    | 1092              | Uno-X 7-Eleven Tinghuset |
| 2597    | 42                | Uno-X Gåseid |
| 2602    | 25096             | Uno-X Langevåg |
| 2596    | 886               | Uno-X Truck Waagan |
| 2595    | 43                | Uno-X Ulsteinvik |
| 2599    | 41                | Uno-X Valderøya |
| 110     | 25008             | Uno-X Volda |
| 2600    | 1093              | Uno-X Ysteneset |
| 7177    | 3552              | Uno-X Vallekrysset |
| 103     | 44                | Uno-X Ørsta |
| 3630    | 992               | YX Fosnavåg |
| 109     | 5692              | YX Furene Volda |
| 3635    | 925               | YX Larsnes |
| 3654    | 902               | YX Sykkylven |
| 3634    | 942               | YX Søvik |

### Alver (18 stasjoner — Holsnøy, Radøy, Alver, Austrheim)

Bbox: lat 60.48–60.86, lon 4.85–5.48. Excl. Askøy (eget distrikt) og båt/marinastasjoner.

| Vår ID   | Drivstoffappen-ID | Navn |
|----------|-------------------|------|
| 1        | 433               | Esso Frekhaug (BASE) |
| 2        | 2190              | Circle K Automat Knarvik (BASE) |
| 11       | 28414             | Haltbakk Express Ostereidet |
| 15       | 3314              | Gabben |
| 25       | 2872              | YX Eikangervåg |
| 44       | 4133              | Fromreide |
| 45       | 1222              | St1 Isdalstø (BASE) |
| 46       | 3472              | St1 Eikanger |
| 47       | 2870              | Oljelevrandøren Hundvin |
| 84       | 2871              | Best Lindås |
| 85       | 920               | YX Hosteland |
| 88       | 922               | YX Manger |
| 89       | 987               | YX Mastrevik |
| 881639   | 9545              | Bunnpris Bøvågen |
| 1285     | 919               | YX Rong |
| 1390753  | 2850              | Oljleverandøren Sletta |
| 1529678  | 25253             | Polar |
| 9058     | 846               | Oljeleverandøren Hope |

**Ikke med (båt/marin):** 91 Feste brygge, 1295 Hjeltefjorden Drivstoff, 7269 Hordasmia Isdalstø, 1529642 Kilstraumen Brygge BÅT
**Ikke med (Askøy):** 1529682 Herdla
**Ikke med (Bergen/Åsane — allerede i base):** 4 St1 Haukås Nyborg, 16 St1 Marikollen, 26 Oljeleverandøren Hylkje, 32 Circle K Haukås
**Ikke med (Osterøy — eget distrikt):** 323716 Høyland Auto, 48 YX Osterøy, 10860 Bil og båtservice Hamre

### Osterøy (5 stasjoner)

Bbox: lat 60.46–60.67, lon 5.35–5.65

| Vår ID   | Drivstoffappen-ID | Navn |
|----------|-------------------|------|
| 23       | 2867              | Circle K Automat Lonevåg |
| 48       | 4038              | YX Osterøy |
| 51       | 4040              | Oljeleverandøren Fotlandsvåg |
| 10860    | 4676              | Bil og båtservice Hamre |
| 323716   | 2848              | Høyland Auto (Hosanger) |

Oppgave: $ARGUMENTS
