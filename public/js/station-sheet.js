import { oppdaterPris, settKjede, endreNavn, foreslåEndring } from './api.js';
import { getInnstillinger } from './settings.js';
import { getKjedeFarge, getKjedeInitials, getKjedeLogo } from './kjede.js';
import { initOcr, visOcrForRolle, skjulOcrPreview, loggOcrVedLagring } from './ocr.js';

let aktivStasjon = null;
let onPrisOppdatert = null;
let tidligereFokus = null;

const backdrop = document.getElementById('sheet-backdrop');
const sheet = document.getElementById('stasjon-sheet');
const viewEl = document.getElementById('sheet-view');
const editEl = document.getElementById('sheet-edit');

// View-elementer
const navnEl = document.getElementById('sheet-navn');
const kjedeEl = document.getElementById('sheet-kjede');
const badgeEl = document.getElementById('sheet-badge');
const avstandEl = document.getElementById('sheet-avstand');
const prisContainer = document.getElementById('sheet-priser');
const tidEl = document.getElementById('sheet-tid');
const endreBtnEl = document.getElementById('sheet-endre-btn');
const bekreftBtnEl = document.getElementById('sheet-bekreft-btn');
const navigerBtnEl = document.getElementById('sheet-naviger-btn');
const kartBtnEl = document.getElementById('sheet-kart-btn');
const forslagBtnEl = document.getElementById('sheet-forslag-btn');

// Endringsforslag-modal
const forslagModalEl = document.getElementById('forslag-modal');
const forslagBackdropEl = document.getElementById('forslag-backdrop');
const forslagKjedeEl = document.getElementById('forslag-kjede-select');
const forslagNavnEl = document.getElementById('forslag-navn-input');
const forslagNedlagtEl = document.getElementById('forslag-nedlagt-check');
const forslagStatusEl = document.getElementById('forslag-status');
const forslagLagreEl = document.getElementById('forslag-lagre-btn');
const forslagAvbrytEl = document.getElementById('forslag-avbryt-btn');

// Admin-elementer
const adminKjedeEl = document.getElementById('sheet-admin-kjede');
const kjedeSelectEl = document.getElementById('sheet-kjede-select');
const kjedeStatusEl = document.getElementById('sheet-kjede-status');
const kjedelagreBtnEl = document.getElementById('sheet-kjede-lagre-btn');
const navnInputEl = document.getElementById('sheet-navn-input');
const navnStatusEl = document.getElementById('sheet-navn-status');
const navnlagreBtnEl = document.getElementById('sheet-navn-lagre-btn');

// Edit-elementer
const bensinInput = document.getElementById('sheet-bensin-input');
const bensin98Input = document.getElementById('sheet-bensin98-input');
const dieselInput = document.getElementById('sheet-diesel-input');
const dieselAvgiftsfriInput = document.getElementById('sheet-diesel-avgiftsfri-input');
const editStatus = document.getElementById('sheet-edit-status');
const editLagreBtn = document.getElementById('sheet-edit-lagre');
const editAvbrytBtn = document.getElementById('sheet-edit-avbryt');

