import { opprettStasjon } from './api.js';

let miniMap = null;
let pin = null;
let onOpprettet = null;

const backdrop = document.getElementById('add-station-backdrop');
const sheet = document.getElementById('add-station-sheet');
const navnInput = document.getElementById('add-station-navn');
const kjedeSelect = document.getElementById('add-station-kjede');
const statusEl = document.getElementById('add-station-status');
const opprettBtn = document.getElementById('add-station-opprett');

export function initAddStation(callback) {
    onOpprettet = callback;

    document.getElementById('add-station-avbryt').addEventListener('click', lukkAddStation);
    backdrop.addEventListener('click', lukkAddStation);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sheet.classList.contains('open')) lukkAddStation();
    });
    opprettBtn.addEventListener('click', doOpprett);
}

export function openAddStation(senter) {
    if (!senter) return;

    navnInput.value = '';
    kjedeSelect.value = '';
    statusEl.textContent = '';
    statusEl.className = 'add-station-status';
    opprettBtn.disabled = false;

    backdrop.classList.add('open');
    sheet.classList.add('open');

    setTimeout(() => {
        if (!miniMap) {
            miniMap = L.map('add-station-map', {
                zoomControl: false,
                attributionControl: false,
            }).setView([senter.lat, senter.lon], 16);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
            }).addTo(miniMap);
            const pinIkon = L.icon({
                iconUrl: '/css/images/marker-icon-2x-red.png',
                shadowUrl: '/css/images/marker-shadow.png',
                iconSize: [25, 41], iconAnchor: [12, 41],
                popupAnchor: [1, -34], shadowSize: [41, 41],
            });
            pin = L.marker([senter.lat, senter.lon], { draggable: true, icon: pinIkon }).addTo(miniMap);
        } else {
            miniMap.setView([senter.lat, senter.lon], 16);
            pin.setLatLng([senter.lat, senter.lon]);
        }
        miniMap.invalidateSize();
    }, 50);

    navnInput.focus();
}

function lukkAddStation() {
    backdrop.classList.remove('open');
    sheet.classList.remove('open');
}

async function doOpprett() {
    const navn = navnInput.value.trim();
    if (!navn) {
        visStatus('Navn er påkrevd', true);
        return;
    }
    if (navn.length > 100) {
        visStatus('Navn kan maks ha 100 tegn', true);
        return;
    }

    const pos = pin.getLatLng();
    const kjede = kjedeSelect.value;

    opprettBtn.disabled = true;
    statusEl.textContent = '';

    try {
        const result = await opprettStasjon(navn, kjede, pos.lat, pos.lng);
        lukkAddStation();
        if (onOpprettet) onOpprettet(result.stasjon);
    } catch (e) {
        visStatus(e.message, true);
        opprettBtn.disabled = false;
    }
}

function visStatus(tekst, feil) {
    statusEl.textContent = tekst;
    statusEl.className = 'add-station-status' + (feil ? ' feil' : '');
}
