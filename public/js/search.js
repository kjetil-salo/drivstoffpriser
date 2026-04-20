let debounceTimer = null;
let onStedsvalg = null;
let aktivResultatIdx = -1;

const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');

export function initSearch(onValg) {
    onStedsvalg = onValg;

    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const q = searchInput.value.trim();
        if (q.length < 2) { lukkSearch(false); return; }
        debounceTimer = setTimeout(() => sokSted(q), 350);
    });

    searchInput.addEventListener('keydown', e => {
        if (e.key === 'Escape') { lukkSearch(); return; }
        const rader = searchResults.querySelectorAll('.search-rad');
        if (!rader.length) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            aktivResultatIdx = Math.min(aktivResultatIdx + 1, rader.length - 1);
            markerResultat(rader);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            aktivResultatIdx = Math.max(aktivResultatIdx - 1, 0);
            markerResultat(rader);
        } else if (e.key === 'Enter' && aktivResultatIdx >= 0) {
            e.preventDefault();
            rader[aktivResultatIdx].click();
        }
    });

    document.addEventListener('click', e => {
        if (!searchResults.contains(e.target) && e.target !== searchInput) {
            lukkSearch();
        }
    });
}

async function sokSted(q) {
    try {
        const resp = await fetch(`/api/stedssok?q=${encodeURIComponent(q)}`);
        const resultater = await resp.json();
        visResultater(resultater);
    } catch {
        lukkSearch(false);
    }
}

function visResultater(resultater) {
    aktivResultatIdx = -1;
    if (!resultater.length) {
        searchResults.innerHTML = '<div class="search-tom">Ingen treff</div>';
        searchResults.removeAttribute('hidden');
        return;
    }
    searchResults.innerHTML = resultater.map((r, i) => {
        const ikon = r.type === 'stasjon' ? '⛽' : '📍';
        return `<div class="search-rad" role="option" id="search-opt-${i}" data-i="${i}">${ikon} ${r.navn}</div>`;
    }).join('');
    searchResults.removeAttribute('hidden');

    searchResults.querySelectorAll('.search-rad').forEach((el, i) => {
        el.addEventListener('click', () => {
            onStedsvalg(resultater[i]);
            lukkSearch();
        });
    });
}

function markerResultat(rader) {
    rader.forEach((r, i) => {
        r.classList.toggle('aktiv', i === aktivResultatIdx);
        r.setAttribute('aria-selected', i === aktivResultatIdx ? 'true' : 'false');
    });
    if (aktivResultatIdx >= 0) {
        searchInput.setAttribute('aria-activedescendant', `search-opt-${aktivResultatIdx}`);
    } else {
        searchInput.removeAttribute('aria-activedescendant');
    }
}

function lukkSearch(tømInput = true) {
    searchResults.setAttribute('hidden', '');
    searchResults.innerHTML = '';
    aktivResultatIdx = -1;
    if (tømInput) searchInput.value = '';
}