export function initSheet(onOppdatert) {
    onPrisOppdatert = onOppdatert;

    backdrop.addEventListener('click', lukkSheet);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sheet.classList.contains('open')) lukkSheet();
    });
    endreBtnEl.addEventListener('click', visEditModus);
    bekreftBtnEl.addEventListener('click', bekreftPris);
    editAvbrytBtn.addEventListener('click', visVisModus);
    editLagreBtn.addEventListener('click', lagrePris);
    forslagBtnEl.addEventListener('click', åpneForslagModal);
    forslagAvbrytEl.addEventListener('click', lukkForslagModal);
    forslagBackdropEl.addEventListener('click', lukkForslagModal);
    forslagLagreEl.addEventListener('click', sendEndringsforslag);

    // OCR: kamera-prisgjenkjenning for admin/moderator
    initOcr(
        (priser) => {
            if (priser.bensin != null) bensinInput.value = formatPrisInput(priser.bensin);
            if (priser.bensin98 != null) bensin98Input.value = formatPrisInput(priser.bensin98);
            if (priser.diesel != null) dieselInput.value = formatPrisInput(priser.diesel);
            if (priser.diesel_avgiftsfri != null) dieselAvgiftsfriInput.value = formatPrisInput(priser.diesel_avgiftsfri);
            // Advarsel hvis gjenkjent kjede ikke matcher stasjonens kjede
            if (priser.kjede && aktivStasjon?.kjede && priser.kjede.toLowerCase() !== aktivStasjon.kjede.toLowerCase()) {
                const ocrStatus = document.getElementById('sheet-ocr-status');
                ocrStatus.textContent = `Gjenkjent kjede: ${priser.kjede} (stasjonen er ${aktivStasjon.kjede}) — sjekk at du er på rett stasjon!`;
                ocrStatus.className = 'ocr-status ocr-status-advarsel';
                ocrStatus.removeAttribute('hidden');
            }
        },
        () => ({ forventet_kjede: aktivStasjon?.kjede || '' })
    );
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && forslagModalEl.classList.contains('open')) lukkForslagModal();
    });
    kjedelagreBtnEl.addEventListener('click', lagreKjede);
    navnlagreBtnEl.addEventListener('click', lagreNavn);

    const enterLagre = (e) => { if (e.key === 'Enter') lagrePris(); };
    bensinInput.addEventListener('keydown', enterLagre);
    bensin98Input.addEventListener('keydown', enterLagre);
    dieselInput.addEventListener('keydown', enterLagre);
    dieselAvgiftsfriInput.addEventListener('keydown', enterLagre);

    bensinInput.addEventListener('input', autoKomma);
    bensin98Input.addEventListener('input', autoKomma);
    dieselInput.addEventListener('input', autoKomma);
    dieselAvgiftsfriInput.addEventListener('input', autoKomma);

    const selectAll = (e) => e.target.select();
    bensinInput.addEventListener('focus', selectAll);
    bensin98Input.addEventListener('focus', selectAll);
    dieselInput.addEventListener('focus', selectAll);
    dieselAvgiftsfriInput.addEventListener('focus', selectAll);
}

export function visStasjonSheet(stasjon) {
    tidligereFokus = document.activeElement;
    aktivStasjon = stasjon;
    fyllVisning(stasjon);
    visVisModus();
    const innlogget = window.__innlogget;
    const harPriser = stasjon.bensin != null || stasjon.bensin98 != null || stasjon.diesel != null || stasjon.diesel_avgiftsfri != null;
    endreBtnEl.style.display = innlogget ? '' : 'none';
    bekreftBtnEl.style.display = innlogget && harPriser ? '' : 'none';
    forslagBtnEl.style.display = innlogget ? '' : 'none';

    if (window.__erAdmin) {
        adminKjedeEl.removeAttribute('hidden');
        kjedeSelectEl.value = stasjon.kjede || '';
        kjedeStatusEl.style.display = 'none';
        kjedelagreBtnEl.disabled = false;
        kjedelagreBtnEl.textContent = 'Lagre kjede';
        navnInputEl.value = stasjon.navn || '';
        navnStatusEl.style.display = 'none';
        navnlagreBtnEl.disabled = false;
        navnlagreBtnEl.textContent = 'Lagre navn';
    } else {
        adminKjedeEl.setAttribute('hidden', '');
    }

    sheet.classList.add('open');
    backdrop.classList.add('open');
    setTimeout(() => navnEl.focus(), 100);
}

export function oppdaterSheetStasjon(stasjon) {
    if (aktivStasjon && aktivStasjon.id === stasjon.id) {
        aktivStasjon = stasjon;
        fyllVisning(stasjon);
    }
}

export function refreshSheetInnstillinger() {
    if (aktivStasjon) fyllVisning(aktivStasjon);
}

export function lukkSheet() {
    sheet.classList.remove('open');
    backdrop.classList.remove('open');
    if (tidligereFokus) { tidligereFokus.focus(); tidligereFokus = null; }
}

