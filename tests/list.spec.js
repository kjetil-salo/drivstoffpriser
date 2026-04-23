/**
 * E2E-tester for listevisning (list.js)
 * Dekker: sortering, "vis eldre"-filter, favoritter, tom liste
 */
const { test, expect } = require('@playwright/test');

const naa = new Date().toISOString().replace('T', ' ').slice(0, 19);
const gammelt = '2020-01-01 00:00:00';

const MOCK_STASJONER = [
    {
        id: 1, navn: 'Circle K Testveien', kjede: 'Circle K',
        lat: 59.9139, lon: 10.7522,
        bensin: 21.35, bensin98: null, diesel: 20.50, diesel_avgiftsfri: null,
        bensin_tidspunkt: naa, bensin98_tidspunkt: null,
        diesel_tidspunkt: naa, diesel_avgiftsfri_tidspunkt: null,
        avstand_m: 350,
    },
    {
        id: 2, navn: 'Uno-X Sentrum', kjede: 'Uno-X',
        lat: 59.915, lon: 10.754,
        bensin: 20.90, bensin98: null, diesel: 19.80, diesel_avgiftsfri: null,
        bensin_tidspunkt: naa, bensin98_tidspunkt: null,
        diesel_tidspunkt: naa, diesel_avgiftsfri_tidspunkt: null,
        avstand_m: 900,
    },
    {
        id: 3, navn: 'Shell Gamleveien', kjede: 'Shell',
        lat: 59.920, lon: 10.760,
        bensin: 22.10, bensin98: null, diesel: 21.20, diesel_avgiftsfri: null,
        bensin_tidspunkt: gammelt, bensin98_tidspunkt: null,
        diesel_tidspunkt: gammelt, diesel_avgiftsfri_tidspunkt: null,
        avstand_m: 1500,
    },
];

async function gåTilListe(page) {
    await page.addInitScript(() => {
        localStorage.setItem('velkommen_vist', '1');
        localStorage.setItem('liste_vis_gamle', '0');
        // siste_pos forhindrer at #velkomst-overlay vises (lagretPos !== null)
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
        route.fulfill({ json: { stasjoner: MOCK_STASJONER } })
    );
    await page.route('/api/meg', route =>
        route.fulfill({ json: { innlogget: false } })
    );
    // Forhindre ekte nyhet-splash fra å blokkere interaksjon
    await page.route('/api/nyhet', route =>
        route.fulfill({ json: {} })
    );
    await page.goto('/');
    await page.click('#loc-btn');
    await expect(page.locator('.leaflet-marker-icon').first()).toBeVisible({ timeout: 10000 });
    await page.click('#tab-liste');
    await expect(page.locator('#view-liste')).toBeVisible();
}

test('liste viser stasjoner med fersk pris', async ({ page }) => {
    await gåTilListe(page);
    // Circle K og Uno-X har fersk pris, Shell har gammel → 2 stasjoner
    await expect(page.locator('.stasjon-kort')).toHaveCount(2);
    await expect(page.locator('.stasjon-kort').first()).toContainText('Circle K Testveien');
});

test('vis eldre enn 24t viser alle stasjoner', async ({ page }) => {
    await gåTilListe(page);
    await expect(page.locator('.stasjon-kort')).toHaveCount(2);
    await page.check('#vis-gamle-check');
    // Alle 3 inkl. Shell Gamleveien med gammel pris
    await expect(page.locator('.stasjon-kort')).toHaveCount(3);
    await expect(page.locator('.stasjon-kort').filter({ hasText: 'Shell Gamleveien' })).toHaveCount(1);
});

test('vis eldre huskes i localStorage', async ({ page }) => {
    await gåTilListe(page);
    await page.check('#vis-gamle-check');
    await expect(page.locator('.stasjon-kort')).toHaveCount(3);

    // Bekreft at verdien er skrevet til localStorage
    const lagret = await page.evaluate(() => localStorage.getItem('liste_vis_gamle'));
    expect(lagret).toBe('1');

    // Toggle tilbake — verdien skal oppdateres
    await page.uncheck('#vis-gamle-check');
    const lagret2 = await page.evaluate(() => localStorage.getItem('liste_vis_gamle'));
    expect(lagret2).toBe('0');
});

test('sortering etter avstand — nærmeste øverst', async ({ page }) => {
    await gåTilListe(page);
    const kort = page.locator('.stasjon-kort');
    await expect(kort.nth(0)).toContainText('Circle K Testveien'); // 350 m
    await expect(kort.nth(1)).toContainText('Uno-X Sentrum');       // 900 m
});

test('sortering etter bensinpris — billigste øverst', async ({ page }) => {
    await gåTilListe(page);
    await page.click('button.sort-btn[data-sort="bensin"]');
    const kort = page.locator('.stasjon-kort');
    // Uno-X 20,90 < Circle K 21,35
    await expect(kort.nth(0)).toContainText('Uno-X Sentrum');
    await expect(kort.nth(1)).toContainText('Circle K Testveien');
});

test('sortering etter diesel — billigste øverst', async ({ page }) => {
    await gåTilListe(page);
    await page.click('button.sort-btn[data-sort="diesel"]');
    const kort = page.locator('.stasjon-kort');
    // Uno-X 19,80 < Circle K 20,50
    await expect(kort.nth(0)).toContainText('Uno-X Sentrum');
    await expect(kort.nth(1)).toContainText('Circle K Testveien');
});

test('favoritt-filter viser kun favoritter', async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem('favoritter', JSON.stringify([1])); // Circle K
    });
    await gåTilListe(page);
    await page.click('#vis-favoritter-btn');
    await expect(page.locator('.stasjon-kort')).toHaveCount(1);
    await expect(page.locator('.stasjon-kort').first()).toContainText('Circle K Testveien');
});

test('favoritt-filter tom viser melding', async ({ page }) => {
    await gåTilListe(page);
    // Ingen favoritter satt
    await page.click('#vis-favoritter-btn');
    await expect(page.locator('.favoritter-tom')).toBeVisible();
    await expect(page.locator('.stasjon-kort')).toHaveCount(0);
});

test('klikk på stasjonskort åpner sheet', async ({ page }) => {
    await gåTilListe(page);
    await page.locator('.stasjon-kort').first().click();
    await expect(page.locator('#stasjon-sheet')).toHaveClass(/open/, { timeout: 3000 });
    await expect(page.locator('#sheet-navn')).toContainText('Circle K Testveien');
});

test('informasjonsrad viser antall stasjoner', async ({ page }) => {
    await gåTilListe(page);
    await expect(page.locator('#sort-label')).toContainText('2 stasjoner');
});
