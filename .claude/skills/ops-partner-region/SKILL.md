---
name: ops-partner-region
description: Vis stasjoner i et partner1-distrikt (Haugalandet/Stavanger/Jæren/Bergen/Kristiansand) og kjør manuell sync for distriktet på Pi.
allowed-tools: Bash, Read
---

Vis stasjonsliste for et distrikt og kjør partner1-sync for det distriktet på Pi.

Argument: $ARGUMENTS (regionsnavn — Haugalandet, Stavanger, Jæren, Bergen eller Kristiansand)

## Bakgrunn

Alle stasjoner under er registrert i `STASJON_MAPPING` i `tools/drivstoffappen_sync.py` og synkes automatisk av cronjobben (`0 5-23 * * *`). Denne skillen brukes for manuell trigring eller for å se hvilke stasjoner som tilhører et distrikt.

Bbox-definisjoner (fra `routes_admin.py`):
- **Bergen**: lat 60.10–60.88, lon 4.70–5.75
- **Haugalandet**: lat 59.08–59.65, lon 5.05–5.60
- **Stavanger**: lat 58.75–59.15, lon 5.40–6.05
- **Jæren**: lat 58.60–58.82, lon 5.35–5.72

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

## Manuell sync på Pi

Hvis argument inneholder et prosenttall (f.eks. "Stavanger 20%"), parse ut prosenten og kjør et wrapper-script som patcher `STASJON_MAPPING` til bare region-stasjoner og kaller `kjør(prosent=N)`.

Eksempel — Stavanger 20%:

```bash
cat > /tmp/region_sync.py << 'EOF'
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/tools')
import drivstoffappen_sync as s

# Lim inn riktig stasjonsliste fra tabellen over
REGION = { <vaar_id>: <drivstoffappen_id>, ... }

s.STASJON_MAPPING = REGION
s.kjør(prosent=20)  # bytt prosent etter argument
EOF
scp /tmp/region_sync.py raspberrypi:/tmp/region_sync.py
ssh raspberrypi "docker cp /tmp/region_sync.py drivstoffpriser-drivstoffpriser-1:/tmp/region_sync.py && docker exec drivstoffpriser-drivstoffpriser-1 python3 /tmp/region_sync.py"
```

Uten prosent — full sync for regionen:

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 /app/tools/drivstoffappen_sync.py"
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

Oppgave: $ARGUMENTS