function fyllVisning(s) {
    navnEl.textContent = s.navn;
    kjedeEl.textContent = s.kjede || '';
    kjedeEl.style.display = s.kjede ? '' : 'none';

    const kjedeEllerNavn = s.kjede || s.navn;
    const logoUrl = getKjedeLogo(kjedeEllerNavn);
    const farge = getKjedeFarge(kjedeEllerNavn);
    const initials = getKjedeInitials(s.kjede || s.navn);
    badgeEl.style.background = farge;
    badgeEl.style.border = '';
    badgeEl.style.position = 'relative';
    badgeEl.innerHTML = `<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff">${initials}</span>` +
        (logoUrl ? `<img src="${logoUrl}" alt="${s.kjede || ''}" style="position:relative;width:32px;height:32px;object-fit:contain" onerror="this.style.display='none'">` : '');

    avstandEl.textContent = s.avstand_m != null ? avstandTekst(s.avstand_m) : '';
    navigerBtnEl.href = `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}`;

    if (s.brukeropprettet) {
        kartBtnEl.href = `https://www.google.com/maps?q=${s.lat},${s.lon}`;
        kartBtnEl.style.display = '';
    } else {
        kartBtnEl.style.display = 'none';
    }

    const inn = getInnstillinger();
    const typer = [
        inn.bensin            && s.har_bensin !== false            ? { label: '95 oktan',       v: s.bensin,             ts: s.bensin_tidspunkt             } : null,
        inn.bensin98          && s.har_bensin98 !== false          ? { label: '98 oktan',       v: s.bensin98,           ts: s.bensin98_tidspunkt           } : null,
        inn.diesel            && s.har_diesel !== false            ? { label: 'Diesel',         v: s.diesel,             ts: s.diesel_tidspunkt             } : null,
        inn.diesel_avgiftsfri && s.har_diesel_avgiftsfri !== false ? { label: 'Avg.fri diesel', v: s.diesel_avgiftsfri,  ts: s.diesel_avgiftsfri_tidspunkt  } : null,
    ].filter(Boolean);
    prisContainer.innerHTML = typer.map((t, i) => `
        ${i > 0 ? '<div class="sheet-divider"></div>' : ''}
        <div class="sheet-pris-blokk">
            <div class="sheet-pris-label">${t.label}</div>
            <div class="sheet-pris-verdi ${t.v == null ? 'ingen' : ''}">${t.v != null ? formatPris(t.v) + ' kr' : '–'}</div>
            ${t.v != null ? `<span class="pris-alder-dot ${prisAlderKlasse(t.ts)}"></span>` : ''}
        </div>`).join('');

    const nyesteTidspunkt = [s.bensin_tidspunkt, s.diesel_tidspunkt, s.bensin98_tidspunkt, s.diesel_avgiftsfri_tidspunkt]
        .filter(Boolean)
        .reduce((a, b) => a > b ? a : b, null);
    if (nyesteTidspunkt) {
        tidEl.textContent = 'Sist oppdatert: ' + formaterTid(nyesteTidspunkt);
        tidEl.style.display = '';
    } else {
        tidEl.style.display = 'none';
    }
}

function visVisModus() {
    viewEl.removeAttribute('hidden');
    editEl.setAttribute('hidden', '');
    visPrisStatus('', null);
    editLagreBtn.disabled = false;
}

function visEditModus() {
    const tittelEl = document.getElementById('sheet-edit-tittel');
    tittelEl.textContent = aktivStasjon.navn || 'Endre pris';
    bensinInput.value = aktivStasjon.bensin != null ? formatPrisInput(aktivStasjon.bensin) : '';
    bensin98Input.value = aktivStasjon.bensin98 != null ? formatPrisInput(aktivStasjon.bensin98) : '';
    dieselInput.value = aktivStasjon.diesel != null ? formatPrisInput(aktivStasjon.diesel) : '';
    dieselAvgiftsfriInput.value = aktivStasjon.diesel_avgiftsfri != null ? formatPrisInput(aktivStasjon.diesel_avgiftsfri) : '';

    const skjul = (id, vis) => document.getElementById(id)?.toggleAttribute('hidden', !vis);
    skjul('sheet-gruppe-bensin',            aktivStasjon.har_bensin !== false);
    skjul('sheet-gruppe-bensin98',          aktivStasjon.har_bensin98 !== false);
    skjul('sheet-gruppe-diesel',            aktivStasjon.har_diesel !== false);
    skjul('sheet-gruppe-diesel-avgiftsfri', aktivStasjon.har_diesel_avgiftsfri !== false);

    visPrisStatus('', null);
    editLagreBtn.disabled = false;
    viewEl.setAttribute('hidden', '');
    editEl.removeAttribute('hidden');
    visOcrForRolle();
    skjulOcrPreview();
    bensinInput.focus();
}

