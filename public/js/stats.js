const OPPDATER_INTERVAL_MS = 60_000;
const MIN_MANUELL_INTERVAL_MS = 15_000;

let sistLastet = 0;
let laster = false;
let autoOppdateringStartet = false;

let _kjedeData = [];
let _kjedeSortKol = 'snitt_diesel';
let _kjedeSortAsc = true;

function visKjedeSnitt(kjedeData) {
    _kjedeData = kjedeData || [];
    _kjedeSortKol = 'snitt_diesel';
    _kjedeSortAsc = true;
    _byggKjedeTabell();
}

function _byggKjedeTabell() {
    const el = document.getElementById('stat-kjede-snitt');
    if (!el) return;
    if (!_kjedeData.length) {
        el.innerHTML = '<div class="stat-pris-ingen">Ingen data</div>';
        return;
    }

    const kolonner = [
        { tekst: 'Kjede',    felt: 'kjede',                    num: false },
        { tekst: '95 oktan', felt: 'snitt_bensin',              num: true  },
        { tekst: 'Diesel',   felt: 'snitt_diesel',              num: true  },
    ];

    // Sorter data
    const sortert = [..._kjedeData].sort((a, b) => {
        const av = a[_kjedeSortKol] ?? (typeof a[_kjedeSortKol] === 'string' ? '' : Infinity);
        const bv = b[_kjedeSortKol] ?? (typeof b[_kjedeSortKol] === 'string' ? '' : Infinity);
        if (av === bv) return 0;
        const cmp = av < bv ? -1 : 1;
        return _kjedeSortAsc ? cmp : -cmp;
    });

    // Finn min-verdi per numerisk kolonne for å fremheve billigste
    const minVerdier = {};
    kolonner.filter(k => k.num && k.felt !== 'antall_stasjoner').forEach(k => {
        const verdier = _kjedeData.map(r => r[k.felt]).filter(v => v);
        if (verdier.length) minVerdier[k.felt] = Math.min(...verdier);
    });

    const tabell = document.createElement('table');
    tabell.className = 'kjede-snitt-tabell';

    // Header
    const thead = tabell.createTHead();
    const hRad = thead.insertRow();
    kolonner.forEach(kol => {
        const th = document.createElement('th');
        const aktiv = _kjedeSortKol === kol.felt;
        th.innerHTML = `<button class="kjede-sort-btn${aktiv ? ' aktiv' : ''}" data-felt="${kol.felt}">${kol.tekst}<span class="kjede-sort-pil">${aktiv ? (_kjedeSortAsc ? '↑' : '↓') : ''}</span></button>`;
        hRad.appendChild(th);
    });

    // Body
    const tbody = tabell.createTBody();
    sortert.forEach(k => {
        const rad = tbody.insertRow();
        kolonner.forEach(kol => {
            const td = rad.insertCell();
            const v = k[kol.felt];
            if (kol.felt === 'kjede') {
                td.className = 'kjede-snitt-navn';
                td.textContent = v || '–';
            } else if (kol.num && kol.felt !== 'antall_stasjoner') {
                td.textContent = v ? v.toFixed(2) : '–';
                if (v && minVerdier[kol.felt] === v) td.className = 'kjede-snitt-billigst';
            } else {
                td.textContent = v ?? '–';
            }
        });
    });

    el.innerHTML = '';
    el.appendChild(tabell);

    // Sorter-klikk
    el.querySelectorAll('.kjede-sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const felt = btn.dataset.felt;
            if (_kjedeSortKol === felt) {
                _kjedeSortAsc = !_kjedeSortAsc;
            } else {
                _kjedeSortKol = felt;
                _kjedeSortAsc = felt !== 'kjede'; // tall: billigst først; tekst: A-Z
            }
            _byggKjedeTabell();
        });
    });
}

function statistikkErSynlig() {
    const view = document.getElementById('view-statistikk');
    return !!view && view.style.display !== 'none' && !document.hidden;
}

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

const medaljer = ['🥇', '🥈', '🥉'];

function lagRadEl(rad, globalIdx) {
    const div = document.createElement('div');
    div.className = 'stat-toppliste-rad' + (rad.er_meg ? ' stat-toppliste-meg' : '');
    const plassEl = document.createElement('span');
    plassEl.className = globalIdx < 3 ? 'stat-toppliste-medalje' : 'stat-toppliste-nr';
    plassEl.textContent = globalIdx < 3 ? medaljer[globalIdx] : `${globalIdx + 1}.`;
    const navnEl = document.createElement('span');
    navnEl.className = 'stat-toppliste-navn' + (!rad.kallenavn && !rad.er_meg ? ' stat-toppliste-anonym' : '');
    navnEl.textContent = rad.kallenavn || (rad.er_meg ? 'Deg' : 'Anonym bidragsyter');
    const antallEl = document.createElement('span');
    antallEl.className = 'stat-toppliste-antall';
    antallEl.textContent = rad.antall;
    div.append(plassEl, navnEl, antallEl);
    return div;
}

