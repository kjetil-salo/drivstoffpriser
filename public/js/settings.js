import { KJEDE_NAVN } from './kjede.js';

const SETTINGS_KEY = 'drivstoff_innstillinger';
const STANDARD_RADIUS = ['5', '10', '20', '30', '50', '100'];

let deferredInstallPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    const btn = document.getElementById('hjemskjerm-btn');
    if (btn) btn.removeAttribute('hidden');
});

export function triggerInstallPrompt() {
    if (!deferredInstallPrompt) return false;
    deferredInstallPrompt.prompt();
    deferredInstallPrompt.userChoice.then(() => { deferredInstallPrompt = null; });
    return true;
}

export function erInstallbar() {
    return !!deferredInstallPrompt;
}

function _escHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let toastTimer;
function visToast(tekst) {
    const el = document.getElementById('toast');
    el.textContent = tekst;
    el.classList.add('toast-vis');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('toast-vis'), 2200);
}

const STANDARD = {
    bensin: true,
    bensin98: true,
    diesel: true,
    diesel_avgiftsfri: false,
    radius: 30,
    radiusValg: '30',
    radiusEgen: '5',
    kartvisning: 'kompakt',
    rabattkort: [],
};

// ── Rabattkort-hjelpere ───────────────────────────────────────────────────────

function _finnKort(kjede, inn) {
    if (!kjede || !inn || !Array.isArray(inn.rabattkort)) return null;
    return inn.rabattkort.find(k => k.kjede === kjede) || null;
}

export function harRabattKort(kjede, inn) {
    return _finnKort(kjede, inn) !== null;
}

export function getRabattVisning(kjede, inn) {
    const kort = _finnKort(kjede, inn);
    if (!kort) return null;
    if (kort.type === 'pst') return `-${kort.verdi}%`;
    return `-${Math.round(kort.verdi * 100)} øre`;
}

export function getEffektivPris(råpris, kjede, inn) {
    if (råpris == null) return null;
    const kort = _finnKort(kjede, inn);
    if (!kort) return råpris;
    if (kort.type === 'pst') {
        return Math.round(råpris * (1 - kort.verdi / 100) * 100) / 100;
    }
    // type === 'kr'
    return Math.round((råpris - kort.verdi) * 100) / 100;
}

// Bakover-kompatibel – returnerer effektiv kr-rabatt (brukt i eldre kode)
export function getRabattØre(kjede, inn) {
    const kort = _finnKort(kjede, inn);
    if (!kort) return 0;
    if (kort.type === 'kr') return kort.verdi * 100; // kr → øre
    return 0; // pst kan ikke uttrykkes som fast øre uten råpris
}

// ── Normalisering ─────────────────────────────────────────────────────────────

function _migrerGammeltRabattkort(gammel) {
    // Gammelt format: { "Circle K": 50, "Uno-X": 30 } (øre som heltall)
    if (!gammel || typeof gammel !== 'object' || Array.isArray(gammel)) return null;
    const kort = [];
    for (const [kjede, øre] of Object.entries(gammel)) {
        const v = Number(øre);
        if (v > 0) kort.push({ kjede, type: 'kr', verdi: Math.round(v) / 100 });
    }
    return kort;
}

function _normaliserKortliste(liste) {
    if (!Array.isArray(liste)) return [];
    const sett = new Map();
    for (const k of liste) {
        if (!k || typeof k !== 'object') continue;
        if (typeof k.kjede !== 'string' || !k.kjede) continue;
        if (k.type !== 'kr' && k.type !== 'pst') continue;
        const v = Number(k.verdi);
        if (!Number.isFinite(v) || v <= 0) continue;
        const maks = k.type === 'pst' ? 100 : 10;
        sett.set(k.kjede, { kjede: k.kjede, type: k.type, verdi: Math.min(v, maks) });
    }
    return [...sett.values()];
}

export function applyServerPreferences(serverPrefs) {
    if (!serverPrefs || typeof serverPrefs !== 'object') return;
    try {
        const lokale = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
        const merged = normaliserInnstillinger({ ...lokale, ...serverPrefs });
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(merged));
    } catch { /* ignorer */ }
}

function formaterRadius(value) {
    const n = Number.parseFloat(String(value).replace(',', '.'));
    if (!Number.isFinite(n)) return '5';
    return String(Math.min(100, Math.max(0.1, n)));
}

