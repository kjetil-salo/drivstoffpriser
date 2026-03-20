import { oppdaterPris } from './api.js';

let aktivStasjon = null;
let onPrisOppdatert = null;

const backdrop = document.getElementById('sheet-backdrop');
const sheet = document.getElementById('stasjon-sheet');
const viewEl = document.getElementById('sheet-view');
const editEl = document.getElementById('sheet-edit');

// View-elementer
const navnEl = document.getElementById('sheet-navn');
const kjedeEl = document.getElementById('sheet-kjede');
const badgeEl = document.getElementById('sheet-badge');
const avstandEl = document.getElementById('sheet-avstand');
const bensinEl = document.getElementById('sheet-bensin');
const dieselEl = document.getElementById('sheet-diesel');
const tidEl = document.getElementById('sheet-tid');
const endreBtnEl = document.getElementById('sheet-endre-btn');

// Edit-elementer
const bensinInput = document.getElementById('sheet-bensin-input');
const dieselInput = document.getElementById('sheet-diesel-input');
const editStatus = document.getElementById('sheet-edit-status');
const editLagreBtn = document.getElementById('sheet-edit-lagre');
const editAvbrytBtn = document.getElementById('sheet-edit-avbryt');

export function initSheet(onOppdatert) {
    onPrisOppdatert = onOppdatert;

    backdrop.addEventListener('click', lukkSheet);
    endreBtnEl.addEventListener('click', visEditModus);
    editAvbrytBtn.addEventListener('click', visVisModus);
    editLagreBtn.addEventListener('click', lagrePris);
}

export function visStasjonSheet(stasjon) {
    aktivStasjon = stasjon;
    fyllVisning(stasjon);
    visVisModus();
    endreBtnEl.style.display = window.__innlogget ? '' : 'none';
    sheet.classList.add('open');
    backdrop.classList.add('open');
}

export function oppdaterSheetStasjon(stasjon) {
    if (aktivStasjon && aktivStasjon.id === stasjon.id) {
        aktivStasjon = stasjon;
        fyllVisning(stasjon);
    }
}

export function lukkSheet() {
    sheet.classList.remove('open');
    backdrop.classList.remove('open');
}

function fyllVisning(s) {
    navnEl.textContent = s.navn;
    kjedeEl.textContent = s.kjede || '';
    kjedeEl.style.display = s.kjede ? '' : 'none';

    badgeEl.textContent = getKjedeInitials(s.kjede || s.navn);
    badgeEl.style.background = getKjedeFarge(s.kjede);

    avstandEl.textContent = s.avstand_m != null ? avstandTekst(s.avstand_m) : '';

    bensinEl.textContent = s.bensin != null ? formatPris(s.bensin) + ' kr' : '–';
    bensinEl.classList.toggle('ingen', s.bensin == null);

    dieselEl.textContent = s.diesel != null ? formatPris(s.diesel) + ' kr' : '–';
    dieselEl.classList.toggle('ingen', s.diesel == null);

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
    dieselInput.value = aktivStasjon.diesel != null ? formatPrisInput(aktivStasjon.diesel) : '';
    visPrisStatus('', null);
    editLagreBtn.disabled = false;
    viewEl.setAttribute('hidden', '');
    editEl.removeAttribute('hidden');
    bensinInput.focus();
}

async function lagrePris() {
    const bensin = parsePris(bensinInput.value);
    const diesel = parsePris(dieselInput.value);

    if (bensin === null && diesel === null) {
        visPrisStatus('Skriv inn minst én pris', true);
        return;
    }

    editLagreBtn.disabled = true;
    visPrisStatus('Lagrer …', false);

    try {
        await oppdaterPris(aktivStasjon.id, bensin, diesel);
        const oppdatert = {
            ...aktivStasjon,
            bensin,
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
    editStatus.textContent = melding;
    editStatus.style.display = 'block';
    editStatus.style.background = erFeil ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)';
    editStatus.style.color = erFeil ? '#ef4444' : '#22c55e';
}

function formatPris(v) {
    return v.toFixed(2).replace('.', ',');
}

function formatPrisInput(v) {
    return v.toFixed(2);
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
        const nå = new Date();
        const erIDag = d.toDateString() === nå.toDateString();
        const tid = d.toLocaleTimeString('no', { hour: '2-digit', minute: '2-digit' });
        if (erIDag) return `i dag ${tid}`;
        return d.toLocaleDateString('no', { day: 'numeric', month: 'short' }) + ' ' + tid;
    } catch {
        return tidStr;
    }
}

function getKjedeFarge(kjede) {
    const k = (kjede || '').toLowerCase();
    if (k.includes('circle k') || k.includes('circlek')) return '#f97316';
    if (k.includes('uno-x') || k.includes('unox') || k.includes('uno x')) return '#16a34a';
    if (k.includes('yx')) return '#dc2626';
    if (k.includes('esso')) return '#2563eb';
    if (k.includes('shell')) return '#ca8a04';
    if (k.includes('preem')) return '#059669';
    if (k.includes('st1')) return '#7c3aed';
    return '#475569';
}

function getKjedeInitials(tekst) {
    if (!tekst) return '⛽';
    const ord = tekst.trim().split(/[\s-]+/);
    if (ord.length === 1) return tekst.substring(0, 2).toUpperCase();
    return ord.map(o => o[0]).join('').substring(0, 3).toUpperCase();
}
