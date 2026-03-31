import { getInnstillinger } from './settings.js';
import { getKjedeFarge, getKjedeInitials, getKjedeLogo } from './kjede.js';

let aktivSort = 'avstand';
let sisteStasjoner = [];
let sisteOnKlikk = null;

export function visListe(stasjoner, onKlikk) {
    sisteStasjoner = stasjoner;
    sisteOnKlikk = onKlikk;

    const container = document.getElementById('liste');
    const info = document.getElementById('liste-info');

    if (!stasjoner || stasjoner.length === 0) {
        info.textContent = 'Ingen stasjoner funnet i nærheten.';
        container.innerHTML = '';
        return;
    }

    const inn = getInnstillinger();
    const medPris = stasjoner.filter(s => s.bensin != null || s.bensin98 != null || s.diesel != null || s.diesel_avgiftsfri != null).length;

    // Tilbakestill aktivSort hvis valgt type ikke lenger er synlig
    if (aktivSort === 'bensin' && !inn.bensin) aktivSort = 'avstand';
    if (aktivSort === 'bensin98' && !inn.bensin98) aktivSort = 'avstand';
    if (aktivSort === 'diesel' && !inn.diesel) aktivSort = 'avstand';
    if (aktivSort === 'diesel_avgiftsfri' && !inn.diesel_avgiftsfri) aktivSort = 'avstand';

    info.innerHTML = `
        <span id="sort-label">${stasjoner.length} stasjoner (${medPris} med pris) – sorter:</span>
        <div id="sort-knapper">
            <button class="sort-btn ${aktivSort === 'avstand' ? 'aktiv' : ''}" data-sort="avstand">Avstand</button>
            ${inn.bensin ? `<button class="sort-btn ${aktivSort === 'bensin' ? 'aktiv' : ''}" data-sort="bensin">95 oktan</button>` : ''}
            ${inn.bensin98 ? `<button class="sort-btn ${aktivSort === 'bensin98' ? 'aktiv' : ''}" data-sort="bensin98">98 oktan</button>` : ''}
            ${inn.diesel ? `<button class="sort-btn ${aktivSort === 'diesel' ? 'aktiv' : ''}" data-sort="diesel">Diesel</button>` : ''}
            ${inn.diesel_avgiftsfri ? `<button class="sort-btn ${aktivSort === 'diesel_avgiftsfri' ? 'aktiv' : ''}" data-sort="diesel_avgiftsfri">Avg.fri</button>` : ''}
        </div>`;

    info.querySelectorAll('.sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            aktivSort = btn.dataset.sort;
            visListe(sisteStasjoner, sisteOnKlikk);
        });
    });

    const billigste = finnBilligste(stasjoner, inn);
    const billigsteId = finnBilligsteId(stasjoner, inn, aktivSort);
    const sortert = sorter(stasjoner, aktivSort, billigsteId);
    container.innerHTML = sortert.map(s => kortHtml(s, billigste, s.id === billigsteId)).join('');

    container.querySelectorAll('.stasjon-kort').forEach(kort => {
        const id = parseInt(kort.dataset.id, 10);
        const handler = () => {
            const stasjon = stasjoner.find(s => s.id === id);
            if (stasjon) onKlikk(stasjon);
        };
        kort.addEventListener('click', handler);
        kort.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); }
        });
    });

    container.querySelectorAll('.sk-kart-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = parseInt(btn.dataset.kartId, 10);
            const stasjon = stasjoner.find(s => s.id === id);
            if (stasjon) document.dispatchEvent(new CustomEvent('vis-pa-kart', { detail: stasjon }));
        });
    });
}

export function oppdaterKort(stasjon, onKlikk) {
    const kort = document.querySelector(`.stasjon-kort[data-id="${stasjon.id}"]`);
    if (!kort) return;
    const inn = getInnstillinger();
    const billigste = finnBilligste(sisteStasjoner, inn);
    const billigsteId = finnBilligsteId(sisteStasjoner, inn, aktivSort);
    const nytt = document.createElement('div');
    nytt.innerHTML = kortHtml(stasjon, billigste, stasjon.id === billigsteId);
    const nyttKort = nytt.firstElementChild;
    nyttKort.addEventListener('click', () => onKlikk(stasjon));
    kort.replaceWith(nyttKort);
}

