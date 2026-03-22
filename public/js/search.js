let debounceTimer = null;
let onStedsvalg = null;

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
        if (e.key === 'Escape') lukkSearch();
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
    if (!resultater.length) {
        searchResults.innerHTML = '<div class="search-tom">Ingen treff</div>';
        return;
    }
    searchResults.innerHTML = resultater.map((r, i) =>
        `<div class="search-rad" data-i="${i}">${r.navn}</div>`
    ).join('');

    searchResults.querySelectorAll('.search-rad').forEach((el, i) => {
        el.addEventListener('click', () => {
            onStedsvalg(resultater[i]);
            lukkSearch();
        });
    });
}

function lukkSearch() {
    searchBox.setAttribute('hidden', '');
    toggleBtn.classList.remove('aktiv');
    searchInput.value = '';
    searchResults.innerHTML = '';
}
