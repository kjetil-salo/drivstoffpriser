const KJEDE_DOMENER = [
    { match: ['circle k', 'circlek'],          domene: 'circlek.no',  farge: '#f97316' },
    { match: ['uno-x', 'unox', 'uno x'],       domene: 'uno-x.no',   farge: '#16a34a' },
    { match: ['yx'],                            domene: 'yx.no',      farge: '#dc2626' },
    { match: ['esso'],                          domene: 'esso.no',    farge: '#2563eb' },
    { match: ['shell'],                         domene: 'shell.no',   farge: '#ca8a04' },
    { match: ['preem'],                         domene: 'preem.no',   farge: '#059669' },
    { match: ['st1', 'st 1'],                   domene: 'st1.no',     farge: '#7c3aed' },
    { match: ['best'],                          domene: 'best.no',    farge: '#0284c7' },
];

function _finn(kjede) {
    const k = (kjede || '').toLowerCase();
    return KJEDE_DOMENER.find(e => e.match.some(m => k.includes(m))) || null;
}

export function getKjedeFarge(kjede) {
    return _finn(kjede)?.farge ?? '#475569';
}

export function getKjedeInitials(tekst) {
    if (!tekst) return '⛽';
    const ord = tekst.trim().split(/[\s-]+/);
    if (ord.length === 1) return tekst.substring(0, 2).toUpperCase();
    return ord.map(o => o[0]).join('').substring(0, 3).toUpperCase();
}

export function getKjedeLogo(kjede) {
    const treff = _finn(kjede);
    if (!treff) return null;
    return `https://www.google.com/s2/favicons?domain=${treff.domene}&sz=64`;
}
