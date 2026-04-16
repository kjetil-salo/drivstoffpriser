import { getKjedeFarge, getKjedeInitials, getKjedeLogo } from './kjede.js';

// ── State ─────────────────────────────────────────
let posisjon = null;
let stasjoner = [];
let redigerer = null;  // { kortEl, stasjon, type, editEl }
let refreshTimer = null;
let dagTeller = parseInt(sessionStorage.getItem('bidrag_dag') || '0');

const radiusEl = document.getElementById('b-radius');
const gpsEl   = document.getElementById('b-gps');
const listeEl = document.getElementById('b-liste');
const rangEl  = document.getElementById('b-rang');

// ── Auth ──────────────────────────────────────────
const meg = await fetch('/api/meg').then(r => r.json()).catch(() => ({}));
if (!meg.innlogget) {
    window.location.href = '/auth/logg-inn?neste=/bidrag';
}

// ── Radius ────────────────────────────────────────
radiusEl.value = localStorage.getItem('bidrag_radius') || '5';
radiusEl.addEventListener('change', () => {
    localStorage.setItem('bidrag_radius', radiusEl.value);
    if (posisjon) hentOgVis();
});

// ── Rang ──────────────────────────────────────────
async function oppdaterRang() {
    try {
        const data = await fetch('/api/toppliste').then(r => r.json());
        const listeUke = Array.isArray(data) ? [] : (data.liste_uke || []);
        const megIdx = listeUke.findIndex(r => r.er_meg);
        if (megIdx >= 0) {
            const { antall } = listeUke[megIdx];
            rangEl.innerHTML = `🏆 <strong>#${megIdx + 1}</strong> &nbsp;·&nbsp; ${antall} denne uken`;
        } else {
            rangEl.textContent = '🏆 Kom deg på lista!';
        }
    } catch { rangEl.textContent = ''; }
}
oppdaterRang();

// ── GPS ───────────────────────────────────────────
function startGPS() {
    if (!navigator.geolocation) {
        gpsEl.textContent = 'GPS ikke tilgjengelig i denne nettleseren';
        return;
    }
    navigator.geolocation.watchPosition(
        pos => {
            const ny = { lat: pos.coords.latitude, lon: pos.coords.longitude };
            if (!posisjon || haversine(posisjon, ny) > 100) {
                posisjon = ny;
                hentOgVis();
            }
        },
        () => { gpsEl.textContent = 'Kunne ikke hente posisjon — sjekk at GPS er på'; },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
}

function haversine(a, b) {
    const R = 6371000;
    const dLat = (b.lat - a.lat) * Math.PI / 180;
    const dLon = (b.lon - a.lon) * Math.PI / 180;
    const x = Math.sin(dLat/2)**2 + Math.cos(a.lat*Math.PI/180) * Math.cos(b.lat*Math.PI/180) * Math.sin(dLon/2)**2;
    return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1-x));
}

startGPS();

// ── Hent og vis ───────────────────────────────────
async function hentOgVis() {
    clearTimeout(refreshTimer);
    const r = parseInt(radiusEl.value);
    try {
        const resp = await fetch(`/api/stasjoner?lat=${posisjon.lat}&lon=${posisjon.lon}&radius=${r}`);
        if (!resp.ok) return;
        const data = await resp.json();
        stasjoner = data.stasjoner || [];
        if (!redigerer) visListe();
        gpsEl.hidden = true;
    } catch {
        gpsEl.textContent = 'Feil ved henting av stasjoner';
        gpsEl.hidden = false;
    }
    refreshTimer = setTimeout(hentOgVis, 30000);
}

// ── Sortering ─────────────────────────────────────
// 0 = uten pris (høyeste prioritet), 1 = gammel (>24h), 2 = ok (<24h), 3 = fersk (<6h)
function prioritet(s) {
    const ts = nyesteTidspunkt(s);
    if (!ts) return 0;
    const alder = (Date.now() - new Date(ts + 'Z')) / 3600000;
    if (alder > 24) return 1;
    if (alder > 6)  return 2;
    return 3;
}

function sorter(list) {
    return [...list].sort((a, b) => a.avstand_m - b.avstand_m);
}

// ── Render ────────────────────────────────────────
function visListe() {
    if (redigerer) lukkEdit(false);
    const sortert = sorter(stasjoner);
    listeEl.innerHTML = '';

    for (const s of sortert) listeEl.appendChild(lagKort(s));

    if (!sortert.length) {
        const tom = document.createElement('li');
        tom.id = 'b-tom';
        tom.textContent = 'Ingen stasjoner funnet i valgt radius';
        listeEl.appendChild(tom);
    }
}

