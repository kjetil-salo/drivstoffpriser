import { getInnstillinger } from './settings.js';
import { getKjedeLogo, getKjedeInitials, getKjedeFarge } from './kjede.js';

let map = null;
let userMarker = null;
const stasjonMarkorer = new Map(); // id → marker
const stasjonData = new Map();     // id → stasjon
let stasjonOnKlikk = null;
let sisteKartvisning = null;
let ruteLag = null;
let ruteAktiv = false;
const MAKS_BILLIGST_ALDER_TIMER = 24 * 7;

export function initMap(containerId, startPos) {
    const senter = startPos ? [startPos.lat, startPos.lon] : [59.91, 10.75];
    const norgeBounds = L.latLngBounds([57.0, 4.0], [71.5, 31.5]);
    map = L.map(containerId, {
        zoomControl: true,
        tap: false,
        maxBounds: norgeBounds,
        maxBoundsViscosity: 1.0,
        minZoom: 5,
    }).setView(senter, 13);
    map.getContainer().setAttribute('aria-label', 'Kart med bensinstasjoner. Bruk listefanen for tastaturnavigasjon.');
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
    }).addTo(map);
    map.zoomControl.setPosition('bottomright');
    map.createPane('userPane').style.zIndex = 650;
}

export function sentrerKart(lat, lon, zoom = 13) {
    if (map) map.setView([lat, lon], zoom);
}

export function panTilPosisjon(lat, lon) {
    if (map) map.panTo([lat, lon]);
}

export function getKartSenter() {
    if (!map) return null;
    const c = map.getCenter();
    return { lat: c.lat, lon: c.lng };
}

export function visRutePris(data, onStasjonKlikk) {
    if (!map) return;
    fjernRutePris();
    ruteAktiv = true;
    stasjonMarkorer.forEach(m => m.remove());

    const gruppe = L.layerGroup().addTo(map);
    const bounds = [];
    const punkter = data?.rute?.punkter || [];
    if (punkter.length) {
        L.polyline(punkter, {
            color: '#38bdf8',
            weight: 5,
            opacity: 0.85,
            lineCap: 'round',
            lineJoin: 'round',
        }).addTo(gruppe);
        bounds.push(...punkter);
    }

    (data?.treff || []).forEach((s, i) => {
        const erToppTre = i < 3;
        const marker = L.circleMarker([s.lat, s.lon], {
            radius: erToppTre ? 10 : 7,
            color: erToppTre ? '#052e16' : '#451a03',
            fillColor: erToppTre ? '#22c55e' : '#f59e0b',
            fillOpacity: 0.95,
            weight: 2,
        }).addTo(gruppe);
        marker.bindTooltip(`${i + 1}. ${s.pris.toFixed(2)}`, {
            permanent: erToppTre,
            direction: 'top',
            offset: [0, -10],
            className: 'rutepris-tooltip',
        });
        marker.on('click', () => onStasjonKlikk(s));
        bounds.push([s.lat, s.lon]);
    });

    ruteLag = gruppe;
    if (bounds.length) {
        map.fitBounds(bounds, { padding: [34, 34], maxZoom: 13 });
    }
}

export function fjernRutePris() {
    ruteAktiv = false;
    if (ruteLag) {
        ruteLag.remove();
        ruteLag = null;
    }
    if (stasjonOnKlikk) {
        visStasjoner([...stasjonData.values()], stasjonOnKlikk);
    }
}

export function initKartBevegelse(onBevegelse) {
    if (!map) return;
    let sisteHentPos = null;
    let timer = null;

    map.on('moveend', () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
            const senter = map.getCenter();
            const lat = senter.lat;
            const lon = senter.lng;
            if (sisteHentPos && kmMellom(lat, lon, sisteHentPos.lat, sisteHentPos.lon) < 10) return;
            sisteHentPos = { lat, lon };
            onBevegelse(lat, lon);
        }, 600);
    });
}

function kmMellom(lat1, lon1, lat2, lon2) {
    const dlat = (lat2 - lat1) * 111;
    const dlon = (lon2 - lon1) * 111 * Math.cos(lat1 * Math.PI / 180);
    return Math.sqrt(dlat * dlat + dlon * dlon);
}

