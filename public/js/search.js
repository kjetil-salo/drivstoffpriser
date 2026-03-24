let debounceTimer = null;
let onStedsvalg = null;
let aktivResultatIdx = -1;

const toggleBtn = document.getElementById('search-toggle');
const searchBox = document.getElementById('search-box');
const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');

export function initSearch(onValg) {
    onStedsvalg = onValg;

    toggleBtn.addEventListener('click', () => {
        const lukket = searchBox.hasAttribute('hidden');
        if (lukket) {
            searchBox.removeAttribute('hidden');
            toggleBtn.classList.add('aktiv');
            toggleBtn.setAttribute('aria-expanded', 'true');
            searchInput.focus();
        } else {
            lukkSearch();
        }
    });

    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const q = searchInput.value.trim();
        if (q.length < 2) { searchResults.innerHTML = ''; return; }
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
        if (!searchBox.contains(e.target) && e.target !== toggleBtn) {
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
        searchResults.innerHTML = '';
    }
}

function visResultater(resultater) {
    aktivResultatIdx = -1;
    if (!resultater.length) {
        searchResults.innerHTML = '<div class="search-tom">Ingen treff</div>';
        return;
    }
    searchResults.innerHTML = resultater.map((r, i) =>
        `<div class="search-rad" role="option" id="search-opt-${i}" data-i="${i}">${r.navn}</div>`
    ).join('');

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

function lukkSearch() {
    searchBox.setAttribute('hidden', '');
    toggleBtn.classList.remove('aktiv');
    toggleBtn.setAttribute('aria-expanded', 'false');
    searchInput.value = '';
    searchResults.innerHTML = '';
}
