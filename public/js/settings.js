const SETTINGS_KEY = 'drivstoff_innstillinger';

let toastTimer;
function visToast(tekst) {
    const el = document.getElementById('toast');
    el.textContent = tekst;
    el.classList.add('toast-vis');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('toast-vis'), 2200);
}

const STANDARD = { bensin: true, bensin98: true, diesel: true, diesel_avgiftsfri: false, radius: 30, kartvisning: 'kompakt' };

export function getInnstillinger() {
    try {
        const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY));
        return { ...STANDARD, ...stored };
    } catch { return { ...STANDARD }; }
}

export function initInnstillinger(onChange) {
    const btn = document.getElementById('innstillinger-btn');
    const panel = document.getElementById('innstillinger-panel');
    const cbBensin = document.getElementById('sett-bensin');
    const cbBensin98 = document.getElementById('sett-bensin98');
    const cbDiesel = document.getElementById('sett-diesel');
    const cbDieselAvgiftsfri = document.getElementById('sett-diesel-avgiftsfri');
    const radiusSelect = document.getElementById('sett-radius');
    const radVanlig = document.getElementById('sett-kartvisning-vanlig');
    const radKompakt = document.getElementById('sett-kartvisning-kompakt');

    const s = getInnstillinger();
    cbBensin.checked = s.bensin;
    cbBensin98.checked = s.bensin98;
    cbDiesel.checked = s.diesel;
    cbDieselAvgiftsfri.checked = s.diesel_avgiftsfri;
    radiusSelect.value = String(s.radius);
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
        const ny = {
            bensin: cbBensin.checked, bensin98: cbBensin98.checked, diesel: cbDiesel.checked,
            diesel_avgiftsfri: cbDieselAvgiftsfri.checked,
            radius: parseInt(radiusSelect.value, 10),
            kartvisning,
        };
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(ny));
        if (onChange) onChange(ny);
    }

    cbBensin.addEventListener('change', function () { oppdater(this); });
    cbBensin98.addEventListener('change', function () { oppdater(this); });
    cbDiesel.addEventListener('change', function () { oppdater(this); });
    cbDieselAvgiftsfri.addEventListener('change', function () { oppdater(this); });
    radiusSelect.addEventListener('change', lagre);
    radVanlig.addEventListener('change', lagre);
    radKompakt.addEventListener('change', lagre);

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
    document.getElementById('del-modal-lukk').addEventListener('click', lukkDelModal);
    delModalBackdrop.addEventListener('click', lukkDelModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !delModal.hasAttribute('hidden')) lukkDelModal();
    });
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
