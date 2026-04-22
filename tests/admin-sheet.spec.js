/**
 * E2E-tester for admin-panel i stasjonskort (station-sheet.js)
 * Dekker: admin-knapp synlighet, kjede-endring, navn-endring, drivstofftyper
 */
const { test, expect } = require('@playwright/test');

const naa = new Date().toISOString().replace('T', ' ').slice(0, 19);

const MOCK_STASJON = {
    id: 1, navn: 'Circle K Testveien', kjede: 'Circle K',
    lat: 59.9139, lon: 10.7522,
    bensin: 21.35, bensin98: null, diesel: 20.50, diesel_avgiftsfri: null,
    bensin_tidspunkt: naa, bensin98_tidspunkt: null,
    diesel_tidspunkt: naa, diesel_avgiftsfri_tidspunkt: null,
    avstand_m: 350,
    har_bensin: true, har_bensin98: false, har_diesel: true, har_diesel_avgiftsfri: false,
};

async function setupOgÅpneSheet(page, { erAdmin = false } = {}) {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        localStorage.setItem('siste_pos', JSON.stringify({ lat: 59.9100, lon: 10.7480 }));
        const pos = {
            coords: { latitude: 59.9100, longitude: 10.7480, accuracy: 15 },
            timestamp: Date.now(),
        };
        const mock = {
            getCurrentPosition: (ok) => setTimeout(() => ok(pos), 30),
            watchPosition: (ok) => { setTimeout(() => ok(pos), 60); return 1; },
            clearWatch: () => {},
        };
        try {
            Object.defineProperty(navigator, 'geolocation', { value: mock, configurable: true });
        } catch {
            navigator.__proto__.geolocation = mock;
        }
    });
    await page.route('/api/stasjoner*', route =>
        route.fulfill({ json: { stasjoner: [MOCK_STASJON] } })
    );
    await page.route('/api/meg', route =>
        route.fulfill({ json: { innlogget: true, brukernavn: 'testbruker', er_admin: erAdmin } })
    );
    await page.route('/api/pris', route =>
        route.fulfill({ json: { ok: true } })
    );
    // Forhindre ekte nyhet-splash
    await page.route('/api/nyhet', route =>
        route.fulfill({ json: {} })
    );
    // Standard-ruter for admin-API — overstyres av individuelle tester ved behov (LIFO)
    await page.route('/admin/sett-kjede', route =>
        route.fulfill({ json: { ok: true } })
    );
    await page.route('/admin/endre-navn', route =>
        route.fulfill({ json: { ok: true } })
    );
    await page.route('/admin/sett-drivstofftyper', route =>
        route.fulfill({ json: { ok: true } })
    );

    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 10000 });
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/, { timeout: 3000 });
}

test('admin-knapp er skjult for vanlig bruker', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: false });
    await expect(page.locator('#sheet-admin-btn')).toHaveAttribute('hidden');
});

test('admin-knapp vises for admin', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await expect(page.locator('#sheet-admin-btn')).not.toHaveAttribute('hidden');
});

test('klikk på admin-knapp viser admin-panel', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await expect(page.locator('#sheet-admin-panel')).toHaveAttribute('hidden');
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-admin-panel')).not.toHaveAttribute('hidden');
    await expect(page.locator('#sheet-admin-btn')).toHaveAttribute('aria-expanded', 'true');
});

test('andre klikk på admin-knapp skjuler panel igjen', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-admin-panel')).not.toHaveAttribute('hidden');
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-admin-panel')).toHaveAttribute('hidden');
    await expect(page.locator('#sheet-admin-btn')).toHaveAttribute('aria-expanded', 'false');
});

test('admin-panel forhåndsfyller kjede fra stasjon', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-kjede-select')).toHaveValue('Circle K');
});

test('admin-panel forhåndsfyller navn fra stasjon', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-navn-input')).toHaveValue('Circle K Testveien');
});

test('lagre kjede sender API-kall og viser bekreftelse', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });

    // Registreres ETTER setup → vinner (Playwright LIFO-matching)
    let fangetKjede = null;
    await page.route('/admin/sett-kjede', async route => {
        const body = await route.request().postDataJSON();
        fangetKjede = body.kjede;
        await route.fulfill({ json: { ok: true } });
    });

    await page.click('#sheet-admin-btn');
    await page.selectOption('#sheet-kjede-select', 'Esso');
    await page.click('#sheet-kjede-lagre-btn');

    await expect(page.locator('#sheet-kjede-status')).toBeVisible({ timeout: 3000 });
    expect(fangetKjede).toBe('Esso');
});

test('lagre navn sender API-kall og viser bekreftelse', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });

    let fangetNavn = null;
    await page.route('/admin/endre-navn', async route => {
        const body = await route.request().postDataJSON();
        fangetNavn = body.navn;
        await route.fulfill({ json: { ok: true } });
    });

    await page.click('#sheet-admin-btn');
    await page.fill('#sheet-navn-input', 'Nytt Stasjonsnavn');
    await page.click('#sheet-navn-lagre-btn');

    await expect(page.locator('#sheet-navn-status')).toBeVisible({ timeout: 3000 });
    expect(fangetNavn).toBe('Nytt Stasjonsnavn');
});

test('drivstofftype-checkboxer reflekterer stasjonens konfigurasjon', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-har-bensin')).toBeChecked();
    await expect(page.locator('#sheet-har-bensin98')).not.toBeChecked();
    await expect(page.locator('#sheet-har-diesel')).toBeChecked();
    await expect(page.locator('#sheet-har-diesel-avgiftsfri')).not.toBeChecked();
});

test('lagre drivstofftyper sender API-kall', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });

    let fangetPayload = null;
    await page.route('/admin/sett-drivstofftyper', async route => {
        fangetPayload = await route.request().postDataJSON();
        await route.fulfill({ json: { ok: true } });
    });

    await page.click('#sheet-admin-btn');
    await page.click('#sheet-har-bensin98'); // Skru på 98 oktan
    await page.click('#sheet-drivstoff-lagre-btn');

    await expect(page.locator('#sheet-drivstoff-status')).toBeVisible({ timeout: 3000 });
    expect(fangetPayload.har_bensin98).toBe(true);
});

test('admin-panel lukkes når sheet lukkes og åpnes skjult neste gang', async ({ page }) => {
    await setupOgÅpneSheet(page, { erAdmin: true });
    await page.click('#sheet-admin-btn');
    await expect(page.locator('#sheet-admin-panel')).not.toHaveAttribute('hidden');

    // Lukk sheet via backdrop
    await page.locator('#sheet-backdrop').click({ position: { x: 100, y: 40 } });
    await expect(page.locator('#stasjon-sheet')).not.toHaveClass(/open/);

    // Åpne igjen — admin-panel skal være skjult
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/);
    await expect(page.locator('#sheet-admin-panel')).toHaveAttribute('hidden');
});