function normaliserInnstillinger(stored = {}) {
    const base = { ...STANDARD, ...stored };
    const lagretRadius = String(base.radius ?? STANDARD.radius);
    const radiusValg = base.radiusValg === 'egen' || STANDARD_RADIUS.includes(String(base.radiusValg))
        ? String(base.radiusValg)
        : (STANDARD_RADIUS.includes(lagretRadius) ? lagretRadius : 'egen');
    const radiusEgen = formaterRadius(base.radiusEgen ?? (radiusValg === 'egen' ? lagretRadius : STANDARD.radiusEgen));
    const radius = radiusValg === 'egen' ? Number.parseFloat(radiusEgen) : Number.parseFloat(radiusValg);

    // Migrér gammelt objekt-format til nytt array-format
    let rabattkort = base.rabattkort;
    if (rabattkort && !Array.isArray(rabattkort)) {
        rabattkort = _migrerGammeltRabattkort(rabattkort) ?? [];
    }
    rabattkort = _normaliserKortliste(rabattkort);

    return { ...base, radiusValg, radiusEgen, radius, rabattkort };
}

export function getInnstillinger() {
    try {
        const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY));
        return normaliserInnstillinger(stored || {});
    } catch { return normaliserInnstillinger(); }
}

function _pushTilServer(innstillinger) {
    fetch('/api/bruker/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(innstillinger),
    }).catch(() => { /* fire-and-forget */ });
}

function _lagreOgVarsle(ny, onChange) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(ny));
    if (window.__innlogget) _pushTilServer(ny);
    if (onChange) onChange(ny);
}

// ── initInnstillinger ─────────────────────────────────────────────────────────

export function initInnstillinger(onChange) {
    const btn = document.getElementById('innstillinger-btn');
    const panel = document.getElementById('innstillinger-panel');
    const cbBensin = document.getElementById('sett-bensin');
    const cbBensin98 = document.getElementById('sett-bensin98');
    const cbDiesel = document.getElementById('sett-diesel');
    const cbDieselAvgiftsfri = document.getElementById('sett-diesel-avgiftsfri');
    const radiusSelect = document.getElementById('sett-radius');
    const radiusEgen = document.getElementById('sett-radius-egen');
    const radVanlig = document.getElementById('sett-kartvisning-vanlig');
    const radKompakt = document.getElementById('sett-kartvisning-kompakt');

    const s = getInnstillinger();
    cbBensin.checked = s.bensin;
    cbBensin98.checked = s.bensin98;
    cbDiesel.checked = s.diesel;
    cbDieselAvgiftsfri.checked = s.diesel_avgiftsfri;
    radiusSelect.value = s.radiusValg;
    radiusEgen.value = s.radiusEgen;
    radiusEgen.hidden = s.radiusValg !== 'egen';
    if (s.kartvisning === 'kompakt') radKompakt.checked = true;
    else radVanlig.checked = true;

    btn.addEventListener('click', () => {
        panel.toggleAttribute('hidden');
        btn.setAttribute('aria-expanded', panel.hasAttribute('hidden') ? 'false' : 'true');
    });

    document.addEventListener('click', (e) => {
        if (panel.hasAttribute('hidden')) return;
        if (!panel.contains(e.target) && !btn.contains(e.target)) {
            panel.setAttribute('hidden', '');
            btn.setAttribute('aria-expanded', 'false');
        }
    });

    function oppdater(cb) {
        if (!cbBensin.checked && !cbBensin98.checked && !cbDiesel.checked && !cbDieselAvgiftsfri.checked) {
            cb.checked = true;
            return;
        }
        lagre();
    }

    function lagre() {
        const kartvisning = document.querySelector('input[name="sett-kartvisning"]:checked')?.value || 'kompakt';
        const radiusValg = radiusSelect.value;
        if (radiusValg === 'egen') radiusEgen.value = formaterRadius(radiusEgen.value);
        const eksisterende = getInnstillinger();
        const ny = normaliserInnstillinger({
            bensin: cbBensin.checked, bensin98: cbBensin98.checked, diesel: cbDiesel.checked,
            diesel_avgiftsfri: cbDieselAvgiftsfri.checked,
            radiusValg,
            radiusEgen: radiusEgen.value,
            kartvisning,
            rabattkort: eksisterende.rabattkort,
        });
        _lagreOgVarsle(ny, onChange);
    }

    cbBensin.addEventListener('change', function () { oppdater(this); });
    cbBensin98.addEventListener('change', function () { oppdater(this); });
    cbDiesel.addEventListener('change', function () { oppdater(this); });
    cbDieselAvgiftsfri.addEventListener('change', function () { oppdater(this); });
    radiusSelect.addEventListener('change', () => {
        radiusEgen.hidden = radiusSelect.value !== 'egen';
        if (radiusSelect.value === 'egen') radiusEgen.focus();
        lagre();
    });
    radiusEgen.addEventListener('change', lagre);
    radiusEgen.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') radiusEgen.blur();
    });
    radVanlig.addEventListener('change', lagre);
    radKompakt.addEventListener('change', lagre);

    // ── Rabattkort-knapp (kun synlig ved innlogging) ───────────────────────────
    const rabattkortBtn = document.getElementById('rabattkort-btn');
    if (rabattkortBtn && window.__innlogget) {
        rabattkortBtn.removeAttribute('hidden');
        _oppdaterRabattkortKnapp(rabattkortBtn, getInnstillinger().rabattkort);
        rabattkortBtn.addEventListener('click', () => {
            panel.setAttribute('hidden', '');
            btn.setAttribute('aria-expanded', 'false');
            _åpneRabattkortModal(onChange);
        });
    }

    // ── Hjemskjerm / del ──────────────────────────────────────────────────────
    const erStandalone = window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone;
    const erIos = /iPad|iPhone|iPod/.test(navigator.userAgent);
    const hjemskjermBtn = document.getElementById('hjemskjerm-btn');
    if (hjemskjermBtn && !erStandalone) {
        if (erIos) hjemskjermBtn.removeAttribute('hidden');
        else if (deferredInstallPrompt) hjemskjermBtn.removeAttribute('hidden');

        hjemskjermBtn.addEventListener('click', async () => {
            if (deferredInstallPrompt) {
                triggerInstallPrompt();
                hjemskjermBtn.setAttribute('hidden', '');
            } else {
                visIosInstallModal();
            }
        });
    }

    const iosBackdrop = document.getElementById('ios-install-backdrop');
    const iosModal = document.getElementById('ios-install-modal');
    if (iosBackdrop && iosModal) {
        document.getElementById('ios-install-lukk')?.addEventListener('click', lukkIosInstallModal);
        iosBackdrop.addEventListener('click', lukkIosInstallModal);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !iosModal.hasAttribute('hidden')) lukkIosInstallModal();
        });
    }

    document.getElementById('del-btn').addEventListener('click', async () => {
        const data = { title: 'Drivstoffprisene', text: 'Finn billigste drivstoff i nærheten', url: 'https://drivstoffprisene.no' };
        if (navigator.share) {
            try {
                await navigator.share(data);
                visToast('✓ Delt!');
            } catch { /* avbrutt av bruker */ }
        } else {
            try {
                await navigator.clipboard.writeText(data.url);
            } catch { /* clipboard ikke tilgjengelig */ }
            visDelModal();
        }
    });

    const delModalBackdrop = document.getElementById('del-modal-backdrop');
    const delModal = document.getElementById('del-modal');
    if (delModalBackdrop && delModal) {
        document.getElementById('del-modal-lukk')?.addEventListener('click', lukkDelModal);
        delModalBackdrop.addEventListener('click', lukkDelModal);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !delModal.hasAttribute('hidden')) lukkDelModal();
        });
    }
}

