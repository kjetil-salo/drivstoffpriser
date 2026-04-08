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
    if (!el) return;
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

function visToppliste(data) {
    const el = document.getElementById('stat-toppliste');
    const liste = Array.isArray(data) ? data : (data.liste || []);
    const minPlass = Array.isArray(data) ? null : data.min_plass;
    if (!liste || liste.length === 0) {
        el.innerHTML = '<div class="stat-toppliste-tom">Ingen registreringer ennå</div>';
        return;
    }
    const medaljer = ['🥇', '🥈', '🥉'];
    const rader = liste.map((rad, i) => {
        const plass = i < 3 ? `<span class="stat-toppliste-medalje">${medaljer[i]}</span>` : `<span class="stat-toppliste-nr">${i + 1}.</span>`;
        const navn = rad.kallenavn
            ? `<span class="stat-toppliste-navn">${rad.kallenavn}</span>`
            : rad.er_meg
                ? `<span class="stat-toppliste-navn">Deg</span>`
                : `<span class="stat-toppliste-navn stat-toppliste-anonym">Anonym bidragsyter</span>`;
        const megKlasse = rad.er_meg ? ' stat-toppliste-meg' : '';
        return `<div class="stat-toppliste-rad${megKlasse}">${plass}${navn}<span class="stat-toppliste-antall">${rad.antall}</span></div>`;
    });
    if (minPlass) {
        rader.push(`<div class="stat-toppliste-rad stat-toppliste-meg stat-toppliste-utenfor"><span class="stat-toppliste-nr">${minPlass.plass}.</span><span class="stat-toppliste-navn">Deg</span><span class="stat-toppliste-antall">${minPlass.antall}</span></div>`);
    }
    el.innerHTML = rader.join('');
    injiserBidragPromo();
}

function injiserBidragPromo() {
    if (document.getElementById('bidrag-promo')) return;
    const promo = document.createElement('div');
    promo.id = 'bidrag-promo';
    promo.innerHTML = `
      <a href="/bidrag" class="bidrag-promo-lenke">Oppdater priser effektivt →</a>
      <label class="bidrag-promo-snarvei">
        <input type="checkbox" id="bidrag-snarvei-cb">
        <span>Vis snarvei øverst</span>
      </label>
    `;
    document.getElementById('stat-toppliste').after(promo);

    const cb = promo.querySelector('#bidrag-snarvei-cb');
    cb.checked = localStorage.getItem('bidrag_snarvei') === '1';
    cb.addEventListener('change', () => {
        localStorage.setItem('bidrag_snarvei', cb.checked ? '1' : '0');
        const btn = document.getElementById('bidrag-btn');
        if (btn) btn.hidden = !cb.checked;
    });
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
