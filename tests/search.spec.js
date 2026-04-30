/**
 * E2E-tester for stedssøk (search.js)
 * Dekker: input, debounce, resultater, keyboard-navigasjon, ESC, klikk utenfor
 */
const { test, expect } = require('@playwright/test');

const MOCK_STASJONER = [
    {
        id: 1, navn: 'Circle K Testveien', kjede: 'Circle K',
        lat: 59.9139, lon: 10.7522,
        bensin: 21.35, diesel: 20.50,
        bensin_tidspunkt: new Date().toISOString().replace('T', ' ').slice(0, 19),
        diesel_tidspunkt: new Date().toISOString().replace('T', ' ').slice(0, 19),
        avstand_m: 350,
    },
];

const MOCK_STEDSSOK_RESULTATER = [
    { navn: 'Bergen sentrum', lat: 60.3913, lon: 5.3221, type: 'sted' },
    { navn: 'Bergensdalen', lat: 60.371, lon: 5.315, type: 'sted' },
];

const MOCK_STASJON_TREFF = [
    { id: 1, navn: 'Circle K Testveien (Circle K)', lat: 59.9139, lon: 10.7522, type: 'stasjon' },
];

async function oppsett(page) {
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
        route.fulfill({ json: {} })
    );
    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 10000 });
}

test('søkefelt er synlig', async ({ page }) => {
    await oppsett(page);
    await expect(page.locator('#search-input')).toBeVisible();
});

test('kort søk viser ingen resultater', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: [] })
    );

    await page.fill('#search-input', 'x');
    // Under 2 tegn = ingen API-kall, søkeresultater skal forbli skjult
    await expect(page.locator('#search-results')).toHaveAttribute('hidden', { timeout: 1000 });
});

test('søk med resultater viser liste', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STEDSSOK_RESULTATER })
    );

    await page.fill('#search-input', 'bergen');
    await expect(page.locator('#search-results')).not.toHaveAttribute('hidden', { timeout: 2000 });
    await expect(page.locator('.search-rad')).toHaveCount(2);
    await expect(page.locator('.search-rad').first()).toContainText('Bergen sentrum');
});

test('søk uten treff viser "Ingen treff"', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: [] })
    );

    await page.fill('#search-input', 'xyzingenting');
    await expect(page.locator('#search-results')).not.toHaveAttribute('hidden', { timeout: 2000 });
    await expect(page.locator('.search-tom')).toBeVisible();
    await expect(page.locator('.search-tom')).toContainText('Ingen treff');
});

test('stasjonstreff vises med pump-ikon', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STASJON_TREFF })
    );

    await page.fill('#search-input', 'circle');
    await expect(page.locator('.search-rad').first()).toContainText('⛽', { timeout: 2000 });
});

test('stedstreff vises med pin-ikon', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STEDSSOK_RESULTATER })
    );

    await page.fill('#search-input', 'bergen');
    await expect(page.locator('.search-rad').first()).toContainText('📍', { timeout: 2000 });
});

test('ESC lukker søkeresultater', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STEDSSOK_RESULTATER })
    );

    await page.fill('#search-input', 'bergen');
    await expect(page.locator('.search-rad')).toHaveCount(2, { timeout: 2000 });

    await page.keyboard.press('Escape');
    await expect(page.locator('#search-results')).toHaveAttribute('hidden', { timeout: 1000 });
});

test('klikk utenfor søkeresultater lukker listen', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STEDSSOK_RESULTATER })
    );

    await page.fill('#search-input', 'bergen');
    await expect(page.locator('.search-rad')).toHaveCount(2, { timeout: 2000 });

    // Klikk et nøytralt sted på siden
    await page.locator('#tab-kart').click();
    await expect(page.locator('#search-results')).toHaveAttribute('hidden', { timeout: 1000 });
});

test('pil ned navigerer mellom resultater', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STEDSSOK_RESULTATER })
    );

    await page.fill('#search-input', 'bergen');
    await expect(page.locator('.search-rad')).toHaveCount(2, { timeout: 2000 });

    await page.keyboard.press('ArrowDown');
    await expect(page.locator('.search-rad').first()).toHaveClass(/aktiv/);
});

test('klikk på resultat lukker søkelisten', async ({ page }) => {
    await oppsett(page);

    await page.route('/api/stedssok*', route =>
        route.fulfill({ json: MOCK_STEDSSOK_RESULTATER })
    );

    await page.fill('#search-input', 'bergen');
    await expect(page.locator('.search-rad')).toHaveCount(2, { timeout: 2000 });

    await page.locator('.search-rad').first().click();
    await expect(page.locator('#search-results')).toHaveAttribute('hidden', { timeout: 1000 });
});
