const { test, expect } = require('@playwright/test');

const MOCK_STASJONER = [
    {
        id: 1, navn: 'Circle K Testveien', kjede: 'Circle K',
        lat: 59.9139, lon: 10.7522,
        bensin: 21.35, bensin98: null, diesel: 20.50,
        bensin_tidspunkt: '2026-03-19 20:00:00',
        bensin98_tidspunkt: null,
        diesel_tidspunkt: '2026-03-19 20:00:00',
        avstand_m: 350,
    },
    {
        id: 2, navn: 'Uno-X Sentrum', kjede: 'Uno-X',
        lat: 59.915, lon: 10.754,
        bensin: null, bensin98: null, diesel: null,
        bensin_tidspunkt: null, bensin98_tidspunkt: null, diesel_tidspunkt: null,
        avstand_m: 900,
    },
];

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        localStorage.setItem('siste_pos', JSON.stringify({ lat: 59.9139, lon: 10.7522 }));
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
    await page.route('/api/meg', route =>
        route.fulfill({ json: { innlogget: true, brukernavn: 'testbruker', er_admin: false } })
    );

    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 10000 });
});

test('stasjon-sheet åpnes ved klikk på markør', async ({ page }) => {
    // Klikk på første markør
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/, { timeout: 3000 });
    await expect(page.locator('#sheet-navn')).toHaveText('Circle K Testveien');
    await expect(page.locator('#sheet-priser')).toContainText('21,35');
    await expect(page.locator('#sheet-priser')).toContainText('20,50');
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
    await expect(page.locator('#sheet-priser')).toContainText('22,50');
    await expect(page.locator('#sheet-priser')).toContainText('21,00');
});

test('backdrop lukker sheet', async ({ page }) => {
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/);
    // Klikk øverst i viewport (over sheet-bunnen) for å unngå at sheet dekker sentrum av backdrop
    await page.locator('#sheet-backdrop').click({ position: { x: 100, y: 40 } });
    await expect(page.locator('#stasjon-sheet')).not.toHaveClass(/open/);
});

// TODO: test stasjon uten priser – trenger spredte koordinater for å unngå Leaflet-markør-kollisjon

test('aktiv fane huskes ved refresh', async ({ page }) => {
    // Bytt til liste-fanen
    await page.click('#tab-liste');
    await expect(page.locator('#view-liste')).toBeVisible();

    // Refresh – tab-tilstand leses fra localStorage synkront ved sideinnlasting
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    // Liste-fanen skal fortsatt være aktiv
    await expect(page.locator('#view-liste')).toBeVisible();
    await expect(page.locator('#view-kart')).toBeHidden();
    await expect(page.locator('#tab-liste')).toHaveAttribute('aria-selected', 'true');
});

test('statistikk-fane huskes ved refresh', async ({ page }) => {
    await page.route('/api/statistikk*', route => route.fulfill({ json: {} }));

    await page.click('#tab-statistikk');
    await expect(page.locator('#view-statistikk')).toBeVisible();

    // Refresh – tab-tilstand leses fra localStorage synkront ved sideinnlasting
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#view-statistikk')).toBeVisible();
    await expect(page.locator('#view-kart')).toBeHidden();
    await expect(page.locator('#tab-statistikk')).toHaveAttribute('aria-selected', 'true');
});