function _oppdaterRabattkortKnapp(btn, rabattkort) {
    const n = Array.isArray(rabattkort) ? rabattkort.length : 0;
    btn.textContent = n > 0 ? `Rabattkort (${n} aktive)` : 'Rabattkort';
}

// ── Rabattkort-modal ──────────────────────────────────────────────────────────

function _åpneRabattkortModal(onChange) {
    const backdrop = document.getElementById('rabattkort-modal-backdrop');
    const modal = document.getElementById('rabattkort-modal');
    if (!backdrop || !modal) return;

    _renderKortliste(onChange);
    backdrop.removeAttribute('hidden');
    modal.removeAttribute('hidden');
    modal.querySelector('#rabattkort-modal-lukk')?.focus();
}

function _lukkRabattkortModal() {
    document.getElementById('rabattkort-modal-backdrop')?.setAttribute('hidden', '');
    document.getElementById('rabattkort-modal')?.setAttribute('hidden', '');
}

function _renderKortliste(onChange) {
    const liste = document.getElementById('rabattkort-kortliste');
    const btn = document.getElementById('rabattkort-btn');
    if (!liste) return;

    const inn = getInnstillinger();
    const kort = inn.rabattkort;

    if (kort.length === 0) {
        liste.innerHTML = '<p class="rabattkort-tom">Ingen kort registrert ennå.</p>';
    } else {
        liste.innerHTML = kort.map((k, i) => {
            const eKjede = _escHtml(k.kjede);
            const visning = k.type === 'pst' ? `${k.verdi}%` : `${Math.round(k.verdi * 100)} øre/l`;
            return `<div class="rabattkort-element">
                <span class="rabattkort-el-kjede">${eKjede}</span>
                <span class="rabattkort-el-verdi">${_escHtml(visning)}</span>
                <button class="rabattkort-slett-btn" data-index="${i}" aria-label="Slett ${eKjede}-kort">×</button>
            </div>`;
        }).join('');

        liste.querySelectorAll('.rabattkort-slett-btn').forEach(slettBtn => {
            slettBtn.addEventListener('click', () => {
                const idx = parseInt(slettBtn.dataset.index, 10);
                const eksisterende = getInnstillinger();
                const nyListe = eksisterende.rabattkort.filter((_, i) => i !== idx);
                const ny = normaliserInnstillinger({ ...eksisterende, rabattkort: nyListe });
                _lagreOgVarsle(ny, onChange);
                if (btn) _oppdaterRabattkortKnapp(btn, ny.rabattkort);
                _renderKortliste(onChange);
            });
        });
    }
}

