---
name: bidragsgraf
description: Vis søylediagram over daglige prisinnlegginger eller unike stasjoner siste N dager (standard 14) uten Kjetils egne kontoer — drivstoffprisene.no
allowed-tools: Bash
---

Generer og vis søylediagram over aktivitet per dag fra andre brukere (ekskluderer alltid kjetil@vikebo.com / bensin@vikebo.com / bensin1@vikebo.com, bruker-id 5, 2422 og 3998).

Argumenter (fra `$ARGS`):
- Tallet alene angir antall dager, f.eks. `/bidragsgraf 21` → 21 dager (standard 14)
- `stasjoner` eller `--stasjoner` → vis unike stasjoner per dag i stedet for innlegginger
- `--sammenlign` → vis Kjetil vs. andre side om side (grouped bar chart)
- Kombinasjon støttes: `/bidragsgraf 21 stasjoner --sammenlign`

## Steg 1: Hent data fra Pi

Bestem `DAGER` (standard 14), `MODUS` (`innlegginger` eller `stasjoner`) og `SAMMENLIGN` (true/false) ut fra `$ARGS`.

### Normalmodus (uten --sammenlign)

For **innlegginger** (`COUNT(*)`):
```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 -c \"
import sqlite3
from datetime import datetime
DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('''
    SELECT DATE(p.tidspunkt) as dag, COUNT(*) as antall
    FROM priser p
    LEFT JOIN brukere b ON b.id = p.bruker_id
    WHERE p.tidspunkt >= DATE('now', '-DAGER days')
      AND (b.brukernavn NOT IN ('kjetil@vikebo.com', 'bensin@vikebo.com', 'bensin1@vikebo.com') OR b.brukernavn IS NULL)
    GROUP BY dag ORDER BY dag
''')
for r in cur.fetchall(): print(r[0], r[1])
conn.close()
print('NÅ:', datetime.now().strftime('%H:%M'))
\""
```

For **stasjoner** (`COUNT(DISTINCT stasjon_id)`):
```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 -c \"
import sqlite3
from datetime import datetime
DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('''
    SELECT DATE(p.tidspunkt) as dag, COUNT(DISTINCT p.stasjon_id) as antall
    FROM priser p
    LEFT JOIN brukere b ON b.id = p.bruker_id
    WHERE p.tidspunkt >= DATE('now', '-DAGER days')
      AND (b.brukernavn NOT IN ('kjetil@vikebo.com', 'bensin@vikebo.com', 'bensin1@vikebo.com') OR b.brukernavn IS NULL)
    GROUP BY dag ORDER BY dag
''')
for r in cur.fetchall(): print(r[0], r[1])
conn.close()
print('NÅ:', datetime.now().strftime('%H:%M'))
\""
```

### Sammenlignings-modus (--sammenlign)

Hent begge grupper i én SSH-kommando. Bruk `AND b.brukernavn IS NOT NULL` for andre (null-priser tilhører Kjetil):

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 -c \"
import sqlite3
DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
FELT = 'COUNT(*)' # eller 'COUNT(DISTINCT p.stasjon_id)' for stasjoner
cur.execute('''
    SELECT DATE(p.tidspunkt) as dag, FELT as antall
    FROM priser p
    LEFT JOIN brukere b ON b.id = p.bruker_id
    WHERE p.tidspunkt >= DATE('now', '-DAGER days')
      AND b.brukernavn NOT IN ('kjetil@vikebo.com', 'bensin@vikebo.com', 'bensin1@vikebo.com')
      AND b.brukernavn IS NOT NULL
    GROUP BY dag ORDER BY dag
''')
print('ANDRE:')
for r in cur.fetchall(): print(r[0], r[1])
cur.execute('''
    SELECT DATE(p.tidspunkt) as dag, FELT as antall
    FROM priser p
    LEFT JOIN brukere b ON b.id = p.bruker_id
    WHERE p.tidspunkt >= DATE('now', '-DAGER days')
      AND (b.brukernavn IN ('kjetil@vikebo.com', 'bensin@vikebo.com', 'bensin1@vikebo.com') OR p.bruker_id IS NULL)
    GROUP BY dag ORDER BY dag
''')
print('KJETIL:')
for r in cur.fetchall(): print(r[0], r[1])
conn.close()
\""
```

Parse output: linjer etter `ANDRE:` er andre-data, linjer etter `KJETIL:` er Kjetil-data.

## Steg 2: Lag diagram lokalt

Skriv Python-kode til `/tmp/bidragsgraf.py` og kjør den.

### Normalmodus

Bygg `data = [("YYYY-MM-DD", antall), ...]` fra SSH-output (ignorer "NÅ:"-linjen).

Bruk grønn (`#43A047`) for stasjoner, blå (`#2196F3`) for innlegginger. Rosa (`#e84393`) for 1. april 2026.

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# data = [...]  og  MODUS = "innlegginger" eller "stasjoner"

datoer = [datetime.strptime(d, "%Y-%m-%d") for d, _ in data]
antall = [v for _, v in data]
basefarge = "#43A047" if MODUS == "stasjoner" else "#2196F3"
farger = ["#e84393" if d.strftime("%Y-%m-%d") == "2026-04-01" else basefarge for d in datoer]

fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
fig.patch.set_facecolor("#f5f7fa")
ax.set_facecolor("#ffffff")

bars = ax.bar(datoer, antall, color=farger, width=0.7, zorder=3)
for bar, val in zip(bars, antall):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 4,
            str(val), ha="center", va="bottom", fontsize=9, fontweight="bold", color="#333333")

avgift_dato = datetime(2026, 4, 1)
if datoer[0] <= avgift_dato <= datoer[-1]:
    ax.axvline(avgift_dato, color="#e84393", linewidth=1.5, linestyle="--", alpha=0.5)
    ax.text(avgift_dato, max(antall) * 0.97, " Avgiftskutt", color="#e84393", fontsize=9, va="top")

ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
plt.setp(ax.xaxis.get_majorticklabels(), fontsize=9, rotation=45, ha="right")

fra = datoer[0].strftime("%d.%m")
til = datoer[-1].strftime("%d.%m.%Y")
ylabel = "Unike stasjoner oppdatert per dag" if MODUS == "stasjoner" else "Prisinnlegginger per dag"
tittel = f"{'Unike stasjoner med prisoppdatering' if MODUS == 'stasjoner' else 'Prisinnlegginger'} per dag — uten Kjetils kontoer\n({fra}–{til})"
ax.set_ylabel(ylabel, fontsize=11)
ax.set_title(tittel, fontsize=13, fontweight="bold", pad=12)
ax.grid(True, alpha=0.3, linestyle="--", axis="y")
ax.set_ylim(0, max(antall) * 1.15)

from datetime import datetime as _dt
utfil = f"/Users/kjetil/notater/drivstoffprisene/bidragsgraf_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
fig.savefig(utfil, dpi=150, bbox_inches="tight")
print(f"Lagret: {utfil}")
```

### Sammenlignings-modus (--sammenlign)

Grouped bar chart med to søyler per dag. Blå/grønn for andre, oransje (`#FF7043`) for Kjetil.

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

# andre = [("YYYY-MM-DD", antall), ...]
# kjetil = [("YYYY-MM-DD", antall), ...]
# MODUS = "innlegginger" eller "stasjoner"

datoer = [datetime.strptime(d, "%Y-%m-%d") for d, _ in andre]
antall_andre = [v for _, v in andre]
antall_kjetil = [v for _, v in kjetil]

x = np.arange(len(datoer))
width = 0.42

farge_andre = "#43A047" if MODUS == "stasjoner" else "#2196F3"
farge_kjetil = "#FF7043"
tekstfarge_andre = "#1B5E20" if MODUS == "stasjoner" else "#1565C0"

fig, ax = plt.subplots(figsize=(16, 6), constrained_layout=True)
fig.patch.set_facecolor("#f5f7fa")
ax.set_facecolor("#ffffff")

bars_andre = ax.bar(x - width/2, antall_andre, width, color=farge_andre, label="Andre brukere", zorder=3)
bars_kjetil = ax.bar(x + width/2, antall_kjetil, width, color=farge_kjetil, label="Kjetil (inkl. null)", zorder=3)

for bar, val in zip(bars_andre, antall_andre):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
            str(val), ha="center", va="bottom", fontsize=7.5, fontweight="bold", color=tekstfarge_andre)

for bar, val in zip(bars_kjetil, antall_kjetil):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
            str(val), ha="center", va="bottom", fontsize=7.5, fontweight="bold", color="#BF360C")

ax.set_xticks(x)
ax.set_xticklabels([d.strftime("%d.%m") for d in datoer], fontsize=9, rotation=45, ha="right")

fra = datoer[0].strftime("%d.%m")
til = datoer[-1].strftime("%d.%m.%Y")
ylabel = "Unike stasjoner oppdatert per dag" if MODUS == "stasjoner" else "Prisinnlegginger per dag"
tittel_type = "Unike stasjoner med prisoppdatering" if MODUS == "stasjoner" else "Prisinnlegginger"
ax.set_ylabel(ylabel, fontsize=11)
ax.set_title(f"{tittel_type} per dag — Kjetil vs. andre\n({fra}–{til})", fontsize=13, fontweight="bold", pad=12)
ax.grid(True, alpha=0.3, linestyle="--", axis="y")
ax.set_ylim(0, max(max(antall_andre), max(antall_kjetil)) * 1.18)
ax.legend(fontsize=10)

from datetime import datetime as _dt
utfil = f"/Users/kjetil/notater/drivstoffprisene/bidragsgraf_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
fig.savefig(utfil, dpi=150, bbox_inches="tight")
print(f"Lagret: {utfil}")
```

```bash
python3 /tmp/bidragsgraf.py
```

## Steg 3: Presenter

Vis grafen med Read-verktøyet på filstien som ble skrevet ut av scriptet (ikke hardkod `/tmp/bidragsgraf.png`), og legg til kort kommentar:
- Toppdag og antall
- Trend: siste uke vs uken før
- Ved --sammenlign: Kjetils andel av total (%) på toppdag og snitt
- Dagens anslag hvis dagen ikke er over (sammenlign med tilsvarende tidspunkt på de 3 siste toppdagene)