async function bekreftPris() {
    bekreftBtnEl.disabled = true;
    bekreftBtnEl.textContent = 'Bekrefter …';
    try {
        const resultat = await oppdaterPris(
            aktivStasjon.id,
            aktivStasjon.bensin,
            aktivStasjon.diesel,
            aktivStasjon.bensin98,
            aktivStasjon.diesel_avgiftsfri
        );
        if (resultat?.status === 401) {
            bekreftBtnEl.disabled = false;
            bekreftBtnEl.textContent = 'Bekreft priser';
            return;
        }
        const _nd = new Date(), _p = n => String(n).padStart(2, '0');
        const naa = `${_nd.getFullYear()}-${_p(_nd.getMonth()+1)}-${_p(_nd.getDate())} ${_p(_nd.getHours())}:${_p(_nd.getMinutes())}:${_p(_nd.getSeconds())}`;

        const oppdatert = {
            ...aktivStasjon,
            bensin_tidspunkt: aktivStasjon.bensin != null ? naa : aktivStasjon.bensin_tidspunkt,
            diesel_tidspunkt: aktivStasjon.diesel != null ? naa : aktivStasjon.diesel_tidspunkt,
            bensin98_tidspunkt: aktivStasjon.bensin98 != null ? naa : aktivStasjon.bensin98_tidspunkt,
            diesel_avgiftsfri_tidspunkt: aktivStasjon.diesel_avgiftsfri != null ? naa : aktivStasjon.diesel_avgiftsfri_tidspunkt,
        };
        aktivStasjon = oppdatert;
        fyllVisning(oppdatert);
        if (onPrisOppdatert) onPrisOppdatert(oppdatert);
    } catch {
        // still, bare ignorer
    }
    bekreftBtnEl.disabled = false;
    bekreftBtnEl.textContent = 'Bekreft priser';
}


function åpneForslagModal() {
    forslagKjedeEl.value = aktivStasjon.kjede || '';
    forslagNavnEl.value = '';
    forslagNavnEl.placeholder = aktivStasjon.navn || '';
    forslagNedlagtEl.checked = false;
    forslagStatusEl.style.display = 'none';
    forslagLagreEl.disabled = false;
    forslagLagreEl.textContent = 'Send forslag';
    forslagModalEl.classList.add('open');
    forslagBackdropEl.classList.add('open');
    setTimeout(() => forslagNavnEl.focus(), 50);
}

function lukkForslagModal() {
    forslagModalEl.classList.remove('open');
    forslagBackdropEl.classList.remove('open');
}

async function sendEndringsforslag() {
    const navn = forslagNavnEl.value.trim();
    const kjede = forslagKjedeEl.value;
    const nedlagt = forslagNedlagtEl.checked;
    const naaværendeKjede = aktivStasjon.kjede || '';
    const kjedeEndret = kjede !== naaværendeKjede;
    if (!navn && !kjedeEndret && !nedlagt) {
        forslagStatusEl.textContent = 'Fyll ut minst ett felt.';
        forslagStatusEl.style.display = 'block';
        forslagStatusEl.style.color = '#ef4444';
        return;
    }
    forslagLagreEl.disabled = true;
    forslagLagreEl.textContent = 'Sender …';
    forslagStatusEl.style.display = 'none';
    try {
        const res = await foreslåEndring(aktivStasjon.id, navn || null, kjedeEndret ? kjede : null, nedlagt);
        if (res?.status === 401) {
            forslagStatusEl.textContent = 'Du må logge inn for å sende forslag.';
            forslagStatusEl.style.display = 'block';
            forslagStatusEl.style.color = '#ef4444';
            forslagLagreEl.disabled = false;
            forslagLagreEl.textContent = 'Send forslag';
            return;
        }
        forslagStatusEl.textContent = 'Takk! Forslaget er sendt til admin.';
        forslagStatusEl.style.display = 'block';
        forslagStatusEl.style.color = '#22c55e';
        forslagLagreEl.textContent = 'Sendt!';
        setTimeout(lukkForslagModal, 1800);
    } catch {
        forslagStatusEl.textContent = 'Feil ved innsending. Prøv igjen.';
        forslagStatusEl.style.display = 'block';
        forslagStatusEl.style.color = '#ef4444';
        forslagLagreEl.disabled = false;
        forslagLagreEl.textContent = 'Send forslag';
    }
}