function byggRadliste(container, liste, synligeRader, minPlass) {
    const synlig = liste.slice(0, synligeRader);
    const skjult = liste.slice(synligeRader);

    synlig.forEach((rad, i) => container.appendChild(lagRadEl(rad, i)));

    if (skjult.length) {
        const merDiv = document.createElement('div');
        merDiv.className = 'stat-toppliste-mer';
        const knapp = document.createElement('button');
        knapp.className = 'stat-toppliste-utvid';
        knapp.textContent = `··· vis topp ${liste.length}`;
        knapp.addEventListener('click', () => {
            merDiv.remove();
            skjult.forEach((rad, i) => container.appendChild(lagRadEl(rad, synligeRader + i)));
            if (minPlass) container.appendChild(lagMinPlassEl(minPlass));
        });
        merDiv.appendChild(knapp);
        container.appendChild(merDiv);
    } else if (minPlass) {
        container.appendChild(lagMinPlassEl(minPlass));
    }
}

function lagMinPlassEl(minPlass) {
    const div = document.createElement('div');
    div.className = 'stat-toppliste-rad stat-toppliste-meg stat-toppliste-utenfor';
    div.innerHTML = `<span class="stat-toppliste-nr">${minPlass.plass}.</span><span class="stat-toppliste-navn">Deg</span><span class="stat-toppliste-antall">${minPlass.antall}</span>`;
    return div;
}

function visToppliste(data) {
    const el = document.getElementById('stat-toppliste');
    const liste = Array.isArray(data) ? data : (data.liste || []);
    const listeUke = Array.isArray(data) ? [] : (data.liste_uke || []);
    const minPlass = Array.isArray(data) ? null : data.min_plass;

    if (!liste.length && !listeUke.length) {
        el.innerHTML = '<div class="stat-toppliste-tom">Ingen registreringer ennå</div>';
        injiserBidragPromo();
        return;
    }

    el.innerHTML = '';

    if (listeUke.length) {
        const seksjon = document.createElement('div');
        seksjon.className = 'stat-toppliste-seksjon';
        const tittel = document.createElement('div');
        tittel.className = 'stat-toppliste-seksjon-tittel';
        tittel.textContent = 'Denne uken';
        seksjon.appendChild(tittel);
        byggRadliste(seksjon, listeUke, 5, null);
        el.appendChild(seksjon);
    }

    if (liste.length) {
        const seksjon = document.createElement('div');
        seksjon.className = 'stat-toppliste-seksjon';
        const tittel = document.createElement('div');
        tittel.className = 'stat-toppliste-seksjon-tittel';
        tittel.textContent = 'Totalt';
        seksjon.appendChild(tittel);
        byggRadliste(seksjon, liste, 10, minPlass);
        el.appendChild(seksjon);
    }

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

function startAutoOppdatering() {
    if (autoOppdateringStartet) return;
    autoOppdateringStartet = true;

    setInterval(() => {
        if (statistikkErSynlig()) lastStatistikk({ force: true });
    }, OPPDATER_INTERVAL_MS);

    document.addEventListener('visibilitychange', () => {
        if (statistikkErSynlig()) lastStatistikk({ force: true });
    });
}

export async function lastStatistikk({ force = false } = {}) {
    startAutoOppdatering();

    const naa = Date.now();
    if (laster) return;
    if (!force && sistLastet && naa - sistLastet < MIN_MANUELL_INTERVAL_MS) return;

    laster = true;
    try {
        const [respStat, respTopp, respKjede] = await Promise.all([
            fetch('/api/statistikk', { cache: 'no-store' }),
            fetch('/api/toppliste', { cache: 'no-store' }),
            fetch('/api/kjede-snitt', { cache: 'no-store' }),
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

        const kjedeData = respKjede.ok ? await respKjede.json() : [];
        visKjedeSnitt(kjedeData);

        sistLastet = Date.now();
    } catch (e) {
        console.warn('Statistikk-feil:', e);
    } finally {
        laster = false;
    }
}

export function resetStatistikk() {
    sistLastet = 0;
}
