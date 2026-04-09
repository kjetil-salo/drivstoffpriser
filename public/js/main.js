import { hentStasjoner } from './api.js';
import { hentPosisjon, startFollowWatch } from './location.js';
import { initMap, sentrerKart, panTilPosisjon, visUserPosisjon, oppdaterUserMarker, registrerBrukerDrag, visStasjoner, oppdaterStasjonPriser, initKartBevegelse, refreshKartInnstillinger, getKartSenter } from './map.js';
import { visListe, oppdaterKort } from './list.js';
import { initSheet, visStasjonSheet, oppdaterSheetStasjon, lukkSheet, refreshSheetInnstillinger } from './station-sheet.js';
import { initSearch } from './search.js';
import { initInnstillinger, getInnstillinger } from './settings.js';
import { initAddStation, openAddStation } from './add-station.js';
import { lastStatistikk } from './stats.js';

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
let followStopFn = null;

// ── DOM ───────────────────────────────────────────
const locBtn = document.getElementById('loc-btn');
const locStatus = document.getElementById('loc-status');
const tabKart = document.getElementById('tab-kart');
const tabListe = document.getElementById('tab-liste');
const tabStatistikk = document.getElementById('tab-statistikk');
const viewKart = document.getElementById('view-kart');
const viewListe = document.getElementById('view-liste');
const viewStatistikk = document.getElementById('view-statistikk');
const velkomst = document.getElementById('velkomst');

// ── Lokasjonsfeil-dialog ───────────────────────────
const lokFeilBackdrop = document.getElementById('lok-feil-backdrop');
const lokFeilDialog = document.getElementById('lok-feil-dialog');
const lokFeilTittel = document.getElementById('lok-feil-tittel');
const lokFeilTekst = document.getElementById('lok-feil-tekst');
const lokFeilSteg = document.getElementById('lok-feil-steg');

let lokFeilTidligereFokus = null;

function visLokFeil({ nektet }) {
    lokFeilTidligereFokus = document.activeElement;
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
    setTimeout(() => document.getElementById('lok-feil-lukk').focus(), 100);
}

function lukkLokFeil() {
    lokFeilBackdrop.setAttribute('hidden', '');
    lokFeilDialog.setAttribute('hidden', '');
    if (lokFeilTidligereFokus) { lokFeilTidligereFokus.focus(); lokFeilTidligereFokus = null; }
}

document.getElementById('lok-feil-lukk').addEventListener('click', lukkLokFeil);
lokFeilBackdrop.addEventListener('click', lukkLokFeil);
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !lokFeilDialog.hasAttribute('hidden')) lukkLokFeil();
});

// ── Facebook-nettleser-sjekk ──────────────────────
if (/FBAN|FBAV|FB_IAB/i.test(navigator.userAgent)) {
    document.getElementById('fb-banner').removeAttribute('hidden');
}

// ── Backup-sjekk ─────────────────────────────────
fetch('/api/instance').then(r => r.json()).then(d => {
    if (d.backup) {
        const banner = document.getElementById('backup-banner');
        banner.removeAttribute('hidden');
        banner.addEventListener('click', () => {
            document.getElementById('backup-info').toggleAttribute('hidden');
        });
    }
}).catch(() => {});

// ── Nyhet-splash ─────────────────────────────────
let nyhetVises = false;
const nyhetData = await fetch('/api/nyhet').then(r => r.json()).catch(() => ({}));
if (nyhetData.tekst) {
    const cookieName = `nyhet_lest_${nyhetData.id}`;
    if (!document.cookie.split(';').some(c => c.trim().startsWith(cookieName + '='))) {
        nyhetVises = true;
        const d = nyhetData;
        const backdrop = document.getElementById('nyhet-backdrop');
        const dialog = document.getElementById('nyhet-dialog');
        document.getElementById('nyhet-tittel').textContent = d.tittel || 'Nyhet';
        document.getElementById('nyhet-tekst').textContent = d.tekst;
        const tidligereFokus = document.activeElement;
        backdrop.removeAttribute('hidden');
        dialog.removeAttribute('hidden');
        setTimeout(() => document.getElementById('nyhet-lukk').focus(), 100);
        function lukk() {
            backdrop.setAttribute('hidden', '');
            dialog.setAttribute('hidden', '');
            const utloper = new Date(d.utloper);
            const maxAge = Math.max(0, Math.floor((utloper - Date.now()) / 1000));
            document.cookie = `${cookieName}=1;max-age=${maxAge};path=/;SameSite=Lax`;
            if (tidligereFokus) tidligereFokus.focus();
        }
        document.getElementById('nyhet-lukk').addEventListener('click', lukk);
        backdrop.addEventListener('click', lukk);
        const escHandler = (e) => {
            if (e.key === 'Escape' && !dialog.hasAttribute('hidden')) { lukk(); document.removeEventListener('keydown', escHandler); }
        };
        document.addEventListener('keydown', escHandler);
    }
}