function lagKort(s) {
    const li = document.createElement('li');
    li.className = 'b-kort';
    li.dataset.id = s.id;

    const kjedeEllerNavn = s.kjede || s.navn;
    const farge    = getKjedeFarge(kjedeEllerNavn);
    const initials = getKjedeInitials(s.kjede || s.navn);
    const logoUrl  = getKjedeLogo(kjedeEllerNavn);

    const avstandTekst = s.avstand_m < 1000
        ? `${Math.round(s.avstand_m)} m`
        : `${(s.avstand_m / 1000).toFixed(1)} km`;

    const ts = nyesteTidspunkt(s);
    const alderTekst = ts ? formaterAlder(ts) : null;
    const gammel = !ts || (Date.now() - new Date(ts + 'Z')) > 24 * 3600000;

    li.innerHTML = `
      <div class="b-kort-topp">
        <div class="b-badge" style="background:${farge}">
          ${logoUrl
            ? `<img src="${logoUrl}" alt="">`
            : `<span>${esc(initials)}</span>`}
        </div>
        <div class="b-info">
          <div class="b-navn">${esc(s.navn)}</div>
          <div class="b-meta">${avstandTekst}${alderTekst
            ? ` · <span class="${gammel ? 'b-gammel' : ''}">${alderTekst}</span>`
            : ' · <em>Ingen priser</em>'}</div>
        </div>
      </div>
      <div class="b-priser">${lagRader(s)}</div>
    `;

    li.querySelectorAll('.b-rad-pris').forEach(el => {
        const type = el.closest('.b-rad').dataset.type;
        el.addEventListener('click', () => åpneInlineEdit(li, s, type, el));
    });
    li.querySelectorAll('.b-rad-bekreft').forEach(btn => {
        btn.addEventListener('click', () => bekreftType(li, s, btn.dataset.type));
    });

    return li;
}

function lagRader(s) {
    return [
        s.har_bensin !== false            ? { type: 'bensin',            label: '95 oktan', v: s.bensin,            ts: s.bensin_tidspunkt }            : null,
        s.har_bensin98 !== false          ? { type: 'bensin98',          label: '98 oktan', v: s.bensin98,          ts: s.bensin98_tidspunkt }          : null,
        s.har_diesel !== false            ? { type: 'diesel',            label: 'Diesel',   v: s.diesel,            ts: s.diesel_tidspunkt }            : null,
        s.har_diesel_avgiftsfri !== false ? { type: 'diesel_avgiftsfri', label: 'Avg.fri',  v: s.diesel_avgiftsfri, ts: s.diesel_avgiftsfri_tidspunkt } : null,
    ].filter(Boolean).map(({ type, label, v, ts }) => {
        const alder = ts ? (Date.now() - new Date(ts + 'Z')) / 3600000 : Infinity;
        const dot = alder < 6 ? 'b-dot-fersk' : alder < 24 ? 'b-dot-ok' : 'b-dot-gammel';
        const pris = v != null ? v.toFixed(2) : '–';
        const harPrisRad = v != null;
        return `<div class="b-rad" data-type="${type}">
          <span class="b-dot ${dot}"></span>
          <span class="b-rad-label">${label}</span>
          <span class="b-rad-pris">${pris}</span>
          ${harPrisRad
            ? `<button class="b-rad-bekreft" data-type="${type}" aria-label="Bekreft ${label}">✓</button>`
            : `<span class="b-rad-bekreft-placeholder"></span>`}
        </div>`;
    }).join('');
}

// ── Inline edit (pris-span → input på plass) ──────
function åpneInlineEdit(kortEl, stasjon, type, prisSpan) {
    if (redigerer) lukkEdit(false);

    const gjeldende = stasjon[type];
    const input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'numeric';
    input.className = 'b-inline-input';
    input.value = gjeldende != null ? formaterØre(String(Math.round(gjeldende * 100))) : '';
    input.placeholder = '0,00';
    input.setAttribute('aria-label', 'Ny pris');

    prisSpan.replaceWith(input);

    const klikkUtenforHandler = e => {
        if (!kortEl.contains(e.target)) lukkEdit(false);
    };
    redigerer = { kortEl, stasjon, type, input, prisSpan, inline: true, klikkUtenforHandler };

    setTimeout(() => document.addEventListener('pointerdown', klikkUtenforHandler, true), 0);

    input.focus();
    setTimeout(() => input.select(), 30);

    input.addEventListener('input', () => {
        const digits = input.value.replace(/\D/g, '').replace(/^0+/, '');
        input.value = formaterØre(digits);
        input.setSelectionRange(input.value.length, input.value.length);
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); lagrePris(); }
        if (e.key === 'Escape') lukkEdit(false);
    });
}


function lukkEdit(suksess = false) {
    if (!redigerer) return;
    const { kortEl, type, input, prisSpan, klikkUtenforHandler } = redigerer;
    redigerer = null;
    if (klikkUtenforHandler) document.removeEventListener('pointerdown', klikkUtenforHandler, true);

    input.replaceWith(prisSpan);
    const rad = kortEl.querySelector(`.b-rad[data-type="${type}"]`);
    if (rad && suksess) rad.classList.add('b-rad-suksess');
}

