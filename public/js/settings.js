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
};

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
    return { ...base, radiusValg, radiusEgen, radius };
}

export function getInnstillinger() {
    try {
        const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY));
        return normaliserInnstillinger(stored || {});
    } catch { return normaliserInnstillinger(); }
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
        const ny = normaliserInnstillinger({
            bensin: cbBensin.checked, bensin98: cbBensin98.checked, diesel: cbDiesel.checked,
            diesel_avgiftsfri: cbDieselAvgiftsfri.checked,
            radiusValg,
            radiusEgen: radiusEgen.value,
            kartvisning,
        });
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(ny));
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
