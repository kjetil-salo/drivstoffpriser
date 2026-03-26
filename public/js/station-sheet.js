import { oppdaterPris, meldNedlagt } from './api.js';
import { getInnstillinger } from './settings.js';
import { getKjedeFarge, getKjedeInitials, getKjedeLogo } from './kjede.js';

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
const nedlagtBtnEl = document.getElementById('sheet-nedlagt-btn');

// Edit-elementer
const bensinInput = document.getElementById('sheet-bensin-input');
const bensin98Input = document.getElementById('sheet-bensin98-input');
const dieselInput = document.getElementById('sheet-diesel-input');
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
    nedlagtBtnEl.addEventListener('click', rapporterNedlagt);

    const enterLagre = (e) => { if (e.key === 'Enter') lagrePris(); };
    bensinInput.addEventListener('keydown', enterLagre);
    bensin98Input.addEventListener('keydown', enterLagre);
    dieselInput.addEventListener('keydown', enterLagre);

    bensinInput.addEventListener('input', autoKomma);
    bensin98Input.addEventListener('input', autoKomma);
    dieselInput.addEventListener('input', autoKomma);
}

export function visStasjonSheet(stasjon) {
    tidligereFokus = document.activeElement;
    aktivStasjon = stasjon;
    fyllVisning(stasjon);
    visVisModus();
    const innlogget = window.__innlogget;
    const harPriser = stasjon.bensin != null || stasjon.bensin98 != null || stasjon.diesel != null;
    endreBtnEl.style.display = innlogget ? '' : 'none';
    bekreftBtnEl.style.display = innlogget && harPriser ? '' : 'none';
    nedlagtBtnEl.style.display = innlogget ? '' : 'none';
    nedlagtBtnEl.disabled = false;
    nedlagtBtnEl.textContent = 'Meld som nedlagt';
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

    const logoUrl = getKjedeLogo(s.kjede);
    const farge = getKjedeFarge(s.kjede);
    badgeEl.style.background = logoUrl ? '#1e293b' : farge;
    badgeEl.style.border = logoUrl ? `1px solid rgba(148,163,184,0.2)` : '';
    if (logoUrl) {
        badgeEl.innerHTML = `<img src="${logoUrl}" alt="${s.kjede || ''}"
            style="width:32px;height:32px;object-fit:contain"
            onerror="this.parentElement.style.background='${farge}';this.parentElement.style.border='';this.parentElement.textContent='${getKjedeInitials(s.kjede || s.navn)}'">`;
    } else {
        badgeEl.textContent = getKjedeInitials(s.kjede || s.navn);
    }

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
        inn.bensin   ? { label: '95 oktan', v: s.bensin }   : null,
        inn.bensin98 ? { label: '98 oktan', v: s.bensin98 } : null,
        inn.diesel   ? { label: 'Diesel',   v: s.diesel }   : null,
    ].filter(Boolean);
    prisContainer.innerHTML = typer.map((t, i) => `
        ${i > 0 ? '<div class="sheet-divider"></div>' : ''}
        <div class="sheet-pris-blokk">
            <div class="sheet-pris-label">${t.label}</div>
            <div class="sheet-pris-verdi ${t.v == null ? 'ingen' : ''}">${t.v != null ? formatPris(t.v) + ' kr' : '–'}</div>
        </div>`).join('');

    if (s.pris_tidspunkt) {
        tidEl.textContent = 'Sist oppdatert: ' + formaterTid(s.pris_tidspunkt);
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
    bensinInput.value = aktivStasjon.bensin != null ? formatPrisInput(aktivStasjon.bensin) : '';
    bensin98Input.value = aktivStasjon.bensin98 != null ? formatPrisInput(aktivStasjon.bensin98) : '';
    dieselInput.value = aktivStasjon.diesel != null ? formatPrisInput(aktivStasjon.diesel) : '';
    visPrisStatus('', null);
    editLagreBtn.disabled = false;
    viewEl.setAttribute('hidden', '');
    editEl.removeAttribute('hidden');
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
            aktivStasjon.bensin98
        );
        if (resultat?.status === 401) {
            bekreftBtnEl.disabled = false;
            bekreftBtnEl.textContent = 'Bekreft priser';
            return;
        }
        const oppdatert = {
            ...aktivStasjon,
            pris_tidspunkt: new Date().toISOString().slice(0, 19).replace('T', ' '),
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

async function rapporterNedlagt() {
    if (!confirm('Er du sikker på at denne stasjonen er nedlagt? Den meldes til admin for vurdering.')) return;
    nedlagtBtnEl.disabled = true;
    nedlagtBtnEl.textContent = 'Sender …';
    try {
        const resultat = await meldNedlagt(aktivStasjon.id);
        if (resultat?.status === 401) {
            nedlagtBtnEl.disabled = false;
            nedlagtBtnEl.textContent = 'Meld som nedlagt';
            return;
        }
        nedlagtBtnEl.textContent = 'Takk for meldingen!';
    } catch {
        nedlagtBtnEl.textContent = 'Feil – prøv igjen';
        nedlagtBtnEl.disabled = false;
    }
}

async function lagrePris() {
    const bensin = parsePris(bensinInput.value);
    const bensin98 = parsePris(bensin98Input.value);
    const diesel = parsePris(dieselInput.value);

    const noenFyltUt = bensinInput.value.trim() !== '' || bensin98Input.value.trim() !== '' || dieselInput.value.trim() !== '';
    if (!noenFyltUt && !confirm('Fjern alle priser på denne stasjonen?')) return;

    const advarsler = sjekkPrisavvik(aktivStasjon, { bensin, bensin98, diesel });
    if (advarsler.length > 0 && !confirm(advarsler.join('\n') + '\n\nVil du lagre likevel?')) return;

    editLagreBtn.disabled = true;
    visPrisStatus('Lagrer …', false);

    try {
        const resultat = await oppdaterPris(aktivStasjon.id, bensin, diesel, bensin98);
        if (resultat?.status === 401) {
            visPrisStatus('Du må logge inn for å endre priser. <a href="/auth/logg-inn">Logg inn</a>', true);
            editLagreBtn.disabled = false;
            return;
        }
        const oppdatert = {
            ...aktivStasjon,
            bensin,
            bensin98,
            diesel,
            pris_tidspunkt: new Date().toISOString().slice(0, 19).replace('T', ' '),
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

function formatPrisInput(v) {
    return v.toFixed(2).replace('.', ',');
}

function sjekkPrisavvik(gammel, ny) {
    const typer = [
        { label: '95 oktan', nøkkel: 'bensin' },
        { label: '98 oktan', nøkkel: 'bensin98' },
        { label: 'Diesel', nøkkel: 'diesel' },
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
        const d = new Date(tidStr.replace(' ', 'T'));
        const diffMs = Date.now() - d.getTime();
        const min = Math.floor(diffMs / 60000);
        const timer = Math.floor(diffMs / 3600000);
        const dager = Math.floor(diffMs / 86400000);
        if (min < 1) return 'akkurat nå';
        if (min < 60) return `for ${min} min siden`;
        if (timer < 24) return `for ${timer} time${timer === 1 ? '' : 'r'} siden`;
        if (dager < 7) return `for ${dager} dag${dager === 1 ? '' : 'er'} siden`;
        return d.toLocaleDateString('no', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return tidStr;
    }
}