function finnBilligste(stasjoner, inn) {
    const billigste = {};
    for (const type of ['bensin', 'bensin98', 'diesel', 'diesel_avgiftsfri']) {
        if (!inn[type]) continue;
        let min = Infinity, minId = null;
        for (const s of stasjoner) {
            if (s[type] != null && s[type] < min) { min = s[type]; minId = s.id; }
        }
        if (minId !== null) billigste[type] = minId;
    }
    return billigste;
}

function finnBilligsteId(stasjoner, inn, felt) {
    let minPris = Infinity, minId = null;
    for (const s of stasjoner) {
        const priser = felt && felt !== 'avstand'
            ? (inn[felt] && s[felt] != null ? [s[felt]] : [])
            : [
                inn.bensin              ? s.bensin              : null,
                inn.bensin98            ? s.bensin98            : null,
                inn.diesel              ? s.diesel              : null,
                inn.diesel_avgiftsfri   ? s.diesel_avgiftsfri   : null,
              ].filter(v => v != null);
        if (!priser.length) continue;
        const min = Math.min(...priser);
        if (min < minPris) { minPris = min; minId = s.id; }
    }
    return minId;
}

function sorter(stasjoner, felt, billigsteId) {
    return [...stasjoner].sort((a, b) => {
        // Billigste øverst kun ved prissortering
        if (felt !== 'avstand') {
            if (a.id === billigsteId) return -1;
            if (b.id === billigsteId) return 1;
        }
        if (felt === 'avstand') return (a.avstand_m ?? Infinity) - (b.avstand_m ?? Infinity);
        const av = a[felt] ?? Infinity;
        const bv = b[felt] ?? Infinity;
        return av - bv;
    });
}

function formatPris(v) {
    if (v == null) return null;
    return v.toFixed(2).replace('.', ',');
}

function avstandTekst(m) {
    return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
}

function prisAlderTekst(tidspunkt) {
    if (!tidspunkt) return null;
    const d = new Date(tidspunkt.replace(' ', 'T'));
    const diffMs = Date.now() - d.getTime();
    const min = Math.floor(diffMs / 60000);
    const timer = Math.floor(diffMs / 3600000);
    const dager = Math.floor(diffMs / 86400000);
    if (min < 1) return 'akkurat nå';
    if (min < 60) return `${min} min siden`;
    if (timer < 24) return `${timer} t siden`;
    if (dager < 7) return `${dager} d siden`;
    return d.toLocaleDateString('no', { day: 'numeric', month: 'short' });
}

function prisAlderKlasse(tidspunkt) {
    if (!tidspunkt) return 'alder-ingen';
    const timer = (Date.now() - new Date(tidspunkt.replace(' ', 'T')).getTime()) / 3600000;
    if (timer < 8) return 'alder-fersk';
    if (timer < 24) return 'alder-gammel';
    if (timer < 48) return 'alder-utdatert';
    return 'alder-kritisk';
}

function prisAlderBanner(tidspunkt) {
    if (!tidspunkt) return null;
    const dager = Math.floor((Date.now() - new Date(tidspunkt.replace(' ', 'T')).getTime()) / 86400000);
    if (dager < 2) return null;
    return `⚠ Prisen er ${dager} dager gammel`;
}