// ── Statistikk ────────────────────────────────────
fetch('/api/logview', { method: 'POST' }).catch(() => {});

// ── Auth-status ───────────────────────────────────
const meg = await fetch('/api/meg').then(r => r.json()).catch(() => ({}));
window.__innlogget = meg.innlogget || false;
window.__erAdmin = meg.er_admin || false;
window.__roller = meg.roller || [];

const authLenke = document.getElementById('auth-lenke');

const bidragBtn = document.getElementById('bidrag-btn');
if (bidragBtn && window.__innlogget && localStorage.getItem('bidrag_snarvei') === '1') {
    bidragBtn.removeAttribute('hidden');
}

const moderatorBtn = document.getElementById('moderator-btn');
if (moderatorBtn && (window.__erAdmin || window.__roller.includes('moderator'))) {
    moderatorBtn.removeAttribute('hidden');
}
if (window.__innlogget) {
    document.getElementById('auth-ikon').removeAttribute('hidden');
    document.getElementById('auth-tekst').textContent = '';
    authLenke.href = '/auth/min-konto';
    authLenke.title = meg.kallenavn || meg.brukernavn;
    authLenke.setAttribute('aria-label', 'Min konto (' + (meg.kallenavn || meg.brukernavn) + ')');
    authLenke.removeAttribute('hidden');
} else {
    document.getElementById('auth-tekst').textContent = 'Logg inn';
    authLenke.href = '/auth/logg-inn';
    authLenke.removeAttribute('hidden');
}

// ── Velkomst-splash ───────────────────────────────
if (!window.__innlogget && !localStorage.getItem('velkommen_vist')) {
    if (!nyhetVises) {
        localStorage.setItem('velkommen_vist', '1');
        const backdrop = document.getElementById('velkommen-backdrop');
        const dialog = document.getElementById('velkommen-dialog');
        const tidligereFokus = document.activeElement;
        backdrop.removeAttribute('hidden');
        dialog.removeAttribute('hidden');
        setTimeout(() => document.getElementById('velkommen-lukk').focus(), 100);
        function lukkVelkommen() {
            backdrop.setAttribute('hidden', '');
            dialog.setAttribute('hidden', '');
            if (tidligereFokus) tidligereFokus.focus();
        }
        document.getElementById('velkommen-lukk').addEventListener('click', lukkVelkommen);
        backdrop.addEventListener('click', lukkVelkommen);
        const escVelkommen = (e) => {
            if (e.key === 'Escape' && !dialog.hasAttribute('hidden')) {
                lukkVelkommen();
                document.removeEventListener('keydown', escVelkommen);
            }
        };
        document.addEventListener('keydown', escVelkommen);
    }
}

// ── Legg til stasjon ─────────────────────────────
const addStationBtn = document.getElementById('add-station-btn');
if (window.__innlogget) {
    addStationBtn.removeAttribute('hidden');
}
addStationBtn.addEventListener('click', () => {
    const senter = getKartSenter();
    if (senter) openAddStation(senter);
});
initAddStation((nyStasjon) => {
    const s = {
        ...nyStasjon,
        bensin: null, diesel: null, bensin98: null,
        bensin_tidspunkt: null, diesel_tidspunkt: null, bensin98_tidspunkt: null, avstand_m: 0,
    };
    stasjoner.push(s);
    visStasjoner(stasjoner, visStasjonSheet);
    if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    sentrerKart(s.lat, s.lon, 16);
});

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
        setTimeout(() => document.getElementById('search-input').focus(), 0);
    });
}

// ── Innstillinger ─────────────────────────────────
let sisteRadius = getInnstillinger().radius;
initInnstillinger(async (ny) => {
    if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    refreshKartInnstillinger();
    refreshSheetInnstillinger();

    // Re-hent stasjoner ved radius-endring
    if (sisteRadius !== null && ny.radius !== sisteRadius) {
        const pos = hentLagretPos() || getKartSenter();
        if (pos) {
            try {
                stasjoner = await hentStasjoner(pos.lat, pos.lon);
                visStasjoner(stasjoner, visStasjonSheet);
                if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
            } catch {}
        }
    }
    sisteRadius = ny.radius;
});


// ── Sheet + search init ───────────────────────────
initSheet(prisOppdatert);

initKartBevegelse(async (lat, lon) => {
    try {
        const nye = await hentStasjoner(lat, lon);
        stasjoner = nye;
        locStatus.textContent = '';
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
        locStatus.textContent = '';
        lagrePosisjon({ lat: sted.lat, lon: sted.lon });
        velkomst.setAttribute('hidden', '');
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
        locStatus.textContent = '';
        visStasjoner(stasjoner, visStasjonSheet);
        if (viewListe.style.display !== 'none') visListe(stasjoner, visStasjonSheet);
    }).catch(() => { locStatus.textContent = ''; });
}

