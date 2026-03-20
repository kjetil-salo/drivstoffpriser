let aktivSort = 'avstand';
let sisteStasjoner = [];
let sisteOnKlikk = null;

export function visListe(stasjoner, onKlikk) {
    sisteStasjoner = stasjoner;
    sisteOnKlikk = onKlikk;

    const container = document.getElementById('liste');
    const info = document.getElementById('liste-info');

    if (!stasjoner || stasjoner.length === 0) {
        info.textContent = 'Ingen stasjoner funnet i nærheten.';
        container.innerHTML = '';
        return;
    }

    info.innerHTML = `
        <span id="sort-label">${stasjoner.length} stasjoner – sorter:</span>
        <div id="sort-knapper">
            <button class="sort-btn ${aktivSort === 'avstand' ? 'aktiv' : ''}" data-sort="avstand">Avstand</button>
            <button class="sort-btn ${aktivSort === 'bensin' ? 'aktiv' : ''}" data-sort="bensin">95 oktan</button>
            <button class="sort-btn ${aktivSort === 'diesel' ? 'aktiv' : ''}" data-sort="diesel">Diesel</button>
        </div>`;

    info.querySelectorAll('.sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            aktivSort = btn.dataset.sort;
            visListe(sisteStasjoner, sisteOnKlikk);
        });
    });

    const sortert = sorter(stasjoner, aktivSort);
    container.innerHTML = sortert.map(s => kortHtml(s)).join('');

    container.querySelectorAll('.stasjon-kort').forEach(kort => {
        const id = parseInt(kort.dataset.id, 10);
        kort.addEventListener('click', () => {
            const stasjon = stasjoner.find(s => s.id === id);
            if (stasjon) onKlikk(stasjon);
        });
    });
}

export function oppdaterKort(stasjon, onKlikk) {
    const kort = document.querySelector(`.stasjon-kort[data-id="${stasjon.id}"]`);
    if (!kort) return;
    const nytt = document.createElement('div');
    nytt.innerHTML = kortHtml(stasjon);
    const nyttKort = nytt.firstElementChild;
    nyttKort.addEventListener('click', () => onKlikk(stasjon));
    kort.replaceWith(nyttKort);
}

function sorter(stasjoner, felt) {
    return [...stasjoner].sort((a, b) => {
        if (felt === 'avstand') return (a.avstand_m ?? Infinity) - (b.avstand_m ?? Infinity);
        const av = a[felt] ?? Infinity;
        const bv = b[felt] ?? Infinity;
        return av - bv;
    });
}

function formatPris(v) {
    if (v == null) return null;
    return v.toFixed(2).replace('.', ',');
}

function avstandTekst(m) {
    return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
}

function kortHtml(s) {
    const b = formatPris(s.bensin);
    const d = formatPris(s.diesel);
    return `<div class="stasjon-kort" data-id="${s.id}">
        <div class="sk-info">
            <div class="sk-navn">${s.navn}</div>
            ${s.kjede ? `<div class="sk-kjede">${s.kjede}</div>` : ''}
            <div class="sk-priser">
                <div class="sk-pris-rad">
                    <span class="sk-pris-label">95</span>
                    <span class="sk-pris-verdi ${b ? '' : 'ingen'}">${b ? b + ' kr' : '–'}</span>
                </div>
                <div class="sk-pris-rad">
                    <span class="sk-pris-label">Diesel</span>
                    <span class="sk-pris-verdi ${d ? '' : 'ingen'}">${d ? d + ' kr' : '–'}</span>
                </div>
            </div>
        </div>
        <span class="sk-avstand">${avstandTekst(s.avstand_m)}</span>
    </div>`;
}
