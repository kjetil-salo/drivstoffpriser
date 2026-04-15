import { finnBilligstLangsRute } from './api.js';
import { hentPosisjon } from './location.js';

const DRIVSTOFF_NAVN = {
    bensin: '95 oktan',
    bensin98: '98 oktan',
    diesel: 'Diesel',
    diesel_avgiftsfri: 'Avg.fri diesel',
};

let fraPos = null;
let viaPos = null;
let tilPos = null;
let onResultat = null;
let onStasjonKlikk = null;
let onFjernRute = null;
let getStartPos = null;

const el = {
    btn: document.getElementById('route-btn'),
    backdrop: document.getElementById('rutepris-backdrop'),
    sheet: document.getElementById('rutepris-sheet'),
    lukk: document.getElementById('rutepris-lukk'),
    fra: document.getElementById('rutepris-fra'),
    fraResultater: document.getElementById('rutepris-fra-resultater'),
    til: document.getElementById('rutepris-til'),
    tilResultater: document.getElementById('rutepris-til-resultater'),
    via: document.getElementById('rutepris-via'),
    viaResultater: document.getElementById('rutepris-via-resultater'),
    her: document.getElementById('rutepris-her'),
    drivstoff: document.getElementById('rutepris-drivstoff'),
    avvik: document.getElementById('rutepris-avvik'),
    sok: document.getElementById('rutepris-sok'),
    status: document.getElementById('rutepris-status'),
    handlinger: document.getElementById('rutepris-handlinger'),
    visKart: document.getElementById('rutepris-vis-kart'),
    fjern: document.getElementById('rutepris-fjern'),
    resultater: document.getElementById('rutepris-resultater'),
};

export function initRuteplanlegger(options) {
    onResultat = options.onResultat;
    onStasjonKlikk = options.onStasjonKlikk;
    onFjernRute = options.onFjernRute;
    getStartPos = options.getStartPos;

    el.btn.addEventListener('click', apne);
    el.lukk.addEventListener('click', lukk);
    el.backdrop.addEventListener('click', lukk);
    el.her.addEventListener('click', brukMinPosisjon);
    el.sok.addEventListener('click', sokRute);
    el.visKart.addEventListener('click', lukk);
    el.fjern.addEventListener('click', fjernRute);
    el.til.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sokRute();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && el.sheet.classList.contains('open')) lukk();
    });

    initAutocomplete(el.fra, el.fraResultater, (sted) => {
        fraPos = sted;
        el.fra.value = sted.navn;
    });
    initAutocomplete(el.via, el.viaResultater, (sted) => {
        viaPos = sted;
        el.via.value = sted.navn;
    });
    initAutocomplete(el.til, el.tilResultater, (sted) => {
        tilPos = sted;
        el.til.value = sted.navn;
    });
}

function apne() {
    const pos = getStartPos?.();
    if (pos) {
        fraPos = pos;
        el.fra.value = 'Min posisjon';
    }
    el.backdrop.classList.add('open');
    el.sheet.classList.add('open');
    setTimeout(() => (el.til.value ? el.sok.focus() : el.til.focus()), 80);
}

function lukk() {
    el.backdrop.classList.remove('open');
    el.sheet.classList.remove('open');
}

function brukMinPosisjon() {
    settStatus('Henter posisjon …');
    hentPosisjon(
        (pos) => {
            fraPos = pos;
            el.fra.value = 'Min posisjon';
            settStatus('');
        },
        () => settStatus('Fikk ikke hentet posisjon. Skriv startsted i stedet.', true),
        (melding) => settStatus(melding)
    );
}

async function sokRute() {
    const fra = rutepunktFraInput(el.fra, fraPos);
    const via = rutepunktFraInput(el.via, viaPos);
    const til = rutepunktFraInput(el.til, tilPos);
    if (!fra || !til) {
        settStatus('Skriv inn både fra og til.', true);
        return;
    }

    el.sok.disabled = true;
    el.resultater.innerHTML = '';
    el.handlinger.hidden = true;
    settStatus('Beregner rute og sjekker priser …');
    try {
        const data = await finnBilligstLangsRute({
            fra,
            til,
            via,
            drivstoff: el.drivstoff.value,
            maksAvvikKm: el.avvik.value,
        });
        onResultat(data);
        visResultater(data);
        el.handlinger.hidden = !data.treff.length;
        settStatus(lagStatusTekst(data), !data.treff.length);
    } catch (e) {
        settStatus(e.message || 'Kunne ikke beregne rute nå.', true);
    } finally {
        el.sok.disabled = false;
    }
}

function fjernRute() {
    onFjernRute?.();
    el.resultater.innerHTML = '';
    el.handlinger.hidden = true;
    settStatus('Ruten er fjernet fra kartet.');
    lukk();
}

