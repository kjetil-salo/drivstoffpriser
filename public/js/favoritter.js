const FAVORITTER_KEY = 'favoritter';

export function hentFavoritter() {
    try {
        const raw = localStorage.getItem(FAVORITTER_KEY);
        return new Set(raw ? JSON.parse(raw) : []);
    } catch { return new Set(); }
}

export function erFavoritt(id) {
    return hentFavoritter().has(id);
}

export function toggleFavoritt(id) {
    const favs = hentFavoritter();
    if (favs.has(id)) {
        favs.delete(id);
    } else {
        favs.add(id);
    }
    try {
        localStorage.setItem(FAVORITTER_KEY, JSON.stringify([...favs]));
    } catch {}
    document.dispatchEvent(new CustomEvent('favoritt-endret', { detail: { id } }));
}
