/**
 * Hurtigpris – fullskjerm prisjeger-modus.
 * Flyt: Kamera-knapp → ta bilde → fullskjerm modal med stasjonskort + OCR-priser → lagre.
 * Minimalt antall trykk for effektive prisjegere.
 */
import { gjenkjennPriserFraBilde } from './ocr.js';
import { oppdaterPris } from './api.js';
import { getKjedeFarge, getKjedeInitials, getKjedeLogo } from './kjede.js';

// DOM
const modal = document.getElementById('hurtigpris');
const backdrop = document.getElementById('hurtigpris-backdrop');
const fileInput = document.getElementById('hurtigpris-kamera');
const stasjonEl = document.getElementById('hurtigpris-stasjon');
const statusEl = document.getElementById('hurtigpris-status');
const imgEl = document.getElementById('hurtigpris-img');
const feltEl = document.getElementById('hurtigpris-felt');
const bunnEl = document.getElementById('hurtigpris-bunn');
const lagreBtn = document.getElementById('hurtigpris-lagre');
const lukkBtn = document.getElementById('hurtigpris-lukk');
const feilBtn = document.getElementById('hurtigpris-feil-btn');

const hpBensin = document.getElementById('hp-bensin');
const hpBensin98 = document.getElementById('hp-bensin98');
const hpDiesel = document.getElementById('hp-diesel');
const hpAvgfri = document.getElementById('hp-avgfri');

let valgtStasjon = null;
let alleStasjoner = [];
let onLagret = null;
let gpsPosisjon = null;

export function initHurtigpris(onPrisLagret) {
    onLagret = onPrisLagret;

    lukkBtn.addEventListener('click', lukk);
    backdrop.addEventListener('click', lukk);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hasAttribute('hidden')) lukk();
    });

    lagreBtn.addEventListener('click', lagre);
    feilBtn.addEventListener('click', visFeilStasjon);
    fileInput.addEventListener('change', onBilde);

    [hpBensin, hpBensin98, hpDiesel, hpAvgfri].forEach(inp => {
        inp.addEventListener('input', autoKomma);
        inp.addEventListener('focus', (e) => e.target.select());
        inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') lagre(); });
    });
}

/**
 * Åpne kamera. Kalles synkront fra click-handler slik at file input fungerer.
 * Starter GPS-oppdatering i parallell.
 */
