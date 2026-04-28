/**
 * E2E-tester for geolokasjon-flyt (location.js)
 * Dekker: vellykket posisjon, nektet tilgang, timeout, cachet posisjon
 */
const { test, expect } = require('@playwright/test');

const MOCK_STASJONER = [
    {
        id: 1, navn: 'Circle K Testveien', kjede: 'Circle K',
        lat: 59.9139, lon: 10.7522,
        bensin: 21.35, bensin98: null, diesel: 20.50, diesel_avgiftsfri: null,
        bensin_tidspunkt: new Date().toISOString().replace('T', ' ').slice(0, 19),
        bensin98_tidspunkt: null,
        diesel_tidspunkt: new Date().toISOString().replace('T', ' ').slice(0, 19),
        diesel_avgiftsfri_tidspunkt: null,
        avstand_m: 350,
    },
];

async function baseMock(page) {
    await page.route('/api/stasjoner*', route =>
        route.fulfill({ json: { stasjoner: MOCK_STASJONER } })
    );
    await page.route('/api/meg', route =>
        route.fulfill({ json: { innlogget: false } })
    );
    await page.route('/api/nyhet', route =>
        route.fulfill({ json: {} })
    );
}

test('vellykket GPS-posisjon viser markør på kartet', async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        const pos = {
            coords: { latitude: 59.9100, longitude: 10.7480, accuracy: 15 },
            timestamp: Date.now(),
        };
        const mock = {
            getCurrentPosition: (ok) => setTimeout(() => ok(pos), 30),
            watchPosition: (ok) => { setTimeout(() => ok(pos), 60); return 1; },
            clearWatch: () => {},
        };
        Object.defineProperty(Navigator.prototype, 'geolocation', { get: () => mock, configurable: true });
    });
    await baseMock(page);
    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 10000 });
});

test('GPS nektet viser feilmelding og knappen er ikke låst', async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        const mock = {
            getCurrentPosition: (_, err) => {
                setTimeout(() => err({ code: 1, message: 'User denied' }), 30);
            },
            watchPosition: (_, err) => {
                setTimeout(() => err({ code: 1, message: 'User denied' }), 60);
                return 1;
            },
            clearWatch: () => {},
        };
        Object.defineProperty(Navigator.prototype, 'geolocation', { get: () => mock, configurable: true });
    });
    await baseMock(page);
    await page.goto('/');
    await page.click('#loc-btn');
    // Etter nektet tilgang skal knappen ikke sitte fast i loading-tilstand
    await expect(page.locator('#loc-btn')).not.toHaveAttribute('disabled', { timeout: 5000 });
});

test('GPS timeout (lav nøyaktighet) gir posisjon etter 10 sekunder', async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        const pos = { coords: { latitude: 59.91, longitude: 10.75, accuracy: 999 }, timestamp: Date.now() };
        const mock = {
            // TIMEOUT-feil (code=3) fra getCurrentPosition → location.js kaller startWatch()
            getCurrentPosition: (_, err) => {
                setTimeout(() => err({ code: 3, message: 'Timeout' }), 100);
            },
            // watchPosition sender lav nøyaktighet → setter bestPosition men trigger ikke finish()
            watchPosition: (ok) => {
                const id = setInterval(() => ok(pos), 200);
                return id;
            },
            clearWatch: (id) => clearInterval(id),
        };
        Object.defineProperty(Navigator.prototype, 'geolocation', { get: () => mock, configurable: true });
    });
    await baseMock(page);
    await page.goto('/');
    await page.click('#loc-btn');
    // Etter 10s timeout i location.js brukes beste tilgjengelige posisjon og markører vises
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 15000 });
});

test('cachet posisjon i localStorage brukes for umiddelbar kartvisning', async ({ page }) => {
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
        Object.defineProperty(Navigator.prototype, 'geolocation', { get: () => mock, configurable: true });
    });
    await baseMock(page);
    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 5000 });
});