async function lagreKjede() {
    const kjede = kjedeSelectEl.value;
    kjedelagreBtnEl.disabled = true;
    kjedelagreBtnEl.textContent = 'Lagrer …';
    kjedeStatusEl.style.display = 'none';
    try {
        await settKjede(aktivStasjon.id, kjede);
        const oppdatert = { ...aktivStasjon, kjede: kjede || null };
        aktivStasjon = oppdatert;
        fyllVisning(oppdatert);
        if (onPrisOppdatert) onPrisOppdatert(oppdatert);
        kjedeStatusEl.textContent = 'Kjede lagret!';
        kjedeStatusEl.style.display = 'block';
        kjedeStatusEl.style.background = 'rgba(34,197,94,0.2)';
        kjedeStatusEl.style.color = '#22c55e';
    } catch {
        kjedeStatusEl.textContent = 'Feil ved lagring. Prøv igjen.';
        kjedeStatusEl.style.display = 'block';
        kjedeStatusEl.style.background = 'rgba(239,68,68,0.2)';
        kjedeStatusEl.style.color = '#ef4444';
    }
    kjedelagreBtnEl.disabled = false;
    kjedelagreBtnEl.textContent = 'Lagre kjede';
}

async function lagreNavn() {
    const navn = navnInputEl.value.trim();
    if (!navn) return;
    navnlagreBtnEl.disabled = true;
    navnlagreBtnEl.textContent = 'Lagrer …';
    navnStatusEl.style.display = 'none';
    try {
        await endreNavn(aktivStasjon.id, navn);
        const oppdatert = { ...aktivStasjon, navn };
        aktivStasjon = oppdatert;
        fyllVisning(oppdatert);
        if (onPrisOppdatert) onPrisOppdatert(oppdatert);
        navnStatusEl.textContent = 'Navn lagret!';
        navnStatusEl.style.display = 'block';
        navnStatusEl.style.background = 'rgba(34,197,94,0.2)';
        navnStatusEl.style.color = '#22c55e';
    } catch {
        navnStatusEl.textContent = 'Feil ved lagring. Prøv igjen.';
        navnStatusEl.style.display = 'block';
        navnStatusEl.style.background = 'rgba(239,68,68,0.2)';
        navnStatusEl.style.color = '#ef4444';
    }
    navnlagreBtnEl.disabled = false;
    navnlagreBtnEl.textContent = 'Lagre navn';
}

async function lagrePris() {
    const bensin = parsePris(bensinInput.value);
    const bensin98 = parsePris(bensin98Input.value);
    const diesel = parsePris(dieselInput.value);
    const diesel_avgiftsfri = parsePris(dieselAvgiftsfriInput.value);

    const noenFyltUt = bensinInput.value.trim() !== '' || bensin98Input.value.trim() !== '' || dieselInput.value.trim() !== '' || dieselAvgiftsfriInput.value.trim() !== '';
    if (!noenFyltUt && !confirm('Fjern alle priser på denne stasjonen?')) return;

    const advarsler = sjekkPrisavvik(aktivStasjon, { bensin, bensin98, diesel, diesel_avgiftsfri });
    if (advarsler.length > 0 && !confirm(advarsler.join('\n') + '\n\nVil du lagre likevel?')) return;

    editLagreBtn.disabled = true;
    visPrisStatus('Lagrer …', false);

    try {
        const resultat = await oppdaterPris(aktivStasjon.id, bensin, diesel, bensin98, diesel_avgiftsfri);
        if (resultat?.status === 401) {
            visPrisStatus('Du må logge inn for å endre priser. <a href="/auth/logg-inn">Logg inn</a>', true);
            editLagreBtn.disabled = false;
            return;
        }
        // Logg OCR-statistikk ved vellykket lagring
        loggOcrVedLagring({ stasjon_id: aktivStasjon.id, bensin, diesel, bensin98, diesel_avgiftsfri });

        const _nd = new Date(), _p = n => String(n).padStart(2, '0');
        const naa = `${_nd.getFullYear()}-${_p(_nd.getMonth()+1)}-${_p(_nd.getDate())} ${_p(_nd.getHours())}:${_p(_nd.getMinutes())}:${_p(_nd.getSeconds())}`;

        const oppdatert = {
            ...aktivStasjon,
            bensin,
            bensin98,
            diesel,
            diesel_avgiftsfri,
            bensin_tidspunkt: bensin !== aktivStasjon.bensin ? naa : aktivStasjon.bensin_tidspunkt,
            diesel_tidspunkt: diesel !== aktivStasjon.diesel ? naa : aktivStasjon.diesel_tidspunkt,
            bensin98_tidspunkt: bensin98 !== aktivStasjon.bensin98 ? naa : aktivStasjon.bensin98_tidspunkt,
            diesel_avgiftsfri_tidspunkt: diesel_avgiftsfri !== aktivStasjon.diesel_avgiftsfri ? naa : aktivStasjon.diesel_avgiftsfri_tidspunkt,
        };
        aktivStasjon = oppdatert;
        fyllVisning(oppdatert);
        if (onPrisOppdatert) onPrisOppdatert(oppdatert);
        visPrisStatus('', null);
        visVisModus();
    } catch (e) {
        visPrisStatus('Feil ved lagring. Prøv igjen.', true);
        editLagreBtn.disabled = false;
    }
}

