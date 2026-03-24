const SETTINGS_KEY = 'drivstoff_innstillinger';
const STANDARD = { bensin: true, bensin98: true, diesel: true };

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

    const s = getInnstillinger();
    cbBensin.checked = s.bensin;
    cbBensin98.checked = s.bensin98;
    cbDiesel.checked = s.diesel;

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
        if (!cbBensin.checked && !cbBensin98.checked && !cbDiesel.checked) {
            cb.checked = true;
            return;
        }
        const ny = { bensin: cbBensin.checked, bensin98: cbBensin98.checked, diesel: cbDiesel.checked };
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(ny));
        if (onChange) onChange(ny);
    }

    cbBensin.addEventListener('change', function () { oppdater(this); });
    cbBensin98.addEventListener('change', function () { oppdater(this); });
    cbDiesel.addEventListener('change', function () { oppdater(this); });
}
