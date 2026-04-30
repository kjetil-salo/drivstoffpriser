/**
 * E2E-tester for nyhet/splash-funksjonalitet
 * Dekker: visning av nyhet, lukking, cookie-persistering, ingen nyhet
 */
const { test, expect } = require('@playwright/test');

const MOCK_STASJONER = [
    {
        id: 1, navn: 'Shell Testveien', kjede: 'Shell',
        lat: 59.9139, lon: 10.7522,
        bensin: 21.0, diesel: 20.0,
        bensin_tidspunkt: new Date().toISOString().replace('T', ' ').slice(0, 19),
        diesel_tidspunkt: new Date().toISOString().replace('T', ' ').slice(0, 19),
        avstand_m: 500,
    },
];

function geoMock() {
    const pos = { coords: { latitude: 59.91, longitude: 10.75, accuracy: 15 }, timestamp: Date.now() };
    return {
        getCurrentPosition: (ok) => setTimeout(() => ok(pos), 30),
        watchPosition: (ok) => { setTimeout(() => ok(pos), 60); return 1; },
        clearWatch: () => {},
    };
}

async function oppsett(page, nyhetData = {}) {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        localStorage.setItem('siste_pos', JSON.stringify({ lat: 59.91, lon: 10.75 }));
        const pos = { coords: { latitude: 59.91, longitude: 10.75, accuracy: 15 }, timestamp: Date.now() };
        const mock = {
            getCurrentPosition: (ok) => setTimeout(() => ok(pos), 30),
            watchPosition: (ok) => { setTimeout(() => ok(pos), 60); return 1; },
            clearWatch: () => {},
        };
        Object.defineProperty(Navigator.prototype, 'geolocation', { get: () => mock, configurable: true });
    });

    await page.route('/api/stasjoner*', route =>
        route.fulfill({ json: { stasjoner: MOCK_STASJONER } })
    );
    await page.route('/api/meg', route =>
        route.fulfill({ json: { innlogget: false } })
    );
    await page.route('/api/nyhet', route =>
        route.fulfill({ json: nyhetData })
    );
}

test('ingen nyhet - dialog forblir skjult', async ({ page }) => {
    await oppsett(page, {});
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    // main.js bruker await fetch('/api/nyhet') – gi litt tid til at JS kjører
    await page.waitForTimeout(800);

    await expect(page.locator('#nyhet-dialog')).toHaveAttribute('hidden');
});

test('aktiv nyhet viser dialog med tekst', async ({ page }) => {
    const nyhetData = {
        tekst: 'Velkommen til drivstoffprisene.no!',
        id: 'test-abc123',
        tittel: 'Nyhet',
        utloper: '2099-12-31T23:59:59',
    };

    await oppsett(page, nyhetData);
    await page.goto('/');

    // Venter på at dialog mister hidden-attributt
    await expect(page.locator('#nyhet-dialog')).not.toHaveAttribute('hidden', { timeout: 4000 });
    await expect(page.locator('#nyhet-tekst')).toContainText('Velkommen til drivstoffprisene.no!');
});

test('aktiv nyhet viser tittel', async ({ page }) => {
    const nyhetData = {
        tekst: 'Testtekst her.',
        id: 'test-tittel',
        tittel: 'Viktig melding',
        utloper: '2099-12-31T23:59:59',
    };

    await oppsett(page, nyhetData);
    await page.goto('/');

    await expect(page.locator('#nyhet-dialog')).not.toHaveAttribute('hidden', { timeout: 4000 });
    await expect(page.locator('#nyhet-tittel')).toContainText('Viktig melding');
});

test('lukk-knapp skjuler dialog', async ({ page }) => {
    const nyhetData = {
        tekst: 'En viktig melding.',
        id: 'test-lukk',
        tittel: 'Nyhet',
        utloper: '2099-12-31T23:59:59',
    };

    await oppsett(page, nyhetData);
    await page.goto('/');
    await expect(page.locator('#nyhet-dialog')).not.toHaveAttribute('hidden', { timeout: 4000 });

    await page.locator('#nyhet-lukk').click();
    await expect(page.locator('#nyhet-dialog')).toHaveAttribute('hidden', { timeout: 2000 });
});

test('lukking setter cookie slik at nyhet ikke vises igjen', async ({ page }) => {
    const nyhetId = 'test-persist-456';
    const nyhetData = {
        tekst: 'Lagres som cookie.',
        id: nyhetId,
        tittel: 'Nyhet',
        utloper: '2099-12-31T23:59:59',
    };

    await oppsett(page, nyhetData);
    await page.goto('/');
    await expect(page.locator('#nyhet-dialog')).not.toHaveAttribute('hidden', { timeout: 4000 });

    await page.locator('#nyhet-lukk').click();
    await expect(page.locator('#nyhet-dialog')).toHaveAttribute('hidden', { timeout: 2000 });

    // Verifiser at cookie er satt
    const cookies = await page.context().cookies();
    const nyhetCookie = cookies.find(c => c.name === `nyhet_lest_${nyhetId}`);
    expect(nyhetCookie).toBeTruthy();
});

test('allerede sett nyhet viser ikke dialog', async ({ page }) => {
    const nyhetId = 'test-allerede-sett';
    const nyhetData = {
        tekst: 'Denne har jeg sett.',
        id: nyhetId,
        tittel: 'Nyhet',
        utloper: '2099-12-31T23:59:59',
    };

    // Sett cookie FØR navigasjon – simulerer at bruker har lukket nyheten tidligere
    await page.context().addCookies([{
        name: `nyhet_lest_${nyhetId}`,
        value: '1',
        domain: 'localhost',
        path: '/',
    }]);

    await oppsett(page, nyhetData);
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(800);

    // Cookie er satt – dialog skal forbli hidden
    await expect(page.locator('#nyhet-dialog')).toHaveAttribute('hidden');
});

test('ESC lukker nyhet-dialog', async ({ page }) => {
    const nyhetData = {
        tekst: 'Trykk Escape.',
        id: 'test-esc',
        tittel: 'Nyhet',
        utloper: '2099-12-31T23:59:59',
    };

    await oppsett(page, nyhetData);
    await page.goto('/');
    await expect(page.locator('#nyhet-dialog')).not.toHaveAttribute('hidden', { timeout: 4000 });

    await page.keyboard.press('Escape');
    await expect(page.locator('#nyhet-dialog')).toHaveAttribute('hidden', { timeout: 2000 });
});
