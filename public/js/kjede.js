export const KJEDE_NAVN = ['Best', 'Bunker Oil', 'Circle K', 'Din-X', 'Driv', 'Esso', 'Haltbakk Express', 'Haslestad Energi', 'Knapphus', 'MH24', 'Oljeleverandøren', 'Preem', 'Shell', 'St1', 'Tanken', 'Trønder Oil', 'Uno-X', 'YX'];

const KJEDE_DOMENER = [
    { match: ['circle k', 'circlek'],          logo: 'circlek',              farge: '#f97316' },
    { match: ['din-x', 'dinx', 'din x'],       logo: 'din-x',                farge: '#d45d00' },
    { match: ['uno-x', 'unox', 'uno x'],       logo: 'uno-x',                farge: '#16a34a' },
    { match: ['yx'],                            logo: 'yx',                   farge: '#dc2626' },
    { match: ['esso'],                          logo: 'esso',                 farge: '#2563eb' },
    { match: ['shell'],                         logo: 'shell',                farge: '#ca8a04' },
    { match: ['preem'],                         logo: 'preem',                farge: '#059669' },
    { match: ['st1', 'st 1'],                   logo: 'st1',                  farge: '#f5c400' },
    { match: ['best'],                          logo: 'best',                 farge: '#0284c7' },
    { match: ['oljeleverandøren', 'oljeleverandoren'], logo: 'oljeleverandoren', farge: '#c87010' },
    { match: ['tanken'],                        logo: 'tanken',               farge: '#e11d48' },
    { match: ['driv'],                          logo: 'driv.svg',             farge: '#cf1130' },
    { match: ['haltbakk'],                      logo: 'haltbakk.webp',        farge: '#b91c1c' },
    { match: ['bunker oil', 'bunkeroil'],       logo: 'bunker-oil.svg',       farge: '#1e40af' },
    { match: ['knapphus'],                      logo: 'knapphus',             farge: '#f59e0b' },
    { match: ['trønder oil', 'tronder oil'],    logo: 'tronder-oil',          farge: '#1d4ed8' },
    { match: ['haslestad energi', 'haslestad'], logo: 'haslestadenergi',       farge: '#e47b02' },
    { match: ['mh24', 'mh service', 'mhservice'], logo: 'mh24',              farge: '#1a5276' },
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