function lagStatusTekst(data) {
    const km = Math.round(data.rute?.km || 0);
    const minutter = Math.round(data.rute?.min || 0);
    if (!data.treff.length) {
        return `Fant ingen priser innenfor ${Number(data.maks_avvik_km || 0).toLocaleString('no-NO')} km fra ruta.`;
    }
    return `${data.treff.length} treff nær ruta, ca. ${km} km og ${minutter} min.`;
}

function visResultater(data) {
    if (!data.treff.length) {
        el.resultater.innerHTML = '<p class="rutepris-tom">Prøv litt større avstand fra ruta.</p>';
        return;
    }
    const drivstoff = DRIVSTOFF_NAVN[data.drivstoff] || 'Pris';
    el.resultater.innerHTML = data.treff.slice(0, 8).map((s, i) => `
        <button class="rutepris-resultat" type="button" data-id="${s.id}">
            <span class="rutepris-rang">${i + 1}</span>
            <span class="rutepris-stasjon">
                <strong>${escapeHtml(s.navn)}</strong>
                <small>${escapeHtml(s.kjede || '')}${s.kjede ? ' · ' : ''}${s.avvik_m} m fra rute</small>
            </span>
            <span class="rutepris-pris">
                <strong>${Number(s.pris).toFixed(2)}</strong>
                <small>${drivstoff}</small>
            </span>
        </button>
    `).join('');
    el.resultater.querySelectorAll('.rutepris-resultat').forEach((rad) => {
        rad.addEventListener('click', () => {
            const stasjon = data.treff.find(s => String(s.id) === rad.dataset.id);
            if (stasjon) {
                lukk();
                onStasjonKlikk(stasjon);
            }
        });
    });
}

function settStatus(tekst, feil = false) {
    el.status.textContent = tekst;
    el.status.classList.toggle('feil', Boolean(feil));
}

function initAutocomplete(input, resultEl, onVelg) {
    let timer = null;
    let resultater = [];
    let aktiv = -1;

    function lukkListe() {
        resultEl.hidden = true;
        resultEl.innerHTML = '';
        aktiv = -1;
    }

    function marker() {
        resultEl.querySelectorAll('.rutepris-autocomplete-rad').forEach((rad, i) => {
            rad.classList.toggle('aktiv', i === aktiv);
        });
    }

    function velg(i) {
        const sted = resultater[i];
        if (!sted) return;
        onVelg(sted);
        lukkListe();
    }

    async function sok(q) {
        try {
            const resp = await fetch(`/api/stedssok?q=${encodeURIComponent(q)}`);
            resultater = await resp.json();
            aktiv = -1;
            if (!resultater.length) {
                resultEl.innerHTML = '<div class="rutepris-autocomplete-tom">Ingen treff</div>';
                resultEl.hidden = false;
                return;
            }
            resultEl.innerHTML = resultater.map((r, i) =>
                `<div class="rutepris-autocomplete-rad" data-i="${i}">${escapeHtml(r.navn)}</div>`
            ).join('');
            resultEl.hidden = false;
            resultEl.querySelectorAll('.rutepris-autocomplete-rad').forEach((rad) => {
                rad.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    velg(Number(rad.dataset.i));
                });
            });
        } catch {
            lukkListe();
        }
    }

    input.addEventListener('focus', () => {
        if (input.value) input.select();
    });

    input.addEventListener('input', () => {
        if (input === el.fra) fraPos = null;
        if (input === el.via) viaPos = null;
        if (input === el.til) tilPos = null;
        clearTimeout(timer);
        const q = input.value.trim();
        if (q.length < 2 || q === 'Min posisjon') {
            lukkListe();
            return;
        }
        timer = setTimeout(() => sok(q), 250);
    });

    input.addEventListener('keydown', (e) => {
        const rader = resultEl.querySelectorAll('.rutepris-autocomplete-rad');
        if (e.key === 'Escape') {
            lukkListe();
        } else if (e.key === 'ArrowDown' && rader.length) {
            e.preventDefault();
            aktiv = Math.min(aktiv + 1, rader.length - 1);
            marker();
        } else if (e.key === 'ArrowUp' && rader.length) {
            e.preventDefault();
            aktiv = Math.max(aktiv - 1, 0);
            marker();
        } else if (e.key === 'Enter' && aktiv >= 0) {
            e.preventDefault();
            velg(aktiv);
        }
    });

    document.addEventListener('click', (e) => {
        if (!resultEl.contains(e.target) && e.target !== input) lukkListe();
    });
}

function rutepunktFraInput(input, pos) {
    const tekst = input.value.trim();
    if (!tekst) return '';
    if (pos && (!pos.navn || tekst === pos.navn)) return `pos:${pos.lat},${pos.lon}`;
    return tekst;
}

function escapeHtml(tekst) {
    return String(tekst || '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[c]));
}