export function visUserPosisjon(pos) {
    if (!map) return;
    oppdaterUserMarker(pos);
    map.setView([pos.lat, pos.lon], 13);
}

export function oppdaterUserMarker(pos) {
    if (!map) return;
    if (userMarker) userMarker.remove();
    userMarker = L.circleMarker([pos.lat, pos.lon], {
        color: '#3b82f6', fillColor: '#3b82f6',
        fillOpacity: 0.85, radius: 8, weight: 3,
        pane: 'userPane',
    }).addTo(map);
}

export function registrerBrukerDrag(onDrag) {
    if (map) map.on('dragstart', onDrag);
}

export function visStasjoner(stasjoner, onKlikk) {
    if (!map) return;
    stasjonMarkorer.forEach(m => m.remove());
    stasjonMarkorer.clear();
    stasjonData.clear();

    stasjonOnKlikk = onKlikk;
    sisteKartvisning = getInnstillinger().kartvisning ?? 'kompakt';
    if (ruteAktiv) {
        stasjoner.forEach(s => stasjonData.set(s.id, s));
        return;
    }
    const billigsteId = finnBilligsteId(stasjoner);
    stasjoner.forEach(s => {
        stasjonData.set(s.id, s);
        const marker = lagMarker(s, s.id === billigsteId);
        const klikk = () => onKlikk(stasjonData.get(s.id));
        marker.on('click', klikk);
        const tooltipEl = marker.getTooltip()?.getElement();
        if (tooltipEl) tooltipEl.addEventListener('click', klikk);
        stasjonMarkorer.set(s.id, marker);
    });
}

function finnBilligsteId(stasjoner) {
    const inn = getInnstillinger();
    let minPris = Infinity, minId = null;
    for (const s of stasjoner) {
        const priser = [
            inn.bensin              ? aktuellPris(s, 'bensin')              : null,
            inn.bensin98            ? aktuellPris(s, 'bensin98')            : null,
            inn.diesel              ? aktuellPris(s, 'diesel')              : null,
            inn.diesel_avgiftsfri   ? aktuellPris(s, 'diesel_avgiftsfri')   : null,
        ].filter(v => v != null);
        if (!priser.length) continue;
        const min = Math.min(...priser);
        if (min < minPris) { minPris = min; minId = s.id; }
    }
    return minId;
}

function aktuellPris(s, type) {
    if (!s || s[type] == null) return null;
    const ts = s[`${type}_tidspunkt`];
    if (!ts) return null;
    const alderTimer = prisAlderTimer(ts);
    return alderTimer !== null && alderTimer <= MAKS_BILLIGST_ALDER_TIMER ? s[type] : null;
}

export function refreshKartInnstillinger() {
    const inn = getInnstillinger();
    const nyKartvisning = inn.kartvisning ?? 'kompakt';

    // Kartvisning endret – full re-render
    if (nyKartvisning !== sisteKartvisning && stasjonOnKlikk) {
        sisteKartvisning = nyKartvisning;
        visStasjoner([...stasjonData.values()], stasjonOnKlikk);
        return;
    }

    const billigsteId = finnBilligsteId([...stasjonData.values()]);
    stasjonData.forEach((s) => {
        const marker = stasjonMarkorer.get(s.id);
        if (!marker) return;
        const erBilligst = s.id === billigsteId;
        if (nyKartvisning === 'kompakt') {
            marker.setIcon(kompaktIkon(s, erBilligst));
        } else {
            oppdaterMarkerTooltip(marker, s, erBilligst);
            marker.setIcon(prisIkon(s));
        }
        marker.setZIndexOffset(erBilligst ? 5000 : 0);
    });
}

