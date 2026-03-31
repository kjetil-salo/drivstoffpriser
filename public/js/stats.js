let lastet = false;

function formaterTid(tidspunkt) {
    if (!tidspunkt) return '';
    const d = new Date(tidspunkt + 'Z');
    const now = new Date();
    const diff = now - d;
    const timer = Math.floor(diff / 3600000);
    const min = Math.floor(diff / 60000);
    if (min < 60) return `${min} min siden`;
    return `${timer} t siden`;
}

function visPrisKort(elementId, data) {
    const el = document.getElementById(elementId);
    if (!data) {
        el.innerHTML = `<div class="stat-pris-ingen">Ingen data</div>`;
        return;
    }
    el.innerHTML = `
        <div class="stat-pris-verdi">${data.pris.toFixed(2)} kr</div>
        <div class="stat-pris-stasjon">${data.stasjon}</div>
        <div class="stat-pris-tid">${formaterTid(data.tidspunkt)}</div>
    `;
    el.style.cursor = 'pointer';
    el.title = `Vis ${data.stasjon} på kartet`;
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    const naviger = () => document.dispatchEvent(new CustomEvent('naviger-til-stasjon', {
        detail: { id: data.stasjon_id, lat: data.lat, lon: data.lon, navn: data.stasjon }
    }));
    el.onclick = naviger;
    el.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); naviger(); } };
}

function visToppliste(liste) {
    const el = document.getElementById('stat-toppliste');
    if (!liste || liste.length === 0) {
        el.innerHTML = '<div class="stat-toppliste-tom">Ingen registreringer ennå</div>';
        return;
    }
    const medaljer = ['🥇', '🥈', '🥉'];
    const rader = liste.map((rad, i) => {
        const plass = i < 3 ? `<span class="stat-toppliste-medalje">${medaljer[i]}</span>` : `<span class="stat-toppliste-nr">${i + 1}.</span>`;
        const navn = rad.kallenavn
            ? `<span class="stat-toppliste-navn">${rad.kallenavn}</span>`
            : `<span class="stat-toppliste-navn stat-toppliste-anonym">Anonym bidragsyter</span>`;
        return `<div class="stat-toppliste-rad">${plass}${navn}<span class="stat-toppliste-antall">${rad.antall}</span></div>`;
    });
    el.innerHTML = rader.join('');
}

export async function lastStatistikk() {
    if (lastet) return;
    try {
        const [respStat, respTopp] = await Promise.all([
            fetch('/api/statistikk'),
            fetch('/api/toppliste')
        ]);
        if (!respStat.ok) return;
        const data = await respStat.json();

        document.getElementById('stat-antall').textContent = data.antall_oppdateringer_24t;

        visPrisKort('stat-billigst-bensin', data.billigst.bensin);
        visPrisKort('stat-billigst-bensin98', data.billigst.bensin98);
        visPrisKort('stat-billigst-diesel', data.billigst.diesel);
        visPrisKort('stat-billigst-diesel_avgiftsfri', data.billigst.diesel_avgiftsfri);

        visPrisKort('stat-dyrest-bensin', data.dyrest.bensin);
        visPrisKort('stat-dyrest-bensin98', data.dyrest.bensin98);
        visPrisKort('stat-dyrest-diesel', data.dyrest.diesel);
        visPrisKort('stat-dyrest-diesel_avgiftsfri', data.dyrest.diesel_avgiftsfri);

        const toppliste = respTopp.ok ? await respTopp.json() : [];
        visToppliste(toppliste);

        lastet = true;
    } catch (e) {
        console.warn('Statistikk-feil:', e);
    }
}

export function resetStatistikk() {
    lastet = false;
}