// ── Tab-bytte ─────────────────────────────────────
function byttTab(tab) {
    viewKart.style.display = 'none';
    viewListe.style.display = 'none';
    viewStatistikk.style.display = 'none';
    tabKart.classList.remove('active');
    tabListe.classList.remove('active');
    tabStatistikk.classList.remove('active');

    tabKart.setAttribute('aria-selected', 'false');
    tabListe.setAttribute('aria-selected', 'false');
    tabStatistikk.setAttribute('aria-selected', 'false');

    if (tab === 'kart') {
        viewKart.style.display = 'block';
        tabKart.classList.add('active');
        tabKart.setAttribute('aria-selected', 'true');
    } else if (tab === 'liste') {
        viewListe.style.display = 'block';
        tabListe.classList.add('active');
        tabListe.setAttribute('aria-selected', 'true');
        visListe(stasjoner, visStasjonSheet);
    } else if (tab === 'statistikk') {
        viewStatistikk.style.display = 'block';
        tabStatistikk.classList.add('active');
        tabStatistikk.setAttribute('aria-selected', 'true');
        lastStatistikk();
    }
    localStorage.setItem('aktivTab', tab);
}

tabKart.addEventListener('click', () => byttTab('kart'));
tabListe.addEventListener('click', () => byttTab('liste'));
tabStatistikk.addEventListener('click', () => byttTab('statistikk'));

byttTab(localStorage.getItem('aktivTab') || 'kart');

// Keyboard-navigasjon for tabs (WAI-ARIA tab pattern)
const tabListe_ = [tabKart, tabListe, tabStatistikk];
const tabNavn = ['kart', 'liste', 'statistikk'];
document.getElementById('tabs').addEventListener('keydown', (e) => {
    const idx = tabListe_.indexOf(document.activeElement);
    if (idx === -1) return;
    let nyIdx = idx;
    if (e.key === 'ArrowRight') nyIdx = (idx + 1) % 3;
    else if (e.key === 'ArrowLeft') nyIdx = (idx + 2) % 3;
    else if (e.key === 'Home') nyIdx = 0;
    else if (e.key === 'End') nyIdx = 2;
    else return;
    e.preventDefault();
    tabListe_[nyIdx].focus();
    byttTab(tabNavn[nyIdx]);
});

document.addEventListener('vis-pa-kart', (e) => {
    const s = e.detail;
    byttTab('kart');
    sentrerKart(s.lat, s.lon, 16);
});

document.addEventListener('naviger-til-stasjon', async (e) => {
    const { id, lat, lon } = e.detail;
    byttTab('kart');
    sentrerKart(lat, lon, 16);
    try {
        const nye = await hentStasjoner(lat, lon);
        stasjoner = nye;
        visStasjoner(stasjoner, visStasjonSheet);
        const stasjon = stasjoner.find(s => s.id === id);
        if (stasjon) visStasjonSheet(stasjon);
    } catch {}
});

// ── Geolokasjon ───────────────────────────────────
registrerBrukerDrag(stoppFollow);

locBtn.addEventListener('click', () => {
    if (!userPos) {
        startLokasjon();
    } else if (followStopFn) {
        stoppFollow();
    } else {
        startFollow();
    }
});

function startFollow() {
    locBtn.classList.add('follow-aktiv');
    locBtn.setAttribute('aria-label', 'Deaktiver GPS-følging');
    let sisteStasjonHentPos = userPos;
    followStopFn = startFollowWatch(
        async (pos) => {
            userPos = pos;
            lagrePosisjon(pos);
            oppdaterUserMarker(pos);
            panTilPosisjon(pos.lat, pos.lon);

            const dlat = (pos.lat - sisteStasjonHentPos.lat) * 111;
            const dlon = (pos.lon - sisteStasjonHentPos.lon) * 111 * Math.cos(pos.lat * Math.PI / 180);
            const km = Math.sqrt(dlat * dlat + dlon * dlon);
            if (km >= 3) {
                sisteStasjonHentPos = pos;
                try {
                    stasjoner = await hentStasjoner(pos.lat, pos.lon);
                    visStasjoner(stasjoner, visStasjonSheet);
                } catch {}
            }
        },
        () => stoppFollow()
    );
}

function stoppFollow() {
    if (!followStopFn) return;
    followStopFn();
    followStopFn = null;
    locBtn.classList.remove('follow-aktiv');
    locBtn.setAttribute('aria-label', 'Hent posisjon');
}

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
                locStatus.textContent = '';
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