export function åpneHurtigKamera(stasjoner) {
    alleStasjoner = stasjoner;
    fileInput.click();

    // Hent fersk GPS i parallell mens brukeren tar bildet
    navigator.geolocation.getCurrentPosition(
        (pos) => {
            gpsPosisjon = { lat: pos.coords.latitude, lon: pos.coords.longitude };
            oppdaterAvstander();
            velgNærmeste();
        },
        () => {
            // GPS feilet – bruk eksisterende avstand_m
            velgNærmeste();
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

// ── Intern logikk ────────────────────────────────

function velgNærmeste() {
    if (!alleStasjoner.length) return;
    let nærmeste = alleStasjoner[0];
    for (const s of alleStasjoner) {
        if (s.avstand_m != null && (nærmeste.avstand_m == null || s.avstand_m < nærmeste.avstand_m)) {
            nærmeste = s;
        }
    }
    fyllStasjonskort(nærmeste);
}

function oppdaterAvstander() {
    if (!gpsPosisjon) return;
    for (const s of alleStasjoner) {
        s.avstand_m = beregnAvstand(gpsPosisjon.lat, gpsPosisjon.lon, s.lat, s.lon);
    }
}

function beregnAvstand(lat1, lon1, lat2, lon2) {
    const dlat = (lat2 - lat1) * 111320;
    const dlon = (lon2 - lon1) * 111320 * Math.cos(lat1 * Math.PI / 180);
    return Math.round(Math.sqrt(dlat * dlat + dlon * dlon));
}

async function onBilde(e) {
    const fil = e.target.files?.[0];
    if (!fil) return;

    vis();
    imgEl.src = URL.createObjectURL(fil);
    imgEl.removeAttribute('hidden');
    visStatus('Analyserer pristavle …', 'loading');

    try {
        const resultat = await gjenkjennPriserFraBilde(
            fil,
            (tekst) => {
                visStatus(tekst, 'loading');
            },
            { forventet_kjede: valgtStasjon?.kjede || '' }
        );

        if (resultat.priser) {
            fyllPriser(resultat.priser);
            const kildeTekst = resultat.kilde === 'tesseract' ? 'lokal OCR' : 'AI';
            visStatus(`Priser gjenkjent (${kildeTekst})`, 'ok');
        } else {
            visStatus('Fant ingen priser — tast inn manuelt', 'advarsel');
        }
    } catch {
        visStatus('Kunne ikke gjenkjenne priser. Tast inn manuelt.', 'feil');
    }

    visPrisfelt();
    fileInput.value = '';
}

function vis() {
    modal.removeAttribute('hidden');
    backdrop.removeAttribute('hidden');
    document.body.style.overflow = 'hidden';
}

function lukk() {
    modal.setAttribute('hidden', '');
    backdrop.setAttribute('hidden', '');
    document.body.style.overflow = '';
    // Reset
    imgEl.setAttribute('hidden', '');
    feltEl.setAttribute('hidden', '');
    bunnEl.setAttribute('hidden', '');
    statusEl.textContent = '';
    statusEl.className = 'hurtigpris-status';
    hpBensin.value = '';
    hpBensin98.value = '';
    hpDiesel.value = '';
    hpAvgfri.value = '';
    lagreBtn.disabled = false;
    lagreBtn.textContent = 'Lagre pris';
    feilBtn.style.display = '';
    valgtStasjon = null;
    gpsPosisjon = null;
    // Fjern evt. feil-stasjon-liste
    const liste = modal.querySelector('.hurtigpris-stasjonliste');
    if (liste) liste.remove();
}

function visStatus(tekst, type) {
    statusEl.textContent = tekst;
    statusEl.className = 'hurtigpris-status hurtigpris-status-' + type;
}

function fyllStasjonskort(stasjon) {
    valgtStasjon = stasjon;
    const kjedeEllerNavn = stasjon.kjede || stasjon.navn;
    const logo = getKjedeLogo(kjedeEllerNavn);
    const farge = getKjedeFarge(kjedeEllerNavn);
    const initials = getKjedeInitials(kjedeEllerNavn);
    const avstand = avstandTekst(stasjon.avstand_m);

    stasjonEl.innerHTML = `
        <div class="hurtigpris-badge" style="background:${farge}">
            <span>${initials}</span>
            ${logo ? `<img src="${logo}" alt="" onerror="this.style.display='none'">` : ''}
        </div>
        <div class="hurtigpris-info">
            <div class="hurtigpris-navn">${stasjon.navn}</div>
            ${stasjon.kjede ? `<div class="hurtigpris-kjede">${stasjon.kjede}</div>` : ''}
            ${avstand ? `<div class="hurtigpris-avstand">${avstand}</div>` : ''}
        </div>`;
}

function visPrisfelt() {
    feltEl.removeAttribute('hidden');
    bunnEl.removeAttribute('hidden');
    hpBensin.focus();
}

function fyllPriser(priser) {
    hpBensin.value = priser.bensin != null ? priser.bensin.toFixed(2).replace('.', ',') : '';
    hpBensin98.value = priser.bensin98 != null ? priser.bensin98.toFixed(2).replace('.', ',') : '';
    hpDiesel.value = priser.diesel != null ? priser.diesel.toFixed(2).replace('.', ',') : '';
    hpAvgfri.value = priser.diesel_avgiftsfri != null ? priser.diesel_avgiftsfri.toFixed(2).replace('.', ',') : '';
}

async function lagre() {
    if (!valgtStasjon) {
        visStatus('Ingen stasjon valgt', 'feil');
        return;
    }

    const bensin = parsePris(hpBensin.value);
    const bensin98 = parsePris(hpBensin98.value);
    const diesel = parsePris(hpDiesel.value);
    const diesel_avgiftsfri = parsePris(hpAvgfri.value);

    if (bensin == null && bensin98 == null && diesel == null && diesel_avgiftsfri == null) {
        visStatus('Fyll inn minst én pris', 'feil');
        return;
    }

    lagreBtn.disabled = true;
    lagreBtn.textContent = 'Lagrer …';

    try {
        const resultat = await oppdaterPris(valgtStasjon.id, bensin, diesel, bensin98, diesel_avgiftsfri);
        if (resultat?.status === 401) {
            visStatus('Ikke innlogget', 'feil');
            lagreBtn.disabled = false;
            lagreBtn.textContent = 'Lagre pris';
            return;
        }

        const _nd = new Date(), _p = n => String(n).padStart(2, '0');
        const naa = `${_nd.getFullYear()}-${_p(_nd.getMonth()+1)}-${_p(_nd.getDate())} ${_p(_nd.getHours())}:${_p(_nd.getMinutes())}:${_p(_nd.getSeconds())}`;

        const oppdatert = {
            ...valgtStasjon,
            bensin, bensin98, diesel, diesel_avgiftsfri,
            bensin_tidspunkt: bensin != null ? naa : valgtStasjon.bensin_tidspunkt,
            diesel_tidspunkt: diesel != null ? naa : valgtStasjon.diesel_tidspunkt,
            bensin98_tidspunkt: bensin98 != null ? naa : valgtStasjon.bensin98_tidspunkt,
            diesel_avgiftsfri_tidspunkt: diesel_avgiftsfri != null ? naa : valgtStasjon.diesel_avgiftsfri_tidspunkt,
        };

        if (onLagret) onLagret(oppdatert);

        visStatus('Lagret!', 'ok');
        lagreBtn.textContent = 'Lagret!';
        setTimeout(lukk, 1000);
    } catch {
        visStatus('Feil ved lagring. Prøv igjen.', 'feil');
        lagreBtn.disabled = false;
        lagreBtn.textContent = 'Lagre pris';
    }
}

function visFeilStasjon() {
    if (!alleStasjoner.length) return;

    // Fjern eksisterende liste
    const eksisterende = modal.querySelector('.hurtigpris-stasjonliste');
    if (eksisterende) { eksisterende.remove(); feilBtn.style.display = ''; return; }

    const sortert = [...alleStasjoner].sort((a, b) => (a.avstand_m ?? 99999) - (b.avstand_m ?? 99999));
    const topp = sortert.slice(0, 8);

    const liste = document.createElement('div');
    liste.className = 'hurtigpris-stasjonliste';
    liste.innerHTML = topp.map(s => {
        const aktiv = valgtStasjon && s.id === valgtStasjon.id;
        return `<button class="hurtigpris-valg ${aktiv ? 'aktiv' : ''}" data-id="${s.id}">
            <span>${s.navn}</span>
            <span class="hurtigpris-valg-avstand">${avstandTekst(s.avstand_m)}</span>
        </button>`;
    }).join('');

    feilBtn.style.display = 'none';
    bunnEl.after(liste);

    liste.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-id]');
        if (!btn) return;
        const stasjon = alleStasjoner.find(s => s.id === parseInt(btn.dataset.id));
        if (stasjon) {
            fyllStasjonskort(stasjon);
            liste.remove();
            feilBtn.style.display = '';
        }
    });
}

function avstandTekst(m) {
    if (m == null) return '';
    return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
}

function autoKomma(e) {
    const sletter = e.inputType === 'deleteContentBackward' || e.inputType === 'deleteContentForward';
    const input = e.target;
    let v = input.value.replace(/[^\d,.]/g, '').replace(/\./g, ',');
    const deler = v.split(',');
    if (deler.length > 2) v = deler[0] + ',' + deler.slice(1).join('');
    if (v.includes(',')) {
        v = deler[0].slice(0, 2) + ',' + deler.slice(1).join('').slice(0, 2);
    } else if (!sletter) {
        v = v.slice(0, 2);
        if (v.length === 2) v += ',';
    }
    input.value = v;
}

function parsePris(v) {
    if (!v || v.trim() === '') return null;
    const n = parseFloat(v.replace(',', '.'));
    return isNaN(n) ? null : n;
}