function kortHtml(s, billigste = {}, erHovedBilligst = false) {
    const inn = getInnstillinger();
    const rader = [
        inn.bensin              ? { label: '95',     v: formatPris(s.bensin),              billigst: billigste.bensin              === s.id, type: 'bensin',              ts: s.bensin_tidspunkt              } : null,
        inn.bensin98            ? { label: '98',     v: formatPris(s.bensin98),            billigst: billigste.bensin98            === s.id, type: 'bensin98',            ts: s.bensin98_tidspunkt            } : null,
        inn.diesel              ? { label: 'Diesel', v: formatPris(s.diesel),              billigst: billigste.diesel              === s.id, type: 'diesel',              ts: s.diesel_tidspunkt              } : null,
        inn.diesel_avgiftsfri   ? { label: 'Avg.fri', v: formatPris(s.diesel_avgiftsfri),  billigst: billigste.diesel_avgiftsfri   === s.id, type: 'diesel_avgiftsfri',   ts: s.diesel_avgiftsfri_tidspunkt   } : null,
    ].filter(Boolean);
    const kjedeEllerNavn = s.kjede || s.navn;
    const logoUrl = getKjedeLogo(kjedeEllerNavn);
    const farge = getKjedeFarge(kjedeEllerNavn);
    const initials = getKjedeInitials(s.kjede || s.navn);
    const badgeHtml = `<div class="sk-badge" style="background:${farge};position:relative">` +
        `<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;color:#fff">${initials}</span>` +
        (logoUrl ? `<img src="${logoUrl}" alt="${s.kjede || ''}" style="position:relative;width:28px;height:28px;object-fit:contain" onerror="this.style.display='none'">` : '') +
        `</div>`;
    // Nyeste oppdatering blant synlige priser → for alderTekst
    const synligeTidspunkt = rader.filter(r => r.v && r.ts).map(r => r.ts);
    const nyesteTidspunkt = synligeTidspunkt.length
        ? synligeTidspunkt.reduce((a, b) => a > b ? a : b)
        : null;
    // Eldste oppdatering blant synlige priser → for ⚠-banner
    const eldsteTidspunkt = synligeTidspunkt.length
        ? synligeTidspunkt.reduce((a, b) => a < b ? a : b)
        : null;
    const alderTekst = prisAlderTekst(nyesteTidspunkt);
    const alderKlasse = prisAlderKlasse(nyesteTidspunkt);
    const alderBanner = prisAlderBanner(eldsteTidspunkt);
    const erKritisk = alderBanner !== null;
    const kortKlasse = erKritisk ? ' gammel-kort' : (erHovedBilligst ? ' billigst-kort' : '');
    const bannerHtml = erKritisk
        ? `<div class="sk-gammel-banner">${alderBanner}</div>`
        : (erHovedBilligst ? '<div class="sk-billigst-banner">★ billigste stasjon</div>' : '');
    return `<div class="stasjon-kort${kortKlasse}" role="listitem" tabindex="0" aria-label="${s.navn}${s.kjede ? ', ' + s.kjede : ''}" data-id="${s.id}">
        ${bannerHtml}
        ${badgeHtml}
        <div class="sk-info">
            <div class="sk-navn">${s.navn}</div>
            ${s.kjede ? `<div class="sk-kjede">${s.kjede}</div>` : ''}
            <div class="sk-priser">
                ${rader.map(r => `<div class="sk-pris-rad${r.type === aktivSort ? ' sort-aktiv' : ''}">
                    <span class="sk-pris-label">${r.label}</span>
                    <span class="sk-pris-verdi ${r.v ? (r.billigst ? 'billigst' : '') : 'ingen'}">${r.v ?? '–'}</span>
                    ${r.v ? `<span class="pris-alder-dot ${prisAlderKlasse(r.ts)}" title="${r.ts ? prisAlderTekst(r.ts) : 'ukjent alder'}"></span>` : ''}
                </div>`).join('')}
            </div>
            ${alderTekst ? `<div class="sk-alder ${alderKlasse}">${alderTekst}</div>` : ''}
        </div>
        <div class="sk-hoyre">
            <span class="sk-avstand">${avstandTekst(s.avstand_m)}</span>
            ${s.brukeropprettet ? `<a class="sk-gmaps-btn" href="https://www.google.com/maps?q=${s.lat},${s.lon}" target="_blank" rel="noopener" aria-label="Åpne ${s.navn} i Google Maps" onclick="event.stopPropagation()">
                <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>` : ''}
            <button class="sk-kart-btn" aria-label="Vis ${s.navn} på kart" data-kart-id="${s.id}">
                <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            </button>
        </div>
    </div>`;
}
