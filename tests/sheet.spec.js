const { test, expect } = require('@playwright/test');

const MOCK_STASJONER = [
    {
        id: 1, navn: 'Circle K Testveien', kjede: 'Circle K',
        lat: 59.9139, lon: 10.7522,
        bensin: 21.35, diesel: 20.50,
        pris_tidspunkt: '2026-03-19 20:00:00',
        avstand_m: 350,
    },
    {
        id: 2, navn: 'Uno-X Sentrum', kjede: 'Uno-X',
        lat: 59.915, lon: 10.754,
        bensin: null, diesel: null,
        pris_tidspunkt: null,
        avstand_m: 900,
    },
];

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        const pos = {
            coords: { latitude: 59.9139, longitude: 10.7522, accuracy: 15 },
            timestamp: Date.now(),
        };
        const mock = {
            getCurrentPosition: (ok) => setTimeout(() => ok(pos), 30),
            watchPosition: (ok) => { setTimeout(() => ok(pos), 60); return 1; },
            clearWatch: () => {},
        };
        // navigator.geolocation er en getter på prototype – må bruke defineProperty
        try {
            Object.defineProperty(navigator, 'geolocation', { value: mock, configurable: true });
        } catch {
            navigator.__proto__.geolocation = mock;
        }
    });

    await page.route('/api/stasjoner*', route =>
        route.fulfill({ json: { stasjoner: MOCK_STASJONER } })
    );
    await page.route('/api/pris', route =>
        route.fulfill({ json: { ok: true } })
    );

    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('#loc-status')).toContainText('stasjoner', { timeout: 6000 });
});

test('stasjon-sheet åpnes ved klikk på markør', async ({ page }) => {
    // Klikk på første markør
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/, { timeout: 3000 });
    await expect(page.locator('#sheet-navn')).toHaveText('Circle K Testveien');
    await expect(page.locator('#sheet-bensin')).toContainText('21,35');
    await expect(page.locator('#sheet-diesel')).toContainText('20,50');
});

test('endre pris-knapp bytter til redigeringsmodus', async ({ page }) => {
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/);

    // Klikk Endre pris
    await page.locator('#sheet-endre-btn').click();

    await expect(page.locator('#sheet-edit')).not.toHaveAttribute('hidden');
    await expect(page.locator('#sheet-view')).toHaveAttribute('hidden', '');
});

test('lagre ny pris oppdaterer visning', async ({ page }) => {
    await page.locator('.leaflet-marker-icon').first().click();
    await page.locator('#sheet-endre-btn').click();

    await page.locator('#sheet-bensin-input').fill('22.50');
    await page.locator('#sheet-diesel-input').fill('21.00');
    await page.locator('#sheet-edit-lagre').click();

    // Skal gå tilbake til visning med nye priser
    await expect(page.locator('#sheet-view')).not.toHaveAttribute('hidden', { timeout: 3000 });
    await expect(page.locator('#sheet-bensin')).toContainText('22,50');
    await expect(page.locator('#sheet-diesel')).toContainText('21,00');
});

test('backdrop lukker sheet', async ({ page }) => {
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/);
    await page.locator('#sheet-backdrop').click();
    await expect(page.locator('#stasjon-sheet')).not.toHaveClass(/open/);
});

// TODO: test stasjon uten priser – trenger spredte koordinater for å unngå Leaflet-markør-kollisjon
