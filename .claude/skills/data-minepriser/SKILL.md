---
name: minepriser
description: Vis søylediagram over Kjetils egne daglige prisinnlegginger og unike stasjoner siste N dager (alle 3 kontoer) — drivstoffprisene.no
allowed-tools: Bash
---

Generer og vis søylediagram med to paneler over Kjetils egne bidrag per dag (kjetil@vikebo.com, bensin@vikebo.com og bensin1@vikebo.com, bruker-id 5, 2422 og 3998): prisinnlegginger øverst, unike stasjoner nederst. Dagens ufullstendige dag vises i grå med stjerne.

Argumenter (fra `$ARGS`):
- Tallet alene angir antall dager, f.eks. `/minepriser 21` → 21 dager (standard 14)

## Steg 1: Hent data fra Pi

Bestem `DAGER` (standard 14) ut fra `$ARGS`.

```bash
ssh raspberrypi "docker exec drivstoffpriser-drivstoffpriser-1 python3 -c \"
import sqlite3
from datetime import datetime
DB = '/app/data/drivstoff.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('''
    SELECT DATE(p.tidspunkt) as dag,
           COUNT(*) as antall_priser,
           COUNT(DISTINCT p.stasjon_id) as unike_stasjoner
    FROM priser p
    LEFT JOIN brukere b ON b.id = p.bruker_id
    WHERE p.tidspunkt >= DATE('now', '-DAGER days')
      AND (b.brukernavn IN ('kjetil@vikebo.com', 'bensin@vikebo.com', 'bensin1@vikebo.com') OR p.bruker_id IS NULL)
    GROUP BY dag ORDER BY dag
''')
for r in cur.fetchall(): print(r[0], r[1], r[2])
conn.close()
print('NÅ:', datetime.now().strftime('%H:%M'))
\""
```

## Steg 2: Lag diagram lokalt

Bygg `data = [("YYYY-MM-DD", priser, stasjoner), ...]` fra SSH-output (ignorer "NÅ:"-linjen).
Dagens dato er ufullstendig — vis den i grå med stjerne (*).

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# data = [("YYYY-MM-DD", priser, stasjoner), ...]
# i_dag = "YYYY-MM-DD"  # dagens dato

datoer    = [datetime.strptime(r[0], "%Y-%m-%d") for r in data]
priser    = [r[1] for r in data]
stasjoner = [r[2] for r in data]

fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, constrained_layout=True)
fig.patch.set_facecolor("#f5f7fa")

datasets = [
    (axes[0], priser,    "#9C27B0", "#6A1B9A", "Prisinnlegginger per dag"),
    (axes[1], stasjoner, "#FF7043", "#BF360C", "Unike stasjoner oppdatert per dag"),
]

for ax, verdier, farge, tekstfarge, ylabel in datasets:
    ax.set_facecolor("#ffffff")
    farger = ["#cccccc" if datoer[i].strftime("%Y-%m-%d") == i_dag else farge for i in range(len(datoer))]
    bars = ax.bar(datoer, verdier, color=farger, width=0.7, zorder=3)
    for bar, val, d in zip(bars, verdier, datoer):
        label = f"{val}*" if d.strftime("%Y-%m-%d") == i_dag else str(val)
        farge_tekst = "#999999" if d.strftime("%Y-%m-%d") == i_dag else tekstfarge
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(verdier)*0.012,
                label, ha="center", va="bottom", fontsize=9, fontweight="bold", color=farge_tekst)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_ylim(0, max(verdier) * 1.18)
    ax.grid(True, alpha=0.3, linestyle="--", axis="y")
    ax.spines[['top','right']].set_visible(False)

axes[0].xaxis.set_major_locator(mdates.DayLocator(interval=1))
axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
plt.setp(axes[1].xaxis.get_majorticklabels(), fontsize=9, rotation=45, ha="right")

fra = datoer[0].strftime("%d.%m")
# Siste fullstendige dag
siste_full = [d for d in datoer if d.strftime("%Y-%m-%d") != i_dag]
til = siste_full[-1].strftime("%d.%m.%Y") if siste_full else datoer[-1].strftime("%d.%m.%Y")
klokkeslett = NÅ  # fra SSH-output
fig.suptitle(f"Kjetils bidrag per dag\n({fra}–{til}, * = pågående dag kl. {klokkeslett})",
             fontsize=13, fontweight="bold")

from datetime import datetime as _dt
utfil = f"/Users/kjetil/notater/drivstoffprisene/minepriser_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
fig.savefig(utfil, dpi=150, bbox_inches="tight")
print(f"Lagret: {utfil}")
```

```bash
python3 /tmp/minepriser.py
```

## Steg 3: Presenter

Vis grafen med Read-verktøyet på filstien skrevet ut av scriptet, og legg til kort kommentar:
- Toppdag for priser og stasjoner
- Snitt for perioden (priser og stasjoner)
- Trend: siste uke vs uken før
