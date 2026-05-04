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
    rabattkort: {},
};

// Kjeder som støtter rabattkort – nøkkel = kjedenavn i DB
const RABATTKORT_KJEDER = ['Circle K', 'Uno-X', 'YX', 'Esso', 'St1'];

export function getRabattØre(kjede, inn) {
    if (!kjede || !inn || !inn.rabattkort) return 0;
    return Number(inn.rabattkort[kjede]) || 0;
}

export function getEffektivPris(råpris, kjede, inn) {
    if (råpris == null) return null;
    const øre = getRabattØre(kjede, inn);
    if (øre === 0) return råpris;
    return Math.round((råpris - øre / 100) * 100) / 100;
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
    // Normaliser rabattkort: kun gyldige kjeder, øre som tall >= 0
    const rabattkort = {};
    if (base.rabattkort && typeof base.rabattkort === 'object') {
        for (const kjede of RABATTKORT_KJEDER) {
            const v = Number(base.rabattkort[kjede]);
            if (v > 0) rabattkort[kjede] = v;
        }
    }
    return { ...base, radiusValg, radiusEgen, radius, rabattkort };
}

export function getInnstillinger() {
    try {
        const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY));
        return normaliserInnstillinger(stored || {});
    } catch { return normaliserInnstillinger(); }
}

function _pushTilServer(innstillinger) {
    const payload = { ...innstillinger };
    fetch('/api/bruker/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }).catch(() => { /* fire-and-forget, ignorer nettverksfeil */ });
}

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

    // Ikke bruk stopPropagation – sjekk panel-state i stedet (iOS-kompatibelt)
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
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(ny));
        if (window.__innlogget) _pushTilServer(ny);
        if (onChange) onChange(ny);
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

    // ── Rabattkort (kun synlig ved innlogging) ────────────────────────────
    const rabattkortSeksjon = document.getElementById('rabattkort-seksjon');
    const rabattkortListe = document.getElementById('rabattkort-liste');
    if (rabattkortSeksjon && rabattkortListe && window.__innlogget) {
        rabattkortSeksjon.removeAttribute('hidden');
        const gjeldende = s.rabattkort || {};
        rabattkortListe.innerHTML = RABATTKORT_KJEDER.map(kjede => {
            const øre = gjeldende[kjede] || '';
            const id = `rabattkort-${kjede.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
            return `<div class="rabattkort-rad" data-kjede="${kjede}">
                <span class="rabattkort-kjede">${kjede}</span>
                <label class="rabattkort-label">
                    <input type="number" class="rabattkort-input" id="${id}" min="0" max="500" step="1"
                        inputmode="numeric" placeholder="øre/l" value="${øre}"
                        aria-label="${kjede} rabatt i øre per liter">
                    <span class="rabattkort-enhet">øre/l</span>
                </label>
            </div>`;
        }).join('');

        function lagreRabattkort() {
            const nyRabattkort = {};
            rabattkortListe.querySelectorAll('.rabattkort-rad').forEach(rad => {
                const kjede = rad.dataset.kjede;
                const input = rad.querySelector('.rabattkort-input');
                const v = Number(input.value);
                if (v > 0) nyRabattkort[kjede] = v;
            });
            const eksisterende = getInnstillinger();
            const ny = normaliserInnstillinger({ ...eksisterende, rabattkort: nyRabattkort });
            localStorage.setItem(SETTINGS_KEY, JSON.stringify(ny));
            if (window.__innlogget) _pushTilServer(ny);
            if (onChange) onChange(ny);
        }

        rabattkortListe.querySelectorAll('.rabattkort-input').forEach(input => {
            input.addEventListener('change', lagreRabattkort);
            input.addEventListener('blur', lagreRabattkort);
        });
    }

    const erStandalone = window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone;
    const erIos = /iPad|iPhone|iPod/.test(navigator.userAgent);
    const erAndroid = /Android/.test(navigator.userAgent);
    const hjemskjermBtn = document.getElementById('hjemskjerm-btn');
    if (hjemskjermBtn && !erStandalone) {
        if (erIos) hjemskjermBtn.removeAttribute('hidden');
        else if (deferredInstallPrompt) hjemskjermBtn.removeAttribute('hidden'); // Android + desktop Chrome/Edge

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
