import { oppdaterPris, bekreftEnPris, settKjede, endreNavn, settDrivstofftyper, foreslåEndring } from './api.js';
import { getInnstillinger } from './settings.js';
import { getKjedeFarge, getKjedeInitials, getKjedeLogo } from './kjede.js';
import { initOcr, visOcrForRolle, skjulOcrPreview, loggOcrVedLagring, loggOcrVedBekreftelse } from './ocr.js';
import { erFavoritt, toggleFavoritt } from './favoritter.js';

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
const navigerBtnEl = document.getElementById('sheet-naviger-btn');
const kartBtnEl = document.getElementById('sheet-kart-btn');
const favorittBtnEl = document.getElementById('sheet-favoritt-btn');
const forslagBtnEl = document.getElementById('sheet-forslag-btn');

// Endringsforslag-modal
const forslagModalEl = document.getElementById('forslag-modal');
const forslagBackdropEl = document.getElementById('forslag-backdrop');
const forslagKjedeEl = document.getElementById('forslag-kjede-select');
const forslagNavnEl = document.getElementById('forslag-navn-input');
const forslagKommentarEl = document.getElementById('forslag-kommentar-input');
const forslagNedlagtEl = document.getElementById('forslag-nedlagt-check');
const forslagStatusEl = document.getElementById('forslag-status');
const forslagLagreEl = document.getElementById('forslag-lagre-btn');
const forslagAvbrytEl = document.getElementById('forslag-avbryt-btn');

// Admin-elementer
const adminBtnEl = document.getElementById('sheet-admin-btn');
const adminPanelEl = document.getElementById('sheet-admin-panel');
const kjedeSelectEl = document.getElementById('sheet-kjede-select');
const kjedeStatusEl = document.getElementById('sheet-kjede-status');
const kjedelagreBtnEl = document.getElementById('sheet-kjede-lagre-btn');
const navnInputEl = document.getElementById('sheet-navn-input');
const navnStatusEl = document.getElementById('sheet-navn-status');
const navnlagreBtnEl = document.getElementById('sheet-navn-lagre-btn');
const harBensinEl = document.getElementById('sheet-har-bensin');
const harBensin98El = document.getElementById('sheet-har-bensin98');
const harDieselEl = document.getElementById('sheet-har-diesel');
const harDieselAvgiftsfriEl = document.getElementById('sheet-har-diesel-avgiftsfri');
const drivstoffStatusEl = document.getElementById('sheet-drivstoff-status');
const drivstofflagreBtnEl = document.getElementById('sheet-drivstoff-lagre-btn');

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
    prisContainer.addEventListener('click', håndterBekreftKlikk);
    editAvbrytBtn.addEventListener('click', visVisModus);
    editLagreBtn.addEventListener('click', lagrePris);
    forslagBtnEl.addEventListener('click', åpneForslagModal);
    forslagAvbrytEl.addEventListener('click', lukkForslagModal);
    forslagBackdropEl.addEventListener('click', lukkForslagModal);
    forslagLagreEl.addEventListener('click', sendEndringsforslag);
    favorittBtnEl.addEventListener('click', () => {
        if (!aktivStasjon) return;
        toggleFavoritt(aktivStasjon.id);
        oppdaterFavorittKnapp(aktivStasjon.id);
    });
    document.addEventListener('favoritt-endret', (e) => {
        if (aktivStasjon && e.detail.id === aktivStasjon.id) {
            oppdaterFavorittKnapp(aktivStasjon.id);
        }
    });

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
        () => ({
            stasjon_id: aktivStasjon?.id || '',
            forventet_kjede: aktivStasjon?.kjede || '',
        })
    );
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && forslagModalEl.classList.contains('open')) lukkForslagModal();
    });
    adminBtnEl.addEventListener('click', toggleAdminPanel);
    kjedelagreBtnEl.addEventListener('click', lagreKjede);
    navnlagreBtnEl.addEventListener('click', lagreNavn);
    drivstofflagreBtnEl.addEventListener('click', lagreDrivstofftyper);

    const enterLagre = (e) => { if (e.key === 'Enter') lagrePris(); };
    bensinInput.addEventListener('keydown', enterLagre);
    bensin98Input.addEventListener('keydown', enterLagre);
    dieselInput.addEventListener('keydown', enterLagre);
    dieselAvgiftsfriInput.addEventListener('keydown', enterLagre);

    bensinInput.addEventListener('input', autoKomma);
    bensin98Input.addEventListener('input', autoKomma);
    dieselInput.addEventListener('input', autoKomma);
    dieselAvgiftsfriInput.addEventListener('input', autoKomma);

    const markDirty = () => { _inputsDirty = true; };
    bensinInput.addEventListener('input', markDirty);
    bensin98Input.addEventListener('input', markDirty);
    dieselInput.addEventListener('input', markDirty);
    dieselAvgiftsfriInput.addEventListener('input', markDirty);

    const selectAll = (e) => e.target.select();
    bensinInput.addEventListener('focus', selectAll);
    bensin98Input.addEventListener('focus', selectAll);
    dieselInput.addEventListener('focus', selectAll);
    dieselAvgiftsfriInput.addEventListener('focus', selectAll);

    // Flytt sheet opp over tastaturet på iOS
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            const aktiv = document.activeElement;
            if (aktiv && !editEl.hasAttribute('hidden') &&
                (aktiv === bensinInput || aktiv === bensin98Input ||
                 aktiv === dieselInput || aktiv === dieselAvgiftsfriInput)) {
                const tastaturHøyde = window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop;
                sheet.style.bottom = Math.max(0, tastaturHøyde) + 'px';
            } else {
                sheet.style.bottom = '';
            }
        });
    }
}