export function oppdaterStasjonPriser(stasjon, onKlikk) {
    stasjonData.set(stasjon.id, stasjon);
    const inn = getInnstillinger();
    const kompakt = (inn.kartvisning ?? 'kompakt') === 'kompakt';
    const billigsteId = finnBilligsteId([...stasjonData.values()]);
    stasjonData.forEach((s) => {
        const m = stasjonMarkorer.get(s.id);
        if (!m) return;
        const erBilligst = s.id === billigsteId;
        if (kompakt) {
            m.setIcon(kompaktIkon(s, erBilligst));
        } else {
            oppdaterMarkerTooltip(m, s, erBilligst);
            m.setIcon(prisIkon(s));
        }
        m.setZIndexOffset(erBilligst ? 5000 : 0);
    });
    const marker = stasjonMarkorer.get(stasjon.id);
    if (!marker) return;
    // Re-bind click med oppdatert data
    marker.off('click');
    marker.on('click', () => onKlikk(stasjon));
}

function harRelevantPris(s) {
    const inn = getInnstillinger();
    return (inn.bensin && s.bensin != null) ||
           (inn.bensin98 && s.bensin98 != null) ||
           (inn.diesel && s.diesel != null);
}

function prisFarge(s) {
    if (!harRelevantPris(s)) return 'grey';
    const tidspunkt = [s.bensin_tidspunkt, s.diesel_tidspunkt, s.bensin98_tidspunkt]
        .filter(Boolean)
        .reduce((a, b) => a > b ? a : b, null);
    const alder = prisAlderTimer(tidspunkt);
    if (alder === null || alder >= 168) return 'grey';  // > 7 dager
    if (alder >= 48) return 'violet';                    // 2–7 dager
    if (alder >= 8) return 'orange';                     // 8–48 timer
    return 'green';                                      // < 8 timer
}

function prisIkon(s) {
    return fargeIkon(prisFarge(s));
}

function prisAlderTimer(tidspunkt) {
    if (!tidspunkt) return null;
    const ts = new Date(tidspunkt.replace(' ', 'T') + 'Z');
    return (Date.now() - ts.getTime()) / 3600000;
}

function oppdaterMarkerTooltip(marker, s, erBilligst) {
    marker.setTooltipContent(byggTooltip(s, erBilligst));
    const el = marker.getTooltip()?.getElement();
    if (el) {
        el.classList.toggle('billigst-tooltip', erBilligst);
        const farge = prisFarge(s);
        ['green', 'orange', 'violet', 'grey'].forEach(f =>
            el.classList.toggle(`tooltip-${f}`, !erBilligst && farge === f));
        el.classList.toggle('tooltip-gammel', farge === 'grey' && harRelevantPris(s));
    }
}

function lagMarker(s, erBilligst = false) {
    const inn = getInnstillinger();
    const kompakt = (inn.kartvisning ?? 'kompakt') === 'kompakt';

    const marker = L.marker([s.lat, s.lon], {
        icon: kompakt ? kompaktIkon(s, erBilligst) : prisIkon(s),
        zIndexOffset: erBilligst ? 5000 : 0,
        title: s.navn,
        alt: s.navn,
    }).addTo(map);

    if (!kompakt) {
        marker.bindTooltip(byggTooltip(s, erBilligst), {
            permanent: true,
            direction: 'top',
            className: erBilligst ? 'station-tooltip billigst-tooltip' : `station-tooltip tooltip-${prisFarge(s)}${prisFarge(s) === 'grey' && harRelevantPris(s) ? ' tooltip-gammel' : ''}`,
            offset: [0, -38],
        });
    }
    return marker;
}

function fargeIkon(farge, stor = false) {
    const size = stor ? [31, 51] : [25, 41];
    const anchor = stor ? [15, 51] : [12, 41];
    return L.icon({
        iconUrl: `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${farge}.png`,
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
        iconSize: size, iconAnchor: anchor,
        popupAnchor: [1, -34], shadowSize: [41, 41],
    });
}

function getKompaktPris(s) {
    const inn = getInnstillinger();
    if (inn.bensin && s.bensin != null) return s.bensin;
    if (inn.bensin98 && s.bensin98 != null) return s.bensin98;
    if (inn.diesel && s.diesel != null) return s.diesel;
    return null;
}

