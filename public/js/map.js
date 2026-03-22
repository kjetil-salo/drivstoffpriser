import { getInnstillinger } from './settings.js';

let map = null;
let userMarker = null;
const stasjonMarkorer = new Map(); // id → marker
const stasjonData = new Map();     // id → stasjon

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
            if (sisteHentPos && kmMellom(lat, lon, sisteHentPos.lat, sisteHentPos.lon) < 3) return;
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
    if (userMarker) userMarker.remove();
    userMarker = L.circleMarker([pos.lat, pos.lon], {
        color: '#3b82f6', fillColor: '#3b82f6',
        fillOpacity: 0.85, radius: 8, weight: 3,
        pane: 'userPane',
    }).addTo(map);
    map.setView([pos.lat, pos.lon], 13);
}

export function visStasjoner(stasjoner, onKlikk) {
    if (!map) return;
    stasjonMarkorer.forEach(m => m.remove());
    stasjonMarkorer.clear();
    stasjonData.clear();

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
            inn.bensin   ? s.bensin   : null,
            inn.bensin98 ? s.bensin98 : null,
            inn.diesel   ? s.diesel   : null,
        ].filter(v => v != null);
        if (!priser.length) continue;
        const min = Math.min(...priser);
        if (min < minPris) { minPris = min; minId = s.id; }
    }
    return minId;
}

export function refreshKartInnstillinger() {
    const billigsteId = finnBilligsteId([...stasjonData.values()]);
    stasjonData.forEach((s) => {
        const marker = stasjonMarkorer.get(s.id);
        if (!marker) return;
        const erBilligst = s.id === billigsteId;
        oppdaterMarkerTooltip(marker, s, erBilligst);
        marker.setIcon(prisIkon(s));
    });
}

export function oppdaterStasjonPriser(stasjon, onKlikk) {
    stasjonData.set(stasjon.id, stasjon);
    const billigsteId = finnBilligsteId([...stasjonData.values()]);
    stasjonData.forEach((s) => {
        const m = stasjonMarkorer.get(s.id);
        if (!m) return;
        const erBilligst = s.id === billigsteId;
        oppdaterMarkerTooltip(m, s, erBilligst);
        m.setIcon(prisIkon(s));
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

function prisIkon(s) {
    if (!harRelevantPris(s)) return fargeIkon('grey');
    const alder = prisAlderTimer(s.pris_tidspunkt);
    if (alder === null || alder >= 24) return fargeIkon('red');
    if (alder >= 8) return fargeIkon('orange');
    return fargeIkon('green');
}

function prisAlderTimer(tidspunkt) {
    if (!tidspunkt) return null;
    const ts = new Date(tidspunkt.replace(' ', 'T'));
    return (Date.now() - ts.getTime()) / 3600000;
}

function oppdaterMarkerTooltip(marker, s, erBilligst) {
    marker.setTooltipContent(byggTooltip(s, erBilligst));
    const el = marker.getTooltip()?.getElement();
    if (el) {
        el.classList.toggle('billigst-tooltip', erBilligst);
    }
}

function lagMarker(s, erBilligst = false) {
    const marker = L.marker([s.lat, s.lon], {
        icon: prisIkon(s),
        zIndexOffset: erBilligst ? 5000 : 0,
    }).addTo(map);

    marker.bindTooltip(byggTooltip(s, erBilligst), {
        permanent: true,
        direction: 'top',
        className: erBilligst ? 'station-tooltip billigst-tooltip' : 'station-tooltip',
        offset: [0, -38],
    });
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
