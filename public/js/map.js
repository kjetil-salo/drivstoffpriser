let map = null;
let userMarker = null;
const stasjonMarkorer = new Map(); // id → marker
const stasjonData = new Map();     // id → stasjon

export function initMap(containerId, startPos) {
    const senter = startPos ? [startPos.lat, startPos.lon] : [59.91, 10.75];
    map = L.map(containerId, { zoomControl: true, tap: false }).setView(senter, 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
    }).addTo(map);
    map.zoomControl.setPosition('bottomright');
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
    }).addTo(map);
    map.setView([pos.lat, pos.lon], 13);
}

export function visStasjoner(stasjoner, onKlikk) {
    if (!map) return;
    stasjonMarkorer.forEach(m => m.remove());
    stasjonMarkorer.clear();
    stasjonData.clear();

    stasjoner.forEach(s => {
        stasjonData.set(s.id, s);
        const marker = lagMarker(s);
        const klikk = () => onKlikk(stasjonData.get(s.id));
        marker.on('click', klikk);
        const tooltipEl = marker.getTooltip()?.getElement();
        if (tooltipEl) tooltipEl.addEventListener('click', klikk);
        stasjonMarkorer.set(s.id, marker);
    });
}

export function oppdaterStasjonPriser(stasjon, onKlikk) {
    stasjonData.set(stasjon.id, stasjon);
    const marker = stasjonMarkorer.get(stasjon.id);
    if (!marker) return;
    marker.setTooltipContent(byggTooltip(stasjon));
    marker.setIcon(prisIkon(stasjon));
    // Re-bind click med oppdatert data
    marker.off('click');
    marker.on('click', () => onKlikk(stasjon));
}

function prisIkon(s) {
    if (s.bensin == null && s.diesel == null) return fargeIkon('grey');
    if (prisErGammel(s.pris_tidspunkt)) return fargeIkon('red');
    return fargeIkon('green');
}

function prisErGammel(tidspunkt) {
    if (!tidspunkt) return true;
    const ts = new Date(tidspunkt.replace(' ', 'T'));
    return (Date.now() - ts.getTime()) > 24 * 60 * 60 * 1000;
}

function lagMarker(s) {
    const marker = L.marker([s.lat, s.lon], {
        icon: prisIkon(s),
    }).addTo(map);

    marker.bindTooltip(byggTooltip(s), {
        permanent: true,
        direction: 'top',
        className: 'station-tooltip',
        offset: [0, -38],
    });
    return marker;
}

function fargeIkon(farge) {
    return L.icon({
        iconUrl: `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${farge}.png`,
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41],
        popupAnchor: [1, -34], shadowSize: [41, 41],
    });
}

function byggTooltip(s) {
    const b = s.bensin != null ? s.bensin.toFixed(2).replace('.', ',') : null;
    const d = s.diesel != null ? s.diesel.toFixed(2).replace('.', ',') : null;
    return `<span class="tt-navn">${s.navn}</span>` +
        (b || d
            ? `<span class="tt-priser">95: ${b ?? '–'} &nbsp; D: ${d ?? '–'}</span>`
            : `<span class="tt-ingen">Ingen pris</span>`);
}