function oppdaterFavorittKnapp(id) {
    const fav = erFavoritt(id);
    favorittBtnEl.classList.toggle('aktiv', fav);
    favorittBtnEl.setAttribute('aria-pressed', fav ? 'true' : 'false');
    favorittBtnEl.setAttribute('aria-label', fav ? 'Fjern fra favoritter' : 'Legg til som favoritt');
}

export function visStasjonSheet(stasjon) {
    tidligereFokus = document.activeElement;
    aktivStasjon = stasjon;
    fyllVisning(stasjon);
    visVisModus();
    oppdaterFavorittKnapp(stasjon.id);
    const innlogget = window.__innlogget;
    const kanLeggeInn = innlogget || window.__anonymTillatt;
    endreBtnEl.style.display = kanLeggeInn ? '' : 'none';
    forslagBtnEl.style.display = innlogget ? '' : 'none';

    if (window.__erAdmin) {
        adminBtnEl.removeAttribute('hidden');
        adminPanelEl.setAttribute('hidden', '');
        adminBtnEl.setAttribute('aria-expanded', 'false');
        kjedeSelectEl.value = stasjon.kjede || '';
        kjedeStatusEl.style.display = 'none';
        kjedelagreBtnEl.disabled = false;
        kjedelagreBtnEl.textContent = 'Lagre kjede';
        navnInputEl.value = stasjon.navn || '';
        navnStatusEl.style.display = 'none';
        navnlagreBtnEl.disabled = false;
        navnlagreBtnEl.textContent = 'Lagre navn';
        harBensinEl.checked = stasjon.har_bensin !== false;
        harBensin98El.checked = stasjon.har_bensin98 !== false;
        harDieselEl.checked = stasjon.har_diesel !== false;
        harDieselAvgiftsfriEl.checked = stasjon.har_diesel_avgiftsfri !== false;
        drivstoffStatusEl.style.display = 'none';
        drivstofflagreBtnEl.disabled = false;
        drivstofflagreBtnEl.textContent = 'Lagre drivstofftyper';
    } else {
        adminBtnEl.setAttribute('hidden', '');
        adminPanelEl.setAttribute('hidden', '');
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
    if (sheet.classList.contains('edit-modus') && _inputsDirty) {
        if (!confirm('Prisen er ikke lagret. Vil du lukke uten å lagre?')) return;
    }
    sheet.classList.remove('open');
    sheet.classList.remove('edit-modus');
    sheet.style.bottom = '';
    backdrop.classList.remove('open');
    adminPanelEl.setAttribute('hidden', '');
    adminBtnEl.setAttribute('aria-expanded', 'false');
    _bekreftedeTyper.clear();
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
    const innlogget = window.__innlogget;
    const typer = [
        inn.bensin            && s.har_bensin !== false            ? { label: '95 oktan',       nøkkel: 'bensin',             v: s.bensin,            ts: s.bensin_tidspunkt             } : null,
        inn.bensin98          && s.har_bensin98 !== false          ? { label: '98 oktan',       nøkkel: 'bensin98',           v: s.bensin98,          ts: s.bensin98_tidspunkt           } : null,
        inn.diesel            && s.har_diesel !== false            ? { label: 'Diesel',         nøkkel: 'diesel',             v: s.diesel,            ts: s.diesel_tidspunkt             } : null,
        inn.diesel_avgiftsfri && s.har_diesel_avgiftsfri !== false ? { label: 'Avg.fri diesel', nøkkel: 'diesel_avgiftsfri',  v: s.diesel_avgiftsfri, ts: s.diesel_avgiftsfri_tidspunkt  } : null,
    ].filter(Boolean);
    prisContainer.innerHTML = typer.map(t => {
        const bekreftet = _bekreftedeTyper.has(t.nøkkel) ? ' bekreftet' : '';
        return `
        <div class="sheet-pris-rad">
            <div class="sheet-pris-rad-label">
                ${t.v != null ? `<span class="pris-alder-dot ${prisAlderKlasse(t.ts)}"></span>` : ''}
                <span>${t.label}</span>
            </div>
            <div class="sheet-pris-verdi ${t.v == null ? 'ingen' : ''}">${t.v != null ? formatPris(t.v) + ' kr' : '–'}</div>
            ${innlogget && t.v != null
                ? `<button class="btn-bekreft-rad${bekreftet}" data-type="${t.nøkkel}" aria-label="Bekreft ${t.label}">✓</button>`
                : (innlogget ? '<div class="btn-bekreft-rad-placeholder"></div>' : '')}
        </div>`;
    }).join('');

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
    _inputsDirty = false;
    sheet.classList.remove('edit-modus');
    sheet.style.bottom = '';
    viewEl.removeAttribute('hidden');
    editEl.setAttribute('hidden', '');
    visPrisStatus('', null);
    editLagreBtn.disabled = false;
}

function visEditModus() {
    const tittelEl = document.getElementById('sheet-edit-tittel');
    tittelEl.textContent = aktivStasjon.navn || 'Endre pris';
    bensinInput.value = (aktivStasjon.har_bensin !== false && aktivStasjon.bensin != null) ? formatPrisInput(aktivStasjon.bensin) : '';
    bensin98Input.value = (aktivStasjon.har_bensin98 !== false && aktivStasjon.bensin98 != null) ? formatPrisInput(aktivStasjon.bensin98) : '';
    dieselInput.value = (aktivStasjon.har_diesel !== false && aktivStasjon.diesel != null) ? formatPrisInput(aktivStasjon.diesel) : '';
    dieselAvgiftsfriInput.value = (aktivStasjon.har_diesel_avgiftsfri !== false && aktivStasjon.diesel_avgiftsfri != null) ? formatPrisInput(aktivStasjon.diesel_avgiftsfri) : '';

    const skjul = (id, vis) => document.getElementById(id)?.toggleAttribute('hidden', !vis);
    skjul('sheet-gruppe-bensin',            aktivStasjon.har_bensin !== false);
    skjul('sheet-gruppe-bensin98',          aktivStasjon.har_bensin98 !== false);
    skjul('sheet-gruppe-diesel',            aktivStasjon.har_diesel !== false);
    skjul('sheet-gruppe-diesel-avgiftsfri', aktivStasjon.har_diesel_avgiftsfri !== false);

    visPrisStatus('', null);
    editLagreBtn.disabled = false;
    _inputsDirty = false;
    sheet.classList.add('edit-modus');
    viewEl.setAttribute('hidden', '');
    editEl.removeAttribute('hidden');
    visOcrForRolle();
    skjulOcrPreview();
    document.getElementById('sheet-scroll')?.scrollTo({ top: 0, behavior: 'smooth' });
    if (!erTouchMobil()) {
        setTimeout(() => bensinInput.focus(), 80);
    }
}

function erTouchMobil() {
    return window.matchMedia?.('(pointer: coarse)').matches || window.innerWidth < 700;
}

const _bekreftedeTyper = new Set();
let _inputsDirty = false;

async function håndterBekreftKlikk(e) {
    const knapp = e.target.closest('.btn-bekreft-rad');
    if (!knapp) return;
    const type = knapp.dataset.type;
    if (!type) return;

    knapp.disabled = true;
    knapp.textContent = '…';

    try {
        const resultat = await bekreftEnPris(aktivStasjon.id, type);
        if (resultat?.status === 401) {
            knapp.disabled = false;
            knapp.textContent = '✓';
            return;
        }
        const _nd = new Date(), _p = n => String(n).padStart(2, '0');
        const naa = `${_nd.getFullYear()}-${_p(_nd.getMonth()+1)}-${_p(_nd.getDate())} ${_p(_nd.getHours())}:${_p(_nd.getMinutes())}:${_p(_nd.getSeconds())}`;

        const tidspunktFelt = type + '_tidspunkt';
        loggOcrVedBekreftelse(aktivStasjon.id, type, aktivStasjon[type]);
        aktivStasjon = { ...aktivStasjon, [tidspunktFelt]: naa };
        _bekreftedeTyper.add(type);
        fyllVisning(aktivStasjon);
        if (onPrisOppdatert) onPrisOppdatert(aktivStasjon);
    } catch {
        knapp.disabled = false;
        knapp.textContent = '✓';
    }
}


function åpneForslagModal() {
    forslagKjedeEl.value = aktivStasjon.kjede || '';
    forslagNavnEl.value = '';
    forslagNavnEl.placeholder = aktivStasjon.navn || '';
    forslagKommentarEl.value = '';
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
    const kommentar = forslagKommentarEl.value.trim();
    const nedlagt = forslagNedlagtEl.checked;
    const naaværendeKjede = aktivStasjon.kjede || '';
    const kjedeEndret = kjede !== naaværendeKjede;
    if (!navn && !kjedeEndret && !nedlagt && !kommentar) {
        forslagStatusEl.textContent = 'Fyll ut minst ett felt.';
        forslagStatusEl.style.display = 'block';
        forslagStatusEl.style.color = '#ef4444';
        return;
    }
    forslagLagreEl.disabled = true;
    forslagLagreEl.textContent = 'Sender …';
    forslagStatusEl.style.display = 'none';
    try {
        const res = await foreslåEndring(aktivStasjon.id, navn || null, kjedeEndret ? kjede : null, nedlagt, kommentar || null);
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

function toggleAdminPanel() {
    const skjult = adminPanelEl.hasAttribute('hidden');
    if (skjult) {
        adminPanelEl.removeAttribute('hidden');
        adminBtnEl.setAttribute('aria-expanded', 'true');
    } else {
        adminPanelEl.setAttribute('hidden', '');
        adminBtnEl.setAttribute('aria-expanded', 'false');
    }
}

async function lagreDrivstofftyper() {
    drivstofflagreBtnEl.disabled = true;
    drivstofflagreBtnEl.textContent = 'Lagrer …';
    drivstoffStatusEl.style.display = 'none';
    const typer = {
        har_bensin: harBensinEl.checked,
        har_bensin98: harBensin98El.checked,
        har_diesel: harDieselEl.checked,
        har_diesel_avgiftsfri: harDieselAvgiftsfriEl.checked,
    };
    try {
        await settDrivstofftyper(aktivStasjon.id, typer);
        const oppdatert = { ...aktivStasjon, ...typer };
        aktivStasjon = oppdatert;
        fyllVisning(oppdatert);
        if (onPrisOppdatert) onPrisOppdatert(oppdatert);
        drivstoffStatusEl.textContent = 'Drivstofftyper lagret!';
        drivstoffStatusEl.style.display = 'block';
        drivstoffStatusEl.style.background = 'rgba(34,197,94,0.2)';
        drivstoffStatusEl.style.color = '#22c55e';
    } catch {
        drivstoffStatusEl.textContent = 'Feil ved lagring. Prøv igjen.';
        drivstoffStatusEl.style.display = 'block';
        drivstoffStatusEl.style.background = 'rgba(239,68,68,0.2)';
        drivstoffStatusEl.style.color = '#ef4444';
    }
    drivstofflagreBtnEl.disabled = false;
    drivstofflagreBtnEl.textContent = 'Lagre drivstofftyper';
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
        visPrisStatus(e.message || 'Feil ved lagring. Prøv igjen.', true);
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
        const erPrivileged = window.__erAdmin || (window.__roller || []).includes('moderator');
        if (!erPrivileged) return 'over 24 t siden';
        if (dager < 7) return `for ${dager} dag${dager === 1 ? '' : 'er'} siden`;
        return d.toLocaleDateString('no', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return tidStr;
    }
}
