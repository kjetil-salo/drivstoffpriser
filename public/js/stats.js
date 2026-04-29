const OPPDATER_INTERVAL_MS = 60_000;
const MIN_MANUELL_INTERVAL_MS = 15_000;

let sistLastet = 0;
let laster = false;
let autoOppdateringStartet = false;

let _kjedeData = [];
let _kjedeSortKol = 'snitt_diesel';
let _kjedeSortAsc = true;

// Radius-filter
let _radiusModus = false;      // false = Norge, true = nærhet
let _gpsPos = null;            // { lat, lon } — caches siste kjente posisjon
let _henterGps = false;
let _toggleInitiert = false;

function _settGpsStatus(tekst) {
    const el = document.getElementById('stat-gps-status');
    if (el) el.textContent = tekst;
}

function _hentGps() {
    return new Promise((resolve, reject) => {
        if (_gpsPos) { resolve(_gpsPos); return; }
        if (!navigator.geolocation) { reject('Geolokasjon støttes ikke'); return; }
        _henterGps = true;
        _settGpsStatus('Henter posisjon …');
        navigator.geolocation.getCurrentPosition(
            pos => {
                _henterGps = false;
                _gpsPos = { lat: pos.coords.latitude, lon: pos.coords.longitude };
                _settGpsStatus('');
                resolve(_gpsPos);
            },
            () => {
                _henterGps = false;
                _settGpsStatus('Ingen posisjon');
                reject('Ingen posisjon');
            },
            { timeout: 10000, maximumAge: 120000 }
        );
    });
}

function _initOmradeToggle() {
    if (_toggleInitiert) return;
    const knappNorge = document.getElementById('stat-toggle-norge');
    const knappNaerhet = document.getElementById('stat-toggle-naerhet');
    const radiusVelger = document.getElementById('stat-radius-velger');
    const radiusSelect = document.getElementById('stat-radius-select');
    if (!knappNorge || !knappNaerhet) return;
    _toggleInitiert = true;

    knappNorge.addEventListener('click', () => {
        _radiusModus = false;
        _gpsPos = null;
        knappNorge.classList.add('aktiv');
        knappNorge.setAttribute('aria-pressed', 'true');
        knappNaerhet.classList.remove('aktiv');
        knappNaerhet.setAttribute('aria-pressed', 'false');
        if (radiusVelger) radiusVelger.hidden = true;
        _settGpsStatus('');
        sistLastet = 0;
        lastStatistikk({ force: true });
    });

    knappNaerhet.addEventListener('click', async () => {
        _radiusModus = true;
        knappNaerhet.classList.add('aktiv');
        knappNaerhet.setAttribute('aria-pressed', 'true');
        knappNorge.classList.remove('aktiv');
        knappNorge.setAttribute('aria-pressed', 'false');
        if (radiusVelger) radiusVelger.hidden = false;
        sistLastet = 0;
        try {
            await _hentGps();
        } catch (_) { /* status satt i _hentGps */ }
        lastStatistikk({ force: true });
    });

    if (radiusSelect) {
        radiusSelect.addEventListener('change', () => {
            sistLastet = 0;
            lastStatistikk({ force: true });
        });
    }
}

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

function visBrukerePerDag(data) {
    const canvas = document.getElementById('stat-brukere-canvas');
    if (!canvas || !data.length) return;

    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth - 16; // padding
    const H = 180;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const PAD_TOP = 24;
    const PAD_BOTTOM = 36;
    const PAD_LEFT = 8;
    const PAD_RIGHT = 8;
    const chartW = W - PAD_LEFT - PAD_RIGHT;
    const chartH = H - PAD_TOP - PAD_BOTTOM;

    const verdier = data.map(d => d.antall);
    const maks = Math.max(...verdier, 1);
    const n = data.length;
    const barW = chartW / n * 0.75;
    const gap = chartW / n;

    // Bakgrunn
    ctx.fillStyle = getComputedStyle(document.documentElement)
        .getPropertyValue('--color-card-bg').trim() || '#ffffff';
    ctx.fillRect(0, 0, W, H);

    // Rutenett
    ctx.strokeStyle = 'rgba(148,163,184,0.2)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = PAD_TOP + chartH * (1 - i / 4);
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(W - PAD_RIGHT, y);
        ctx.stroke();
    }

    // Søyler og etiketter
    ctx.fillStyle = '#FF9800';
    const fontSize = Math.max(8, Math.min(10, Math.floor(gap * 0.5)));
    ctx.font = `bold ${fontSize}px sans-serif`;
    ctx.textAlign = 'center';

    data.forEach((d, i) => {
        const x = PAD_LEFT + i * gap + gap / 2;
        const barH = (d.antall / maks) * chartH;
        const y = PAD_TOP + chartH - barH;

        ctx.fillStyle = '#FF9800';
        ctx.fillRect(x - barW / 2, y, barW, barH);

        // Tall over søyle
        if (d.antall > 0) {
            ctx.fillStyle = '#374151';
            ctx.fillText(d.antall, x, y - 3);
        }
    });

    // X-akse datoetiketter (annenhver)
    ctx.fillStyle = '#6b7280';
    const labelSize = Math.max(7, Math.min(9, Math.floor(gap * 0.45)));
    ctx.font = `${labelSize}px sans-serif`;
    ctx.textAlign = 'center';
    data.forEach((d, i) => {
        if (i % 2 !== 0) return;
        const x = PAD_LEFT + i * gap + gap / 2;
        const dato = new Date(d.dato + 'T12:00:00');
        const etikett = dato.toLocaleDateString('nb-NO', { day: 'numeric', month: 'short' });
        ctx.fillText(etikett, x, H - 6);
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
    _initOmradeToggle();

    const naa = Date.now();
    if (laster) return;
    if (!force && sistLastet && naa - sistLastet < MIN_MANUELL_INTERVAL_MS) return;

    laster = true;
    try {
        let statUrl = '/api/statistikk';
        if (_radiusModus && _gpsPos) {
            const radius = document.getElementById('stat-radius-select')?.value || '25';
            statUrl += `?lat=${_gpsPos.lat}&lon=${_gpsPos.lon}&radius=${radius}`;
        }

        const [respStat, respTopp, respKjede, respBrukere] = await Promise.all([
            fetch(statUrl, { cache: 'no-store' }),
            fetch('/api/toppliste', { cache: 'no-store' }),
            fetch('/api/kjede-snitt', { cache: 'no-store' }),
            fetch('/api/brukere-per-dag', { cache: 'no-store' }),
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

        const brukereData = respBrukere.ok ? await respBrukere.json() : [];
        visBrukerePerDag(brukereData);

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
