export const KJEDE_NAVN = ['Circle K', 'Uno-X', 'YX', 'Esso', 'Shell', 'Preem', 'St1', 'Best', 'Oljeleverandøren', 'Tanken', 'Driv', 'Haltbakk Express', 'Bunker Oil', 'Knapphus', 'Trønder Oil'];

const KJEDE_DOMENER = [
    { match: ['circle k', 'circlek'],          logo: 'circlek',              farge: '#f97316' },
    { match: ['uno-x', 'unox', 'uno x'],       logo: 'uno-x',                farge: '#16a34a' },
    { match: ['yx'],                            logo: 'yx',                   farge: '#dc2626' },
    { match: ['esso'],                          logo: 'esso',                 farge: '#2563eb' },
    { match: ['shell'],                         logo: 'shell',                farge: '#ca8a04' },
    { match: ['preem'],                         logo: 'preem',                farge: '#059669' },
    { match: ['st1', 'st 1'],                   logo: 'st1',                  farge: '#7c3aed' },
    { match: ['best'],                          logo: 'best',                 farge: '#0284c7' },
    { match: ['oljeleverandøren', 'oljeleverandoren'], logo: 'oljeleverandoren', farge: '#0d9488' },
    { match: ['tanken'],                        logo: 'tanken',               farge: '#e11d48' },
    { match: ['driv'],                          logo: 'driv.svg',             farge: '#cf1130' },
    { match: ['haltbakk'],                      logo: 'haltbakk.webp',        farge: '#b91c1c' },
    { match: ['bunker oil', 'bunkeroil'],       logo: 'bunker-oil.svg',       farge: '#1e40af' },
    { match: ['knapphus'],                      logo: 'knapphus',             farge: '#f59e0b' },
    { match: ['trønder oil', 'tronder oil'],    logo: 'tronder-oil',          farge: '#1d4ed8' },
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
    const fil = treff.logo.includes('.') ? treff.logo : `${treff.logo}.png`;
    return `/img/kjeder/${fil}`;
}