// Kobler opp modal-events (kalles én gang ved sidelast)
export function initRabattkortModal(onChange) {
    const backdrop = document.getElementById('rabattkort-modal-backdrop');
    const modal = document.getElementById('rabattkort-modal');
    if (!backdrop || !modal) return;

    // Populer kjede-dropdown
    const kjedeSelect = document.getElementById('rabattkort-kjede-select');
    if (kjedeSelect && kjedeSelect.options.length <= 1) {
        for (const navn of KJEDE_NAVN) {
            const opt = document.createElement('option');
            opt.value = navn;
            opt.textContent = navn;
            kjedeSelect.appendChild(opt);
        }
    }

    const lukkBtn = document.getElementById('rabattkort-modal-lukk');
    lukkBtn?.addEventListener('click', _lukkRabattkortModal);
    backdrop.addEventListener('click', _lukkRabattkortModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hasAttribute('hidden')) _lukkRabattkortModal();
    });

    // Legg til-skjema
    const leggTilBtn = document.getElementById('rabattkort-legg-til-btn');
    leggTilBtn?.addEventListener('click', () => {
        const kjedeEl = document.getElementById('rabattkort-kjede-select');
        const typeEl = document.getElementById('rabattkort-type-select');
        const verdiEl = document.getElementById('rabattkort-verdi-input');
        const statusEl = document.getElementById('rabattkort-status');

        const kjede = kjedeEl?.value;
        const type = typeEl?.value;
        const verdi = Number(verdiEl?.value);

        if (!kjede) { if (statusEl) statusEl.textContent = 'Velg kjede.'; return; }
        if (!Number.isFinite(verdi) || verdi <= 0) {
            if (statusEl) statusEl.textContent = 'Tast inn gyldig verdi.';
            return;
        }
        const maks = type === 'pst' ? 100 : 10;
        if (verdi > maks) {
            if (statusEl) statusEl.textContent = type === 'pst' ? 'Maks 100%.' : 'Maks 10 kr/l.';
            return;
        }

        const eksisterende = getInnstillinger();
        // Overskriv hvis kjeden allerede finnes
        const filtrert = eksisterende.rabattkort.filter(k => k.kjede !== kjede);
        const nyListe = [...filtrert, { kjede, type, verdi }];
        const ny = normaliserInnstillinger({ ...eksisterende, rabattkort: nyListe });
        _lagreOgVarsle(ny, onChange);

        const btn = document.getElementById('rabattkort-btn');
        if (btn) _oppdaterRabattkortKnapp(btn, ny.rabattkort);

        if (statusEl) statusEl.textContent = '';
        if (verdiEl) verdiEl.value = '';
        _renderKortliste(onChange);
    });
}

// ── Del-modal og iOS-install ──────────────────────────────────────────────────

function visDelModal() {
    document.getElementById('del-modal-backdrop').removeAttribute('hidden');
    document.getElementById('del-modal').removeAttribute('hidden');
    document.getElementById('del-modal-lukk').focus();
}

function lukkDelModal() {
    document.getElementById('del-modal-backdrop').setAttribute('hidden', '');
    document.getElementById('del-modal').setAttribute('hidden', '');
}

function visIosInstallModal() {
    document.getElementById('ios-install-backdrop')?.removeAttribute('hidden');
    const modal = document.getElementById('ios-install-modal');
    if (modal) {
        modal.removeAttribute('hidden');
        modal.querySelector('#ios-install-lukk')?.focus();
    }
}

function lukkIosInstallModal() {
    document.getElementById('ios-install-backdrop')?.setAttribute('hidden', '');
    document.getElementById('ios-install-modal')?.setAttribute('hidden', '');
}