function visPrisStatus(melding, erFeil) {
    if (!melding) { editStatus.style.display = 'none'; return; }
    editStatus.innerHTML = melding;
    editStatus.style.display = 'block';
    editStatus.style.background = erFeil ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)';
    editStatus.style.color = erFeil ? '#ef4444' : '#22c55e';
}

function formatPris(v) {
    return v.toFixed(2).replace('.', ',');
}

function prisAlderKlasse(tidspunkt) {
    if (!tidspunkt) return 'alder-ingen';
    const timer = (Date.now() - new Date(tidspunkt.replace(' ', 'T') + 'Z').getTime()) / 3600000;
    if (timer < 8) return 'alder-fersk';
    if (timer < 24) return 'alder-gammel';
    if (timer < 48) return 'alder-utdatert';
    return 'alder-kritisk';
}

function formatPrisInput(v) {
    return v.toFixed(2).replace('.', ',');
}

function sjekkPrisavvik(gammel, ny) {
    const typer = [
        { label: '95 oktan',       nøkkel: 'bensin' },
        { label: '98 oktan',       nøkkel: 'bensin98' },
        { label: 'Diesel',         nøkkel: 'diesel' },
        { label: 'Avg.fri diesel', nøkkel: 'diesel_avgiftsfri' },
    ];
    const advarsler = [];
    for (const { label, nøkkel } of typer) {
        const gammelPris = gammel[nøkkel];
        const nyPris = ny[nøkkel];
        if (gammelPris != null && nyPris != null && gammelPris > 0) {
            const avvik = Math.abs(nyPris - gammelPris) / gammelPris;
            if (avvik > 0.3) {
                advarsler.push(`${label}: ${formatPris(gammelPris)} → ${formatPris(nyPris)} kr (${Math.round(avvik * 100)}% endring)`);
            }
        }
    }
    return advarsler;
}

function autoKomma(e) {
    const sletter = e.inputType === 'deleteContentBackward' || e.inputType === 'deleteContentForward';
    const input = e.target;
    let v = input.value;
    // Fjern alt unntatt siffer og komma/punktum
    v = v.replace(/[^\d,.]/g, '');
    // Normaliser: erstatt punktum med komma
    v = v.replace(/\./g, ',');
    // Bare tillat ett komma
    const deler = v.split(',');
    if (deler.length > 2) {
        v = deler[0] + ',' + deler.slice(1).join('');
    }
    if (v.includes(',')) {
        // Har komma: maks to siffer før, maks to etter
        const hel = deler[0].slice(0, 2);
        const des = deler.slice(1).join('').slice(0, 2);
        v = hel + ',' + des;
    } else if (!sletter) {
        // Ingen komma ennå: maks to siffer, legg til komma etter andre (bare ved inntasting)
        v = v.slice(0, 2);
        if (v.length === 2) {
            v = v + ',';
        }
    }
    input.value = v;
}

function parsePris(v) {
    if (!v || v.trim() === '') return null;
    const n = parseFloat(v.replace(',', '.'));
    return isNaN(n) ? null : n;
}

function avstandTekst(m) {
    return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
}

function formaterTid(tidStr) {
    try {
        const d = new Date(tidStr.replace(' ', 'T') + 'Z');
        const diffMs = Date.now() - d.getTime();
        const min = Math.floor(diffMs / 60000);
        const timer = Math.floor(diffMs / 3600000);
        const dager = Math.floor(diffMs / 86400000);
        if (min < 1) return 'akkurat nå';
        if (min < 60) return `for ${min} min siden`;
        if (timer < 3) { const restMin = min - timer * 60; return `for ${timer} time${timer === 1 ? '' : 'r'}${restMin > 0 ? ` og ${restMin} min` : ''} siden`; }
        if (timer < 24) return `for ${timer} time${timer === 1 ? '' : 'r'} siden`;
        if (dager < 7) return `for ${dager} dag${dager === 1 ? '' : 'er'} siden`;
        return d.toLocaleDateString('no', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return tidStr;
    }
}
