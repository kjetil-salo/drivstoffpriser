import { hentStasjoner } from './api.js';
import { hentPosisjon } from './location.js';
import { initMap, sentrerKart, visUserPosisjon, visStasjoner, oppdaterStasjonPriser } from './map.js';
import { visListe, oppdaterKort } from './list.js';
import { initSheet, visStasjonSheet, oppdaterSheetStasjon, lukkSheet } from './station-sheet.js';
import { initSearch } from './search.js';

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

// ── Statistikk ────────────────────────────────────
fetch('/api/logview', { method: 'POST' }).catch(() => {});

// ── Auth-status ───────────────────────────────────
const meg = await fetch('/api/meg').then(r => r.json()).catch(() => ({}));
window.__innlogget = meg.innlogget || false;

const authLenke = document.getElementById('auth-lenke');
if (window.__innlogget) {
    authLenke.textContent = meg.brukernavn;
    authLenke.href = '/auth/logg-ut';
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
        locBtn.click();
    });
    document.getElementById('velkomst-sok-btn').addEventListener('click', () => {
        velkomst.setAttribute('hidden', '');
        document.getElementById('search-toggle').click();
    });
}

// ── Sheet + search init ───────────────────────────
initSheet(prisOppdatert);

initSearch(async (sted) => {
    lukkSheet();
    sentrerKart(sted.lat, sted.lon, 13);
    locStatus.textContent = `Henter stasjoner for ${sted.navn.split(',')[0]} …`;
    try {
        stasjoner = await hentStasjoner(sted.lat, sted.lon);
        locStatus.textContent = `${stasjoner.length} stasjoner funnet`;
        visStasjoner(stasjoner, visStasjonSheet);
        if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    } catch {
        locStatus.textContent = 'Feil ved henting av stasjoner';
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
            } catch {
                locStatus.textContent = 'Feil ved henting av stasjoner';
            }
        },
        (feil) => {
            locBtn.disabled = false;
            locStatus.textContent = feil;
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
