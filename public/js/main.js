import { hentStasjoner, hentTotaltMedPris } from './api.js';
import { hentPosisjon } from './location.js';
import { initMap, sentrerKart, visUserPosisjon, visStasjoner, oppdaterStasjonPriser, initKartBevegelse, refreshKartInnstillinger } from './map.js';
import { visListe, oppdaterKort } from './list.js';
import { initSheet, visStasjonSheet, oppdaterSheetStasjon, lukkSheet, refreshSheetInnstillinger } from './station-sheet.js';
import { initSearch } from './search.js';
import { initInnstillinger } from './settings.js';

// ── Lagret posisjon ───────────────────────────────
const LAGRET_POS_KEY = 'siste_pos';

function hentLagretPos() {
    try {
        const raw = localStorage.getItem(LAGRET_POS_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function lagrePosisjon(pos) {
    try {
        localStorage.setItem(LAGRET_POS_KEY, JSON.stringify({ lat: pos.lat, lon: pos.lon }));
    } catch {}
}

// ── State ─────────────────────────────────────────
let stasjoner = [];
let userPos = null;

// ── DOM ───────────────────────────────────────────
const locBtn = document.getElementById('loc-btn');
const locStatus = document.getElementById('loc-status');
const tabKart = document.getElementById('tab-kart');
const tabListe = document.getElementById('tab-liste');
const viewKart = document.getElementById('view-kart');
const viewListe = document.getElementById('view-liste');
const velkomst = document.getElementById('velkomst');

// ── Lokasjonsfeil-dialog ───────────────────────────
const lokFeilBackdrop = document.getElementById('lok-feil-backdrop');
const lokFeilDialog = document.getElementById('lok-feil-dialog');
const lokFeilTittel = document.getElementById('lok-feil-tittel');
const lokFeilTekst = document.getElementById('lok-feil-tekst');
const lokFeilSteg = document.getElementById('lok-feil-steg');

function visLokFeil({ nektet }) {
    if (nektet) {
        lokFeilTittel.textContent = 'Posisjon er blokkert';
        lokFeilTekst.textContent = 'Appen har ikke tilgang til posisjonen din. Følg stegene under for å tillate tilgang:';
        lokFeilSteg.removeAttribute('hidden');
    } else {
        lokFeilTittel.textContent = 'Kunne ikke hente posisjon';
        lokFeilTekst.textContent = 'Det oppstod en feil ved henting av posisjon. Sjekk at GPS er aktivert og prøv igjen.';
        lokFeilSteg.setAttribute('hidden', '');
    }
    lokFeilBackdrop.removeAttribute('hidden');
    lokFeilDialog.removeAttribute('hidden');
}

function lukkLokFeil() {
    lokFeilBackdrop.setAttribute('hidden', '');
    lokFeilDialog.setAttribute('hidden', '');
}

document.getElementById('lok-feil-lukk').addEventListener('click', lukkLokFeil);
lokFeilBackdrop.addEventListener('click', lukkLokFeil);

// ── Statistikk ────────────────────────────────────
fetch('/api/logview', { method: 'POST' }).catch(() => {});

// ── Auth-status ───────────────────────────────────
const meg = await fetch('/api/meg').then(r => r.json()).catch(() => ({}));
window.__innlogget = meg.innlogget || false;

const authLenke = document.getElementById('auth-lenke');
if (window.__innlogget) {
    authLenke.textContent = meg.brukernavn;
    authLenke.href = '/auth/logg-ut';
    authLenke.addEventListener('click', e => {
        if (!confirm('Logg ut?')) e.preventDefault();
    });
    authLenke.removeAttribute('hidden');
} else {
    authLenke.textContent = 'Logg inn';
    authLenke.href = '/auth/logg-inn';
    authLenke.removeAttribute('hidden');
}

// ── Init kart med siste kjente posisjon ───────────
const lagretPos = hentLagretPos();
initMap('map', lagretPos);

// ── Velkomst-overlay ──────────────────────────────
if (!lagretPos) {
    velkomst.removeAttribute('hidden');
    document.getElementById('velkomst-posisjon-btn').addEventListener('click', () => {
        velkomst.setAttribute('hidden', '');
        startLokasjon();
    });
    document.getElementById('velkomst-sok-btn').addEventListener('click', () => {
        velkomst.setAttribute('hidden', '');
        setTimeout(() => document.getElementById('search-toggle').click(), 0);
    });
}

// ── Innstillinger ─────────────────────────────────
initInnstillinger(() => {
    if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    refreshKartInnstillinger();
    refreshSheetInnstillinger();
});

// ── Totalt med pris ───────────────────────────────
hentTotaltMedPris().then(totalt => {
    if (totalt != null) {
        document.getElementById('totalt-info').textContent = `${totalt} stasjoner med pris registrert totalt`;
    }
}).catch(() => {});

// ── Sheet + search init ───────────────────────────
initSheet(prisOppdatert);

initKartBevegelse(async (lat, lon) => {
    try {
        const nye = await hentStasjoner(lat, lon);
        stasjoner = nye;
        locStatus.textContent = `${nye.length} stasjoner`;
        visStasjoner(stasjoner, visStasjonSheet);
        if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    } catch (e) {
        if (e.utenfor) locStatus.textContent = 'Kun tilgjengelig i Norge';
    }
});

initSearch(async (sted) => {
    lukkSheet();
    sentrerKart(sted.lat, sted.lon, 13);
    locStatus.textContent = `Henter stasjoner for ${sted.navn.split(',')[0]} …`;
    try {
        stasjoner = await hentStasjoner(sted.lat, sted.lon);
        locStatus.textContent = `${stasjoner.length} stasjoner funnet`;
        visStasjoner(stasjoner, visStasjonSheet);
        if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    } catch (e) {
        locStatus.textContent = e.utenfor ? 'Kun tilgjengelig i Norge' : 'Feil ved henting av stasjoner';
    }
});

// Last stasjoner for siste posisjon ved oppstart
if (lagretPos) {
    locStatus.textContent = 'Henter stasjoner …';
    hentStasjoner(lagretPos.lat, lagretPos.lon).then(s => {
        stasjoner = s;
        locStatus.textContent = `${s.length} stasjoner`;
        visStasjoner(stasjoner, visStasjonSheet);
        if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    }).catch(() => { locStatus.textContent = ''; });
}

// ── Tab-bytte ─────────────────────────────────────
function byttTab(tab) {
    if (tab === 'kart') {
        viewKart.style.display = 'block';
        viewListe.style.display = 'none';
        tabKart.classList.add('active');
        tabListe.classList.remove('active');
    } else {
        viewKart.style.display = 'none';
        viewListe.style.display = 'block';
        tabKart.classList.remove('active');
        tabListe.classList.add('active');
        visListe(stasjoner, visStasjonSheet);
    }
}

tabKart.addEventListener('click', () => byttTab('kart'));
tabListe.addEventListener('click', () => byttTab('liste'));

document.addEventListener('vis-pa-kart', (e) => {
    const s = e.detail;
    byttTab('kart');
    sentrerKart(s.lat, s.lon, 16);
});

// ── Geolokasjon ───────────────────────────────────
locBtn.addEventListener('click', startLokasjon);

function startLokasjon() {
    locBtn.disabled = true;
    locStatus.textContent = 'Henter posisjon …';

    hentPosisjon(
        async (pos) => {
            userPos = pos;
            lagrePosisjon(pos);
            locBtn.disabled = false;
            locStatus.textContent = `±${Math.round(pos.accuracy)} m`;
            visUserPosisjon(pos);

            locStatus.textContent = 'Henter stasjoner …';
            try {
                stasjoner = await hentStasjoner(pos.lat, pos.lon);
                locStatus.textContent = `${stasjoner.length} stasjoner funnet`;
                visStasjoner(stasjoner, visStasjonSheet);
                if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
            } catch (e) {
                locStatus.textContent = e.utenfor ? 'Kun tilgjengelig i Norge' : 'Feil ved henting av stasjoner';
            }
        },
        (feil) => {
            locBtn.disabled = false;
            locStatus.textContent = '';
            visLokFeil(feil);
        },
        (melding) => {
            locStatus.textContent = melding;
        }
    );
}

// ── Prisoppdatering (fra sheet) ───────────────────
function prisOppdatert(oppdatert) {
    stasjoner = stasjoner.map(s => s.id === oppdatert.id ? oppdatert : s);
    oppdaterStasjonPriser(oppdatert, visStasjonSheet);
    oppdaterSheetStasjon(oppdatert);
    oppdaterKort(oppdatert, visStasjonSheet);
}