async function lagrePris() {
    if (!redigerer) return;
    const { kortEl, stasjon, type, input, prisSpan } = redigerer;

    const verdi = input.value.trim().replace(',', '.');
    const pris  = parseFloat(verdi);
    if (isNaN(pris) || pris < 14 || pris > 37) {
        input.classList.add('b-input-feil');
        setTimeout(() => input.classList.remove('b-input-feil'), 600);
        lukkEdit(false);
        return;
    }

    try {
        const resp = await fetch('/api/pris', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stasjon_id:        stasjon.id,
                bensin:            type === 'bensin'            ? pris : stasjon.bensin,
                bensin98:          type === 'bensin98'          ? pris : stasjon.bensin98,
                diesel:            type === 'diesel'            ? pris : stasjon.diesel,
                diesel_avgiftsfri: type === 'diesel_avgiftsfri' ? pris : stasjon.diesel_avgiftsfri,
                kilde:             'bidrag',
            }),
        });
        if (resp.status === 401) { window.location.href = '/auth/logg-inn?neste=/bidrag'; return; }
        if (!resp.ok) throw new Error();

        const naa = new Date().toISOString().replace('T', ' ').slice(0, 19);
        stasjon[type] = pris;
        stasjon[`${type}_tidspunkt`] = naa;

        prisSpan.textContent = pris.toFixed(2);
        const rad = kortEl.querySelector(`.b-rad[data-type="${type}"]`);
        if (rad) rad.querySelector('.b-dot').className = 'b-dot b-dot-fersk';

        lukkEdit(true);

        dagTeller++;
        sessionStorage.setItem('bidrag_dag', dagTeller);
        setTimeout(hentOgVis, 1500);
        oppdaterRang();

    } catch {
        input.classList.add('b-input-feil');
        setTimeout(() => input.classList.remove('b-input-feil'), 600);
    }
}

// ── Bekreft ───────────────────────────────────────
async function bekreftType(kortEl, stasjon, type) {
    if (redigerer && redigerer.kortEl === kortEl && redigerer.type === type) {
        lagrePris();
        return;
    }
    const btn = kortEl.querySelector(`.b-rad-bekreft[data-type="${type}"]`);
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = '…';

    try {
        const resp = await fetch('/api/pris', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stasjon_id:        stasjon.id,
                bensin:            stasjon.bensin,
                bensin98:          stasjon.bensin98,
                diesel:            stasjon.diesel,
                diesel_avgiftsfri: stasjon.diesel_avgiftsfri,
                kilde:             'bidrag',
            }),
        });
        if (resp.status === 401) { window.location.href = '/auth/logg-inn?neste=/bidrag'; return; }
        if (!resp.ok) throw new Error();

        const naa = new Date().toISOString().replace('T', ' ').slice(0, 19);
        stasjon[`${type}_tidspunkt`] = naa;

        const rad = kortEl.querySelector(`.b-rad[data-type="${type}"]`);
        if (rad) rad.querySelector('.b-dot').className = 'b-dot b-dot-fersk';
        rad?.classList.add('b-rad-suksess');

        dagTeller++;
        sessionStorage.setItem('bidrag_dag', dagTeller);
        oppdaterRang();

        btn.textContent = '✓';
        setTimeout(hentOgVis, 1500);
    } catch {
        btn.disabled = false;
        btn.textContent = '✓';
    }
}

// ── Hjelpere ──────────────────────────────────────
function harPris(s) {
    return s.bensin != null || s.bensin98 != null || s.diesel != null || s.diesel_avgiftsfri != null;
}

function nyesteTidspunkt(s) {
    return [s.bensin_tidspunkt, s.diesel_tidspunkt, s.bensin98_tidspunkt, s.diesel_avgiftsfri_tidspunkt]
        .filter(Boolean).reduce((a, b) => a > b ? a : b, null);
}

function formaterAlder(ts) {
    const diff = Date.now() - new Date(ts + 'Z');
    const dager = Math.floor(diff / 86400000);
    const timer = Math.floor(diff / 3600000);
    const min   = Math.floor(diff / 60000);
    if (dager > 0) return `${dager} d siden`;
    if (timer > 0) return `${timer} t siden`;
    return `${min} min siden`;
}

function esc(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Formater sifferstreng som pris: "2199" → "21,99", "219" → "2,19", "21" → "0,21"
function formaterØre(digits) {
    if (!digits) return '';
    if (digits.length === 1) return `0,0${digits}`;
    if (digits.length === 2) return `0,${digits}`;
    return `${digits.slice(0, -2)},${digits.slice(-2)}`;
}
