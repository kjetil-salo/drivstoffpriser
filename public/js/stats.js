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
        el.innerHTML = `
            <div class="stat-pris-type">${el.querySelector('.stat-pris-type')?.textContent || ''}</div>
            <div class="stat-pris-ingen">Ingen priser siste 24 timer</div>
        `;
        return;
    }
    const typeLabel = el.querySelector('.stat-pris-type')?.textContent || '';
    el.innerHTML = `
        <div class="stat-pris-type">${typeLabel}</div>
        <div class="stat-pris-verdi">${data.pris.toFixed(2)} kr</div>
        <div class="stat-pris-stasjon">${data.stasjon}</div>
        <div class="stat-pris-tid">${formaterTid(data.tidspunkt)}</div>
    `;
}

export async function lastStatistikk() {
    if (lastet) return;
    try {
        const resp = await fetch('/api/statistikk');
        if (!resp.ok) return;
        const data = await resp.json();

        document.getElementById('stat-antall').textContent = data.antall_oppdateringer_24t;

        visPrisKort('stat-billigst-bensin', data.billigst.bensin);
        visPrisKort('stat-billigst-bensin98', data.billigst.bensin98);
        visPrisKort('stat-billigst-diesel', data.billigst.diesel);

        visPrisKort('stat-dyrest-bensin', data.dyrest.bensin);
        visPrisKort('stat-dyrest-bensin98', data.dyrest.bensin98);
        visPrisKort('stat-dyrest-diesel', data.dyrest.diesel);

        lastet = true;
    } catch (e) {
        console.warn('Statistikk-feil:', e);
    }
}

export function resetStatistikk() {
    lastet = false;
}
