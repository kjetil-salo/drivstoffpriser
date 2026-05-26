import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../public/js/settings.js', () => ({
    getInnstillinger: vi.fn(),
    getEffektivPris: vi.fn((pris) => pris),
    harRabattKort: vi.fn(() => false),
    getRabattVisning: vi.fn(() => null),
    triggerInstallPrompt: vi.fn(),
    erInstallbar: vi.fn(() => false),
    applyServerPreferences: vi.fn(),
    initInnstillinger: vi.fn(),
    initRabattkortModal: vi.fn(),
    getRabattØre: vi.fn(() => 0),
}));
vi.mock('../public/js/kjede.js', () => ({
    getKjedeFarge: vi.fn(() => '#666'),
    getKjedeInitials: vi.fn(() => 'K'),
    getKjedeLogo: vi.fn(() => null),
}));
vi.mock('../public/js/favoritter.js', () => ({
    erFavoritt: vi.fn(() => false),
    toggleFavoritt: vi.fn(),
    hentFavoritter: vi.fn(() => []),
}));
vi.mock('../public/js/utils.js', () => ({
    fraDbTidspunkt: vi.fn((ts) => new Date(ts.replace(' ', 'T') + 'Z')),
    prisAlderKlasse: vi.fn(() => 'alder-fersk'),
    prisAlderTekst: vi.fn(() => ''),
    prisAlderTekstKort: vi.fn(() => ''),
}));

import { finnBilligste, finnBilligsteId, sorter } from '../public/js/list.js';
import { getInnstillinger } from '../public/js/settings.js';

const fersk = new Date(Date.now() - 30 * 60000).toISOString().replace('T', ' ').slice(0, 19);

function lagStasjon(overrides) {
    return {
        id: 1, navn: 'Test', kjede: 'Test',
        bensin: null, diesel: null, bensin98: null, diesel_avgiftsfri: null,
        bensin_tidspunkt: null, diesel_tidspunkt: null,
        bensin98_tidspunkt: null, diesel_avgiftsfri_tidspunkt: null,
        avstand_m: 500,
        ...overrides,
    };
}

function stdInn(overrides = {}) {
    return { bensin: true, diesel: true, bensin98: false, diesel_avgiftsfri: false, ...overrides };
}

beforeEach(() => {
    getInnstillinger.mockReturnValue(stdInn());
});

// ─── finnBilligsteId ─────────────────────────────────────────────────────────

describe('finnBilligsteId', () => {
    it('returnerer billigste bensin-stasjon ved avstand-sort', () => {
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 17.48, bensin_tidspunkt: fersk }),
            lagStasjon({ id: 2, bensin: 18.50, bensin_tidspunkt: fersk }),
            lagStasjon({ id: 3, bensin: 18.19, bensin_tidspunkt: fersk }),
        ];
        const ids = finnBilligsteId(stasjoner, stdInn(), 'avstand');
        expect(ids.has(1)).toBe(true);
        expect(ids.size).toBe(1);
    });

    it('avgiftsfri diesel skal IKKE overstyre bensin-banneret ved avstand-sort', () => {
        // Regresjonstest for feilen Håkon fant i Rakkestad
        const inn = stdInn({ diesel_avgiftsfri: true });
        getInnstillinger.mockReturnValue(inn);
        const stasjoner = [
            lagStasjon({ id: 1, navn: 'Automat 1', bensin: 17.48, bensin_tidspunkt: fersk }),
            lagStasjon({ id: 2, navn: 'Best', bensin: 18.50, bensin_tidspunkt: fersk,
                         diesel_avgiftsfri: 15.80, diesel_avgiftsfri_tidspunkt: fersk }),
        ];
        const ids = finnBilligsteId(stasjoner, inn, 'avstand');
        expect(ids.has(1)).toBe(true);  // Automat 1 — billigst bensin
        expect(ids.has(2)).toBe(false); // Best — billig avgiftsfri, men det er ikke primærtype
    });

    it('bruker avgiftsfri diesel som grunnlag når sort er diesel_avgiftsfri', () => {
        const inn = stdInn({ diesel_avgiftsfri: true });
        getInnstillinger.mockReturnValue(inn);
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 17.48, bensin_tidspunkt: fersk }),
            lagStasjon({ id: 2, diesel_avgiftsfri: 15.80, diesel_avgiftsfri_tidspunkt: fersk }),
        ];
        const ids = finnBilligsteId(stasjoner, inn, 'diesel_avgiftsfri');
        expect(ids.has(2)).toBe(true);
        expect(ids.size).toBe(1);
    });

    it('returnerer tom mengde hvis ingen har den aktive pristypen', () => {
        const inn = stdInn({ bensin: false, diesel: false, bensin98: true });
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 17.48, bensin_tidspunkt: fersk }), // kun bensin
        ];
        const ids = finnBilligsteId(stasjoner, inn, 'avstand');
        expect(ids.size).toBe(0);
    });

    it('returnerer begge ved prislikhet', () => {
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 17.69, bensin_tidspunkt: fersk }),
            lagStasjon({ id: 2, bensin: 17.69, bensin_tidspunkt: fersk }),
            lagStasjon({ id: 3, bensin: 18.50, bensin_tidspunkt: fersk }),
        ];
        const ids = finnBilligsteId(stasjoner, stdInn(), 'bensin');
        expect(ids.has(1)).toBe(true);
        expect(ids.has(2)).toBe(true);
        expect(ids.has(3)).toBe(false);
        expect(ids.size).toBe(2);
    });
});

// ─── finnBilligste ───────────────────────────────────────────────────────────

describe('finnBilligste', () => {
    it('markerer billigst per drivstofftype uavhengig av hverandre', () => {
        const inn = stdInn();
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 17.48, bensin_tidspunkt: fersk, diesel: 19.00, diesel_tidspunkt: fersk }),
            lagStasjon({ id: 2, bensin: 18.50, bensin_tidspunkt: fersk, diesel: 18.50, diesel_tidspunkt: fersk }),
        ];
        const b = finnBilligste(stasjoner, inn);
        expect(b.bensin.has(1)).toBe(true);  // billigst bensin
        expect(b.diesel.has(2)).toBe(true);  // billigst diesel
    });

    it('ignorerer pristyper som ikke er aktivert', () => {
        const inn = stdInn({ diesel: false });
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 17.48, bensin_tidspunkt: fersk, diesel: 18.50, diesel_tidspunkt: fersk }),
        ];
        const b = finnBilligste(stasjoner, inn);
        expect(b.bensin).toBeDefined();
        expect(b.diesel).toBeUndefined();
    });
});

// ─── sorter ──────────────────────────────────────────────────────────────────

describe('sorter', () => {
    it('billigste stasjon kommer øverst ved prissortering', () => {
        const stasjoner = [
            lagStasjon({ id: 1, bensin: 18.50, bensin_tidspunkt: fersk, avstand_m: 200 }),
            lagStasjon({ id: 2, bensin: 17.48, bensin_tidspunkt: fersk, avstand_m: 800 }),
        ];
        const billigsteIds = new Set([2]);
        const sortert = sorter(stasjoner, 'bensin', billigsteIds);
        expect(sortert[0].id).toBe(2);
    });

    it('nærmeste øverst ved avstand-sortering', () => {
        const stasjoner = [
            lagStasjon({ id: 1, avstand_m: 800 }),
            lagStasjon({ id: 2, avstand_m: 200 }),
            lagStasjon({ id: 3, avstand_m: 1500 }),
        ];
        const sortert = sorter(stasjoner, 'avstand', new Set());
        expect(sortert.map(s => s.id)).toEqual([2, 1, 3]);
    });
});