function kompaktIkon(s, erBilligst) {
    const farge = prisFarge(s);
    const borderFarge = farge === 'green'  ? '#22c55e'
        : farge === 'orange' ? '#f97316'
        : farge === 'violet' ? '#a78bfa'
        : '#9ca3af';

    const kjedeEllerNavn = s.kjede || s.navn;
    const logoUrl = getKjedeLogo(kjedeEllerNavn);
    const initials = getKjedeInitials(kjedeEllerNavn);
    const kjedeFarge = getKjedeFarge(kjedeEllerNavn);

    const pris = getKompaktPris(s);
    const prisStr = pris != null ? pris.toFixed(2).replace('.', ',') : null;

    const tidspunkt = [s.bensin_tidspunkt, s.diesel_tidspunkt, s.bensin98_tidspunkt]
        .filter(Boolean)
        .reduce((a, b) => a > b ? a : b, null);
    const alder = prisAlderTimer(tidspunkt);
    let alderHtml = '';
    if (alder !== null && alder >= 8) {
        let alderTekst, alderKlass;
        if (alder >= 168) { alderTekst = '>7d'; alderKlass = 'grey'; }
        else if (alder >= 48) { alderTekst = Math.round(alder / 24) + 'd'; alderKlass = 'violet'; }
        else { alderTekst = Math.round(alder) + 't'; alderKlass = 'orange'; }
        alderHtml = `<span class="km-alder km-alder--${alderKlass}">${alderTekst}</span>`;
    }

    let innerHtml = `<span class="km-initials">${initials}</span>`;
    if (logoUrl) {
        innerHtml += `<img src="${logoUrl}" class="km-img" onerror="this.style.display='none'">`;
    }

    const circleStyle = `background:${kjedeFarge}`;
    const billigstKlass = erBilligst ? ' km-billigst' : '';

    return L.divIcon({
        className: '',
        html: `<div class="km-root${billigstKlass}">` +
            `<div class="km-circle" style="border-color:${borderFarge};${circleStyle}">${innerHtml}</div>` +
            (prisStr ? `<div class="km-pris">${prisStr}${alderHtml}</div>` : '') +
            `</div>`,
        iconSize: erBilligst ? [54, 72] : [44, 60],
        iconAnchor: erBilligst ? [27, 46] : [22, 38],
        popupAnchor: erBilligst ? [0, -46] : [0, -38],
    });
}

function billigstIkon() {
    return L.divIcon({
        className: '',
        html: `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="50" viewBox="0 0 34 50">
            <path d="M17 0 C7.6 0 0 7.6 0 17 C0 29.75 17 50 17 50 C17 50 34 29.75 34 17 C34 7.6 26.4 0 17 0 Z"
                  fill="#f59e0b" stroke="#b45309" stroke-width="2"/>
            <text x="17" y="23" text-anchor="middle" font-size="16" fill="white" font-weight="bold">★</text>
        </svg>`,
        iconSize: [34, 50],
        iconAnchor: [17, 50],
        popupAnchor: [0, -50],
    });
}

function byggTooltip(s, erBilligst = false) {
    const inn = getInnstillinger();
    const fmt = v => v != null ? v.toFixed(2).replace('.', ',') : null;
    const rader = [
        inn.bensin   && { label: '95', v: fmt(s.bensin) },
        inn.bensin98 && { label: '98', v: fmt(s.bensin98) },
        inn.diesel   && { label: 'D',  v: fmt(s.diesel) },
    ].filter(Boolean);
    const harPris = rader.some(r => r.v != null);
    if (erBilligst) {
        return `<span class="tt-billigst-label">BILLIGST</span>` +
            `<span class="tt-navn">${s.navn}</span>` +
            (harPris
                ? `<span class="tt-priser">${rader.filter(r => r.v).map(r => `${r.label}: ${r.v}`).join(' &nbsp; ')}</span>`
                : `<span class="tt-ingen">Ingen pris</span>`);
    }
    return `<span class="tt-navn">${s.navn}</span>` +
        (harPris
            ? `<span class="tt-priser">${rader.filter(r => r.v).map(r => `${r.label}: ${r.v}`).join(' &nbsp; ')}</span>`
            : `<span class="tt-ingen">Ingen pris</span>`);
}
